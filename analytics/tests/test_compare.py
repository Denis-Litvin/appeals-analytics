from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from analytics import stats
from analytics.forms import compare_form
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")


class CompareTests(TestCase):
    """База 1-7 сентября (7 дней), текущий период 8-21 сентября (14 дней)."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.steady = Reason.objects.get(name="Задержка доставки")  # 2 в день в обоих периодах
        cls.growing = Reason.objects.get(name="Приложение вылетает")  # 1 в день, потом 3 в день
        cls.small = Reason.objects.get(name="Удаление аккаунта")  # 1 и 3 за период: мало для вывода
        cls.new = Reason.objects.get(name="Брак или повреждение")  # в базе нет, потом 12
        appeals = []

        def spread(reason, total, first_day, days):
            for i in range(total):
                day = first_day + i % days
                appeals.append(
                    Appeal(
                        text="x", created_at=datetime(2026, 9, day, 9 + i % 12, i % 60, tzinfo=MSK),
                        category=reason.category, reason=reason, category_source="auto",
                    )
                )

        spread(cls.steady, 14, 1, 7)
        spread(cls.steady, 28, 8, 14)
        spread(cls.growing, 7, 1, 7)
        spread(cls.growing, 42, 8, 14)
        spread(cls.small, 1, 1, 7)
        spread(cls.small, 3, 8, 14)
        spread(cls.new, 12, 8, 14)
        Appeal.objects.bulk_create(appeals)

    def compare(self, by="reason"):
        form = compare_form(
            {
                "preset": "custom",
                "base_from": "2026-09-01",
                "base_to": "2026-09-07",
                "current_from": "2026-09-08",
                "current_to": "2026-09-21",
            }
        )
        base = stats.load_frame(form.appeals(*form.base))
        current = stats.load_frame(form.appeals(*form.current))
        rows, totals = stats.compare(base, current, 7, 14, by=by)
        return {row["name"]: row for row in rows}, totals

    def test_different_lengths_compared_per_day(self):
        rows, _ = self.compare()
        steady = rows[self.steady.name]
        self.assertEqual((steady["base_count"], steady["current_count"]), (14, 28))
        self.assertEqual((steady["base_per_day"], steady["current_per_day"]), (2.0, 2.0))
        self.assertAlmostEqual(steady["change"], 0)
        self.assertFalse(steady["notable"])

    def test_growth_is_notable(self):
        rows, _ = self.compare()
        growing = rows[self.growing.name]
        self.assertAlmostEqual(growing["change"], 2.0)
        self.assertEqual(growing["expected"], 14.0)
        self.assertTrue(growing["notable"])

    def test_small_numbers_not_notable(self):
        rows, _ = self.compare()
        small = rows[self.small.name]
        self.assertAlmostEqual(small["change"], 0.5)  # 1/7 в день против 3/14
        self.assertFalse(small["notable"])

    def test_zero_base_is_new(self):
        rows, _ = self.compare()
        new = rows[self.new.name]
        self.assertIsNone(new["change"])
        self.assertEqual(new["base_count"], 0)
        self.assertTrue(new["notable"])

    def test_by_category_and_totals(self):
        rows, totals = self.compare(by="category")
        self.assertEqual(rows["Доставка"]["current_count"], 28)
        self.assertEqual((totals["base_count"], totals["current_count"]), (22, 85))
        self.assertAlmostEqual(totals["change"], (85 / 14) / (22 / 7) - 1)

    def test_page(self):
        self.client.force_login(User.objects.get(username="analyst"))
        params = {
            "preset": "custom", "base_from": "2026-09-01", "base_to": "2026-09-07",
            "current_from": "2026-09-08", "current_to": "2026-09-21",
        }
        response = self.client.get(reverse("analytics:compare"), params)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "новое")
        self.assertContains(response, 'class="notable"')
        self.assertContains(response, "(7 дн.)")
        self.assertContains(response, "(14 дн.)")


class CompareFormTests(TestCase):
    def test_week_preset_by_default(self):
        form = compare_form({})
        today = timezone.localdate()
        self.assertEqual(form.current, (today - timedelta(days=6), today))
        self.assertEqual(form.base, (today - timedelta(days=13), today - timedelta(days=7)))

    def test_month_preset(self):
        form = compare_form({"preset": "month"})
        self.assertEqual((form.current[1] - form.current[0]).days, 29)
        self.assertEqual(form.base[1], form.current[0] - timedelta(days=1))

    def test_custom_requires_all_dates(self):
        form = compare_form({"preset": "custom", "base_from": "2026-09-01"})
        self.assertIn("preset", form.errors)
        self.assertEqual(form.cleaned_data["preset"], "week")

    def test_custom_rejects_reversed_period(self):
        form = compare_form(
            {"preset": "custom", "base_from": "2026-09-07", "base_to": "2026-09-01",
             "current_from": "2026-09-08", "current_to": "2026-09-14"}
        )
        self.assertIn("preset", form.errors)

    def test_custom_periods_kept(self):
        form = compare_form(
            {"preset": "custom", "base_from": "2025-09-01", "base_to": "2025-09-30",
             "current_from": "2026-09-01", "current_to": "2026-09-30"}
        )
        self.assertEqual(form.base, (date(2025, 9, 1), date(2025, 9, 30)))
        self.assertEqual(form.current, (date(2026, 9, 1), date(2026, 9, 30)))


class ComparePageAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())

    def test_empty_periods(self):
        self.client.force_login(User.objects.get(username="analyst"))
        response = self.client.get(reverse("analytics:compare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "В обоих периодах нет обращений")
        self.assertContains(response, "нет базы")

    def test_operator_forbidden(self):
        self.client.force_login(User.objects.get(username="operator"))
        self.assertEqual(self.client.get(reverse("analytics:compare")).status_code, 403)
