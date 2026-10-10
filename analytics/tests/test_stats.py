import statistics
from collections import Counter
from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Count
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from analytics import stats
from analytics.forms import PeriodForm, period_form
from appeals.management.commands.generate_appeals import generate
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)
START_DAY, END_DAY = date(2026, 8, 25), date(2026, 9, 23)


def in_period(start, end):
    return Appeal.objects.filter(
        created_at__gte=datetime(start.year, start.month, start.day, tzinfo=MSK),
        created_at__lt=datetime(end.year, end.month, end.day, tzinfo=MSK) + timedelta(days=1),
    )


class StatsMatchOrmTests(TestCase):
    """Числа из pandas сверяются с прямыми подсчётами в базе."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(1500, 3, seed=8, end=END)
        cls.form = period_form({"date_from": START_DAY.isoformat(), "date_to": END_DAY.isoformat()})
        cls.df = stats.load_frame(cls.form.appeals())
        cls.orm = in_period(START_DAY, END_DAY)

    def test_total_and_summary(self):
        s = stats.summary(self.df, START_DAY, END_DAY)
        total = self.orm.count()
        self.assertEqual(s.total, total)
        self.assertEqual(s.days, 30)
        self.assertEqual(s.per_day, round(total / 30, 1))
        self.assertEqual(s.without_category, self.orm.filter(category__isnull=True).count())
        self.assertEqual(s.open_count, self.orm.filter(status__in=["new", "in_work"]).count())
        hours = [
            (a.resolved_at - a.created_at).total_seconds() / 3600 for a in self.orm.exclude(resolved_at=None)
        ]
        self.assertEqual(s.median_resolution_hours, round(statistics.median(hours), 1))

    def test_category_breakdown(self):
        expected = Counter(dict(self.orm.values_list("category__name").annotate(n=Count("id"))))
        expected[stats.NO_CATEGORY] = expected.pop(None, 0)
        got = {row["name"]: row["count"] for row in stats.by_category(self.df)}
        self.assertEqual(got, dict(expected))
        self.assertAlmostEqual(sum(r["share"] for r in stats.by_category(self.df)), 1.0)

    def test_channel_and_status_breakdown(self):
        channels = dict(self.orm.values_list("channel").annotate(n=Count("id")))
        self.assertEqual({r["key"]: r["count"] for r in stats.by_channel(self.df)}, channels)
        statuses = dict(self.orm.values_list("status").annotate(n=Count("id")))
        self.assertEqual({r["key"]: r["count"] for r in stats.by_status(self.df)}, statuses)

    def test_top_reasons(self):
        # При равных числах на границе топа ORM и pandas могут взять разные причины, поэтому сверяем
        # каждое число с базой и порядок чисел, а не набор названий.
        orm_counts = dict(self.orm.exclude(reason=None).values_list("reason__name").annotate(n=Count("id")))
        top = stats.top_reasons(self.df)
        self.assertEqual(len(top), 10)
        for row in top:
            self.assertEqual(row["count"], orm_counts[row["name"]])
        self.assertEqual([r["count"] for r in top], sorted(orm_counts.values(), reverse=True)[:10])

    def test_weekday_hour(self):
        table = stats.weekday_hour(self.df)
        self.assertEqual(sum(row["total"] for row in table["rows"]), self.orm.count())
        cells = Counter(
            {
                (wd - 1, h): n
                for wd, h, n in self.orm.annotate(wd=ExtractIsoWeekDay("created_at", tzinfo=MSK), h=ExtractHour("created_at", tzinfo=MSK))
                .values_list("wd", "h")
                .annotate(n=Count("id"))
            }
        )
        for wd in range(7):
            for h in range(24):
                self.assertEqual(table["rows"][wd]["cells"][h], cells[(wd, h)])

    def test_filters_apply_to_stats(self):
        form = period_form({"date_from": START_DAY.isoformat(), "date_to": END_DAY.isoformat(), "category": "payment", "channel": "app"})
        df = stats.load_frame(form.appeals())
        self.assertEqual(len(df), self.orm.filter(category__slug="payment", channel="app").count())


class ProblemsTests(TestCase):
    """Ручной набор из 20 обращений: предыдущий период A5 B3 C1, текущий A2 B5 C3 D1."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        names = {
            "A": "Задержка доставки",
            "B": "Двойное списание",
            "C": "Приложение вылетает",
            "D": "Брак или повреждение",
        }
        cls.reasons = {key: Reason.objects.get(name=name) for key, name in names.items()}
        appeals = []

        def add(key, count, day, status="resolved"):
            reason = cls.reasons[key]
            for i in range(count):
                created = datetime(2026, 9, day, 10 + i, tzinfo=MSK)
                appeals.append(
                    Appeal(
                        text=key, created_at=created, category=reason.category, reason=reason,
                        category_source="auto", status=status,
                        resolved_at=created + timedelta(hours=4 * (i + 1)) if status == "resolved" else None,
                    )
                )

        # Предыдущий период 1-10 сентября, текущий 11-20.
        add("A", 5, 3)
        add("B", 3, 4)
        add("C", 1, 5)
        add("A", 2, 12)
        add("B", 3, 13)
        add("B", 2, 14, status="new")
        add("C", 3, 15)
        add("D", 1, 16, status="in_work")
        Appeal.objects.bulk_create(appeals)

    def rating(self):
        form = period_form({"date_from": "2026-09-11", "date_to": "2026-09-20"})
        prev_start, prev_end = stats.previous_period(*form.period)
        self.assertEqual((prev_start, prev_end), (date(2026, 9, 1), date(2026, 9, 10)))
        rows = stats.problems(stats.load_frame(form.appeals()), stats.load_frame(form.appeals(prev_start, prev_end)))
        names = {r.name: key for key, r in self.reasons.items()}
        return {names[row["name"]]: row for row in rows}

    def test_ranks_and_changes(self):
        r = self.rating()
        self.assertEqual({k: v["rank"] for k, v in r.items()}, {"B": 1, "C": 2, "A": 3, "D": 4})
        self.assertEqual({k: v["prev_rank"] for k, v in r.items()}, {"B": 2, "C": 3, "A": 1, "D": None})
        self.assertEqual({k: v["rank_change"] for k, v in r.items()}, {"B": 1, "C": 1, "A": -2, "D": None})

    def test_growth_and_counts(self):
        r = self.rating()
        self.assertEqual({k: (v["count"], v["prev_count"]) for k, v in r.items()}, {"B": (5, 3), "C": (3, 1), "A": (2, 5), "D": (1, 0)})
        self.assertAlmostEqual(r["B"]["growth"], 2 / 3)
        self.assertAlmostEqual(r["C"]["growth"], 2.0)
        self.assertAlmostEqual(r["A"]["growth"], -0.6)
        self.assertIsNone(r["D"]["growth"])
        self.assertAlmostEqual(r["B"]["share"], 5 / 11)

    def test_open_share_and_resolution(self):
        r = self.rating()
        self.assertAlmostEqual(r["B"]["open_share"], 2 / 5)
        self.assertEqual(r["D"]["open_share"], 1.0)
        self.assertIsNone(r["D"]["median_resolution_hours"])
        self.assertEqual(r["C"]["median_resolution_hours"], 8.0)  # 4, 8, 12 часов
        self.assertEqual(r["A"]["median_resolution_hours"], 6.0)  # 4 и 8 часов

    def test_ties_share_rank(self):
        self.assertEqual(Appeal.objects.count(), 20)
        reason = self.reasons["D"]
        Appeal.objects.bulk_create(
            [
                Appeal(text="D", created_at=datetime(2026, 9, 17, 12, i, tzinfo=MSK), category=reason.category,
                       reason=reason, category_source="auto")
                for i in range(2)
            ]
        )
        # Теперь в текущем периоде B 5, C 3, D 3, A 2: у C и D общее второе место, A на четвёртом.
        r = self.rating()
        self.assertEqual({k: v["rank"] for k, v in r.items()}, {"B": 1, "C": 2, "D": 2, "A": 4})


