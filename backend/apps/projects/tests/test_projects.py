import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import Environment, Project, ProjectMember, UploadedFile

User = get_user_model()


class ProjectFixture(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="Passw0rd!"
        )
        self.member = User.objects.create_user(
            username="member", email="member@example.com", password="Passw0rd!"
        )
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="Passw0rd!"
        )
        self.project = Project.objects.create(
            name="Demo API Project", project_type="api", owner=self.owner
        )
        ProjectMember.objects.create(project=self.project, user=self.owner, role="owner")
        ProjectMember.objects.create(project=self.project, user=self.member, role="editor")
        self.client.force_authenticate(self.owner)


class ProjectCRUDTests(ProjectFixture):
    def test_create_project_assigns_owner_and_membership(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            "/api/projects/",
            {"name": "New Web Project", "project_type": "web", "description": "d"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        project = Project.objects.get(pk=resp.data["id"])
        self.assertEqual(project.owner, self.outsider)
        self.assertTrue(
            ProjectMember.objects.filter(project=project, user=self.outsider,
                                         role="owner").exists()
        )

    def test_list_only_returns_my_projects(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

    def test_member_can_read_project_but_not_delete(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project.id}/").status_code, 200
        )
        self.assertEqual(
            self.client.delete(f"/api/projects/{self.project.id}/").status_code, 403
        )

    def test_viewer_cannot_create_suite_like_resources(self):
        ProjectMember.objects.filter(project=self.project, user=self.member).update(
            role="viewer"
        )
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/projects/environments/",
            {"project": self.project.id, "name": "prod", "base_url": "https://x.test"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_delete_project(self):
        self.assertEqual(
            self.client.delete(f"/api/projects/{self.project.id}/").status_code, 204
        )

    def test_add_and_remove_member(self):
        resp = self.client.post(
            f"/api/projects/{self.project.id}/members/add/",
            {"user": self.outsider.id, "role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        membership = ProjectMember.objects.get(project=self.project, user=self.outsider)
        self.assertEqual(membership.role, "viewer")

        resp = self.client.delete(
            f"/api/projects/{self.project.id}/members/{membership.id}/"
        )
        self.assertEqual(resp.status_code, 204)

    def test_cannot_remove_owner(self):
        owner_member = ProjectMember.objects.get(project=self.project, user=self.owner)
        resp = self.client.delete(
            f"/api/projects/{self.project.id}/members/{owner_member.id}/"
        )
        self.assertEqual(resp.status_code, 400)

    def test_project_stats(self):
        resp = self.client.get(f"/api/projects/{self.project.id}/stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["member_count"], 2)

    def test_perf_project_linked_api_projects_validation(self):
        resp = self.client.post(
            "/api/projects/",
            {"name": "Perf", "project_type": "perf"},
            format="json",
        )
        perf = Project.objects.get(pk=resp.data["id"])
        resp = self.client.post(
            f"/api/projects/{perf.id}/",
            {},
            format="json",
        )
        # PATCH through detail endpoint
        resp = self.client.patch(
            f"/api/projects/{perf.id}/",
            {"linked_api_projects": [self.project.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(list(perf.linked_api_projects.values_list("id", flat=True)),
                         [self.project.id])

    def test_non_perf_project_cannot_link_api_projects(self):
        resp = self.client.patch(
            f"/api/projects/{self.project.id}/",
            {"linked_api_projects": [self.project.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class EnvironmentTests(ProjectFixture):
    def test_first_environment_becomes_default(self):
        resp = self.client.post(
            "/api/projects/environments/",
            {"project": self.project.id, "name": "test", "base_url": "http://t.test"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        env = Environment.objects.get(pk=resp.data["id"])
        self.assertTrue(env.is_default)

    def test_set_default_is_exclusive(self):
        first = Environment.objects.create(project=self.project, name="a", is_default=True)
        second = Environment.objects.create(project=self.project, name="b")
        resp = self.client.post(
            f"/api/projects/environments/{second.id}/set-default/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_duplicate_environment_name_rejected(self):
        Environment.objects.create(project=self.project, name="dup")
        resp = self.client.post(
            "/api/projects/environments/",
            {"project": self.project.id, "name": "dup"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class FileUploadTests(ProjectFixture):
    def test_upload_and_deduplicate_by_hash(self):
        content = b"openapi: 3.0.0\ninfo:\n  title: t\n"
        first = self.client.post(
            "/api/projects/files/",
            {"project": self.project.id, "file": io.BytesIO(content),
             "purpose": "spec"},
            format="multipart",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post(
            "/api/projects/files/",
            {"project": self.project.id, "file": io.BytesIO(content),
             "purpose": "spec"},
            format="multipart",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(UploadedFile.objects.filter(project=self.project).count(), 1)

    def test_upload_rejects_empty_file(self):
        resp = self.client.post(
            "/api/projects/files/",
            {"project": self.project.id, "file": io.BytesIO(b"")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_requires_project(self):
        resp = self.client.post(
            "/api/projects/files/",
            {"file": io.BytesIO(b"x")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)


class KnowledgeDocumentTests(ProjectFixture):
    def test_create_and_list_knowledge_document(self):
        resp = self.client.post(
            "/api/projects/knowledge/",
            {"project": self.project.id, "title": "接口说明", "content": "登录接口说明"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["status"], "pending")
        listing = self.client.get("/api/projects/knowledge/")
        self.assertEqual(listing.data["count"], 1)

    def test_outsider_cannot_create_knowledge(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            "/api/projects/knowledge/",
            {"project": self.project.id, "title": "x", "content": "y"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class ThirdPartyConfigTests(ProjectFixture):
    def test_config_created_on_demand(self):
        resp = self.client.get(
            f"/api/projects/{self.project.id}/third-party-config/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["dingtalk_webhook"], "")

    def test_update_config_requires_admin(self):
        self.client.force_authenticate(self.member)  # editor
        resp = self.client.patch(
            f"/api/projects/{self.project.id}/third-party-config/",
            {"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"/api/projects/{self.project.id}/third-party-config/",
            {"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
