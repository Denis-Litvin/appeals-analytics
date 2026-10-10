from datetime import date, datetime
from io import StringIO
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from analytics import charts, stats
from analytics.forms import period_form
from analytics.models import SpikeAlert
from appeals.management.commands.generate_appeals import generate
from appeals.models import Category

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)
PERIOD = {"date_from": "2026-08-25", "date_to": "2026-09-23"}


def lines(figure):
    return [trace for trace in figure["data"] if trace["mode"] == "lines"]


class ChartDataTests(TestCase):
    """Числа на графиках совпадают с таблицами stats.py, ссылки ведут на тот же срез в списке обращений."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(1500, 3, seed=8, end=END)
        cls.form = period_form(PERIOD)
        cls.df = stats.load_frame(cls.form.appeals())
        cls.figures = charts.dashboard(cls.df, cls.form)

    def setUp(self):
        self.client.force_login(User.objects.get(username="analyst"))

    def found(self, link):
        """Сколько обращений покажет список по ссылке из графика."""
        response = self.client.get(link)
        self.assertEqual(response.status_code, 200)
        return response.context["page"].paginator.count

    def test_categories_match_stats(self):
        pie = self.figures["categories"]["data"][0]
        rows = stats.by_category(self.df)
        self.assertEqual(pie["labels"], [r["name"] for r in rows])
        self.assertEqual(pie["values"], [r["count"] for r in rows])
        self.assertEqual(sum(pie["values"]), len(self.df))

    def test_daily_sums_match_categories(self):
        traces = lines(self.figures["daily"])
        totals = {r["name"]: r["count"] for r in stats.by_category(self.df)}
        self.assertEqual({t["name"]: sum(t["y"]) for t in traces}, totals)
        self.assertEqual(len(traces[0]["x"]), 30)
        self.assertEqual((traces[0]["x"][0], traces[0]["x"][-1]), ("2026-08-25", "2026-09-23"))

    def test_reasons_match_top(self):
        bar = self.figures["reasons"]["data"][0]
        rows = stats.top_reasons(self.df)
        self.assertEqual(bar["x"][::-1], [r["count"] for r in rows])
        self.assertEqual(bar["y"][::-1], [r["name"] for r in rows])

    def test_heatmap_matches(self):
        heat = self.figures["heatmap"]["data"][0]
        table = stats.weekday_hour(self.df)
        self.assertEqual(heat["z"], [row["cells"] for row in table["rows"]])
        self.assertEqual(heat["y"], stats.WEEKDAYS)

    def test_channels_and_statuses_match(self):
        for name, rows in (("channels", stats.by_channel(self.df)), ("statuses", stats.by_status(self.df))):
            with self.subTest(chart=name):
                bar = self.figures[name]["data"][0]
                self.assertEqual(bar["x"], [r["name"] for r in rows])
                self.assertEqual(bar["y"], [r["count"] for r in rows])

    def test_category_click_opens_same_slice(self):
        pie = self.figures["categories"]["data"][0]
        for label, value, link in zip(pie["labels"], pie["values"], pie["customdata"]):
            with self.subTest(category=label):
                query = parse_qs(urlsplit(link).query)
                self.assertEqual(query["date_from"], [PERIOD["date_from"]])
                self.assertEqual(query["date_to"], [PERIOD["date_to"]])
                self.assertEqual(self.found(link), value)

    def test_reason_click(self):
        bar = self.figures["reasons"]["data"][0]
        self.assertEqual(self.found(bar["customdata"][-1]), bar["x"][-1])

    def test_daily_point_click(self):
        trace = lines(self.figures["daily"])[0]
        busiest = max(range(len(trace["y"])), key=trace["y"].__getitem__)
        link = trace["customdata"][busiest]
        query = parse_qs(urlsplit(link).query)
        self.assertEqual(query["date_from"], query["date_to"])
        self.assertEqual(self.found(link), trace["y"][busiest])

    def test_channel_and_status_clicks(self):
        for name in ("channels", "statuses"):
            bar = self.figures[name]["data"][0]
            with self.subTest(chart=name):
                self.assertEqual(self.found(bar["customdata"][0]), bar["y"][0])

    def test_page_filters_kept_in_links(self):
        form = period_form({**PERIOD, "channel": "email"})
        df = stats.load_frame(form.appeals())
        pie = charts.categories(df, charts.link_base(form))["data"][0]
        query = parse_qs(urlsplit(pie["customdata"][0]).query)
        self.assertEqual(query["channel"], ["email"])
        self.assertEqual(self.found(pie["customdata"][0]), pie["values"][0])

    def test_spike_marks(self):
        delivery = Category.objects.get(slug="delivery")
        alert = SpikeAlert.objects.create(category=delivery, day=date(2026, 9, 10), count=40, baseline=9, ratio=4.4)
        figure = charts.daily(self.df, *self.form.period, charts.link_base(self.form), [alert])
        marks = figure["data"][-1]
        line = next(t for t in lines(figure) if t["name"] == "Доставка")
        self.assertEqual(marks["name"], "Всплеск")
        self.assertEqual(marks["x"], ["2026-09-10"])
        self.assertEqual(marks["y"], [line["y"][line["x"].index("2026-09-10")]])
        self.assertIn("40 при норме 9", marks["text"][0])


class DashboardPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(300, 1, seed=5, end=END)
        delivery = Category.objects.get(slug="delivery")
        SpikeAlert.objects.create(category=delivery, day=date(2026, 9, 20), count=30, baseline=8, ratio=3.75)
        SpikeAlert.objects.create(category=delivery, day=date(2026, 7, 1), count=30, baseline=8, ratio=3.75)

    def get(self, username, params=None):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(reverse("analytics:dashboard"), params or {})

    def test_analyst_sees_charts_offline(self):
        response = self.get("analyst", {"date_from": "2026-09-01", "date_to": "2026-09-30"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["charts"]), {"daily", "categories", "reasons", "heatmap", "channels", "statuses"})
        self.assertContains(response, f'<script src="/assets/plotly-{charts.PLOTLY_VERSION}.min.js"></script>', html=True)
        self.assertContains(response, 'id="charts-data"')
        self.assertNotContains(response, "cdn")
        self.assertNotContains(response, "https://")

    def test_only_period_alerts_marked(self):
        response = self.get("analyst", {"date_from": "2026-09-01", "date_to": "2026-09-30"})
        marks = response.context["charts"]["daily"]["data"][-1]
        self.assertEqual(marks["x"], ["2026-09-20"])

    def test_empty_period(self):
        response = self.get("analyst", {"date_from": "2020-01-01", "date_to": "2020-01-31"})
        self.assertContains(response, "Нет данных за период.")
        self.assertNotContains(response, "plotly")

    def test_operator_forbidden(self):
        self.assertEqual(self.get("operator").status_code, 403)


class PlotlyJsTests(TestCase):
    def test_served_from_package_with_cache(self):
        response = self.client.get(reverse("analytics:plotly_js", args=[charts.PLOTLY_VERSION]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/javascript; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(response.content, charts.PLOTLY_JS.read_bytes())

    def test_other_version_not_found(self):
        self.assertEqual(self.client.get(reverse("analytics:plotly_js", args=["0.0.1"])).status_code, 404)
