"""Seed the five built-in notification channels.

Idempotent: existing rows are left untouched so operators can customise names or
disable a channel without the next migrate reverting it.
"""

from django.db import migrations

BUILTIN_CHANNELS = [
    {
        "channel_code": "dingtalk",
        "name": "钉钉群机器人",
        "description": "通过钉钉自定义机器人 Webhook 推送 Markdown 消息（errcode==0 视为成功）。",
        "config_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "title": "Webhook 地址"},
                "secret": {"type": "string", "title": "加签密钥（可选）"},
            },
            "required": ["webhook_url"],
        },
    },
    {
        "channel_code": "wechat_work",
        "name": "企业微信群机器人",
        "description": "通过企业微信机器人 Webhook 推送 Markdown 消息（errcode==0 视为成功）。",
        "config_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "title": "Webhook 地址"},
            },
            "required": ["webhook_url"],
        },
    },
    {
        "channel_code": "feishu",
        "name": "飞书自定义机器人",
        "description": "通过飞书自定义机器人 Webhook 推送消息卡片（code==0 视为成功）。",
        "config_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "title": "Webhook 地址"},
                "secret": {"type": "string", "title": "签名校验密钥（可选）"},
            },
            "required": ["webhook_url"],
        },
    },
    {
        "channel_code": "email",
        "name": "邮件",
        "description": "使用 EmailConfig 中的动态 SMTP 配置发送 HTML + 纯文本双格式邮件。",
        "config_schema": {
            "type": "object",
            "properties": {
                "target_address": {
                    "type": "string",
                    "title": "收件人邮箱（多个用逗号分隔）",
                },
            },
            "required": ["target_address"],
        },
    },
    {
        "channel_code": "webhook",
        "name": "通用 Webhook",
        "description": "向任意 HTTP 端点 POST JSON（title / markdown / content / project_id / timestamp）。",
        "config_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "title": "回调地址"},
            },
            "required": ["webhook_url"],
        },
    },
]


def seed_channels(apps, schema_editor):
    NotificationChannel = apps.get_model("notifications", "NotificationChannel")
    for item in BUILTIN_CHANNELS:
        NotificationChannel.objects.get_or_create(
            channel_code=item["channel_code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "config_schema": item["config_schema"],
                "is_active": True,
            },
        )


def unseed_channels(apps, schema_editor):
    NotificationChannel = apps.get_model("notifications", "NotificationChannel")
    codes = [item["channel_code"] for item in BUILTIN_CHANNELS]
    NotificationChannel.objects.filter(
        channel_code__in=codes, receivers__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_channels, unseed_channels),
    ]
