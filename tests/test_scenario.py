"""Сквозной сценарий через интерфейс и API: оператор принимает обращения, растёт поток по одной причине,
аналитик получает уведомление, видит рост в статистике и отчёте, выгружает данные и забирает их через API."""

from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import SpikeAlert
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")
TEXT = "Не приходит код подтверждения по смс, не могу войти в приложение"


class ScenarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.reason = Reason.objects.get(name="Не приходит код подтверждения")
        # Четыре недели обычного потока: по два обращения в день по этой причине.
        today = timezone.localdate()
        history = []
        for days_ago in range(1, 29):
            day = today - timedelta(days=days_ago)
            for hour in (11, 15):
                history.append(
                    Appeal(
                        text=TEXT, created_at=datetime(day.year, day.month, day.day, hour, tzinfo=MSK),
                        category=cls.reason.category, reason=cls.reason, category_source="auto", status="closed",
                    )
                )
        Appeal.objects.bulk_create(history)

    def login(self, username):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": username, "password": "demo12345"}, follow=True)
        self.assertEqual(response.resolver_match.view_name, "appeals:list")
        return response

    def test_operator_to_analyst(self):
        # 1. Оператор входит через форму входа и заносит 12 одинаковых жалоб, принятых по телефону.
        self.login("operator")
        for i in range(12):
            self.client.post(
                reverse("appeals:create"),
                {"channel": "phone", "author_name": "Пётр Сидоров", "author_email": f"petrov{i}@mail.ru",
                 "subject": "", "text": TEXT},
            )
        created = list(Appeal.objects.order_by("-id")[:12])
        self.assertTrue(all(a.reason_id == self.reason.pk and a.category_source == "auto" for a in created))

        # 2. Рост найден сразу при сохранении: два уведомления (причина и категория), письма ушли аналитикам.
        alerts = SpikeAlert.objects.filter(day=timezone.localdate())
        self.assertEqual({a.reason_id for a in alerts}, {self.reason.pk, None})
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("analyst@example.com", mail.outbox[0].to)

        # 3. Оператор берёт обращение в работу и решает его. Категория остаётся автоматической.
        appeal = created[0]
        for status in ("in_work", "resolved"):
            self.client.post(
                reverse("appeals:edit", args=[appeal.pk]),
                {"status": status, "assignee": "", "category": appeal.category_id, "reason": appeal.reason_id},
            )
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, "resolved")
        self.assertEqual(appeal.assignee.username, "operator")
        self.assertIsNotNone(appeal.resolved_at)
        self.assertEqual(appeal.category_source, "auto")

        # 4. Аналитик входит и видит счётчик уведомлений в меню.
        response = self.login("analyst")
        self.assertEqual(response.context["unread_alerts"], 2)
        response = self.client.get(reverse("analytics:alerts"))
        self.assertContains(response, "Не приходит код подтверждения")

        # 5. Статистика и отчёт за сегодня показывают эти 12 обращений и рост.
        period = {"date_from": timezone.localdate().isoformat(), "date_to": timezone.localdate().isoformat()}
        stats_page = self.client.get(reverse("analytics:stats"), period)
        self.assertEqual(stats_page.context["summary"].total, 12)
        report = self.client.get(reverse("analytics:reports"), period)
        self.assertTrue(any(line.startswith("Резкий рост за период: 2.") for line in report.context["report"]["conclusions"]))

        # 6. Выгрузка списка: у аналитика email замаскирован.
        export = self.client.get(reverse("appeals:export"), {**period, "format": "csv"})
        content = export.content.decode("utf-8-sig")
        self.assertIn("p***@mail.ru", content)
        self.assertNotIn("petrov0@mail.ru", content)

        # 7. Через API аналитик получает те же числа.
        token = APIClient().post(reverse("api:token"), {"username": "analyst", "password": "demo12345"}).json()["token"]
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        summary = api.get(reverse("api:summary"), period).json()
        self.assertEqual(summary["total"], 12)
        self.assertEqual(api.get(reverse("api:alerts"), {"unread": "1"}).json()["count"], 2)

        # 8. Аналитик отмечает уведомления прочитанными, счётчик пропадает.
        self.client.post(reverse("analytics:alerts_read_all"))
        self.assertNotContains(self.client.get(reverse("appeals:list")), 'class="counter"')
