import io
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .eod_excel_report import build_transactions_workbook, render_workbook_bytes
from .excel_report_import_service import RestoreError, restore_seller_backup
from .models import LedgerTransaction, Seller, SellerCustomer


def make_seller(**kwargs):
    defaults = dict(
        username=f"seller-{Seller.objects.count()}",
        business_name="Test Shop",
        email=f"seller{Seller.objects.count()}@example.com",
        phone="9000000000",
    )
    defaults.update(kwargs)
    return Seller.objects.create(**defaults)


def make_customer(seller, **kwargs):
    defaults = dict(name="Ramesh", phone="9876500000")
    defaults.update(kwargs)
    return SellerCustomer.objects.create(seller=seller, **defaults)


def make_tx(seller, customer, tx_type, amount, **kwargs):
    return LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=tx_type,
        amount=Decimal(str(amount)),
        **kwargs,
    )


class RestoreSelfNoopTests(TestCase):
    def test_restoring_a_sellers_own_current_backup_changes_nothing(self):
        seller = make_seller()
        customer = make_customer(seller)
        make_tx(seller, customer, LedgerTransaction.TYPE_CREDIT, "100.00")
        make_tx(seller, customer, LedgerTransaction.TYPE_PAYMENT, "40.00", payment_method="cash")
        customer.outstanding_amount = Decimal("60.00")
        customer.save()

        content = render_workbook_bytes(build_transactions_workbook(seller))
        result = restore_seller_backup(seller, io.BytesIO(content))

        self.assertEqual(result["customers_created"], 0)
        self.assertEqual(result["transactions_imported"], 0)
        self.assertEqual(result["transactions_skipped_duplicate"], 2)
        customer.refresh_from_db()
        self.assertEqual(customer.outstanding_amount, Decimal("60.00"))
        self.assertEqual(LedgerTransaction.objects.filter(seller=seller).count(), 2)


class RestoreFromEmptyTests(TestCase):
    def test_full_data_loss_is_reconstructed_exactly(self):
        seller = make_seller()
        c1 = make_customer(seller, name="Ramesh", phone="9876500001")
        c2 = make_customer(seller, name="Suresh", phone="9876500002")
        make_tx(seller, c1, LedgerTransaction.TYPE_CREDIT, "300.00")
        make_tx(seller, c1, LedgerTransaction.TYPE_PAYMENT, "100.00", payment_method="cash")
        make_tx(seller, c2, LedgerTransaction.TYPE_CREDIT, "50.00")
        c1.outstanding_amount = Decimal("200.00")
        c1.save()
        c2.outstanding_amount = Decimal("50.00")
        c2.save()

        content = render_workbook_bytes(build_transactions_workbook(seller))

        # Simulate the seller losing their device/data entirely.
        LedgerTransaction.objects.filter(seller=seller).delete()
        SellerCustomer.objects.filter(seller=seller).delete()

        result = restore_seller_backup(seller, io.BytesIO(content))

        self.assertEqual(result["customers_created"], 2)
        self.assertEqual(result["transactions_imported"], 3)
        self.assertEqual(result["transactions_skipped_duplicate"], 0)

        restored_c1 = SellerCustomer.objects.get(seller=seller, phone="9876500001")
        restored_c2 = SellerCustomer.objects.get(seller=seller, phone="9876500002")
        self.assertEqual(restored_c1.outstanding_amount, Decimal("200.00"))
        self.assertEqual(restored_c2.outstanding_amount, Decimal("50.00"))


