import random
import statistics
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase

from appeals.management.commands.generate_appeals import SPIKES, generate, typo
from appeals.models import Appeal, Category
from appeals.roles import OPERATOR

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)


def prepare():
    call_command("load_dictionary", stdout=StringIO())
    call_command("setup_roles", "--demo-users", stdout=StringIO())


def snapshot():
    return [
        (a.text, a.subject, a.created_at, a.channel, a.status, a.author_email, tuple(t.name for t in a.tags.all()))
        for a in Appeal.objects.order_by("created_at", "id").prefetch_related("tags")
    ]


class TypoTests(TestCase):
    def test_typo_is_one_edit_and_keeps_first_letter(self):
        rnd = random.Random(1)
        for word in ["курьер", "оплата", "приложение", "возврат", "доставка"] * 20:
            changed = typo(word, rnd)
            self.assertEqual(changed[0], word[0])
            self.assertLessEqual(abs(len(changed) - len(word)), 1)


class DeterminismTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        prepare()

    def test_same_seed_same_data(self):
        generate(500, 2, seed=11, end=END, clear=True)
        first = snapshot()
        generate(500, 2, seed=11, end=END, clear=True)
        self.assertEqual(snapshot(), first)
        self.assertEqual(len(first), 500)

    def test_other_seed_other_data(self):
        generate(500, 2, seed=11, end=END, clear=True)
        first = [row[0] for row in snapshot()]
        generate(500, 2, seed=12, end=END, clear=True)
        self.assertNotEqual([row[0] for row in snapshot()], first)


class EmptyDictionaryTests(TestCase):
    def test_requires_dictionary(self):
        with self.assertRaises(CommandError):
            generate(100, 1, seed=1, end=END)


class GeneratedDataTests(TestCase):
    """Одна генерация на 3000 обращений за полгода, проверки по свойствам данных."""

    @classmethod
    def setUpTestData(cls):
        prepare()
        cls.stats = generate(3000, 6, seed=5, end=END)
        cls.appeals = list(Appeal.objects.select_related("category", "assignee").prefetch_related("tags"))

    def test_count_and_period(self):
        self.assertEqual(self.stats.total, 3000)
        self.assertLessEqual(max(a.created_at for a in self.appeals), END)
        self.assertGreaterEqual(min(a.created_at for a in self.appeals), END - timedelta(days=184))

    def test_weekdays_busier_than_weekends(self):
        by_wd = self.stats.by_weekday
        workdays = statistics.mean(by_wd[d] for d in range(5))
        weekend = statistics.mean(by_wd[d] for d in (5, 6))
        self.assertGreater(workdays, weekend * 1.25)

    def test_day_busier_than_night(self):
        hours = [a.created_at.astimezone(MSK).hour for a in self.appeals]
        night = sum(h < 7 for h in hours)
        day = sum(10 <= h < 17 for h in hours)
        self.assertGreater(day, night * 5)

    def test_volume_grows(self):
        start = min(a.created_at for a in self.appeals)
        first_month = sum(a.created_at < start + timedelta(days=30) for a in self.appeals)
        last_month = sum(a.created_at > END - timedelta(days=30) for a in self.appeals)
        self.assertGreater(last_month, first_month * 1.2)

    def test_share_without_category(self):
        share = sum(a.category_id is None for a in self.appeals) / len(self.appeals)
        self.assertTrue(0.10 <= share <= 0.20, f"без категории {share:.1%}")

    def test_auto_category_accuracy(self):
        self.assertGreaterEqual(self.stats.auto_correct / self.stats.intended, 0.8)

    def test_manual_categories(self):
        manual = [a for a in self.appeals if a.category_source == Appeal.Source.MANUAL]
        self.assertTrue(0.01 <= len(manual) / len(self.appeals) <= 0.08)
        self.assertTrue(all(a.category_id for a in manual))

    def test_spikes_stand_out(self):
        self.assertEqual(len(self.stats.spikes), sum(length for _, length, _, _ in SPIKES))
        for day, reason, count, median in self.stats.spikes:
            with self.subTest(day=day, reason=reason):
                self.assertGreaterEqual(count, 5 * max(median, 1))

    def test_text_variety(self):
        words = sorted(self.stats.words)
        self.assertLessEqual(words[0], 3)
        self.assertGreaterEqual(words[-1], 35)
        self.assertTrue(any("\n\n" in a.text for a in self.appeals))
        self.assertGreater(len({a.text for a in self.appeals}), 2500)

    def test_statuses_and_resolution(self):
        for a in self.appeals:
            if a.status in ("new", "in_work"):
                self.assertIsNone(a.resolved_at)
            else:
                self.assertTrue(a.created_at < a.resolved_at <= END)
        old = [a for a in self.appeals if a.created_at < END - timedelta(days=14)]
        self.assertGreater(sum(a.status in ("resolved", "closed") for a in old) / len(old), 0.9)
        fresh = [a for a in self.appeals if a.created_at > END - timedelta(hours=12)]
        self.assertTrue(all(a.status in ("new", "in_work") for a in fresh))

    def test_assignees_are_operators(self):
        operators = set(User.objects.filter(groups__name=OPERATOR).values_list("id", flat=True))
        assigned = {a.assignee_id for a in self.appeals if a.assignee_id}
        self.assertEqual(assigned, operators)
        self.assertTrue(all(a.assignee_id is None for a in self.appeals if a.status == "new"))

    def test_device_tags(self):
        for a in self.appeals:
            if "айфон" in a.text.lower():
                self.assertIn("iOS", [t.name for t in a.tags.all()])
        self.assertTrue(any(a.tags.all() for a in self.appeals))

    def test_text_norm_filled(self):
        self.assertTrue(all(a.text_norm for a in self.appeals))


class CommandsTests(TestCase):
    def test_setup_demo(self):
        out = StringIO()
        call_command("setup_demo", "--count", "400", "--months", "2", stdout=out)
        self.assertEqual(Appeal.objects.count(), 400)
        self.assertEqual(Category.objects.count(), 8)
        self.assertEqual(User.objects.count(), 5)
        text = out.getvalue()
        self.assertIn("Автокатегория совпала с заложенной", text)
        self.assertIn("Всплеск", text)
        self.assertIn("пароль demo12345", text)

        out = StringIO()
        call_command("setup_demo", "--count", "300", "--months", "2", stdout=out)
        self.assertIn("генерация пропущена", out.getvalue())
        self.assertEqual(Appeal.objects.count(), 400)

        call_command("setup_demo", "--count", "300", "--months", "2", "--reset", stdout=StringIO())
        self.assertEqual(Appeal.objects.count(), 300)
