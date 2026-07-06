"""SMS pack pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP


def _money(value):
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def sms_pack_pricing(pack):
    qty = Decimal(pack.sms_quantity)
    unit_paise = Decimal(pack.unit_price_paise)
    gst_percent = Decimal(pack.gst_percent)

    subtotal = (qty * unit_paise / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    gst_amount = (subtotal * gst_percent / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    total = subtotal + gst_amount

    unit_inr = unit_paise / Decimal('100')
    unit_inr_float = float(unit_inr)
    if unit_paise % 1:
        unit_display = f'₹{unit_inr_float:g}'
    else:
        unit_display = f'₹{_money(unit_inr)}'
    return {
        'sms_quantity': int(pack.sms_quantity),
        'unit_price_paise': float(unit_paise),
        'unit_price_inr': unit_inr_float,
        'unit_price_display': unit_display,
        'gst_percent': float(gst_percent),
        'subtotal_inr': _money(subtotal),
        'gst_amount_inr': _money(gst_amount),
        'total_inr': _money(total),
        'price_note': f'All prices are exclusive of {float(gst_percent):g}% GST',
    }


def sms_pack_to_dict(pack):
    data = {
        'id': pack.id,
        'name': pack.name,
        'slug': pack.slug,
        'is_active': pack.is_active,
        'sort_order': pack.sort_order,
        'created_at': pack.created_at.isoformat(),
        'updated_at': pack.updated_at.isoformat(),
    }
    data.update(sms_pack_pricing(pack))
    return data


def list_active_sms_packs():
    from adminapp.models import SmsPack

    packs = SmsPack.objects.filter(is_active=True).order_by('sort_order', 'sms_quantity')
    return [sms_pack_to_dict(p) for p in packs]


def sms_pack_order_to_dict(order):
    seller = order.seller
    return {
        'id': str(order.id),
        'seller_id': order.seller_id,
        'seller_name': seller.business_name if seller else None,
        'pack_slug': order.pack_slug,
        'pack_name': order.pack_name,
        'sms_quantity': int(order.sms_quantity),
        'amount': float(order.amount),
        'currency': order.currency,
        'reference_id': order.reference_id,
        'razorpay_order_id': order.razorpay_order_id,
        'razorpay_payment_id': order.razorpay_payment_id or None,
        'status': order.status,
        'error_message': order.error_message or None,
        'created_at': order.created_at.isoformat(),
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
    }
