"""通知中心服务层。

对外固定入口（供 scheduled_tasks / performance 等模块调用）::

    from apps.notifications.services import trigger_notification
    trigger_notification(scheduled_task, execution_log, result=None) -> dict

设计原则：
* 单渠道失败只记日志 + NotificationLog(status=failed)，绝不影响其它渠道与主流程。
* HTTP 统一 ``requests.post(timeout=10)``，测试中通过 unittest.mock 打桩，不联网。
* Markdown / HTML 组装为纯函数，便于单测。
"""

import logging
import re
from datetime import date, datetime

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.html import escape

from apps.common.api.api_exception_handler import BusinessError
from apps.notifications.models import (
    CHANNEL_DINGTALK,
    CHANNEL_EMAIL,
    CHANNEL_FEISHU,
    CHANNEL_WEBHOOK,
    CHANNEL_WECHAT_WORK,
    CHANNEL_CODES,
    LOG_STATUS_FAILED,
    LOG_STATUS_SUCCESS,
    TRIGGER_FAIL,
    EmailConfig,
    NotificationLog,
    NotificationReceiver,
)

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 10

DEFAULT_TITLE = "定时任务执行结果"

STAT_ALIASES = {
    "total": ("total", "total_count", "total_cases", "case_total"),
    "passed": ("passed", "pass_count", "passed_count", "success", "success_count"),
    "failed": ("failed", "fail_count", "failed_count", "fail"),
    "skipped": ("skipped", "skip_count", "skipped_count"),
    "pass_rate": ("pass_rate", "success_rate", "rate"),
}

STATUS_LABELS = {
    "passed": "通过",
    "failed": "未通过",
    "error": "异常",
    "running": "执行中",
    "pending": "等待执行",
    "cancelled": "已取消",
}

_EMAIL_SPLIT_RE = re.compile(r"[,;，；]")


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
_MISSING = object()


def _field(obj, name, default=None):
    """Read a field from a dict or a model/object uniformly."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_int(value, default=0):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value, limit=None):
    text = "" if value is None else str(value)
    if limit is not None and len(text) > limit:
        return text[:limit]
    return text


def _format_datetime(value):
    """Format a datetime/date/string for display (deterministic in tests)."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _normalize_target_list(targets):
    """Accept ``None`` / comma string / iterable -> list of non-empty strings."""
    if not targets:
        return []
    if isinstance(targets, str):
        targets = _EMAIL_SPLIT_RE.split(targets)
    result = []
    for item in targets:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        if _EMAIL_SPLIT_RE.search(text):
            result.extend(part.strip() for part in _EMAIL_SPLIT_RE.split(text) if part.strip())
        else:
            result.append(text)
    return result


# ---------------------------------------------------------------------------
# markdown / html
# ---------------------------------------------------------------------------
def build_report_url(report_url):
    """Turn a relative report path into an absolute URL using ``SITE_URL``."""
    if not report_url:
        return ""
    if isinstance(report_url, (list, tuple)):
        report_url = next((item for item in report_url if item), "")
    if not isinstance(report_url, str):
        return ""
    report_url = report_url.strip()
    if not report_url:
        return ""
    if report_url.startswith(("http://", "https://", "//")):
        return report_url
    site_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not site_url:
        return report_url
    return f"{site_url}/{report_url.lstrip('/')}"


