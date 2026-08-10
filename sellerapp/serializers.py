import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    CustomerFile,
    CustomerNote,
    Seller,
    SellerCustomer,
    SellerNotification,
    SellerSettings,
    TeamMember,
)
from .payment_fields import PaymentMethodField
from .utils import parse_client_uuid, seller_customer_phone_exists, seller_to_dict


class ClientIdField(serializers.Field):
    """Accept UUID or Flutter offline id: local:<uuid>."""

    def to_internal_value(self, data):
        if data is None or data == '':
            return None
        try:
            return parse_client_uuid(data, required=True)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, value):
        return str(value) if value else None


class CustomerRefField(ClientIdField):
    """Server customer id or offline client_id (local:<uuid>)."""


class SellerRegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name')
    mobile = serializers.CharField(source='phone')
    role = serializers.CharField(required=False, default=Seller.ROLE_SELLER)

    upi_id = serializers.CharField(max_length=100, required=False, allow_blank=True)

    class Meta:
        model = Seller
        fields = [
            'name',
            'email',
            'mobile',
            'password',
            'role',
            'business_name',
            'upi_id',
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'business_name': {'required': False},
        }

    def validate_role(self, value):
        if value != Seller.ROLE_SELLER:
            raise serializers.ValidationError('Only seller role is allowed.')
        return value

    def validate(self, attrs):
        if not attrs.get('business_name'):
            attrs['business_name'] = attrs.get('full_name') or 'My Shop'
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data['email']
        user = Seller.objects.create_user(
            username=email,
            password=password,
            **validated_data,
        )
        SellerSettings.objects.get_or_create(seller=user)
        from .subscription_service import start_seller_trial

        start_seller_trial(user)
        return user


class SellerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from django.contrib.auth import authenticate

        seller = authenticate(
            self.context['request'],
            email=attrs['email'],
            password=attrs['password'],
        )
        if seller is None or not isinstance(seller, Seller):
            raise serializers.ValidationError('Invalid credentials.')
        attrs['user'] = seller
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SellerOTPSendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(max_length=15, required=False)
    phone = serializers.CharField(max_length=15, required=False)

    def validate(self, attrs):
        attrs['phone'] = attrs.get('mobile') or attrs.get('phone') or ''
        if not attrs.get('email') and not attrs['phone']:
            raise serializers.ValidationError('email or mobile is required.')
        return attrs

    def save(self):
        from customerapp.models import OTPRecord
        from customerapp.otp_service import resolve_seller_email, send_login_otp

        try:
            otp, delivery = send_login_otp(
                email=self.validated_data.get('email'),
                phone=self.validated_data.get('phone') or None,
                purpose=OTPRecord.PURPOSE_SELLER_LOGIN,
                resolver=resolve_seller_email,
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        self.delivery_result = delivery
        return otp


class SellerOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(max_length=15, required=False)
    phone = serializers.CharField(max_length=15, required=False)
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        attrs['phone'] = attrs.get('mobile') or attrs.get('phone') or ''
        if not attrs.get('email') and not attrs['phone']:
            raise serializers.ValidationError('email or mobile is required.')
        return attrs

    def save(self):
        from customerapp.otp_service import verify_seller_login_otp

        try:
            return verify_seller_login_otp(
                email=self.validated_data.get('email'),
                phone=self.validated_data.get('phone') or None,
                otp_code=self.validated_data['otp'],
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class SellerCustomerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCustomer
        fields = [
            'name',
            'phone',
            'email',
            'address',
            'flat_number',
            'tower',
            'society',
            'city',
            'state',
            'country',
        ]
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'flat_number': {'required': False, 'allow_blank': True},
            'tower': {'required': False, 'allow_blank': True},
            'society': {'required': False, 'allow_blank': True},
            'city': {'required': False, 'allow_blank': True},
            'state': {'required': False, 'allow_blank': True},
            'country': {'required': False, 'allow_blank': True},
        }

    def validate_phone(self, value):
        phone = (value or '').strip()
        if not phone:
            raise serializers.ValidationError('Phone number is required.')
        seller = self.context['seller']
        if seller_customer_phone_exists(seller, phone):
            raise serializers.ValidationError(
                'A customer with this phone number already exists.'
            )
        return phone

    def create(self, validated_data):
        seller = self.context['seller']
        customer = SellerCustomer(seller=seller, **validated_data)
        customer.sync_composed_address()
        customer.save()
        from customerapp.messaging import (
            link_seller_customer,
            notify_customer_added_by_seller,
        )

        link_seller_customer(customer)
        notify_customer_added_by_seller(customer, seller)
        return customer


class SellerCustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCustomer
        fields = [
            'name',
            'phone',
            'email',
            'address',
            'flat_number',
            'tower',
            'society',
            'city',
            'state',
            'country',
            'status',
        ]
        extra_kwargs = {
            'name': {'required': False},
            'phone': {'required': False},
            'email': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'flat_number': {'required': False, 'allow_blank': True},
            'tower': {'required': False, 'allow_blank': True},
            'society': {'required': False, 'allow_blank': True},
            'city': {'required': False, 'allow_blank': True},
            'state': {'required': False, 'allow_blank': True},
            'country': {'required': False, 'allow_blank': True},
            'status': {'required': False},
        }

    def validate_phone(self, value):
        phone = (value or '').strip()
        if not phone:
            raise serializers.ValidationError('Phone number is required.')
        seller = self.context['seller']
        instance = self.instance
        if seller_customer_phone_exists(seller, phone, exclude_id=instance.pk if instance else None):
            raise serializers.ValidationError(
                'A customer with this phone number already exists.'
            )
        return phone

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.sync_composed_address()
        instance.save()
        return instance


class ClientIdMixin(serializers.Serializer):
    client_id = ClientIdField(required=False, allow_null=True)
    device_created_at = serializers.DateTimeField(required=False, allow_null=True)


class ReceivePaymentSerializer(ClientIdMixin):
    customer_id = CustomerRefField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = PaymentMethodField(default='cash')
    note = serializers.CharField(required=False, allow_blank=True, default='')
    send_sms = serializers.BooleanField(required=False, default=None, allow_null=True)


class AddCreditSerializer(ClientIdMixin):
    customer_id = CustomerRefField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    due_date = serializers.DateField(required=False, allow_null=True)
    send_sms = serializers.BooleanField(required=False, default=None, allow_null=True)


class AdvanceDepositSerializer(ClientIdMixin):
    customer_id = CustomerRefField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    payment_method = PaymentMethodField(default='upi')
    note = serializers.CharField(required=False, allow_blank=True, default='')


class AdvanceUseSerializer(ClientIdMixin):
    customer_id = CustomerRefField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    note = serializers.CharField(required=False, allow_blank=True, default='')


class SyncOperationSerializer(serializers.Serializer):
    client_id = ClientIdField()
    op = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.DictField(required=False, default=dict)

    _PAYLOAD_KEYS = (
        'name',
        'phone',
        'email',
        'address',
        'flat_number',
        'tower',
        'society',
        'city',
        'state',
        'country',
        'device_created_at',
        'amount',
        'note',
        'payment_method',
        'send_sms',
        'due_date',
        'customer_id',
        'customer_client_id',
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            return super().to_internal_value(data)

        item = dict(data)
        aliases = (
            ('clientId', 'client_id'),
            ('type', 'op'),
            ('operation', 'op'),
            ('data', 'payload'),
            ('body', 'payload'),
        )
        for src, dst in aliases:
            if src in item and dst not in item:
                item[dst] = item.pop(src)

        payload = dict(item.get('payload') or {})
        for key in self._PAYLOAD_KEYS:
            if key in item and key not in payload:
                payload[key] = item[key]

        op = (item.get('op') or payload.pop('type', '') or payload.pop('operation', '') or '').strip()
        if not op:
            raise serializers.ValidationError({'op': 'This field is required.'})

        item['op'] = op
        item['payload'] = payload
        return super().to_internal_value(item)


class SyncPushSerializer(serializers.Serializer):
    operations = SyncOperationSerializer(many=True, required=False, default=list)

    def to_internal_value(self, data):
        if isinstance(data, list):
            data = {'operations': data}
        elif isinstance(data, dict):
            for key in ('operations', 'ops', 'changes', 'items', 'data', 'queue'):
                if key in data and isinstance(data[key], list):
                    data = {'operations': data[key]}
                    break
        return super().to_internal_value(data)


class RemindSerializer(serializers.Serializer):
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )


class CustomerNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerNote
        fields = ['id', 'text', 'created_at']
        read_only_fields = ['id', 'created_at']


class CustomerFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerFile
        fields = ['id', 'file', 'label', 'created_at']
        read_only_fields = ['id', 'created_at']


class SellerSettingsSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='seller.business_name', read_only=True)
    team_count = serializers.SerializerMethodField()

    class Meta:
        model = SellerSettings
        fields = [
            'language',
            'reminder_channels',
            'push_notifications_enabled',
            'auto_remind_enabled',
            'auto_remind_time',
            'auto_remind_days_before',
            'daily_summary_enabled',
            'daily_summary_time',
            'daily_summary_channels',
            'business_name',
            'team_count',
            'updated_at',
        ]
        read_only_fields = ['updated_at', 'business_name', 'team_count']

    def validate_auto_remind_time(self, value):
        return self._validate_hhmm(value)

    def validate_daily_summary_time(self, value):
        return self._validate_hhmm(value)

    def _validate_hhmm(self, value):
        text = str(value or '').strip()
        parts = text.split(':')
        if len(parts) != 2:
            raise serializers.ValidationError('Time must be HH:mm (24-hour).')
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise serializers.ValidationError('Invalid time.')
        return f'{hour:02d}:{minute:02d}'

    def get_team_count(self, obj):
        return obj.seller.team_members.count()


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seller
        fields = [
            'business_name',
            'full_name',
            'phone',
            'email',
            'address',
            'gst_number',
            'upi_id',
            'bank_account_number',
            'bank_ifsc',
            'bank_account_holder',
            'razorpay_route_status',
        ]
        read_only_fields = ['email', 'razorpay_route_status']

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        bank_fields = {
            'bank_account_number',
            'bank_ifsc',
            'bank_account_holder',
        }
        if bank_fields.intersection(validated_data.keys()):
            from easyudhar.razorpay_route import (
                ensure_seller_linked_account,
                seller_payout_ready,
            )

            if seller_payout_ready(instance):
                try:
                    ensure_seller_linked_account(instance)
                    instance.refresh_from_db(fields=['razorpay_route_status'])
                except Exception:
                    pass
        return instance


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['id', 'name', 'phone', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']


class SellerNotificationSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='notification_type')
    customer_id = serializers.SerializerMethodField()

    class Meta:
        model = SellerNotification
        fields = [
            'id',
            'type',
            'title',
            'subtitle',
            'customer_id',
            'reference_id',
            'is_read',
            'created_at',
        ]

    def get_customer_id(self, obj):
        if obj.seller_customer_id:
            return str(obj.seller_customer_id)
        return None


class FcmTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=['android', 'ios'])
    device_id = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=''
    )
