from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from analytics.forms import period_form
from analytics.models import SpikeAlert
from analytics.reports import build, signed
from appeals.models import Appeal, Category, Reason

MSK = ZoneInfo("Europe/Moscow")
CURRENT = {"date_from": "2026-09-11", "date_to": "2026-09-20"}


class ReportTests(TestCase):
    """Ручной набор. Предыдущий период 1-10 сентября, текущий 11-20 сентября.

    Доставка 20 -> 22 (+10%, мало для вывода), Оплата 10 -> 30 (+200%), Аккаунт и вход 15 -> 25 (+67%),
    Возвраты 20 -> 8 (-60%), без категории 5 -> 15. Всего 70 -> 100.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        reasons = {
            "delivery": Reason.objects.get(name="Задержка доставки"),
            "payment": Reason.objects.get(name="Двойное списание"),
            "account": Reason.objects.get(name="Не могу войти в аккаунт"),
            "returns": Reason.objects.get(name="Не вернули деньги"),
        }
        appeals = []

        def add(key, count, first_day):
            reason = reasons.get(key)
            for i in range(count):
                created = datetime(2026, 9, first_day + i % 10, 9 + i % 10, i % 60, tzinfo=MSK)
                appeal = Appeal(text="x", created_at=created, category_source="none")
                if reason:
                    appeal.category, appeal.reason, appeal.category_source = reason.category, reason, "auto"
                appeals.append(appeal)

        for key, before, now in (
            ("delivery", 20, 22), ("payment", 10, 30), ("account", 15, 25), ("returns", 20, 8), (None, 5, 15)
        ):
            add(key, before, 1)
            add(key, now, 11)
        Appeal.objects.bulk_create(appeals)
        payment = Category.objects.get(slug="payment")
        SpikeAlert.objects.create(category=payment, day=date(2026, 9, 15), count=12, baseline=1, ratio=12)
        SpikeAlert.objects.create(category=payment, day=date(2026, 9, 5), count=9, baseline=1, ratio=9)

    def report(self, **params):
        return build(period_form({**CURRENT, **params}))

    def test_periods(self):
        report = self.report()
        self.assertEqual((report["prev_start"], report["prev_end"]), (date(2026, 9, 1), date(2026, 9, 10)))
        self.assertEqual((report["summary"].total, report["previous"].total), (100, 70))

    def test_volume(self):
        self.assertEqual(
            self.report()["conclusions"][0],
            "Всего обращений за период: 100, в среднем 10 в день. Это на 43% больше, чем в предыдущем периоде (70).",
        )

    def test_largest_category(self):
        self.assertIn("Больше всего обращений в категории «Оплата»: 30, 30,0% от всех.", self.report()["conclusions"])

    def test_biggest_growth(self):
        # Оплата растёт сильнее Аккаунта (+67%). Без категории вырос на 200%, но это не категория.
        # Доставка +10%: изменение не считается заметным.
        lines = self.report()["conclusions"]
        self.assertIn("Сильнее всего выросла категория «Оплата»: было 10, стало 30, +200%.", lines)

    def test_biggest_decrease(self):
        self.assertIn("Сильнее всего снизилась категория «Возвраты»: было 20, стало 8, -60%.", self.report()["conclusions"])

    def test_top_reason(self):
        self.assertIn(
            "Самая частая причина: «Двойное списание» (Оплата), за период 30, в предыдущем периоде 10 (+200%).",
            self.report()["conclusions"],
        )

    def test_spikes_only_in_period(self):
        report = self.report()
        self.assertEqual([a.day for a in report["alerts"]], [date(2026, 9, 15)])
        self.assertIn("Резкий рост за период: 1. Самые сильные: 15.09 Оплата (12 при норме 1).", report["conclusions"])

    def test_without_category_warning(self):
        self.assertIn(
            "Обращений без категории: 15, 15,0%. Их стоит разобрать вручную и дополнить словарь ключевых фраз.",
            self.report()["conclusions"],
        )

    def test_filtered_report(self):
        # Только Доставка: рост с 20 до 22 не заметный, уведомления по Оплате в отчёт не попадают.
        lines = self.report(category="delivery")["conclusions"]
        self.assertIn("Заметного роста по категориям нет.", lines)
        self.assertIn("Резкого роста обращений за период не было.", lines)
        self.assertTrue(lines[0].startswith("Всего обращений за период: 22,"))

    def test_summary_rows(self):
        rows = {row["name"]: row for row in self.report()["summary_rows"]}
        self.assertEqual((rows["Обращений"]["current"], rows["Обращений"]["previous"]), ("100", "70"))
        self.assertAlmostEqual(rows["Обращений"]["change"], 100 / 70 - 1)
        self.assertEqual(rows["Без категории"]["current"], "15 (15,0%)")
        self.assertEqual(rows["Медиана времени решения"]["current"], "нет данных")

    def test_signed(self):
        self.assertEqual(signed(2.0), "+200%")
        self.assertEqual(signed(-0.6), "-60%")
        self.assertEqual(signed(None), "нет базы")

    def test_no_previous_period(self):
        lines = build(period_form({"date_from": "2026-09-01", "date_to": "2026-09-10"}))["conclusions"]
        self.assertIn("В предыдущем периоде обращений не было, сравнивать не с чем.", lines[0])


class ReportPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        reason = Reason.objects.get(name="Задержка доставки")
        Appeal.objects.bulk_create(
            [
                Appeal(text="x", created_at=datetime(2026, 9, 12, 10, tzinfo=MSK) + timedelta(hours=i),
                       category=reason.category, reason=reason, category_source="auto")
                for i in range(30)
            ]
        )

    def get(self, username, params=CURRENT):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(reverse("analytics:reports"), params)

    def test_analyst_sees_report(self):
        response = self.get("analyst")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выводы")
        self.assertContains(response, "Всего обращений за период: 30")
        self.assertContains(response, 'id="chart-daily"')
        self.assertEqual(set(response.context["charts"]), {"daily", "categories", "reasons"})

    def test_print_version(self):
        response = self.get("analyst")
        self.assertContains(response, 'href="/static/css/print.css" media="print"')
        self.assertContains(response, '<div class="no-print"><form method="get" class="panel">')
        self.assertContains(response, '<div class="actions no-print">')
        css = open(finders.find("css/print.css"), encoding="utf-8").read()
        hidden = css.split("{ display: none !important; }")[0]
        for selector in (".topbar", ".no-print"):
            self.assertIn(selector, hidden)

    def test_empty_period(self):
        response = self.get("analyst", {"date_from": "2020-01-01", "date_to": "2020-01-31"})
        self.assertContains(response, "Нет данных за период.")
        self.assertNotIn("charts", response.context)

    def test_operator_forbidden(self):
        self.assertEqual(self.get("operator").status_code, 403)
