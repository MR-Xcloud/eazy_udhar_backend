from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import AdminUser


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from django.contrib.auth import authenticate

        admin = authenticate(
            self.context['request'],
            email=attrs['email'],
            password=attrs['password'],
        )
        if admin is None or not isinstance(admin, AdminUser):
            raise serializers.ValidationError('Invalid credentials.')
        attrs['user'] = admin
        return attrs


class AdminUserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name')

    class Meta:
        model = AdminUser
        fields = ['id', 'email', 'name', 'role', 'is_active', 'password', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'id': {'read_only': True},
            'created_at': {'read_only': True},
        }

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = AdminUser(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# Token refresh uses rest_framework_simplejwt.views.TokenRefreshView (standard JWT).
