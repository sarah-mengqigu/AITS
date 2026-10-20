"""Cron helpers: validation, next-run computation, Chinese description.

Everything here is dependency-free apart from ``croniter`` (already pinned by
the backend) — **no** network access and **no** external description library
(``cronstrue`` & friends).  The Chinese description is produced by the small
deterministic mapper further down so it always works offline.

Public API
----------
``validate_cron(expression) -> str``        normalise / raise :class:`CronError`
``resolve_timezone(name) -> ZoneInfo``      validate a tz name
``next_runs(expression, count=5, ...)``     list[datetime] (tz aware)
``next_run(expression, ...)``               single datetime | None
``describe_cron(expression) -> str``        e.g. ``每天 03:00 执行``
``preview(expression, count=5, ...)``       payload for ``/cron/preview/``
``get_crontab_schedule(expression, tz)``    persisted ``django_celery_beat`` row
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from django.utils import timezone as dj_timezone

DEFAULT_TIMEZONE = "Asia/Shanghai"
CRON_FIELD_COUNT = 5

#: ``(minute, hour, day_of_month, month_of_year, day_of_week)``
CRON_FIELDS = ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")

_WEEKDAY_LABELS = ("周日", "周一", "周二", "周三", "周四", "周五", "周六", "周日")

_MAX_PREVIEW_RUNS = 20


class CronError(ValueError):
    """Raised when a cron expression / timezone cannot be used."""


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def split_cron(expression) -> tuple[str, str, str, str, str]:
    """Split and sanity check a 5 field cron expression."""
    text = str(expression or "").strip()
    if not text:
        raise CronError("cron 表达式不能为空")
    parts = text.split()
    if len(parts) != CRON_FIELD_COUNT:
        raise CronError(
            f"cron 表达式必须包含 {CRON_FIELD_COUNT} 个字段（分 时 日 月 周），"
            f"当前为 {len(parts)} 个"
        )
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def validate_cron(expression) -> str:
    """Validate ``expression`` and return its normalised (single space) form."""
    parts = split_cron(expression)
    normalised = " ".join(parts)
    try:
        croniter(normalised)
    except Exception as exc:  # CroniterBadCronError / ZeroDivisionError / ...
        raise CronError(f"无效的 cron 表达式: {normalised}") from exc
    return normalised


def resolve_timezone(name=None):
    """Return a :class:`zoneinfo.ZoneInfo` for ``name`` (default Asia/Shanghai)."""
    zone = str(name or "").strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CronError(f"无效的时区: {zone}") from exc


# ---------------------------------------------------------------------------
# next runs
# ---------------------------------------------------------------------------
def next_runs(expression, count: int = 5, base=None, timezone_name=None) -> list[datetime]:
    """Return the next ``count`` fire times of ``expression`` (tz aware)."""
    normalised = validate_cron(expression)
    tz = resolve_timezone(timezone_name)
    try:
        total = max(int(count), 0)
    except (TypeError, ValueError):
        total = 5
    total = min(total, _MAX_PREVIEW_RUNS)

    base_dt = base or dj_timezone.now()
    if dj_timezone.is_naive(base_dt):
        base_dt = dj_timezone.make_aware(base_dt, tz)
    local_base = base_dt.astimezone(tz)

    iterator = croniter(normalised, local_base)
    runs: list[datetime] = []
    for _ in range(total):
        value = iterator.get_next(datetime)
        if dj_timezone.is_naive(value):
            value = dj_timezone.make_aware(value, tz)
        runs.append(value.astimezone(tz))
    return runs


def next_run(expression, timezone_name=None, base=None):
    """Return the next fire time of ``expression`` or ``None``."""
    runs = next_runs(expression, count=1, base=base, timezone_name=timezone_name)
    return runs[0] if runs else None


def format_run(value: datetime) -> str:
    """Render a run time the same way DRF renders datetimes."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# tiny deterministic crontab parser (used for the human description)
# ---------------------------------------------------------------------------
def _expand_numbers(text, minimum: int, maximum: int):
    """Expand ``*`` / ``a`` / ``a-b`` / ``a,b`` into ints (``None`` if exotic)."""
    text = str(text).strip()
    if text == "*":
        return list(range(minimum, maximum + 1))
    if "/" in text:
        return None
    values: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, _, high = part.partition("-")
            try:
                low_i, high_i = int(low), int(high)
            except (TypeError, ValueError):
                return None
            if high_i < low_i:
                return None
            values.extend(range(low_i, high_i + 1))
        else:
            try:
                values.append(int(part))
            except (TypeError, ValueError):
                return None
    return values or None


def _step_value(text):
    """Return ``n`` for ``*/n`` style fields (``None`` otherwise)."""
    text = str(text).strip()
    if not text.startswith("*/"):
        return None
    try:
        return int(text[2:])
    except (TypeError, ValueError):
        return None


def _weekday_text(field) -> str:
    values = _expand_numbers(field, 0, 7)
    if values is None:
        return f"第 {field} 天"
    labels: list[str] = []
    for value in values:
        label = _WEEKDAY_LABELS[value % 7]
        if label not in labels:
            labels.append(label)
    if len(labels) == 7:
        return "每天"
    return "、".join(labels)


def _month_text(field) -> str:
    values = _expand_numbers(field, 1, 12)
    if values is None:
        return f"{field} 月"
    return "、".join(f"{value} 月" for value in values)


