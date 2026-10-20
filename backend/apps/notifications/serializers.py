"""Serializers for the 通知中心 module."""

from rest_framework import serializers

from apps.notifications.models import (
    EmailConfig,
    NotificationChannel,
    NotificationLog,
    NotificationReceiver,
)


class NotificationChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannel
        fields = (
            "id",
            "channel_code",
            "name",
            "description",
            "is_active",
            "config_schema",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_config_schema(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_schema 必须是对象")
        return value


class NotificationReceiverSerializer(serializers.ModelSerializer):
    channel_code = serializers.CharField(source="channel.channel_code", read_only=True)
    channel_name = serializers.CharField(source="channel.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, default="")

    class Meta:
        model = NotificationReceiver
        fields = (
            "id",
            "project",
            "project_name",
            "name",
            "channel",
            "channel_code",
            "channel_name",
            "webhook_url",
            "target_address",
            "is_active",
            "description",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_metadata(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("metadata 必须是对象")
        return value

    def validate(self, attrs):
        channel = attrs.get("channel") or getattr(self.instance, "channel", None)
        target_address = attrs.get(
            "target_address", getattr(self.instance, "target_address", "")
        )
        if channel is not None and channel.channel_code == "email":
            if target_address and "@" not in target_address:
                raise serializers.ValidationError(
                    {"target_address": "请填写合法的邮箱地址（多个用逗号分隔）"}
                )
        return attrs


class EmailConfigSerializer(serializers.ModelSerializer):
    """SMTP singleton serializer; ``password`` is masked on every read."""

    password = serializers.CharField(
        required=False, allow_blank=True, style={"input_type": "password"}
    )

    class Meta:
        model = EmailConfig
        fields = (
            "id",
            "host",
            "port",
            "username",
            "password",
            "from_email",
            "use_ssl",
            "use_tls",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "port": {"required": False, "min_value": 1, "max_value": 65535},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["password"] = "******" if getattr(instance, "password", "") else ""
        return data

    def validate(self, attrs):
        # 前端把掩码原样回传时不要覆盖真实密码。
        if attrs.get("password") in ("******", "***"):
            attrs.pop("password", None)
        return attrs


class NotificationLogSerializer(serializers.ModelSerializer):
    receiver_name = serializers.CharField(source="receiver.name", read_only=True, default="")
    project_name = serializers.CharField(source="project.name", read_only=True, default="")

    class Meta:
        model = NotificationLog
        fields = (
            "id",
            "project",
            "project_name",
            "receiver",
            "receiver_name",
            "channel_code",
            "title",
            "content",
            "status",
            "error_message",
            "payload",
            "scheduled_task_id",
            "scheduled_task_name",
            "task_execution_log_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