def build_markdown(
    task_name,
    total=0,
    passed=0,
    failed=0,
    skipped=0,
    pass_rate=None,
    status="",
    started_at=None,
    report_url="",
    title=DEFAULT_TITLE,
    conclusion=None,
    extra_lines=None,
):
    """Assemble the Markdown payload shared by every channel (pure function)."""
    total = _as_int(total)
    passed = _as_int(passed)
    failed = _as_int(failed)
    skipped = _as_int(skipped)
    if pass_rate is None or pass_rate == "":
        computed = round(passed / total * 100, 2) if total else 0.0
    else:
        computed = round(_as_float(pass_rate, 0.0), 2)

    status_key = (status or "").lower()
    status_label = STATUS_LABELS.get(status_key, "已完成")
    if conclusion is None:
        conclusion = (
            "测试未通过" if status_key in ("failed", "error") or failed > 0 else "测试通过"
        )

    lines = [
        f"## {title}",
        f"**任务名称**: {task_name or '未命名任务'}",
        f"**执行结果**: {status_label}",
        f"**通过/失败/跳过/总计**: {passed}/{failed}/{skipped}/{total}",
        f"**成功率**: {computed}%",
        f"**测试结论**: {conclusion}",
    ]
    started_text = _format_datetime(started_at)
    if started_text:
        lines.append(f"**开始时间**: {started_text}")
    report_link = build_report_url(report_url)
    if report_link:
        lines.append(f"**报告链接**: [查看报告]({report_link})")
    for line in extra_lines or []:
        if line:
            lines.append(str(line))
    return "\n".join(lines)


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _inline_markdown_html(text):
    """Escape then render the small inline subset we emit (**bold**, [text](url))."""
    escaped = escape(text)
    escaped = _LINK_RE.sub(
        lambda match: f'<a href="{match.group(2)}">{match.group(1)}</a>', escaped
    )
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return escaped


