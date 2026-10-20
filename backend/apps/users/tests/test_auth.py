from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _register(self, username="alice", email="alice@example.com", password="Passw0rd!"):
        return self.client.post(
            "/api/auth/register/",
            {"username": username, "email": email, "password": password,
             "password_confirm": password, "nickname": "Alice"},
            format="json",
        )

    def test_register_returns_tokens_and_user(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["username"], "alice")
        self.assertTrue(User.objects.filter(email="alice@example.com").exists())

    def test_register_rejects_duplicate_email(self):
        self._register()
        resp = self.client.post(
            "/api/auth/register/",
            {"username": "bob", "email": "alice@example.com", "password": "Passw0rd!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "validation_error")

    def test_register_rejects_weak_password(self):
        resp = self.client.post(
            "/api/auth/register/",
            {"username": "weak", "email": "weak@example.com", "password": "123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_and_me(self):
        self._register()
        resp = self.client.post(
            "/api/auth/login/", {"username": "alice", "password": "Passw0rd!"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        access = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "alice@example.com")
        self.assertEqual(me.data["display_name"], "Alice")

    def test_login_with_email(self):
        self._register()
        resp = self.client.post(
            "/api/auth/login/", {"email": "alice@example.com", "password": "Passw0rd!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_login_wrong_password(self):
        self._register()
        resp = self.client.post(
            "/api/auth/login/", {"username": "alice", "password": "nope"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_refresh_rotation_blacklists_old_token(self):
        tokens = self._register().data
        refresh = tokens["refresh"]
        rotated = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(rotated.status_code, 200, rotated.data)
        # old refresh must be blacklisted after rotation
        again = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(again.status_code, 401)

    def test_logout_blacklists_refresh(self):
        tokens = self._register().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]},
                                format="json")
        self.assertEqual(resp.status_code, 200)
        reused = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]},
                                  format="json")
        self.assertEqual(reused.status_code, 401)

    def test_change_password(self):
        tokens = self._register().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "Passw0rd!", "new_password": "NewPassw0rd!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        login = self.client.post(
            "/api/auth/login/", {"username": "alice", "password": "NewPassw0rd!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