class RestorePreservesOffLedgerAdjustmentTests(TestCase):
    """The key regression test: a customer's live outstanding_amount can include
    adjustments that aren't backed by any LedgerTransaction row (this happens on the
    real dataset — see the module docstring). Merging in a missing historical
    transaction must add its effect on top of that live balance, not discard it by
    recomputing the total from the ledger alone.
    """

    def test_merge_adds_missing_transaction_without_losing_manual_adjustment(self):
        seller = make_seller()
        customer = make_customer(seller)
        make_tx(seller, customer, LedgerTransaction.TYPE_CREDIT, "100.00", note="first purchase")
        customer.outstanding_amount = Decimal("100.00")
        customer.save()

        # Backup taken while both credits existed.
        make_tx(seller, customer, LedgerTransaction.TYPE_CREDIT, "50.00", note="second purchase")
        customer.outstanding_amount = Decimal("150.00")
        customer.save()
        content = render_workbook_bytes(build_transactions_workbook(seller))

        # Now simulate: the second credit's row was lost locally, AND an unrelated
        # manual adjustment of +25 was applied directly to the balance (no tx row).
        LedgerTransaction.objects.filter(seller=seller, note="second purchase").delete()
        customer.outstanding_amount = Decimal("125.00")  # 100 (remaining ledger) + 25 manual adjustment
        customer.save()

        result = restore_seller_backup(seller, io.BytesIO(content))

        self.assertEqual(result["transactions_imported"], 1)
        self.assertEqual(result["transactions_skipped_duplicate"], 1)
        customer.refresh_from_db()
        # 125 (current live balance, adjustment included) + 50 (restored credit) = 175.
        # A full ledger replay would have produced 150, silently dropping the +25.
        self.assertEqual(customer.outstanding_amount, Decimal("175.00"))


class RestoreIdentityCheckTests(TestCase):
    def test_blocks_restoring_another_sellers_backup_by_default(self):
        seller_a = make_seller(business_name="Shop A", email="a@example.com")
        seller_b = make_seller(business_name="Shop B", email="b@example.com")
        make_customer(seller_a)
        content = render_workbook_bytes(build_transactions_workbook(seller_a))

        with self.assertRaises(RestoreError) as ctx:
            restore_seller_backup(seller_b, io.BytesIO(content))
        self.assertEqual(ctx.exception.code, "identity_mismatch")
        self.assertEqual(SellerCustomer.objects.filter(seller=seller_b).count(), 0)

    def test_force_flag_allows_restoring_mismatched_backup(self):
        seller_a = make_seller(business_name="Shop A", email="a2@example.com")
        seller_b = make_seller(business_name="Shop B", email="b2@example.com")
        make_customer(seller_a)
        content = render_workbook_bytes(build_transactions_workbook(seller_a))

        result = restore_seller_backup(seller_b, io.BytesIO(content), force_identity_mismatch=True)
        self.assertFalse(result["identity"]["matched"])
        self.assertEqual(result["customers_created"], 1)


class RestoreBadFormatTests(TestCase):
    def test_rejects_a_file_without_the_expected_sheets(self):
        from openpyxl import Workbook

        seller = make_seller()
        wb = Workbook()
        content = io.BytesIO()
        wb.save(content)
        content.seek(0)

        with self.assertRaises(RestoreError) as ctx:
            restore_seller_backup(seller, content)
        self.assertEqual(ctx.exception.code, "bad_format")


class RestoreSameFileDuplicatesTests(TestCase):
    def test_two_distinct_transactions_sharing_type_amount_and_minute_both_import(self):
        """Two genuinely different transactions can look identical at minute
        granularity (same customer/type/amount/no note). Restoring must not collapse
        them into one just because they resemble each other inside the same file."""
        seller = make_seller()
        customer = make_customer(seller)
        now = timezone.localtime()
        make_tx(
            seller, customer, LedgerTransaction.TYPE_PAYMENT, "500.00",
            payment_method="cash", device_created_at=now,
        )
        make_tx(
            seller, customer, LedgerTransaction.TYPE_PAYMENT, "500.00",
            payment_method="cash", device_created_at=now,
        )
        customer.outstanding_amount = Decimal("0.00")
        customer.save()
        content = render_workbook_bytes(build_transactions_workbook(seller))

        LedgerTransaction.objects.filter(seller=seller).delete()
        SellerCustomer.objects.filter(seller=seller).delete()

        result = restore_seller_backup(seller, io.BytesIO(content))
        self.assertEqual(result["transactions_imported"], 2)
        self.assertEqual(result["transactions_skipped_duplicate"], 0)
        self.assertEqual(LedgerTransaction.objects.filter(seller=seller).count(), 2)
