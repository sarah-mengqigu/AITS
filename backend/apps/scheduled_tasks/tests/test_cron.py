"""Cron helper tests (validation / next runs / Chinese description / preview)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.scheduled_tasks.services import cron


class CronValidationTests(SimpleTestCase):
    def test_validate_cron_normalises_whitespace(self):
        self.assertEqual(cron.validate_cron("  0   3 *  * * "), "0 3 * * *")

    def test_validate_cron_rejects_bad_expressions(self):
        for bad in ("", "   ", "0 3 * *", "0 0 3 * * *", "bad cron", "*/0 * * * *"):
            with self.assertRaises(cron.CronError):
                cron.validate_cron(bad)

    def test_resolve_timezone(self):
        self.assertEqual(str(cron.resolve_timezone("Asia/Shanghai")), "Asia/Shanghai")
        self.assertEqual(str(cron.resolve_timezone(None)), "Asia/Shanghai")
        with self.assertRaises(cron.CronError):
            cron.resolve_timezone("Mars/Olympus")


class CronDescriptionTests(SimpleTestCase):
    def test_describe_daily(self):
        self.assertEqual(cron.describe_cron("0 3 * * *"), "每天 03:00 执行")
        self.assertEqual(cron.describe_cron("30 8,20 * * *"), "每天 08:30、20:30 执行")

    def test_describe_interval_and_hourly(self):
        self.assertEqual(cron.describe_cron("*/15 * * * *"), "每 15 分钟执行")
        self.assertEqual(cron.describe_cron("0 * * * *"), "每小时第 0 分钟执行")
        self.assertEqual(cron.describe_cron("* * * * *"), "每分钟执行")

    def test_describe_weekly_and_monthly(self):
        self.assertIn("周一", cron.describe_cron("0 9 * * 1"))
        self.assertIn("周一", cron.describe_cron("0 9 * * 1-5"))
        self.assertIn("周六", cron.describe_cron("0 9 * * 6"))
        self.assertIn("每月", cron.describe_cron("0 0 1 * *"))
        self.assertIn("每年", cron.describe_cron("0 0 1 3 *"))


class CronNextRunTests(SimpleTestCase):
    def test_next_runs_returns_five_aware_datetimes(self):
        base = datetime(2024, 1, 1, 10, 7, tzinfo=ZoneInfo("Asia/Shanghai"))
        runs = cron.next_runs("0 3 * * *", count=5, base=base)
        self.assertEqual(len(runs), 5)
        self.assertEqual([run.day for run in runs], [2, 3, 4, 5, 6])
        self.assertTrue(all(run.hour == 3 and run.minute == 0 for run in runs))
        self.assertTrue(all(run.tzinfo is not None for run in runs))

    def test_next_run_single(self):
        base = datetime(2024, 1, 1, 10, 7, tzinfo=ZoneInfo("Asia/Shanghai"))
        nxt = cron.next_run("*/15 * * * *", base=base)
        self.assertEqual((nxt.hour, nxt.minute), (10, 15))


class CronPreviewTests(SimpleTestCase):
    def test_preview_payload_is_valid(self):
        payload = cron.preview("0 3 * * *")
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["description"], "每天 03:00 执行")
        self.assertEqual(len(payload["next_runs"]), 5)
        self.assertIn("03:00:00", payload["next_runs"][0])
        self.assertEqual(payload["message"], "")

    def test_preview_handles_invalid_and_missing_expression(self):
        invalid = cron.preview("not-a-cron")
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["next_runs"], [])
        self.assertTrue(invalid["message"])

        missing = cron.preview("")
        self.assertFalse(missing["valid"])
        self.assertIn("expr", missing["message"])

    def test_preview_respects_count_and_timezone(self):
        payload = cron.preview("0 0 * * *", count=3, timezone_name="UTC")
        self.assertTrue(payload["valid"])
        self.assertEqual(len(payload["next_runs"]), 3)
        self.assertEqual(payload["timezone"], "UTC")
