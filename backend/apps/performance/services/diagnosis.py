"""AI / rules based diagnosis for performance anomalies (``ARCHITECTURE`` §2.6).

Entry points
------------
``diagnose_execution(execution, alert=None, project=None) -> AiDiagnosisRecord``
    Build a diagnosis for an execution (optionally linked to a Grafana alert),
    persist it and push a notification through ``apps.notifications``.

``handle_grafana_webhook(payload) -> dict``
    Parse a Grafana alerting webhook payload, create ``AiDiagnosisRecord`` rows
    with ``source="grafana"`` and diagnose them. Invalid payloads raise
    :class:`BusinessError`.

The LLM is imported lazily from ``apps.ai_core``; any import/call problem (or
mock mode, which carries no real analysis) degrades to a deterministic Chinese
rules diagnosis so the endpoint never fails because of AI availability.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.common.api.api_exception_handler import BusinessError

from ..constants import (
    ERROR_RATE_SEVERE,
    ERROR_RATE_WARNING,
    MIN_AVG_TPS_THRESHOLD,
    NOTIFY_TARGET_CACHE_KEY,
    P95_RESPONSE_TIME_THRESHOLD_MS,
    P99_RESPONSE_TIME_THRESHOLD_MS,
)
from ..models import AiDiagnosisRecord, PerformanceExecution

logger = logging.getLogger(__name__)

MAX_WEBHOOK_ALERTS = 10
NOTIFY_CACHE_TTL = 3600

STATUS_LABELS = {
    "pending": "等待中",
    "running": "执行中",
    "passed": "通过",
    "failed": "未通过",
    "error": "异常",
    "cancelled": "已取消",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _as_int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _text(value, limit=2000) -> str:
    return str(value or "")[:limit]


def _status_code_summary(dist) -> str:
    if not isinstance(dist, dict) or not dist:
        return "无状态码数据"
    return "，".join(f"{code}: {count}" for code, count in sorted(
        dist.items(), key=lambda item: str(item[0])
    ))


def _execution_stats_text(execution: PerformanceExecution) -> str:
    lines = [
        f"- 执行 ID：{execution.id}（{execution.name}）",
        f"- 执行状态：{STATUS_LABELS.get(execution.status, execution.status)}",
        f"- 总请求数：{execution.total_requests}",
        f"- 平均 TPS：{execution.avg_tps}",
        f"- 响应时间：P50 {execution.p50_response_time}ms / "
        f"P95 {execution.p95_response_time}ms / P99 {execution.p99_response_time}ms",
        f"- 错误率：{float(execution.error_rate or 0.0):.2%}",
        f"- 状态码分布：{_status_code_summary(execution.status_code_dist)}",
    ]
    if execution.error_message:
        lines.append(f"- 执行错误信息：{_text(execution.error_message, 500)}")
    return "\n".join(lines)


def build_diagnosis_prompt(execution, alert=None) -> str:
    """Prompt handed to the LLM (also useful for debugging / tests)."""
    parts = [
        "你是 AITS 性能测试平台的 SRE 诊断助手。",
        "请基于下面的压测执行数据与告警信息，输出中文诊断结论：",
        "1) 一句话结论；2) 可能根因（按可能性排序）；3) 可执行的优化/排查建议。",
        "要求简洁，不超过 400 字，不要输出 JSON。",
        "",
    ]
    if execution is not None:
        parts.append("## 压测执行数据")
        parts.append(_execution_stats_text(execution))
        parts.append("")
    if alert:
        parts.append("## 告警信息")
        parts.append(alert_to_text(alert))
        parts.append("")
    parts.append("## 诊断结论")
    return "\n".join(parts)


def alert_to_text(alert: dict) -> str:
    """Flatten a Grafana alert (or manual dict) into readable lines."""
    if not isinstance(alert, dict):
        return str(alert)
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = (
        alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    )
    lines = []
    name = labels.get("alertname") or alert.get("alert_name") or alert.get("title") or ""
    severity = labels.get("severity") or alert.get("severity") or ""
    status = alert.get("status") or ""
    if name:
        lines.append(f"- 告警名称：{name}")
    if severity:
        lines.append(f"- 告警级别：{severity}")
    if status:
        lines.append(f"- 告警状态：{status}")
    summary = annotations.get("summary") or alert.get("summary") or ""
    description = annotations.get("description") or alert.get("description") or ""
    if summary:
        lines.append(f"- 告警摘要：{summary}")
    if description:
        lines.append(f"- 告警详情：{description}")
    if labels:
        extra = {k: v for k, v in labels.items() if k not in ("alertname", "severity")}
        if extra:
            lines.append(f"- 标签：{json.dumps(extra, ensure_ascii=False, default=str)}")
    return "\n".join(lines) or "- 无结构化告警信息"


# ---------------------------------------------------------------------------
# LLM (lazy, always degradable)
# ---------------------------------------------------------------------------
def _llm_diagnosis(project, prompt: str) -> str | None:
    """Call ai_core's LLM; return ``None`` when unavailable / mock / failing."""
    try:
        from apps.ai_core.services.llm_service import LLMService
    except Exception as exc:  # noqa: BLE001 - ai_core may be absent
        logger.warning("ai_core LLMService 不可用，使用规则诊断: %s", exc)
        return None
    try:
        service = LLMService(project=project)
        if getattr(service, "is_mock", True):
            logger.info("LLM 处于 mock 模式，降级为规则诊断以保证结论可读")
            return None
        result = service.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
        )
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            logger.warning("LLM 返回空内容，降级为规则诊断")
            return None
        return text
    except Exception as exc:  # noqa: BLE001 - diagnosis must never explode
        logger.warning("LLM 诊断失败，降级为规则诊断: %s", exc)
        return None