def build_email_html(markdown_text):
    """Convert our Markdown subset into a self-contained responsive HTML email."""
    markdown_text = markdown_text or ""
    parts = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            close_list()
            continue
        if line.startswith("### "):
            close_list()
            parts.append(f"<h3>{_inline_markdown_html(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            parts.append(f"<h2>{_inline_markdown_html(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            parts.append(f"<h1>{_inline_markdown_html(line[2:])}</h1>")
        elif line.startswith(("- ", "* ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markdown_html(line[2:])}</li>")
        elif line.startswith(("---", "***")):
            close_list()
            parts.append("<hr />")
        else:
            close_list()
            parts.append(f"<p>{_inline_markdown_html(line)}</p>")
    close_list()

    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        "  <title>AITS 通知</title>\n"
        "  <style>\n"
        "    body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', Arial, "
        "sans-serif; color: #1f2d3d; background: #f5f7fa; margin: 0; padding: 24px; }\n"
        "    .aits-notification { max-width: 720px; margin: 0 auto; background: #ffffff; "
        "border-radius: 8px; padding: 24px; border: 1px solid #e4e7ed; }\n"
        "    h2 { color: #409eff; font-size: 20px; margin-top: 0; }\n"
        "    p { line-height: 1.7; margin: 8px 0; }\n"
        "    strong { color: #303133; }\n"
        "    a { color: #409eff; }\n"
        "    hr { border: none; border-top: 1px solid #e4e7ed; margin: 16px 0; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '  <div class="aits-notification">\n'
        f"    {body}\n"
        "  </div>\n"
        "</body>\n"
        "</html>"
    )


# ---------------------------------------------------------------------------
# low level HTTP senders
# ---------------------------------------------------------------------------
def _request_json(url, payload):
    """POST JSON with the shared timeout and return ``(status_code, body)``."""
    if not url:
        raise BusinessError(message="未配置 Webhook 地址", code="webhook_url_missing")
    try:
        response = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise BusinessError(
            message=f"请求通知地址失败: {exc}", code="notification_http_error"
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive for exotic mocks
        raise BusinessError(
            message=f"请求通知地址失败: {exc}", code="notification_http_error"
        ) from exc

    status_code = getattr(response, "status_code", 200) or 200
    if status_code >= 400:
        raise BusinessError(
            message=f"通知地址返回 HTTP {status_code}", code="notification_http_error"
        )
    try:
        body = response.json()
    except Exception:
        body = None
    return status_code, body


def _response_message(body, default="未知错误"):
    if isinstance(body, dict):
        for key in ("errmsg", "msg", "message", "error"):
            value = body.get(key)
            if value:
                return str(value)
    return default


def send_dingtalk(webhook_url, markdown, title):
    """钉钉群机器人：``errcode == 0`` 视为成功。"""
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": markdown},
    }
    status_code, body = _request_json(webhook_url, payload)
    errcode = body.get("errcode") if isinstance(body, dict) else None
    if errcode not in (0, "0"):
        raise BusinessError(
            message=f"钉钉发送失败: {_response_message(body)}",
            code="dingtalk_send_failed",
        )
    return {
        "channel": CHANNEL_DINGTALK,
        "status_code": status_code,
        "response": body,
        "payload": payload,
    }


def send_wecom(webhook_url, markdown, title):
    """企业微信群机器人：``errcode == 0`` 视为成功。"""
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    status_code, body = _request_json(webhook_url, payload)
    errcode = body.get("errcode") if isinstance(body, dict) else None
    if errcode not in (0, "0"):
        raise BusinessError(
            message=f"企业微信发送失败: {_response_message(body)}",
            code="wecom_send_failed",
        )
    return {
        "channel": CHANNEL_WECHAT_WORK,
        "status_code": status_code,
        "response": body,
        "payload": payload,
    }


def send_feishu(webhook_url, markdown, title):
    """飞书自定义机器人：``code == 0``（兼容旧版 ``StatusCode``）视为成功。"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title or DEFAULT_TITLE},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": markdown}},
            ],
        },
    }
    status_code, body = _request_json(webhook_url, payload)
    code = None
    if isinstance(body, dict):
        code = body.get("code", body.get("StatusCode"))
    if code not in (0, "0"):
        raise BusinessError(
            message=f"飞书发送失败: {_response_message(body)}",
            code="feishu_send_failed",
        )
    return {
        "channel": CHANNEL_FEISHU,
        "status_code": status_code,
        "response": body,
        "payload": payload,
    }


def send_webhook(url, payload):
    """Generic webhook: any 2xx response is success (body may be empty)."""
    status_code, body = _request_json(url, payload)
    return {
        "channel": CHANNEL_WEBHOOK,
        "status_code": status_code,
        "response": body,
        "payload": payload,
    }


def _config_value(config, key, default=None):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def send_email(config, subject, markdown, targets):
    """Send one HTML + plain-text email through the dynamic SMTP config."""
    host = _config_value(config, "host", "") or ""
    if not host:
        raise BusinessError(message="未配置邮件服务器 host", code="email_not_configured")
    port = _as_int(_config_value(config, "port", 465), default=465)
    username = _config_value(config, "username", "") or ""
    password = _config_value(config, "password", "") or ""
    from_email = _config_value(config, "from_email", "") or username or getattr(
        settings, "DEFAULT_FROM_EMAIL", ""
    )
    use_ssl = bool(_config_value(config, "use_ssl", True))
    use_tls = bool(_config_value(config, "use_tls", False))

    recipients = _normalize_target_list(targets)
    if not recipients:
        raise BusinessError(message="邮件接收人为空", code="email_no_recipients")
    if not from_email:
        raise BusinessError(message="未配置发件人", code="email_no_sender")

    html_content = build_email_html(markdown)
    message = EmailMultiAlternatives(
        subject=subject or DEFAULT_TITLE,
        body=markdown or "",
        from_email=from_email,
        to=recipients,
    )
    message.attach_alternative(html_content, "text/html")
    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=host,
        port=port,
        username=username,
        password=password,
        use_ssl=use_ssl,
        use_tls=use_tls,
        fail_silently=False,
    )
    message.connection = connection
    sent = message.send(fail_silently=False)
    if not sent:
        raise BusinessError(message="邮件发送失败", code="email_send_failed")
    return {
        "channel": CHANNEL_EMAIL,
        "sent": sent,
        "recipients": recipients,
        "payload": {"subject": subject, "to": recipients, "from_email": from_email},
    }


# ---------------------------------------------------------------------------
# target resolution
# ---------------------------------------------------------------------------
def resolve_targets(project, receiver_ids):
    """Active receivers for ``project`` filtered by ``receiver_ids``."""
    queryset = NotificationReceiver.objects.filter(is_active=True).select_related(
        "channel", "project"
    )
    if project is not None:
        queryset = queryset.filter(project=project)
    if receiver_ids is not None:
        ids = []
        for value in receiver_ids:
            value_int = _as_int(value, default=None)
            if value_int is not None:
                ids.append(value_int)
        if not ids:
            return []
        queryset = queryset.filter(id__in=ids)
    return list(queryset.order_by("id"))


def _extract_notice_targets(scheduled_task):
    """Return ``(receiver_objects, receiver_ids)`` from a task object/dict."""
    raw = _field(scheduled_task, "notice_targets", _MISSING)
    if raw is _MISSING or raw is None:
        raw = _field(scheduled_task, "notice_target_ids", None)
        if raw is None:
            raw = _field(scheduled_task, "receiver_ids", None)
    if raw is None:
        return [], []

    if isinstance(raw, dict):
        if "id" in raw and len(raw) == 1:
            raw = [raw["id"]]
        else:
            raw = raw.get("ids") or raw.get("results") or raw.get("targets") or []
    if hasattr(raw, "all"):  # Django M2M manager / queryset
        raw = list(raw.all())
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]

    objects, ids = [], []
    for item in raw:
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str):
            item = item.strip()
            if item.isdigit():
                ids.append(int(item))
        elif isinstance(item, dict) and "id" in item:
            item_id = _as_int(item.get("id"), default=None)
            if item_id is not None:
                ids.append(item_id)
        elif hasattr(item, "pk"):
            objects.append(item)
    return objects, ids


def _resolve_notice_targets(scheduled_task, project):
    target_objects, target_ids = _extract_notice_targets(scheduled_task)
    targets = []
    seen = set()
    if target_ids:
        for receiver in resolve_targets(project, target_ids):
            if receiver.pk not in seen:
                seen.add(receiver.pk)
                targets.append(receiver)
    for receiver in target_objects:
        if not getattr(receiver, "is_active", False):
            continue
        if receiver.pk in seen:
            continue
        if project is not None and receiver.project_id not in (None, project.pk):
            continue
        seen.add(receiver.pk)
        targets.append(receiver)
    return targets


# ---------------------------------------------------------------------------
# stats / context extraction
# ---------------------------------------------------------------------------
def _pick_stats(source):
    stats = {}
    for canonical, aliases in STAT_ALIASES.items():
        for alias in aliases:
            if isinstance(source, dict):
                if alias in source and source[alias] not in (None, ""):
                    stats[canonical] = source[alias]
                    break
            else:
                value = getattr(source, alias, None)
                if value is not None:
                    stats[canonical] = value
                    break
    return stats


def _extract_stats(source):
    if source is None:
        return {}
    if isinstance(source, dict):
        stats = {}
        summary = source.get("summary")
        if isinstance(summary, dict):
            stats.update(_pick_stats(summary))
        stats.update(_pick_stats(source))
        return stats
    stats = {}
    summary = getattr(source, "summary", None)
    if isinstance(summary, dict):
        stats.update(_pick_stats(summary))
    stats.update(_pick_stats(source))
    return stats


def _resolve_scheduled_task(scheduled_task):
    """Allow ``scheduled_task`` to be an object, a dict, or a primary key.

    The design document lists ``trigger_notification(scheduled_task_id, ...)`` as
    the entry point; supporting an integer keeps that contract working once
    ``apps.scheduled_tasks`` is available, without creating an import dependency.
    """
    if isinstance(scheduled_task, bool):
        return scheduled_task
    if isinstance(scheduled_task, int) or (
        isinstance(scheduled_task, str) and scheduled_task.strip().isdigit()
    ):
        try:
            from apps.scheduled_tasks.models import ScheduledTask

            return ScheduledTask.objects.filter(pk=int(scheduled_task)).first()
        except Exception:  # noqa: BLE001 - scheduled_tasks may not be implemented yet
            logger.warning(
                "notifications: cannot resolve scheduled_task id %s", scheduled_task
            )
            return None
    return scheduled_task


def _stats_from_cases(cases):
    if not isinstance(cases, list) or not cases:
        return {}
    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    for case in cases:
        if not isinstance(case, dict):
            continue
        counts["total"] += 1
        status = str(case.get("status") or "").lower()
        if status in ("passed", "success", "pass"):
            counts["passed"] += 1
        elif status in ("skipped", "skip"):
            counts["skipped"] += 1
        elif status in ("failed", "error", "fail"):
            counts["failed"] += 1
    return counts


def _finalize_stats(raw_stats):
    total = _as_int(raw_stats.get("total"))
    passed = _as_int(raw_stats.get("passed"))
    failed = _as_int(raw_stats.get("failed"))
    skipped = _as_int(raw_stats.get("skipped"))
    if total <= 0:
        total = passed + failed + skipped
    pass_rate = _as_float(raw_stats.get("pass_rate"))
    if pass_rate is None:
        pass_rate = round(passed / total * 100, 2) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(pass_rate, 2),
    }


def _is_all_passed(stats, status):
    status_key = (status or "").lower()
    if status_key in ("failed", "error"):
        return False
    total = _as_int(stats.get("total"))
    failed = _as_int(stats.get("failed"))
    if total <= 0:
        return status_key == "passed"
    return failed == 0


def _resolve_project(scheduled_task, execution_log=None, result=None):
    candidate = _field(scheduled_task, "project", None)
    if candidate is None:
        candidate = _field(execution_log, "project", None)
    if candidate is None:
        candidate = _field(result, "project", None)
    if candidate is None:
        return None
    if hasattr(candidate, "pk"):
        return candidate
    project_id = _as_int(candidate, default=None)
    if project_id is None:
        return None
    from apps.projects.models import Project

    return Project.objects.filter(pk=project_id).first()


def _extract_report_url(result, execution_log):
    for source in (result, execution_log):
        if source is None:
            continue
        for key in ("report_url", "report_path", "report_link"):
            value = _field(source, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        report_urls = _field(source, "report_urls", None)
        if report_urls:
            if isinstance(report_urls, str):
                return report_urls
            if isinstance(report_urls, dict):
                for value in report_urls.values():
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            if isinstance(report_urls, (list, tuple)):
                for value in report_urls:
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return ""


def _resolve_started_at(result, execution_log):
    for source in (result, execution_log):
        if source is None:
            continue
        value = _field(source, "started_at", None)
        if value:
            return value
    return None


def _resolve_status(result, execution_log, scheduled_task=None):
    for source in (result, execution_log, scheduled_task):
        if source is None:
            continue
        value = _field(source, "status", None)
        if value:
            return str(value)
    return ""


def _project_webhook(project, attr):
    if project is None:
        return ""
    try:
        config = getattr(project, "third_party_config", None)
    except Exception:
        config = None
    if config is None:
        try:
            from apps.projects.models import ProjectThirdPartyConfig

            config = ProjectThirdPartyConfig.objects.filter(project=project).first()
        except Exception:
            config = None
    return (getattr(config, attr, "") or "") if config is not None else ""


# ---------------------------------------------------------------------------
# channel dispatch
# ---------------------------------------------------------------------------
def _send_by_channel(channel_code, webhook_url, target_address, title, markdown, project=None):
    """Dispatch ``markdown`` through one channel; raises BusinessError on failure."""
    channel_code = (channel_code or "").strip()
    webhook_url = (webhook_url or "").strip()

    if channel_code == CHANNEL_DINGTALK:
        url = webhook_url or _project_webhook(project, "dingtalk_webhook")
        return send_dingtalk(url, markdown, title)
    if channel_code == CHANNEL_WECHAT_WORK:
        url = webhook_url or _project_webhook(project, "wecom_webhook")
        return send_wecom(url, markdown, title)
    if channel_code == CHANNEL_FEISHU:
        url = webhook_url or _project_webhook(project, "feishu_webhook")
        return send_feishu(url, markdown, title)
    if channel_code == CHANNEL_EMAIL:
        config = EmailConfig.get_solo()
        if config is None or not getattr(config, "is_active", True):
            raise BusinessError(
                message="未配置或未启用邮件服务器", code="email_not_configured"
            )
        return send_email(config, title, markdown, target_address)
    if channel_code == CHANNEL_WEBHOOK:
        payload = {
            "title": title,
            "markdown": markdown,
            "content": markdown,
            "project_id": getattr(project, "id", None),
            "timestamp": timezone.now().isoformat(),
        }
        return send_webhook(webhook_url, payload)
    raise BusinessError(
        message=f"不支持的通知渠道: {channel_code}", code="unsupported_channel"
    )


def _write_log(
    *,
    project,
    receiver,
    channel_code,
    title,
    content,
    status,
    error_message="",
    payload=None,
    scheduled_task_id=None,
    scheduled_task_name="",
    task_execution_log_id=None,
):
    return NotificationLog.objects.create(
        project=project,
        receiver=receiver,
        channel_code=channel_code,
        title=_safe_text(title, limit=255),
        content=content or "",
        status=status,
        error_message=_safe_text(error_message),
        payload=payload or {},
        scheduled_task_id=scheduled_task_id,
        scheduled_task_name=_safe_text(scheduled_task_name, limit=255),
        task_execution_log_id=task_execution_log_id,
    )


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------
def trigger_notification(scheduled_task, execution_log=None, result=None):
    """Send one scheduled-task result notification to every active receiver.

    :param scheduled_task: object **or** dict. Recognised keys: ``id``, ``name``,
        ``project``, ``trigger_condition`` (``always`` / ``fail``),
        ``notice_targets`` (M2M manager / receiver objects / id list).
    :param execution_log: latest task execution log object or dict providing
        ``id``, ``status``, ``started_at``, ``total/passed/failed/skipped/pass_rate``
        and ``report_urls``.
    :param result: optional raw execution result dict; its stats override the
        execution log and may contain ``summary`` / ``cases`` / ``report_url``.

    :returns: ``{"sent": n, "failed": m, "results": [...]}``; additionally
        ``{"skipped": True, "reason": "all_passed"}`` when ``trigger_condition``
        is ``fail`` but everything passed and ``reason="no_targets"`` when no
        active receiver is configured. Never raises for channel-level failures.
    """
    scheduled_task = _resolve_scheduled_task(scheduled_task)
    task_id = _as_int(_field(scheduled_task, "id", None), default=None)
    execution_log_id = _as_int(_field(execution_log, "id", None), default=None)
    task_name = (
        _field(scheduled_task, "name", None)
        or _field(execution_log, "scheduled_task_name", None)
        or _field(result, "task_name", None)
        or "定时任务"
    )
    trigger_condition = (
        str(_field(scheduled_task, "trigger_condition", "always") or "always").lower()
    )
    project = _resolve_project(scheduled_task, execution_log, result)
    status = _resolve_status(result, execution_log, scheduled_task)

    stats = {}
    stats.update(_extract_stats(execution_log))
    stats.update(_extract_stats(result))
    if not _as_int(stats.get("total")) and isinstance(result, dict):
        case_stats = _stats_from_cases(result.get("cases"))
        if case_stats:
            stats.update(case_stats)
    stats = _finalize_stats(stats)

    if trigger_condition == TRIGGER_FAIL and _is_all_passed(stats, status):
        logger.info("notifications: task %s all passed, skip (trigger_condition=fail)", task_id)
        return {
            "skipped": True,
            "reason": "all_passed",
            "sent": 0,
            "failed": 0,
            "results": [],
        }

    targets = _resolve_notice_targets(scheduled_task, project)
    if not targets:
        logger.info("notifications: task %s has no active receivers, nothing to send", task_id)
        return {
            "skipped": True,
            "reason": "no_targets",
            "sent": 0,
            "failed": 0,
            "results": [],
        }

    title = DEFAULT_TITLE
    markdown = build_markdown(
        task_name=task_name,
        total=stats["total"],
        passed=stats["passed"],
        failed=stats["failed"],
        skipped=stats["skipped"],
        pass_rate=stats["pass_rate"],
        status=status,
        started_at=_resolve_started_at(result, execution_log),
        report_url=_extract_report_url(result, execution_log),
        title=title,
    )
    base_payload = {
        "trigger_condition": trigger_condition,
        "status": status,
        "stats": stats,
        "scheduled_task_id": task_id,
        "scheduled_task_name": _safe_text(task_name, limit=255),
        "task_execution_log_id": execution_log_id,
    }

    sent = 0
    failed = 0
    results = []
    for receiver in targets:
        channel_code = getattr(receiver, "channel_code", "") or ""
        receiver_project = getattr(receiver, "project", None) or project
        try:
            channel = getattr(receiver, "channel", None)
            if channel is not None and not getattr(channel, "is_active", True):
                raise BusinessError(
                    message=f"通知渠道已停用: {channel_code}", code="channel_inactive"
                )
            response = _send_by_channel(
                channel_code,
                getattr(receiver, "webhook_url", ""),
                getattr(receiver, "target_address", ""),
                title,
                markdown,
                project=receiver_project,
            )
            log = _write_log(
                project=receiver_project,
                receiver=receiver,
                channel_code=channel_code,
                title=title,
                content=markdown,
                status=LOG_STATUS_SUCCESS,
                payload={**base_payload, "response": response},
                scheduled_task_id=task_id,
                scheduled_task_name=task_name,
                task_execution_log_id=execution_log_id,
            )
            sent += 1
            results.append(
                {
                    "receiver_id": getattr(receiver, "id", None),
                    "receiver_name": getattr(receiver, "name", ""),
                    "channel_code": channel_code,
                    "status": LOG_STATUS_SUCCESS,
                    "log_id": log.id,
                }
            )
        except Exception as exc:  # noqa: BLE001 - one channel must never break others
            logger.exception(
                "notifications: send failed receiver=%s channel=%s: %s",
                getattr(receiver, "id", None),
                channel_code,
                exc,
            )
            log = _write_log(
                project=receiver_project,
                receiver=receiver,
                channel_code=channel_code,
                title=title,
                content=markdown,
                status=LOG_STATUS_FAILED,
                error_message=str(exc),
                payload=base_payload,
                scheduled_task_id=task_id,
                scheduled_task_name=task_name,
                task_execution_log_id=execution_log_id,
            )
            failed += 1
            results.append(
                {
                    "receiver_id": getattr(receiver, "id", None),
                    "receiver_name": getattr(receiver, "name", ""),
                    "channel_code": channel_code,
                    "status": LOG_STATUS_FAILED,
                    "error": str(exc),
                    "log_id": log.id,
                }
            )

    logger.info(
        "notifications: task %s sent=%s failed=%s", task_id, sent, failed
    )
    return {
        "skipped": False,
        "sent": sent,
        "failed": failed,
        "results": results,
        "title": title,
        "markdown": markdown,
    }


def send_test_notification(
    receiver=None,
    channel_code=None,
    webhook_url="",
    target_address="",
    project=None,
    title="通知测试",
    content=None,
):
    """Send a one-off test message and always write a NotificationLog."""
    title = title or "通知测试"
    if receiver is not None:
        if not channel_code:
            channel_code = getattr(receiver, "channel_code", "")
        webhook_url = webhook_url or getattr(receiver, "webhook_url", "")
        target_address = target_address or getattr(receiver, "target_address", "")
        project = project or getattr(receiver, "project", None)
    channel_code = (channel_code or "").strip()
    if not channel_code:
        raise BusinessError(message="缺少 channel_code", code="missing_channel")
    if channel_code not in CHANNEL_CODES:
        raise BusinessError(
            message=f"不支持的通知渠道: {channel_code}", code="unsupported_channel"
        )

    markdown = content or build_markdown(
        task_name="通知测试",
        total=0,
        passed=0,
        failed=0,
        skipped=0,
        pass_rate=0,
        status="",
        started_at=timezone.now(),
        title=title,
    )
    payload = {
        "test": True,
        "channel_code": channel_code,
        "webhook_url": webhook_url or "",
        "target_address": target_address or "",
        "project_id": getattr(project, "id", None) if project is not None else None,
    }
    try:
        response = _send_by_channel(
            channel_code,
            webhook_url,
            target_address,
            title,
            markdown,
            project=project,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifications: test send failed channel=%s: %s", channel_code, exc)
        log = _write_log(
            project=project,
            receiver=receiver,
            channel_code=channel_code,
            title=title,
            content=markdown,
            status=LOG_STATUS_FAILED,
            error_message=str(exc),
            payload=payload,
        )
        if isinstance(exc, BusinessError):
            raise
        raise BusinessError(
            message=f"通知发送失败: {exc}", code="notification_test_failed"
        ) from exc

    log = _write_log(
        project=project,
        receiver=receiver,
        channel_code=channel_code,
        title=title,
        content=markdown,
        status=LOG_STATUS_SUCCESS,
        payload={**payload, "response": response},
    )
    return {
        "sent": 1,
        "failed": 0,
        "results": [
            {
                "receiver_id": getattr(receiver, "id", None),
                "channel_code": channel_code,
                "status": LOG_STATUS_SUCCESS,
                "log_id": log.id,
            }
        ],
    }
