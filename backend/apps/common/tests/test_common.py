from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.parsers.yaml_json import (
    extract_first_object,
    normalize_scalar,
    parse_any,
    parse_json,
    strip_code_fence,
)
from apps.common.permissions import get_user_role, role_at_least
from apps.common.storage.file_storage import save_bytes, sha256_of_bytes
from apps.projects.models import Project, ProjectMember

User = get_user_model()


class ParserTests(TestCase):
    def test_strip_code_fence(self):
        text = 'here you go\n```json\n{"a": 1}\n```\ndone'
        self.assertEqual(strip_code_fence(text), '{"a": 1}')

    def test_parse_json_with_fence(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_parse_any_yaml(self):
        self.assertEqual(parse_any("a: 1\nb:\n  - x"), {"a": 1, "b": ["x"]})

    def test_parse_json_invalid_raises_business_error(self):
        with self.assertRaises(Exception) as ctx:
            parse_json("{invalid")
        self.assertEqual(getattr(ctx.exception, "biz_code", ""), "invalid_json")

    def test_extract_first_object_from_prose(self):
        text = 'sure! {"tool": "click", "target": "login"} hope it helps'
        self.assertEqual(extract_first_object(text), {"tool": "click", "target": "login"})

    def test_normalize_scalar(self):
        self.assertIs(normalize_scalar("true"), True)
        self.assertEqual(normalize_scalar("42"), 42)
        self.assertIsNone(normalize_scalar("null"))


class StorageTests(TestCase):
    def test_save_bytes_dedupes(self):
        path1, sha1, size1 = save_bytes(b"hello", "a.txt", subdir="test")
        path2, sha2, size2 = save_bytes(b"hello", "b.txt", subdir="test")
        self.assertEqual(path1, path2)
        self.assertEqual(sha1, sha2)
        self.assertEqual(size1, 5)
        self.assertEqual(sha1, sha256_of_bytes(b"hello"))


class PermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("o", "o@x.com", "Passw0rd!")
        self.viewer = User.objects.create_user("v", "v@x.com", "Passw0rd!")
        self.project = Project.objects.create(name="p", project_type="api", owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.viewer, role="viewer")

    def test_role_lookup(self):
        self.assertEqual(get_user_role(self.owner, self.project), "owner")
        self.assertEqual(get_user_role(self.viewer, self.project), "viewer")
        self.assertIsNone(get_user_role(User.objects.create_user("x", "x@x.com", "Passw0rd!"),
                                       self.project))

    def test_role_ordering(self):
        self.assertTrue(role_at_least("admin", "editor"))
        self.assertFalse(role_at_least("viewer", "editor"))


class MonitoringEndpointTests(TestCase):
    def test_health(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_metrics_exposes_counters(self):
        from apps.common.metrics import record_case

        record_case("api", "passed", 3)
        resp = self.client.get("/metrics/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"aits_test_cases_total", resp.content)


class ExceptionEnvelopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_unauthorized_envelope(self):
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "unauthorized")
        self.assertIn("message", resp.data)

    def test_not_found_envelope(self):
        user = User.objects.create_user("u", "u@x.com", "Passw0rd!")
        self.client.force_authenticate(user)
        resp = self.client.get("/api/projects/999999/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "not_found")
