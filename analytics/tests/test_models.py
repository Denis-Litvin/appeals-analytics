from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from analytics.models import SpikeAlert
from appeals.models import Category, Reason


class SpikeAlertTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Оплата", slug="payment")
        cls.reason = Reason.objects.create(category=cls.category, name="Двойное списание")
        cls.day = date(2026, 9, 15)

    def make(self, reason=None):
        return SpikeAlert.objects.create(
            category=self.category, reason=reason, day=self.day, count=40, baseline=12, ratio=3.3
        )

    def test_one_category_alert_per_day(self):
        self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make()

    def test_one_reason_alert_per_day(self):
        self.make(self.reason)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(self.reason)

    def test_category_and_reason_alerts_coexist(self):
        self.make()
        self.make(self.reason)
        self.assertEqual(SpikeAlert.objects.filter(day=self.day).count(), 2)
