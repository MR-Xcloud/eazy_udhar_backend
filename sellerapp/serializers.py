import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
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
from .utils import seller_customer_phone_exists, seller_to_dict


class SellerRegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name')
    mobile = serializers.CharField(source='phone')
    role = serializers.CharField(required=False, default=Seller.ROLE_SELLER)

    class Meta:
        model = Seller
        fields = ['name', 'email', 'mobile', 'password', 'role', 'business_name']
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

    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data['email']
        user = Seller.objects.create_user(
            username=email,
            password=password,
            **validated_data,
        )
        SellerSettings.objects.get_or_create(seller=user)
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


class SellerCustomerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerCustomer
        fields = ['name', 'phone', 'email', 'address', 'city', 'state', 'country']
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
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
        customer = SellerCustomer.objects.create(seller=seller, **validated_data)
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
        fields = ['name', 'phone', 'email', 'address', 'city', 'state', 'country', 'status']

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


class ReceivePaymentSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.CharField(default='UPI')
    note = serializers.CharField(required=False, allow_blank=True, default='')
    send_sms = serializers.BooleanField(required=False, default=None, allow_null=True)


class AddCreditSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    send_sms = serializers.BooleanField(required=False, default=None, allow_null=True)


class AdvanceDepositSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    payment_method = serializers.CharField(default='UPI')
    note = serializers.CharField(required=False, allow_blank=True, default='')


class AdvanceUseSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    note = serializers.CharField(required=False, allow_blank=True, default='')


class RemindSerializer(serializers.Serializer):
    channels = serializers.ListField(
        child=serializers.CharField(), default=['whatsapp', 'sms']
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
            'business_name',
            'team_count',
            'updated_at',
        ]
        read_only_fields = ['updated_at', 'business_name', 'team_count']

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
        ]
        read_only_fields = ['email']


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
