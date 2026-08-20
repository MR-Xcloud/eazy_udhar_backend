import io
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from sellerapp.eod_excel_report import build_transactions_workbook, render_workbook_bytes
from sellerapp.models import LedgerTransaction, Seller, SellerCustomer

from .models import AdminUser


class SellerBackupRestoreViewTests(TestCase):
    def setUp(self):
        self.seller = Seller.objects.create(
            username="seller-1", business_name="Test Shop", email="seller1@example.com", phone="9000000000",
        )
        self.customer = SellerCustomer.objects.create(seller=self.seller, name="Ramesh", phone="9876500000")
        LedgerTransaction.objects.create(
            seller=self.seller, customer=self.customer,
            transaction_type=LedgerTransaction.TYPE_CREDIT, amount=Decimal("100.00"),
        )
        self.customer.outstanding_amount = Decimal("100.00")
        self.customer.save()
        self.content = render_workbook_bytes(build_transactions_workbook(self.seller))

    def _client_as(self, role):
        admin = AdminUser.objects.create_user(
            username=f"admin-{role}", email=f"{role}@example.com", password="x", role=role,
        )
        client = APIClient()
        client.force_authenticate(user=admin)
        return client

    def test_support_admin_can_restore(self):
        client = self._client_as(AdminUser.ROLE_SUPPORT)
        upload = io.BytesIO(self.content)
        upload.name = "backup.xlsx"
        res = client.post(
            f"/admin-api/v1/sellers/{self.seller.pk}/backup-restore",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["transactions_skipped_duplicate"], 1)
        self.assertEqual(res.data["transactions_imported"], 0)

    def test_read_only_admin_is_forbidden(self):
        client = self._client_as(AdminUser.ROLE_READ_ONLY)
        upload = io.BytesIO(self.content)
        upload.name = "backup.xlsx"
        res = client.post(
            f"/admin-api/v1/sellers/{self.seller.pk}/backup-restore",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(res.status_code, 403)

    def test_missing_file_is_rejected(self):
        client = self._client_as(AdminUser.ROLE_SUPPORT)
        res = client.post(f"/admin-api/v1/sellers/{self.seller.pk}/backup-restore", {}, format="multipart")
        self.assertEqual(res.status_code, 400)

    def test_identity_mismatch_returns_409_with_details(self):
        other = Seller.objects.create(
            username="seller-2", business_name="Other Shop", email="other@example.com", phone="9000000001",
        )
        client = self._client_as(AdminUser.ROLE_SUPPORT)
        upload = io.BytesIO(self.content)
        upload.name = "backup.xlsx"
        res = client.post(
            f"/admin-api/v1/sellers/{other.pk}/backup-restore",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "identity_mismatch")
