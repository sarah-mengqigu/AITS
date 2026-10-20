from django.contrib import admin

from apps.notifications.models import (
    EmailConfig,
    NotificationChannel,
    NotificationLog,
    NotificationReceiver,
)


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "channel_code", "name", "is_active", "created_at")
    list_filter = ("is_active", "channel_code")
    search_fields = ("name", "channel_code")


@admin.register(NotificationReceiver)
class NotificationReceiverAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "channel", "is_active", "created_at")
    list_filter = ("is_active", "channel__channel_code")
    search_fields = ("name", "webhook_url", "target_address")
    raw_id_fields = ("project",)


@admin.register(EmailConfig)
class EmailConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "host", "port", "from_email", "use_ssl", "use_tls", "is_active")
    list_filter = ("is_active", "use_ssl", "use_tls")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "channel_code",
        "title",
        "status",
        "project",
        "scheduled_task_name",
        "created_at",
    )
    list_filter = ("status", "channel_code")
    search_fields = ("title", "content", "scheduled_task_name", "error_message")
    raw_id_fields = ("project", "receiver")
