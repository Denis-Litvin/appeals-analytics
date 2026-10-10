"""Матрица доступа (Д10): каждый адрес сайта и API для анонима, оператора, аналитика и администратора.

Тест сам собирает все именованные адреса проекта. Новый адрес без строки в SITE или API роняет тест,
поэтому права на него придётся явно описать здесь.
"""

from datetime import date, datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import URLResolver, get_resolver, reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from analytics.charts import PLOTLY_VERSION
from analytics.models import SpikeAlert
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")
ROLES = ("anonymous", "operator", "analyst", "admin")
LOGIN = 302  # аноним на сайте уходит на страницу входа
ME = 302  # успешный POST на сайте возвращает на страницу

# (имя адреса, метод, ожидаемые коды для ролей в порядке ROLES)
SITE = [
    ("home", "get", (LOGIN, 302, 302, 302)),
    ("login", "get", (200, 200, 200, 200)),
    ("logout", "post", (302, 302, 302, 302)),
    ("appeals:list", "get", (LOGIN, 200, 200, 200)),
    ("appeals:create", "get", (LOGIN, 200, 403, 200)),
    ("appeals:export", "get", (LOGIN, 403, 200, 200)),
    ("appeals:detail", "get", (LOGIN, 200, 200, 200)),
    ("appeals:edit", "get", (LOGIN, 200, 403, 200)),
    ("appeals:auto_category", "post", (LOGIN, ME, 403, ME)),
    ("analytics:stats", "get", (LOGIN, 403, 200, 200)),
    ("analytics:problems", "get", (LOGIN, 403, 200, 200)),
    ("analytics:compare", "get", (LOGIN, 403, 200, 200)),
    ("analytics:dashboard", "get", (LOGIN, 403, 200, 200)),
    ("analytics:reports", "get", (LOGIN, 403, 200, 200)),
    ("analytics:report_export", "get", (LOGIN, 403, 200, 200)),
    ("analytics:alerts", "get", (LOGIN, 403, 200, 200)),
    ("analytics:alerts_read_all", "post", (LOGIN, 403, ME, ME)),
    ("analytics:alerts_read", "post", (LOGIN, 403, ME, ME)),
    ("analytics:plotly_js", "get", (200, 200, 200, 200)),
]
API = [
    ("api:token", "post", (400, 400, 400, 400)),  # без логина и пароля
    ("api:summary", "get", (401, 403, 200, 200)),
    ("api:categories", "get", (401, 403, 200, 200)),
    ("api:top_reasons", "get", (401, 403, 200, 200)),
    ("api:problems", "get", (401, 403, 200, 200)),
    ("api:timeseries", "get", (401, 403, 200, 200)),
    ("api:compare", "get", (401, 403, 200, 200)),
    ("api:alerts", "get", (401, 403, 200, 200)),
    ("api:appeals", "get", (401, 200, 200, 200)),
    ("api:appeals", "post", (401, 201, 403, 201)),
    ("api:appeal", "get", (401, 200, 200, 200)),
]


def project_urls(patterns=None, namespace=""):
    """Все именованные адреса проекта, кроме админки Django."""
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(pattern, URLResolver):
            if pattern.namespace == "admin":
                continue
            prefix = f"{namespace}{pattern.namespace}:" if pattern.namespace else namespace
            yield from project_urls(pattern.url_patterns, prefix)
        elif pattern.name:
            yield namespace + pattern.name


class AccessMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.appeal = Appeal.objects.create(text="Курьер опоздал на два часа", created_at=datetime(2026, 9, 10, tzinfo=MSK))
        reason = Reason.objects.get(name="Задержка доставки")
        cls.alert = SpikeAlert.objects.create(
            category=reason.category, reason=reason, day=date(2026, 9, 10), count=20, baseline=3, ratio=6.7
        )
        cls.tokens = {u.username: Token.objects.create(user=u).key for u in User.objects.all()}

    def url(self, name):
        kwargs = {
            "appeals:detail": {"pk": self.appeal.pk},
            "appeals:edit": {"pk": self.appeal.pk},
            "appeals:auto_category": {"pk": self.appeal.pk},
            "analytics:alerts_read": {"pk": self.alert.pk},
            "analytics:plotly_js": {"version": PLOTLY_VERSION},
            "api:appeal": {"pk": self.appeal.pk},
        }.get(name)
        return reverse(name, kwargs=kwargs)

    def test_every_url_is_in_matrix(self):
        covered = {name for name, _, _ in SITE + API}
        self.assertEqual(set(project_urls()) - covered, set())

    def test_site(self):
        for name, method, codes in SITE:
            for role, expected in zip(ROLES, codes):
                with self.subTest(url=name, role=role):
                    self.client.logout()
                    if role != "anonymous":
                        self.client.force_login(User.objects.get(username=role))
                    response = getattr(self.client, method)(self.url(name))
                    self.assertEqual(response.status_code, expected)
                    if role == "anonymous" and expected == LOGIN:
                        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_api(self):
        body = {"text": "Не приходит код подтверждения по смс"}
        for name, method, codes in API:
            for role, expected in zip(ROLES, codes):
                with self.subTest(url=name, method=method, role=role):
                    client = APIClient()
                    if role != "anonymous":
                        client.credentials(HTTP_AUTHORIZATION=f"Token {self.tokens[role]}")
                    response = getattr(client, method)(self.url(name), body if method == "post" else None, format="json")
                    self.assertEqual(response.status_code, expected)

    def test_admin_site_only_for_admin(self):
        for role, expected in zip(ROLES, (302, 302, 302, 200)):
            with self.subTest(role=role):
                self.client.logout()
                if role != "anonymous":
                    self.client.force_login(User.objects.get(username=role))
                self.assertEqual(self.client.get(reverse("admin:index")).status_code, expected)

    def test_favicon_open_for_everyone(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/static/favicon.svg")
