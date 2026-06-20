import random
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import (
    AccountStatementLine,
    Customer,
    CustomerAccount,
    CustomerNotification,
    CustomerPayment,
    CustomerSettings,
    OTPRecord,
    PaymentMethod,
)


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name')
    mobile = serializers.CharField(source='phone')
    role = serializers.CharField(required=False, default=Customer.ROLE_CUSTOMER)

    promo_code = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=''
    )

    class Meta:
        model = Customer
        fields = ['name', 'email', 'mobile', 'password', 'role', 'promo_code']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_role(self, value):
        if value != Customer.ROLE_CUSTOMER:
            raise serializers.ValidationError('Only customer role is allowed.')
        return value

    def validate_email(self, value):
        if Customer.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already exists.')
        return value

    def validate_mobile(self, value):
        if Customer.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Phone number already exists.')
        return value

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError('Password must be at least 8 characters.')
        return value

    def validate_promo_code(self, value):
        return (value or '').strip()

    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data['email']
        user = Customer.objects.create_user(
            username=email,
            password=password,
            **validated_data,
        )
        CustomerSettings.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs['email']
        password = attrs['password']
        user = authenticate(
            self.context['request'],
            username=email,
            password=password,
        )
        if user is None:
            raise serializers.ValidationError('Invalid credentials.')
        attrs['user'] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        email = self.validated_data['email']
        try:
            user = Customer.objects.get(email=email)
        except Customer.DoesNotExist:
            return None
        otp = f'{random.randint(100000, 999999)}'
        OTPRecord.objects.create(
            email=email,
            phone=user.phone,
            otp_code=otp,
            purpose=OTPRecord.PURPOSE_RESET,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        return otp


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            record = OTPRecord.objects.filter(
                email=attrs['email'],
                purpose=OTPRecord.PURPOSE_RESET,
                is_verified=False,
                expires_at__gte=timezone.now(),
            ).latest('created_at')
        except OTPRecord.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired OTP.')
        if record.otp_code != attrs['otp']:
            raise serializers.ValidationError('Invalid OTP.')
        attrs['otp_record'] = record
        return attrs

    def save(self):
        record = self.validated_data['otp_record']
        user = Customer.objects.get(email=self.validated_data['email'])
        password = self.validated_data['new_password']
        validate_password(password, user)
        user.set_password(password)
        user.save()
        record.is_verified = True
        record.save(update_fields=['is_verified'])
        return user


class GoogleSignInSerializer(serializers.Serializer):
    id_token = serializers.CharField()

    def validate(self, attrs):
        raise serializers.ValidationError(
            'Google sign-in is not configured yet. Use email/password login.'
        )


class OTPSendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(max_length=15, required=False)
    phone = serializers.CharField(max_length=15, required=False)

    def validate(self, attrs):
        attrs['phone'] = attrs.get('mobile') or attrs.get('phone') or ''
        if not attrs.get('email') and not attrs['phone']:
            raise serializers.ValidationError('email or mobile is required.')
        return attrs

    def save(self):
        from .otp_service import resolve_customer_email, send_login_otp

        try:
            otp, delivery = send_login_otp(
                email=self.validated_data.get('email'),
                phone=self.validated_data.get('phone') or None,
                purpose=OTPRecord.PURPOSE_LOGIN,
                resolver=resolve_customer_email,
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        self.delivery_result = delivery
        return otp


class OTPVerifySerializer(serializers.Serializer):
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
        from .otp_service import verify_customer_login_otp

        try:
            return verify_customer_login_otp(
                email=self.validated_data.get('email'),
                phone=self.validated_data.get('phone') or None,
                otp_code=self.validated_data['otp'],
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class CustomerAccountSerializer(serializers.ModelSerializer):
    shop_id = serializers.UUIDField(source='id', read_only=True)
    shop = serializers.CharField(source='shop_name')
    amount = serializers.DecimalField(
        source='outstanding_amount', max_digits=12, decimal_places=2
    )
    due_date = serializers.DateField(source='next_due_date', allow_null=True)
    overdue = serializers.SerializerMethodField()
    advance = serializers.SerializerMethodField()
    total_deposited = serializers.SerializerMethodField()
    total_used = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    advance_deposited = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    advance_used = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    advance_balance = serializers.SerializerMethodField()
    deposited = serializers.SerializerMethodField()
    used = serializers.SerializerMethodField()
    balance_available = serializers.SerializerMethodField()
    seller_upi_id = serializers.SerializerMethodField()

    class Meta:
        model = CustomerAccount
        fields = [
            'shop_id',
            'shop',
            'shop_name',
            'due_date',
            'next_due_date',
            'amount',
            'outstanding_amount',
            'status',
            'has_balance',
            'overdue',
            'advance',
            'total_deposited',
            'total_used',
            'remaining',
            'advance_deposited',
            'advance_used',
            'advance_balance',
            'deposited',
            'used',
            'balance_available',
            'seller_upi_id',
        ]

    def get_overdue(self, obj):
        return obj.is_overdue

    def _advance_payload(self, obj):
        from sellerapp.services import advance_summary

        return advance_summary(obj)

    def get_advance(self, obj):
        return self._advance_payload(obj)

    def get_total_deposited(self, obj):
        return float(obj.advance_deposited)

    def get_total_used(self, obj):
        return float(obj.advance_used)

    def get_remaining(self, obj):
        return float(obj.advance_balance)

    def get_advance_balance(self, obj):
        return float(obj.advance_balance)

    def get_deposited(self, obj):
        return float(obj.advance_deposited)

    def get_used(self, obj):
        return float(obj.advance_used)

    def get_balance_available(self, obj):
        return float(obj.advance_balance)

    def get_seller_upi_id(self, obj):
        seller = obj.seller
        if seller is None and obj.seller_customer_id:
            seller = getattr(obj.seller_customer, 'seller', None)
        if seller is None:
            return ''
        return (seller.upi_id or '').strip()


class StatementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountStatementLine
        fields = ['id', 'description', 'amount', 'line_type', 'date', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    shop_id = serializers.SerializerMethodField()
    shop_name = serializers.SerializerMethodField()
    method_label = serializers.SerializerMethodField()

    class Meta:
        model = CustomerPayment
        fields = [
            'id',
            'shop_id',
            'shop_name',
            'amount',
            'method',
            'method_label',
            'status',
            'is_partial',
            'reference_id',
            'razorpay_order_id',
            'razorpay_payment_id',
            'created_at',
        ]
        read_only_fields = fields

    def get_shop_id(self, obj):
        return str(obj.account_id) if obj.account_id else None

    def get_shop_name(self, obj):
        return obj.account.shop_name if obj.account else None

    def get_method_label(self, obj):
        from easyudhar.payment_utils import payment_method_label

        return payment_method_label(obj.method)


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'method_type',
            'label',
            'upi_id',
            'account_ref',
            'is_default',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='notification_type')
    time = serializers.DateTimeField(source='created_at', read_only=True)
    shop_id = serializers.SerializerMethodField()
    shop_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomerNotification
        fields = [
            'id',
            'type',
            'title',
            'subtitle',
            'shop_id',
            'shop_name',
            'reference_id',
            'time',
            'is_read',
            'created_at',
        ]

    def get_shop_id(self, obj):
        if obj.shop_account_id:
            return str(obj.shop_account_id)
        return None

    def get_shop_name(self, obj):
        if obj.shop_account_id:
            return obj.shop_account.shop_name
        return None


class ShopMessageSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, default='')


class ChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, default='')


class FcmTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=['android', 'ios'])
    device_id = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=''
    )


class ProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name', required=False)
    mobile = serializers.CharField(source='phone', required=False)

    class Meta:
        model = Customer
        fields = [
            'name',
            'full_name',
            'mobile',
            'phone',
            'email',
            'promo_code',
            'avatar_initials',
            'role',
        ]
        read_only_fields = ['email', 'promo_code', 'avatar_initials', 'role']


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerSettings
        fields = [
            'language',
            'privacy_show_phone',
            'privacy_show_email',
            'keep_signed_in',
            'push_notifications_enabled',
            'updated_at',
        ]
        read_only_fields = ['updated_at']

