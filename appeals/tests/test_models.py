from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from appeals.models import Appeal, Category, KeywordRule, Reason, Tag


class AppealModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.payment = Category.objects.create(name="Оплата", slug="payment")
        cls.delivery = Category.objects.create(name="Доставка", slug="delivery")
        cls.card_declined = Reason.objects.create(category=cls.payment, name="Не проходит оплата картой")
        cls.courier_late = Reason.objects.create(category=cls.delivery, name="Курьер опаздывает")

    def test_appeal_without_category(self):
        appeal = Appeal.objects.create(text="Здравствуйте, у меня вопрос")
        self.assertIsNone(appeal.category)
        self.assertEqual(appeal.category_source, Appeal.Source.NONE)
        self.assertEqual(appeal.status, Appeal.Status.NEW)
        self.assertEqual(appeal.category_matches, [])

    def test_tags(self):
        ios, vip = Tag.objects.create(name="iOS"), Tag.objects.create(name="VIP")
        appeal = Appeal.objects.create(text="Не открывается приложение")
        appeal.tags.add(ios, vip)
        self.assertEqual(set(appeal.tags.values_list("name", flat=True)), {"iOS", "VIP"})
        self.assertEqual(list(ios.appeals.all()), [appeal])

    def test_reason_requires_category_in_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appeal.objects.create(text="текст", reason=self.card_declined, category_source="manual")

    def test_auto_source_requires_category(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appeal.objects.create(text="текст", category_source=Appeal.Source.AUTO)

    def test_none_source_forbids_category(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appeal.objects.create(text="текст", category=self.payment, category_source=Appeal.Source.NONE)

    def test_manual_without_category_allowed(self):
        # Оператор может вручную решить, что категории нет, и пересчёт это не тронет.
        appeal = Appeal.objects.create(text="текст", category_source=Appeal.Source.MANUAL)
        self.assertIsNone(appeal.category_id)

    def test_clean_rejects_reason_from_other_category(self):
        appeal = Appeal(
            text="текст",
            category=self.payment,
            reason=self.courier_late,
            category_source=Appeal.Source.MANUAL,
        )
        with self.assertRaises(ValidationError) as ctx:
            appeal.full_clean()
        self.assertIn("reason", ctx.exception.message_dict)

    def test_category_with_appeals_cannot_be_deleted(self):
        Appeal.objects.create(
            text="текст", category=self.payment, reason=self.card_declined, category_source=Appeal.Source.AUTO
        )
        with self.assertRaises(ProtectedError):
            self.card_declined.delete()

    def test_rule_phrase_unique_within_reason(self):
        KeywordRule.objects.create(reason=self.card_declined, phrase="не проходит оплата")
        with self.assertRaises(IntegrityError), transaction.atomic():
            KeywordRule.objects.create(reason=self.card_declined, phrase="не проходит оплата")
        KeywordRule.objects.create(reason=self.courier_late, phrase="не проходит оплата")