def _day_of_month_text(field) -> str:
    values = _expand_numbers(field, 1, 31)
    if values is None:
        return f"{field} 日"
    return "、".join(str(value) for value in values) + " 日"


def _describe_time(minute: str, hour: str) -> str:
    if hour == "*":
        if minute == "*":
            return "每分钟"
        step = _step_value(minute)
        if step:
            return f"每 {step} 分钟"
        return f"每小时第 {str(minute).replace(',', '、')} 分钟"

    step_hour = _step_value(hour)
    if step_hour:
        if minute == "*":
            return f"每 {step_hour} 小时每分钟"
        return f"每 {step_hour} 小时的第 {minute} 分钟"

    hours = _expand_numbers(hour, 0, 23)
    minutes = _expand_numbers(minute, 0, 59)
    if hours is None or minutes is None:
        return f"{hour} 时 {minute} 分"

    times = [f"{h:02d}:{m:02d}" for h in hours for m in minutes]
    if len(times) > 8:
        times = times[:8] + ["…"]
    return "、".join(times)


def _describe_date(day_of_month: str, month: str, day_of_week: str) -> str:
    if (
        day_of_week != "*"
        and day_of_month == "*"
        and month == "*"
    ):
        return "每" + _weekday_text(day_of_week)
    if day_of_week == "*" and day_of_month != "*" and month == "*":
        return f"每月 {_day_of_month_text(day_of_month)}"
    if day_of_week == "*" and day_of_month == "*" and month != "*":
        return f"每年 {_month_text(month)}"
    simple = True
    pieces: list[str] = []
    if month != "*":
        pieces.append(f"每年 {_month_text(month)}")
        simple = False
    if day_of_month != "*":
        pieces.append(f"{_day_of_month_text(day_of_month)}")
        simple = False
    if day_of_week != "*":
        pieces.append(f"每{_weekday_text(day_of_week)}")
        simple = False
    if simple:
        return "每天"
    return " ".join(pieces)


def describe_cron(expression) -> str:
    """Return a short Chinese description such as ``每天 03:00 执行``."""
    minute, hour, day_of_month, month, day_of_week = split_cron(expression)
    validate_cron(expression)

    time_text = _describe_time(minute, hour)
    date_text = _describe_date(day_of_month, month, day_of_week)

    if date_text == "每天" and hour == "*":
        return f"{time_text}执行"
    if date_text == "每天":
        return f"每天 {time_text} 执行"
    return f"{date_text} {time_text} 执行"


# ---------------------------------------------------------------------------
# preview payload (``/api/scheduled-tasks/cron/preview/``)
# ---------------------------------------------------------------------------
def preview(expression, count: int = 5, timezone_name=None) -> dict:
    """Build the ``{"valid", "description", "next_runs"}`` preview payload."""
    raw = str(expression or "").strip()
    tz_name = str(timezone_name or "").strip() or DEFAULT_TIMEZONE
    if not raw:
        return {
            "valid": False,
            "expression": "",
            "description": "",
            "next_runs": [],
            "timezone": tz_name,
            "message": "缺少 expr 参数",
        }
    try:
        normalised = validate_cron(raw)
        runs = next_runs(normalised, count=count, timezone_name=tz_name)
        return {
            "valid": True,
            "expression": normalised,
            "description": describe_cron(normalised),
            "next_runs": [format_run(run) for run in runs],
            "timezone": tz_name,
            "message": "",
        }
    except CronError as exc:
        return {
            "valid": False,
            "expression": raw,
            "description": "",
            "next_runs": [],
            "timezone": tz_name,
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# django-celery-beat integration
# ---------------------------------------------------------------------------
def crontab_spec(expression, timezone_name=None) -> dict:
    """Field values accepted by ``django_celery_beat.CrontabSchedule``."""
    minute, hour, day_of_month, month_of_year, day_of_week = split_cron(expression)
    validate_cron(expression)
    return {
        "minute": minute,
        "hour": hour,
        "day_of_month": day_of_month,
        "month_of_year": month_of_year,
        "day_of_week": day_of_week,
        "timezone": resolve_timezone(timezone_name),
    }


def get_crontab_schedule(expression, timezone_name=None):
    """Return a persisted ``CrontabSchedule`` for ``expression`` (idempotent).

    ``django-celery-beat >= 2.6`` exposes ``CrontabSchedule.from_crontab``; the
    backend pins 2.5.0 which does not, so when the helper is available we honour
    it and otherwise build the very same field values ourselves.  Either way we
    persist through ``get_or_create`` so repeated syncs never duplicate rows.
    """
    from django_celery_beat.models import CrontabSchedule

    spec = crontab_spec(expression, timezone_name)
    from_crontab = getattr(CrontabSchedule, "from_crontab", None)
    if callable(from_crontab):
        try:
            built = from_crontab(
                " ".join(spec[field] for field in (
                    "minute", "hour", "day_of_month", "month_of_year", "day_of_week"
                )),
                timezone=spec["timezone"],
            )
            for field in CRON_FIELDS:
                spec[field] = getattr(built, field)
        except Exception:  # pragma: no cover - only for future beat versions
            pass

    try:
        return CrontabSchedule.objects.get(**spec)
    except CrontabSchedule.DoesNotExist:
        return CrontabSchedule.objects.create(**spec)
    except CrontabSchedule.MultipleObjectsReturned:  # pragma: no cover - defensive
        return CrontabSchedule.objects.filter(**spec).first()
