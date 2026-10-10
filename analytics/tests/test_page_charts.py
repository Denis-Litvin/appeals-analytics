from datetime import datetime
from io import StringIO
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from analytics import charts
from appeals.management.commands.generate_appeals import generate

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-28"}
COMPARE = {
    "preset": "custom", "base_from": "2026-08-01", "base_to": "2026-08-21",
    "current_from": "2026-09-01", "current_to": "2026-09-28",
}


class PageChartsTests(TestCase):
    """Графики на страницах статистики, рейтинга и сравнения показывают те же числа, что таблицы рядом."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(1500, 3, seed=8, end=END)

    def setUp(self):
        self.client.force_login(User.objects.get(username="analyst"))

    def get(self, name, params):
        response = self.client.get(reverse(name), params)
        self.assertEqual(response.status_code, 200)
        return response

    def found(self, link):
        return self.client.get(link).context["page"].paginator.count

    def test_stats_charts_match_tables(self):
        context = self.get("analytics:stats", PERIOD).context
        figures = context["charts"]
        pie = figures["categories"]["data"][0]
        self.assertEqual(pie["values"], [r["count"] for r in context["categories"]])
        self.assertEqual(pie["labels"], [r["name"] for r in context["categories"]])
        bar = figures["reasons"]["data"][0]
        self.assertEqual(bar["x"][::-1], [r["count"] for r in context["reasons"]])
        self.assertEqual(figures["channels"]["data"][0]["y"], [r["count"] for r in context["channels"]])
        self.assertEqual(figures["statuses"]["data"][0]["y"], [r["count"] for r in context["statuses"]])
        heat = figures["heatmap"]["data"][0]
        self.assertEqual(sum(map(sum, heat["z"])), context["summary"].total)

    def test_stats_page_loads_charts(self):
        response = self.get("analytics:stats", PERIOD)
        self.assertContains(response, 'id="chart-heatmap"')
        self.assertContains(response, 'id="charts-data"')
        self.assertContains(response, charts.PLOTLY_VERSION)

    def test_problems_chart_matches_table(self):
        context = self.get("analytics:problems", PERIOD).context
        rows = context["rows"][: charts.PROBLEMS_LIMIT]
        previous, current = context["charts"]["problems"]["data"]
        self.assertEqual(len(current["y"]), charts.PROBLEMS_LIMIT)
        self.assertEqual(current["y"][::-1], [r["name"] for r in rows])
        self.assertEqual(current["x"][::-1], [r["count"] for r in rows])
        self.assertEqual(previous["x"][::-1], [r["prev_count"] for r in rows])
        self.assertEqual(current["text"][::-1], [charts.growth_label(r["growth"]) for r in rows])

    def test_problems_bars_open_their_period(self):
        context = self.get("analytics:problems", PERIOD).context
        previous, current = context["charts"]["problems"]["data"]
        self.assertEqual(self.found(current["customdata"][-1]), current["x"][-1])
        self.assertEqual(self.found(previous["customdata"][-1]), previous["x"][-1])
        query = parse_qs(urlsplit(previous["customdata"][-1]).query)
        self.assertEqual((query["date_from"], query["date_to"]), (["2026-08-04"], ["2026-08-31"]))

    def test_growth_label(self):
        self.assertEqual(charts.growth_label(0.254), "+25%")
        self.assertEqual(charts.growth_label(-0.4), "-40%")
        self.assertEqual(charts.growth_label(None), "новая")

    def test_compare_charts_match_table(self):
        context = self.get("analytics:compare", COMPARE).context
        base, current = context["charts"]["categories"]["data"]
        rows = context["categories"]
        self.assertEqual(base["x"], [r["name"] for r in rows])
        self.assertEqual(base["y"], [r["base_per_day"] for r in rows])
        self.assertEqual(current["y"], [r["current_per_day"] for r in rows])
        base_line, current_line = context["charts"]["daily"]["data"]
        self.assertEqual(len(base_line["x"]), 21)
        self.assertEqual(len(current_line["x"]), 28)
        self.assertEqual(sum(base_line["y"]), context["totals"]["base_count"])
        self.assertEqual(sum(current_line["y"]), context["totals"]["current_count"])

    def test_compare_bars_open_their_period(self):
        context = self.get("analytics:compare", COMPARE).context
        base, current = context["charts"]["categories"]["data"]
        rows = context["categories"]
        self.assertEqual(self.found(base["customdata"][0]), rows[0]["base_count"])
        self.assertEqual(self.found(current["customdata"][0]), rows[0]["current_count"])
        line = context["charts"]["daily"]["data"][1]
        self.assertEqual(self.found(line["customdata"][0]), line["y"][0])

    def test_empty_period(self):
        empty = {"date_from": "2020-01-01", "date_to": "2020-01-31"}
        empty_compare = {
            "preset": "custom", "base_from": "2020-01-01", "base_to": "2020-01-07",
            "current_from": "2020-01-08", "current_to": "2020-01-14",
        }
        for name, params in (
            ("analytics:stats", empty), ("analytics:problems", empty), ("analytics:compare", empty_compare)
        ):
            with self.subTest(page=name):
                response = self.get(name, params)
                self.assertContains(response, "Нет данных за период.")
                self.assertNotIn("charts", response.context)
                self.assertNotContains(response, "charts-data")
