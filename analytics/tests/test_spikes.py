from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from analytics import spikes
from analytics.models import SpikeAlert
from appeals.management.commands.generate_appeals import generate
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")
DAY = date(2026, 9, 30)  # среда


def table(history, today, days=28, key=1):
    """Таблица день × ключ: history повторяется по кругу за days дней до DAY, today в сам день DAY."""
    index = pd.date_range(DAY - timedelta(days=days), DAY, freq="D")
    values = [history[i % len(history)] for i in range(days)] + [today]
    return pd.DataFrame({key: values}, index=index)


def found(data, level="category", **kwargs):
    return spikes.find(data, DAY, DAY, level, **kwargs)


class FindTests(TestCase):
    """Каждое из трёх условий проверяется отдельно: остальные два выполнены."""

    def test_clear_spike(self):
        self.assertEqual(found(table([10], 30)), [(DAY, 1, 30, 10.0)])

    def test_ratio_below_two(self):
        # Превышение 15 и далеко за разбросом, но рост меньше чем вдвое.
        self.assertEqual(found(table([20], 35)), [])
        self.assertEqual(len(found(table([20], 40))), 1)

    def test_excess_too_small(self):
        # С 1 до 6: рост в 6 раз, разброса нет, но превышение 5. Для категории мало, для причины хватает.
        self.assertEqual(found(table([1], 6), "category"), [])
        self.assertEqual(found(table([1], 6), "reason"), [(DAY, 1, 6, 1.0)])

    def test_within_noise(self):
        # Ряд 0, 20, 0, 20: медиана 10, разброс 14,8. 26 вдвое больше медианы, но в пределах колебаний.
        self.assertEqual(found(table([0, 20], 26)), [])
        self.assertEqual(len(found(table([0, 20], 60))), 1)

    def test_short_history_skipped(self):
        self.assertEqual(found(table([10], 50, days=10)), [])

    def test_days_before_first_appeal_not_history(self):
        # Данные начались 10 дней назад, до этого нули. Без first_day это 18 нулевых дней и «рост с нуля».
        data = table([0] * 18 + [3] * 10, 12)
        self.assertEqual(len(found(data)), 1)
        self.assertEqual(found(data, first_day=DAY - timedelta(days=10)), [])

    def test_partial_today(self):
        # К середине дня обычно приходит половина потока: 15 к обеду при норме 10 в сутки уже всплеск.
        self.assertEqual(found(table([10], 15)), [])
        self.assertEqual(found(table([10], 15), today=DAY, today_share=0.5), [(DAY, 1, 15, 5.0)])

    def test_weekday_correction(self):
        # По понедельникам обращений вдвое больше. Без поправки обычный понедельник выглядит всплеском.
        monday = date(2026, 9, 28)
        index = pd.date_range(monday - timedelta(days=28), monday, freq="D")
        data = pd.DataFrame({1: [22 if d.weekday() == 0 else 10 for d in index]}, index=index)
        self.assertEqual(len(spikes.find(data, monday, monday, "category")), 1)
        self.assertEqual(spikes.find(data, monday, monday, "category", totals=data[1]), [])

    def test_weekday_factors(self):
        index = pd.date_range(date(2026, 8, 31), periods=28, freq="D")
        totals = pd.Series([20 if d.weekday() == 0 else 10 for d in index], index=index)
        factors = spikes.weekday_factors(totals)
        mean = totals.mean()
        self.assertAlmostEqual(factors[0], 20 / mean)
        self.assertAlmostEqual(factors[3], 10 / mean)
        self.assertEqual(spikes.weekday_factors(totals * 0), {wd: 1.0 for wd in range(7)})

    def test_ratio_from_zero_baseline(self):
        self.assertEqual(spikes.Spike(DAY, 1, None, 12, 0.0).ratio, 12.0)
        self.assertEqual(spikes.Spike(DAY, 1, None, 12, 4.0).ratio, 3.0)


class GeneratedDataTests(TestCase):
    """Демо-генератор закладывает 4 всплеска. Детектор должен найти все и почти не шуметь."""

    END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        cls.stats = generate(6000, 6, seed=42, end=cls.END)
        cls.found = spikes.detect(cls.stats.start, cls.stats.end, now=cls.END)
        cls.reason_ids = dict(Reason.objects.values_list("name", "id"))
        cls.reason_category = dict(Reason.objects.values_list("name", "category_id"))

    def test_all_planted_found(self):
        reason_hits = {(s.day, s.reason_id) for s in self.found if s.reason_id}
        category_hits = {(s.day, s.category_id) for s in self.found if not s.reason_id}
        planted_reasons = {reason for _, reason, _, _ in self.stats.spikes}
        self.assertEqual(len(planted_reasons), 4)
        for day, reason, count, usual in self.stats.spikes:
            with self.subTest(day=day, reason=reason):
                self.assertIn((day, self.reason_ids[reason]), reason_hits)
                self.assertIn((day, self.reason_category[reason]), category_hits)

    def test_few_false_alarms_by_category(self):
        planted = {(day, self.reason_category[reason]) for day, reason, _, _ in self.stats.spikes}
        extra = [s for s in self.found if not s.reason_id and (s.day, s.category_id) not in planted]
        self.assertLessEqual(len(extra), 5, extra)

    def test_save_is_idempotent(self):
        first = spikes.save(self.found)
        self.assertEqual(len(first), len(self.found))
        self.assertEqual(spikes.save(self.found), [])
        self.assertEqual(SpikeAlert.objects.count(), len(self.found))

    def test_save_updates_count(self):
        spike = self.found[0]
        spikes.save([spike])
        spikes.save([spikes.Spike(spike.day, spike.category_id, spike.reason_id, spike.count + 5, spike.baseline)])
        alert = SpikeAlert.objects.get()
        self.assertEqual(alert.count, spike.count + 5)


