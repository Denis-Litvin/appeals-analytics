from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from appeals.models import Appeal
from appeals.roles import (
    ADMIN,
    ADMIN_PERMS,
    ANALYST,
    DEMO_PASSWORD,
    OPERATOR,
    author_for,
    mask_email,
    mask_name,
)

APPEAL_PAGES = ["appeals:list"]
ANALYTICS_PAGES = [
    "analytics:stats",
    "analytics:problems",
    "analytics:compare",
    "analytics:dashboard",
    "analytics:reports",
    "analytics:alerts",
]


class SetupRolesTests(TestCase):
    def test_command_is_idempotent(self):
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        self.assertEqual(Group.objects.count(), 3)
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Group.objects.get(name=ADMIN).permissions.count(), len(ADMIN_PERMS))

    def test_demo_users_get_their_groups(self):
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        self.assertEqual(User.objects.get(username="operator").groups.get().name, OPERATOR)
        self.assertEqual(User.objects.get(username="analyst").groups.get().name, ANALYST)
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_staff)
        self.assertFalse(admin.is_superuser)
        self.assertFalse(User.objects.get(username="operator").is_staff)

    def test_rerun_keeps_changed_password(self):
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        user = User.objects.get(username="operator")
        user.set_password("new-password-1")
        user.save()
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        self.assertTrue(User.objects.get(username="operator").check_password("new-password-1"))


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        User.objects.create_user("nobody", password=DEMO_PASSWORD)

    def get_as(self, username, url):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(url)

    def test_access_matrix(self):
        expected = {
            "operator": {"appeals": 200, "analytics": 403},
            "analyst": {"appeals": 200, "analytics": 200},
            "admin": {"appeals": 200, "analytics": 200},
            "nobody": {"appeals": 403, "analytics": 403},
        }
        for username, codes in expected.items():
            for name in APPEAL_PAGES:
                with self.subTest(user=username, page=name):
                    self.assertEqual(self.get_as(username, reverse(name)).status_code, codes["appeals"])
            for name in ANALYTICS_PAGES:
                with self.subTest(user=username, page=name):
                    self.assertEqual(self.get_as(username, reverse(name)).status_code, codes["analytics"])

    def test_anonymous_redirected_to_login(self):
        for name in APPEAL_PAGES + ANALYTICS_PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_admin_site_only_for_admin(self):
        self.assertEqual(self.get_as("admin", "/admin/").status_code, 200)
        self.assertEqual(self.get_as("admin", "/admin/appeals/keywordrule/").status_code, 200)
        for username in ("operator", "analyst"):
            with self.subTest(user=username):
                response = self.get_as(username, "/admin/")
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_menu_depends_on_role(self):
        stats_link = f'href="{reverse("analytics:stats")}"'
        admin_link = 'href="/admin/"'
        operator_page = self.get_as("operator", reverse("appeals:list")).content.decode()
        self.assertNotIn(stats_link, operator_page)
        self.assertNotIn(admin_link, operator_page)
        analyst_page = self.get_as("analyst", reverse("appeals:list")).content.decode()
        self.assertIn(stats_link, analyst_page)
        self.assertNotIn(admin_link, analyst_page)
        admin_page = self.get_as("admin", reverse("appeals:list")).content.decode()
        self.assertIn(stats_link, admin_page)
        self.assertIn(admin_link, admin_page)

    def test_forbidden_page(self):
        response = self.get_as("operator", reverse("analytics:stats"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Нет доступа", status_code=403)
        self.assertContains(response, "Перейти к обращениям", status_code=403)


class MaskingTests(TestCase):
    def test_mask_email(self):
        self.assertEqual(mask_email("ivan.petrov@mail.ru"), "i***@mail.ru")
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email("не email"), "***")

    def test_mask_name(self):
        self.assertEqual(mask_name("Иван Петров"), "И*** П***")
        self.assertEqual(mask_name(""), "")

    def test_author_for_roles(self):
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        appeal = Appeal(author_name="Иван Петров", author_email="ivan@mail.ru", text="текст")
        operator = User.objects.get(username="operator")
        analyst = User.objects.get(username="analyst")
        admin = User.objects.get(username="admin")
        self.assertEqual(author_for(operator, appeal), ("Иван Петров", "ivan@mail.ru"))
        self.assertEqual(author_for(admin, appeal), ("Иван Петров", "ivan@mail.ru"))
        self.assertEqual(author_for(analyst, appeal), ("И*** П***", "i***@mail.ru"))
