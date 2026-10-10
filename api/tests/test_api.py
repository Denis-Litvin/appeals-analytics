from datetime import date, datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from analytics.models import SpikeAlert
from appeals.management.commands.generate_appeals import generate
from appeals.models import Appeal, Category

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-28"}
ANALYTICS = ["api:summary", "api:categories", "api:top_reasons", "api:problems", "api:timeseries", "api:compare",
             "api:alerts"]


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(800, 2, seed=4, end=END)
        cls.appeal = Appeal.objects.create(
            text="С карты списали дважды за один заказ", author_name="Иван Петров",
            author_email="ivan.petrov@mail.ru", created_at=datetime(2026, 9, 10, 12, tzinfo=MSK),
        )
        cls.tokens = {u.username: Token.objects.create(user=u).key for u in User.objects.all()}
        payment = Category.objects.get(slug="payment")
        cls.alert = SpikeAlert.objects.create(category=payment, day=date(2026, 9, 15), count=30, baseline=8, ratio=3.75)

    def api(self, username=None):
        client = APIClient()
        if username:
            client.credentials(HTTP_AUTHORIZATION=f"Token {self.tokens[username]}")
        return client

    def get(self, username, name, params=None, **kwargs):
        return self.api(username).get(reverse(name, kwargs=kwargs or None), params or {})

    def page_context(self, name, params):
        """Контекст страницы сайта с теми же параметрами, для сверки чисел."""
        self.client.force_login(User.objects.get(username="analyst"))
        return self.client.get(reverse(name), params).context

    def test_token(self):
        response = self.api().post(reverse("api:token"), {"username": "analyst", "password": "demo12345"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], self.tokens["analyst"])
        wrong = self.api().post(reverse("api:token"), {"username": "analyst", "password": "не тот"})
        self.assertEqual(wrong.status_code, 400)

    def test_without_token_401(self):
        for name in ANALYTICS + ["api:appeals"]:
            with self.subTest(url=name):
                response = self.get(None, name)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "Token")
        self.assertEqual(self.get(None, "api:appeal", pk=self.appeal.pk).status_code, 401)
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Token 0000")
        self.assertEqual(bad.get(reverse("api:summary")).status_code, 401)

    def test_operator_forbidden_on_analytics(self):
        for name in ANALYTICS:
            with self.subTest(url=name):
                self.assertEqual(self.get("operator", name).status_code, 403)
        self.assertEqual(self.get("operator", "api:appeals").status_code, 200)

    def test_analyst_cannot_create(self):
        response = self.api("analyst").post(reverse("api:appeals"), {"text": "Не приходит код"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_admin_has_everything(self):
        for name in ANALYTICS + ["api:appeals"]:
            with self.subTest(url=name):
                self.assertEqual(self.get("admin", name).status_code, 200)

    def test_summary_matches_stats_page(self):
        data = self.get("analyst", "api:summary", PERIOD).json()
        page = self.page_context("analytics:stats", PERIOD)["summary"]
        self.assertGreater(data["total"], 300)
        for field in ("total", "days", "per_day", "open_count", "without_category", "median_resolution_hours"):
            self.assertEqual(data[field], getattr(page, field), field)
        self.assertAlmostEqual(data["open_share"], page.open_share)
        self.assertEqual(data["period"], {"date_from": "2026-09-01", "date_to": "2026-09-28", "days": 28})

    def test_categories_and_top_match_stats_page(self):
        page = self.page_context("analytics:stats", PERIOD)
        categories = self.get("analyst", "api:categories", PERIOD).json()["results"]
        self.assertEqual([(r["name"], r["count"]) for r in categories], [(r["name"], r["count"]) for r in page["categories"]])
        top = self.get("analyst", "api:top_reasons", PERIOD).json()["results"]
        self.assertEqual([r["count"] for r in top], [r["count"] for r in page["reasons"]])

    def test_problems_match_page(self):
        page = self.page_context("analytics:problems", PERIOD)
        data = self.get("analyst", "api:problems", PERIOD).json()
        self.assertEqual([(r["name"], r["rank"], r["count"]) for r in data["results"]],
                         [(r["name"], r["rank"], r["count"]) for r in page["rows"]])
        self.assertEqual(data["previous_period"]["date_to"], "2026-08-31")

    def test_timeseries(self):
        data = self.get("analyst", "api:timeseries", PERIOD).json()
        summary = self.get("analyst", "api:summary", PERIOD).json()
        self.assertEqual(len(data["days"]), 28)
        self.assertEqual(sum(data["total"]), summary["total"])
        self.assertEqual(sum(sum(s["values"]) for s in data["series"]), summary["total"])

    def test_compare_matches_page(self):
        params = {"preset": "custom", "base_from": "2026-08-01", "base_to": "2026-08-14",
                  "current_from": "2026-09-01", "current_to": "2026-09-28"}
        data = self.get("analyst", "api:compare", params).json()
        page = self.page_context("analytics:compare", params)
        self.assertEqual(data["totals"]["current_count"], page["totals"]["current_count"])
        self.assertEqual(data["totals"]["base_count"], page["totals"]["base_count"])
        self.assertEqual(len(data["results"]), len(page["categories"]))
        by_reason = self.get("analyst", "api:compare", {**params, "by": "reason"}).json()
        self.assertEqual(len(by_reason["results"]), len(page["reasons"]))

    def test_bad_parameters_400(self):
        cases = [
            ("api:summary", {"date_from": "вчера"}, "date_from"),
            ("api:top_reasons", {"limit": "100"}, "limit"),
            ("api:compare", {"by": "tag"}, "by"),
            ("api:compare", {"preset": "custom"}, "preset"),
            ("api:alerts", {"date_to": "2026-13-01"}, "date_to"),
            ("api:appeals", {"date_from": "abc"}, "date_from"),
        ]
        for name, params, field in cases:
            with self.subTest(url=name, params=params):
                response = self.get("analyst", name, params)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())

    def test_email_masked_for_analyst(self):
        data = self.get("analyst", "api:appeal", pk=self.appeal.pk).json()
        self.assertEqual((data["author_name"], data["author_email"]), ("И*** П***", "i***@mail.ru"))
        listed = self.get("analyst", "api:appeals", {"q": f"#{self.appeal.pk}"}).json()["results"][0]
        self.assertEqual(listed["author_email"], "i***@mail.ru")
        full = self.get("operator", "api:appeal", pk=self.appeal.pk).json()
        self.assertEqual(full["author_email"], "ivan.petrov@mail.ru")

    def test_appeal_filters_and_pagination(self):
        data = self.get("analyst", "api:appeals", {"category": "payment", "page_size": 10}).json()
        self.assertEqual(data["count"], Appeal.objects.filter(category__slug="payment").count())
        self.assertEqual(len(data["results"]), 10)
        self.assertTrue(all(a["category"]["slug"] == "payment" for a in data["results"]))
        oldest = self.get("analyst", "api:appeals", {"order": "old", "page_size": 1}).json()["results"][0]
        self.assertEqual(oldest["id"], Appeal.objects.order_by("created_at", "id").first().pk)

    def test_detail(self):
        data = self.get("operator", "api:appeal", pk=self.appeal.pk).json()
        self.assertEqual(data["category"]["slug"], "payment")
        self.assertEqual(data["reason"]["name"], "Двойное списание")
        self.assertEqual(self.get("operator", "api:appeal", pk=999999).status_code, 404)

    def test_create_gets_category(self):
        response = self.api("operator").post(
            reverse("api:appeals"),
            {"channel": "app", "text": "Приложение вылетает при оплате", "author_email": "olga@mail.ru",
             "tags": ["iOS"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["category"]["slug"], "app")
        self.assertEqual(data["reason"]["name"], "Приложение вылетает")
        self.assertEqual(data["category_source"], "auto")
        self.assertEqual(data["tags"], ["iOS"])
        self.assertEqual(data["new_alerts"], [])
        self.assertTrue(Appeal.objects.filter(pk=data["id"], text_norm__contains="вылета").exists())

    def test_create_validation(self):
        response = self.api("operator").post(
            reverse("api:appeals"), {"text": "  ", "channel": "fax", "tags": ["нет такого"]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"text", "channel", "tags"})

    def test_alerts(self):
        data = self.get("analyst", "api:alerts").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["category"], "payment")
        self.assertFalse(data["results"][0]["read"])
        self.alert.read_by.add(User.objects.get(username="analyst"))
        self.assertEqual(self.get("analyst", "api:alerts", {"unread": "1"}).json()["count"], 0)
        self.assertEqual(self.get("analyst", "api:alerts", {"date_from": "2026-09-16"}).json()["count"], 0)

    def test_site_login_not_required(self):
        # Middleware входа на сайт не перехватывает API: без токена 401 в JSON, а не переход на /login/.
        response = self.get(None, "api:appeals")
        self.assertEqual(response["Content-Type"], "application/json")
