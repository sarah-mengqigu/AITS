from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "nickname", "display_name", "avatar", "phone",
            "department", "is_active", "is_staff", "is_superuser", "date_joined",
            "last_login", "roles",
        )
        read_only_fields = ("id", "date_joined", "last_login", "is_staff", "is_superuser")

    def get_roles(self, obj):
        if getattr(obj, "is_superuser", False):
            return ["owner"]
        return list(
            obj.project_memberships.values_list("role", flat=True).distinct()
        )


class UserBriefSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "email", "avatar")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password_confirm", "nickname", "phone",
                  "department")

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("用户名已存在")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("邮箱已被注册")
        return value

    def validate(self, attrs):
        confirm = attrs.pop("password_confirm", None)
        if confirm is not None and confirm != attrs.get("password"):
            raise serializers.ValidationError({"password_confirm": "两次输入的密码不一致"})
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        credential = attrs.get("username") or attrs.get("email")
        password = attrs.get("password")
        if not credential or not password:
            raise serializers.ValidationError({"detail": "用户名和密码不能为空"})
        user = None
        if "@" in credential:
            user = User.objects.filter(email__iexact=credential).first()
        if user is None:
            user = User.objects.filter(username__iexact=credential).first()
        if user is None or not user.check_password(password):
            raise serializers.ValidationError({"detail": "用户名或密码错误"})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "账号已被禁用"})
        attrs["user"] = user
        return attrs


class AITSTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds identity claims to both access and refresh tokens."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["nickname"] = user.nickname or user.username
        token["email"] = user.email
        return token


def issue_tokens(user) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["username"] = user.username
    refresh["nickname"] = user.nickname or user.username
    refresh["email"] = user.email
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("原密码不正确")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
