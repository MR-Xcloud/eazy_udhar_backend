from rest_framework import serializers

from easyudhar.payment_utils import normalize_payment_method, normalize_seller_payment_method, payment_method_label


class PaymentMethodField(serializers.CharField):
    """Validate and normalize seller/manual payment methods."""

    def __init__(self, **kwargs):
        kwargs.setdefault('default', 'upi')
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return normalize_seller_payment_method(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, value):
        return normalize_payment_method(value or 'upi')