# ---------------------------------------------------------------------------
# rules based diagnosis (deterministic fallback)
# ---------------------------------------------------------------------------
def rule_diagnosis(execution, alert=None) -> str:
    """Deterministic Chinese diagnosis derived from the stored metrics."""
    lines = ["## 诊断结论（规则引擎）"]
    if execution is None:
        lines.append(
            "未关联到具体的性能执行记录，以下为告警本身的排查建议："
        )
        if alert:
            lines.append(alert_to_text(alert))
        lines.extend(
            [
                "",
                "## 排查建议",
                "1. 在 Grafana 中打开对应告警面板，确认异常时间窗口与影响范围；",
                "2. 检查压测机、被测服务与 Prometheus/Windows Exporter 的采集是否正常；",
                "3. 若为延迟或错误率告警，优先核对最近一次性能执行的 P95 与错误率趋势；",
                "4. 如为容量问题，建议降低并发用户数后重新执行压测以定位拐点。",
            ]
        )
        return "\n".join(lines)

    error_rate = float(execution.error_rate or 0.0)
    p95 = int(execution.p95_response_time or 0)
    p99 = int(execution.p99_response_time or 0)
    avg_tps = float(execution.avg_tps or 0.0)
    total = int(execution.total_requests or 0)
    dist = execution.status_code_dist if isinstance(execution.status_code_dist, dict) else {}

    lines.append(
        f"本次执行「{execution.name}」状态为 {STATUS_LABELS.get(execution.status, execution.status)}，"
        f"共 {total} 个请求，平均 TPS {avg_tps}，错误率 {error_rate:.2%}，"
        f"P50/P95/P99 分别为 {execution.p50_response_time}ms/{p95}ms/{p99}ms。"
    )

    findings: list[str] = []
    suggestions: list[str] = []

    if total <= 0:
        findings.append("本次执行没有采集到有效请求数据，无法计算性能指标。")
        suggestions.append("检查目标 Host 是否可达、locustfile 是否含有 @task 方法，再重新执行压测。")
    if error_rate > ERROR_RATE_SEVERE:
        findings.append(f"错误率高达 {error_rate:.2%}，超过严重阈值 {ERROR_RATE_SEVERE:.0%}，服务基本不可用。")
        suggestions.append("优先回滚最近变更并检查服务端异常日志，确认依赖（数据库/缓存/下游接口）是否健康。")
    elif error_rate > ERROR_RATE_WARNING:
        findings.append(f"错误率 {error_rate:.2%} 高于关注阈值 {ERROR_RATE_WARNING:.0%}，属于明显异常。")
        suggestions.append("排查失败请求对应的接口与状态码，定位是参数、鉴权还是服务端容量问题。")
    elif error_rate > 0.01:
        findings.append(f"错误率 {error_rate:.2%} 略高于通过阈值 1%，存在零星失败。")
        suggestions.append("抽样查看失败请求，确认是否为超时、限流或偶发网络抖动。")

    if p95 > P95_RESPONSE_TIME_THRESHOLD_MS:
        findings.append(f"P95 为 {p95}ms，高于 {P95_RESPONSE_TIME_THRESHOLD_MS}ms 阈值，长尾延迟明显。")
        suggestions.append("定位慢接口（P95 最高的 @task），检查数据库慢查询、锁竞争与线程池配置。")
    if p99 > P99_RESPONSE_TIME_THRESHOLD_MS:
        findings.append(f"P99 达到 {p99}ms，极端请求耗时过长，存在超时风险。")
        suggestions.append("为该链路补充超时与熔断策略，并检查是否有同步阻塞或大对象序列化。")

    server_errors = sum(
        count for code, count in dist.items() if str(code).startswith(("5", "4"))
    )
    if server_errors:
        detail = "，".join(
            f"{code}×{count}"
            for code, count in sorted(dist.items(), key=lambda item: str(item[0]))
            if str(code).startswith(("5", "4"))
        )
        findings.append(f"异常状态码分布：{detail}。")
        if any(str(code).startswith("5") for code in dist):
            suggestions.append("5xx 占比偏高时检查应用错误日志、GC 与连接池，必要时临时扩容。")
        if any(str(code).startswith("429") for code in dist):
            suggestions.append("出现 429 说明触发了限流，需与网关/服务端确认限流阈值与压测模型。")
        if any(str(code).startswith(("401", "403")) for code in dist):
            suggestions.append("出现 401/403 需检查 token 过期时间与鉴权头，或降低压测时长。")
        if any(str(code).startswith("404") for code in dist):
            suggestions.append("出现 404 需核对 locustfile 中的路径与 Host 前缀是否正确。")
    if total and avg_tps < MIN_AVG_TPS_THRESHOLD:
        findings.append(f"平均 TPS 仅 {avg_tps}，低于预期吞吐，压测模型或目标服务可能存在瓶颈。")
        suggestions.append("确认压测机资源（CPU/内存/网络）与并发用户数，逐步提升并发寻找吞吐拐点。")

    if not findings:
        findings.append("各项指标均在阈值内，本次压测结果健康，暂无异常。")
    if not suggestions:
        suggestions.append("保持当前配置，可将本次结果作为基线，在发布前后做对比压测。")

    lines.append("")
    lines.append("## 关键发现")
    lines.extend(f"- {item}" for item in findings)
    lines.append("")
    lines.append("## 优化建议")
    lines.extend(f"{index}. {item}" for index, item in enumerate(suggestions, start=1))
    if execution.error_message:
        lines.append("")
        lines.append(f"## 执行错误\n{_text(execution.error_message, 800)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# notification dispatch (lazy import, never raises)
# ---------------------------------------------------------------------------
def resolve_notify_receiver():
    """Resolve the configured Grafana AI receiver (settings -> cache -> keyword)."""
    try:
        from apps.notifications.models import NotificationReceiver
    except Exception as exc:  # noqa: BLE001 - notifications may be absent
        logger.warning("notifications 模块不可用，跳过 AI 诊断通知: %s", exc)
        return None

    receiver_id = _as_int(getattr(settings, "GRAFANA_AI_NOTIFY_RECEIVER_ID", ""), None)
    if receiver_id is not None:
        receiver = NotificationReceiver.objects.filter(pk=receiver_id).first()
        if receiver is not None:
            cache.set(NOTIFY_TARGET_CACHE_KEY, receiver.pk, NOTIFY_CACHE_TTL)
            return receiver

    cached_id = _as_int(cache.get(NOTIFY_TARGET_CACHE_KEY), None)
    if cached_id is not None:
        receiver = NotificationReceiver.objects.filter(pk=cached_id).first()
        if receiver is not None:
            return receiver
        cache.delete(NOTIFY_TARGET_CACHE_KEY)

    keyword = str(getattr(settings, "GRAFANA_AI_NOTIFY_RECEIVER_NAME_KEYWORD", "") or "").strip()
    if not keyword:
        return None
    receiver = (
        NotificationReceiver.objects.filter(is_active=True, name__icontains=keyword)
        .order_by("id")
        .first()
    )
    if receiver is not None:
        cache.set(NOTIFY_TARGET_CACHE_KEY, receiver.pk, NOTIFY_CACHE_TTL)
        logger.info("AI 诊断通知接收人已缓存: %s (%s)", receiver.pk, receiver.name)
    return receiver


def _notify(record: AiDiagnosisRecord, execution=None) -> bool:
    receiver = resolve_notify_receiver()
    if receiver is None:
        logger.info("未配置 AI 诊断通知接收人，跳过通知")
        return False
    try:
        from apps.notifications.services import trigger_notification
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifications.trigger_notification 不可用: %s", exc)
        return False

    total = int(getattr(execution, "total_requests", 0) or 0)
    error_rate = float(getattr(execution, "error_rate", 0.0) or 0.0)
    failed = int(round(total * error_rate)) if total else 0
    task_name = f"性能测试 AI 诊断 - {record.alert_name or '执行异常'}"
    pseudo_task = {
        "id": None,
        "name": task_name,
        "project": record.project,
        "trigger_condition": "always",
        "notice_targets": [receiver],
    }
    execution_log = {
        "id": None,
        "scheduled_task_name": task_name,
        "status": "failed" if (failed or error_rate > 0.01) else "passed",
        "total": total,
        "passed": max(total - failed, 0),
        "failed": failed,
        "skipped": 0,
        "pass_rate": round((max(total - failed, 0) / total * 100) if total else 0.0, 2),
        "project": record.project,
        "report_url": getattr(execution, "report_path", "") if execution else "",
    }
    result = {
        "title": "AITS 性能测试 AI 诊断",
        "status": execution_log["status"],
        "summary": {
            "total": total,
            "error_rate": error_rate,
            "p95_response_time": getattr(execution, "p95_response_time", 0),
        },
        "report_url": execution_log["report_url"],
        "project": record.project,
    }
    try:
        trigger_notification(pseudo_task, execution_log, result)
        return True
    except Exception as exc:  # noqa: BLE001 - auxiliary channel
        logger.warning("AI 诊断通知发送失败: %s", exc)
        return False


# ---------------------------------------------------------------------------
# record building
# ---------------------------------------------------------------------------
def _diagnose_record(record: AiDiagnosisRecord, execution, alert) -> AiDiagnosisRecord:
    prompt = build_diagnosis_prompt(execution, alert)
    content = _llm_diagnosis(record.project, prompt)
    if not content:
        content = rule_diagnosis(execution, alert)
    record.diagnosis_content = content
    record.save(update_fields=["diagnosis_content", "updated_at"])
    if _notify(record, execution):
        record.notified_at = timezone.now()
        record.save(update_fields=["notified_at", "updated_at"])
    return record


def diagnose_execution(execution, alert=None, project=None) -> AiDiagnosisRecord:
    """Diagnose ``execution`` (optionally tied to a Grafana ``alert``) and persist."""
    alert = alert if isinstance(alert, dict) else {}
    if project is None and execution is not None:
        project = getattr(execution, "project", None)
    if project is None and alert:
        project = _project_from_alert(alert)

    source = str(alert.get("source") or "").strip()
    if source not in ("grafana", "manual"):
        source = "grafana" if alert.get("labels") else "manual"
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = (
        alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    )
    alert_name = str(
        labels.get("alertname")
        or alert.get("alert_name")
        or alert.get("title")
        or annotations.get("summary")
        or ""
    )[:255]
    severity = str(labels.get("severity") or alert.get("severity") or "")[:32]
    grafana_url = str(
        alert.get("grafana_url")
        or alert.get("generatorURL")
        or annotations.get("dashboardURL")
        or ""
    )[:500]

    record = AiDiagnosisRecord.objects.create(
        project=project,
        execution=execution if isinstance(execution, PerformanceExecution) else None,
        source=source,
        alert_name=alert_name,
        severity=severity,
        grafana_url=grafana_url,
        status="pending",
        raw_payload=alert or {
            "execution_id": getattr(execution, "id", None),
            "source": "manual",
        },
    )
    return _diagnose_record(record, execution, alert)


# ---------------------------------------------------------------------------
# Grafana webhook
# ---------------------------------------------------------------------------
def _project_from_alert(alert: dict):
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = (
        alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    )
    raw = (
        labels.get("project_id")
        or labels.get("project")
        or annotations.get("project_id")
        or alert.get("project_id")
        or alert.get("project")
    )
    project_id = _as_int(raw, None)
    if project_id is None:
        return None
    from apps.projects.models import Project

    return Project.objects.filter(pk=project_id).first()


def _execution_from_alert(alert: dict):
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = (
        alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    )
    raw = (
        labels.get("execution_id")
        or labels.get("aits_execution_id")
        or annotations.get("execution_id")
        or alert.get("execution_id")
    )
    execution_id = _as_int(raw, None)
    if execution_id is None:
        return None
    return PerformanceExecution.objects.filter(pk=execution_id).first()


def handle_grafana_webhook(payload) -> dict:
    """Process a Grafana alerting webhook payload.

    :returns: ``{"record_id", "status", "count", "record_ids"}``. ``record_id``
        is ``None`` when no project could be resolved for unlinked alerts.
    :raises BusinessError: when the payload is not a Grafana alerting body.
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BusinessError(
                message="Grafana 告警载荷不是合法 JSON", code="invalid_payload"
            ) from exc
    if not isinstance(payload, dict):
        raise BusinessError(message="Grafana 告警载荷格式错误", code="invalid_payload")
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        raise BusinessError(
            message="Grafana 告警载荷缺少 alerts 数组", code="invalid_payload"
        )

    records = []
    for raw_alert in alerts[:MAX_WEBHOOK_ALERTS]:
        if not isinstance(raw_alert, dict):
            continue
        alert = dict(raw_alert)
        alert.setdefault("status", payload.get("status") or "firing")
        alert.setdefault("title", payload.get("title") or "")
        alert.setdefault("externalURL", payload.get("externalURL") or "")
        alert["source"] = "grafana"
        execution = _execution_from_alert(alert)
        project = getattr(execution, "project", None) or _project_from_alert(alert)
        if project is None:
            # The alert is still recorded (project is nullable) so nothing is
            # lost when Grafana has no AITS project label configured.
            logger.warning(
                "Grafana 告警未关联项目，按无项目记录落库: %s",
                (alert.get("labels") or {}).get("alertname"),
            )
        record = diagnose_execution(execution, alert=alert, project=project)
        if str(alert.get("status") or "").lower() == "resolved":
            record.status = "resolved"
            record.resolved_at = timezone.now()
            record.save(update_fields=["status", "resolved_at", "updated_at"])
        records.append(record)

    if not records:
        return {
            "record_id": None,
            "record_ids": [],
            "status": "skipped",
            "count": 0,
            "message": "告警已接收但未包含可解析的 alerts 元素，未创建诊断记录",
        }
    return {
        "record_id": records[0].id,
        "record_ids": [record.id for record in records],
        "status": "processed",
        "count": len(records),
    }