class NewAppealTests(TestCase):
    """28 дней по 2 обращения в день на причину «Приложение вылетает», сегодня уже 20."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.reason = Reason.objects.get(name="Приложение вылетает")
        today = timezone.localdate()
        appeals = []
        for days_ago in range(1, 29):
            day = today - timedelta(days=days_ago)
            for hour in (11, 15):
                appeals.append(Appeal(created_at=datetime(day.year, day.month, day.day, hour, tzinfo=MSK)))
        appeals += [Appeal(created_at=timezone.now()) for _ in range(20)]
        for appeal in appeals:
            appeal.text = "Приложение вылетает при запуске"
            appeal.category, appeal.reason, appeal.category_source = cls.reason.category, cls.reason, "auto"
        Appeal.objects.bulk_create(appeals)

    def create(self):
        return self.client.post(
            reverse("appeals:create"),
            {"channel": "app", "author_name": "Павел", "author_email": "", "subject": "",
             "text": "Приложение вылетает сразу после запуска, переустановка не помогла"},
            follow=True,
        )

    def test_first_appeal_creates_alerts_and_mail(self):
        self.client.force_login(User.objects.get(username="operator"))
        response = self.create()
        self.assertEqual(Appeal.objects.latest("id").reason, self.reason)
        self.assertEqual(SpikeAlert.objects.count(), 2)  # по категории и по причине
        self.assertContains(response, "Резкий рост")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Резкий рост обращений: 2")
        self.assertIn("analyst@example.com", mail.outbox[0].to)
        self.assertNotIn("operator@example.com", mail.outbox[0].to)

    def test_next_appeal_updates_alert(self):
        self.client.force_login(User.objects.get(username="operator"))
        self.create()
        response = self.create()
        self.assertNotContains(response, "Резкий рост")
        self.assertEqual(SpikeAlert.objects.count(), 2)
        alert = SpikeAlert.objects.get(reason=self.reason)
        self.assertEqual(alert.count, 22)
        self.assertEqual(len(mail.outbox), 1)

    def test_appeal_without_category_skipped(self):
        self.assertEqual(spikes.check_appeal(Appeal(text="Добрый день")), [])

    def test_command(self):
        out = StringIO()
        call_command("check_spikes", stdout=out)
        self.assertIn("новых уведомлений: 2", out.getvalue())
        self.assertIn("Приложение вылетает: 20", out.getvalue())
        call_command("check_spikes", "--notify", stdout=out)
        self.assertEqual(len(mail.outbox), 0)  # новых нет, письмо не нужно


class AlertsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        reason = Reason.objects.get(name="Двойное списание")
        cls.first = SpikeAlert.objects.create(
            category=reason.category, reason=reason, day=date(2026, 9, 10), count=30, baseline=4, ratio=7.5
        )
        cls.second = SpikeAlert.objects.create(
            category=reason.category, day=date(2026, 9, 11), count=41, baseline=12, ratio=3.42
        )
        cls.analyst = User.objects.get(username="analyst")

    def test_analyst_sees_alerts_and_counter(self):
        self.client.force_login(self.analyst)
        response = self.client.get(reverse("analytics:alerts"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["unread_alerts"], 2)
        self.assertContains(response, '<span class="counter">2</span>', html=True)
        self.assertContains(response, "Оплата: Двойное списание")
        self.assertContains(response, "в 7,5 раза")
        self.assertContains(response, "date_from=2026-09-10&date_to=2026-09-10")

    def test_operator_has_no_counter_and_forbidden(self):
        self.client.force_login(User.objects.get(username="operator"))
        response = self.client.get(reverse("appeals:list"))
        self.assertNotIn("unread_alerts", response.context)
        self.assertNotContains(response, 'class="counter"')
        self.assertEqual(self.client.get(reverse("analytics:alerts")).status_code, 403)
        self.assertEqual(self.client.post(reverse("analytics:alerts_read_all")).status_code, 403)

    def test_read_one(self):
        self.client.force_login(self.analyst)
        url = reverse("analytics:alerts")
        response = self.client.post(reverse("analytics:alerts_read", args=[self.first.pk]), {"next": url + "?unread=1"})
        self.assertRedirects(response, url + "?unread=1")
        self.assertTrue(self.first.read_by.filter(pk=self.analyst.pk).exists())
        response = self.client.get(url, {"unread": "1"})
        self.assertEqual(response.context["unread_alerts"], 1)
        self.assertEqual(list(response.context["page"].object_list), [self.second])
        # Второе уведомление осталось непрочитанным.
        self.assertFalse(self.second.read_by.exists())

    def test_read_all(self):
        self.client.force_login(self.analyst)
        self.client.post(reverse("analytics:alerts_read_all"))
        response = self.client.get(reverse("analytics:alerts"), {"unread": "1"})
        self.assertEqual(response.context["unread_alerts"], 0)
        self.assertContains(response, "Непрочитанных уведомлений нет.")

    def test_foreign_next_ignored(self):
        self.client.force_login(self.analyst)
        response = self.client.post(reverse("analytics:alerts_read_all"), {"next": "https://example.org/"})
        self.assertRedirects(response, reverse("analytics:alerts"))

    def test_read_requires_post(self):
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(reverse("analytics:alerts_read_all")).status_code, 405)
