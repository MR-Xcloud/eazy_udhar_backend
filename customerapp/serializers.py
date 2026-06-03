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

    class Meta:
        model = Customer
        fields = ['name', 'email', 'mobile', 'password', 'role']
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
    mobile = serializers.CharField(max_length=15)

    def save(self):
        otp = f'{random.randint(100000, 999999)}'
        OTPRecord.objects.create(
            phone=self.validated_data['mobile'],
            otp_code=otp,
            purpose=OTPRecord.PURPOSE_LOGIN,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        return otp


class OTPVerifySerializer(serializers.Serializer):
    mobile = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        try:
            record = OTPRecord.objects.filter(
                phone=attrs['mobile'],
                purpose=OTPRecord.PURPOSE_LOGIN,
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
        record.is_verified = True
        record.save(update_fields=['is_verified'])
        user, _ = Customer.objects.get_or_create(
            phone=self.validated_data['mobile'],
            defaults={
                'username': self.validated_data['mobile'],
                'email': f"{self.validated_data['mobile']}@otp.local",
                'full_name': 'Customer',
            },
        )
        if not user.has_usable_password():
            user.set_unusable_password()
            user.save()
        CustomerSettings.objects.get_or_create(user=user)
        return user


class CustomerAccountSerializer(serializers.ModelSerializer):
    shop_id = serializers.UUIDField(source='id', read_only=True)
    shop = serializers.CharField(source='shop_name')
    amount = serializers.DecimalField(
        source='outstanding_amount', max_digits=12, decimal_places=2
    )
    due_date = serializers.DateField(source='next_due_date', allow_null=True)
    overdue = serializers.SerializerMethodField()

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
        ]

    def get_overdue(self, obj):
        return obj.is_overdue


class StatementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountStatementLine
        fields = ['id', 'description', 'amount', 'line_type', 'date', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    shop_id = serializers.UUIDField(write_only=True, required=False)
    shop_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    class Meta:
        model = CustomerPayment
        fields = [
            'id',
            'shop_id',
            'shop_ids',
            'amount',
            'method',
            'status',
            'reference_id',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'reference_id', 'created_at']


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'method_type', 'label', 'upi_id', 'is_default', 'created_at']
        read_only_fields = ['id', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='notification_type')
    time = serializers.DateTimeField(source='created_at', read_only=True)
    shop_id = serializers.SerializerMethodField()

    class Meta:
        model = CustomerNotification
        fields = [
            'id',
            'type',
            'title',
            'subtitle',
            'shop_id',
            'reference_id',
            'time',
            'is_read',
            'created_at',
        ]

    def get_shop_id(self, obj):
        if obj.shop_account_id:
            return str(obj.shop_account_id)
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
        fields = ['name', 'full_name', 'mobile', 'phone', 'email', 'avatar_initials', 'role']
        read_only_fields = ['email', 'avatar_initials', 'role']


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerSettings
        fields = [
            'language',
            'privacy_show_phone',
            'privacy_show_email',
            'keep_signed_in',
            'updated_at',
        ]
        read_only_fields = ['updated_at']