class PeriodFormTests(TestCase):
    def test_default_is_last_30_days(self):
        form = period_form({})
        today = timezone.localdate()
        self.assertEqual(form.period, (today - timedelta(days=29), today))

    def test_wrong_dates_fall_back_to_default(self):
        form = period_form({"date_from": "2026-10-05", "date_to": "2026-10-01"})
        self.assertIn("date_to", form.errors)
        self.assertEqual(form.period, (date(2026, 9, 2), date(2026, 10, 1)))
        form = period_form({"date_from": "мусор"})
        self.assertEqual(form.period[1], timezone.localdate())

    def test_period_is_limited(self):
        form = PeriodForm({"date_from": "2020-01-01", "date_to": "2026-01-01"})
        form.is_valid()
        self.assertEqual((form.period[1] - form.period[0]).days, 365)


class PagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(300, 1, seed=2, end=timezone.now())

    def get_as(self, username, url, params=None):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(url, params or {})

    def test_pages_for_analyst_and_admin(self):
        for username in ("analyst", "admin"):
            for name in ("analytics:stats", "analytics:problems"):
                with self.subTest(user=username, page=name):
                    response = self.get_as(username, reverse(name))
                    self.assertEqual(response.status_code, 200)

    def test_operator_forbidden(self):
        for name in ("analytics:stats", "analytics:problems"):
            with self.subTest(page=name):
                self.assertEqual(self.get_as("operator", reverse(name)).status_code, 403)

    def test_stats_page_content(self):
        response = self.get_as("analyst", reverse("analytics:stats"))
        total = response.context["summary"].total
        self.assertGreater(total, 200)
        self.assertContains(response, "Частые причины")
        self.assertContains(response, "По дням недели и часам")
        self.assertContains(response, "?category=")  # строки категорий ведут в отфильтрованный список

    def test_empty_period(self):
        params = {"date_from": "2020-01-01", "date_to": "2020-01-31"}
        self.assertContains(self.get_as("analyst", reverse("analytics:stats"), params), "Нет обращений за период")
        self.assertContains(self.get_as("analyst", reverse("analytics:problems"), params), "Нет обращений")

    def test_problems_page_content(self):
        response = self.get_as("analyst", reverse("analytics:problems"))
        self.assertContains(response, "Изменение места")
        self.assertEqual(response.context["rows"][0]["rank"], 1)
