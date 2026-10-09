from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from appeals.classify import Classifier, Rule, one_edit
from appeals.models import Appeal, Category, KeywordRule, Reason
from appeals.text import phrase_stems

from .labeled_texts import HOLDOUT, LABELED


def make_classifier(*rules):
    """Классификатор без базы: (id причины, id категории, фраза, вес)."""
    return Classifier([Rule(rid, cid, phrase, weight, phrase_stems(phrase)) for rid, cid, phrase, weight in rules])


class OneEditTests(SimpleTestCase):
    def test_single_edits(self):
        self.assertTrue(one_edit("курьер", "курер"))  # пропуск
        self.assertTrue(one_edit("постамат", "постоамат"))  # лишняя буква
        self.assertTrue(one_edit("постамат", "постомат"))  # замена
        self.assertTrue(one_edit("списал", "спсиал"))  # перестановка соседних

    def test_two_edits_rejected(self):
        self.assertFalse(one_edit("поменя", "обменя"))
        self.assertFalse(one_edit("описан", "отписа"))
        self.assertFalse(one_edit("курьер", "курьер"))


class MatchingTests(SimpleTestCase):
    def setUp(self):
        self.clf = make_classifier(
            (1, 10, "не проходит оплата", 3),
            (2, 10, "не привязывается карта", 3),
            (3, 20, "курьер опаздывает", 3),
            (4, 20, "не дозвониться", 3),
            (5, 30, "разбит", 3),
            (6, 40, "ошибка", 1),
            (7, 50, "пункт выдачи", 3),
            (8, 60, "нагрубил", 3),
            (9, 70, "отписаться", 3),
        )

    def found(self, text):
        return {m["phrase"] for m in self.clf.classify(text).matches}

    def test_any_word_order(self):
        self.assertIn("не привязывается карта", self.found("карта не привязывается"))
        self.assertIn("не проходит оплата", self.found("Оплата у меня не проходит"))

    def test_negation_must_precede_its_word(self):
        self.assertNotIn("не проходит оплата", self.found("оплата проходит, но не сразу"))

    def test_window_limit(self):
        far = "не проходит у меня уже третий день подряд никакая оплата"
        self.assertNotIn("не проходит оплата", self.found(far))

    def test_typo_in_long_word(self):
        self.assertIn("курьер опаздывает", self.found("курер опаздывает"))

    def test_typo_must_keep_first_letter(self):
        self.assertNotIn("не дозвониться", self.found("курьер не позвонил"))

    def test_typo_in_ending(self):
        self.assertIn("курьер опаздывает", self.found("курер опаздывет"))

    def test_shortened_word_needs_same_length(self):
        # «описанию» без последней буквы отличается от «отписаться» одной вставкой, это не опечатка.
        self.assertNotIn("отписаться", self.found("не соответствует описанию"))

    def test_short_form_of_participle(self):
        self.assertIn("разбит", self.found("пришла разбитая ваза"))

    def test_thresholds(self):
        self.assertIsNone(self.clf.classify("какая-то ошибка").category_id)  # 1 балл меньше порога
        tie = self.clf.classify("в пункте выдачи нагрубил сотрудник")
        self.assertIsNone(tie.category_id)  # 3 против 3, нет перевеса в полтора раза
        self.assertEqual(len(tie.matches), 2)
        clear = self.clf.classify("карта не привязывается, пишет ошибка")
        self.assertEqual((clear.category_id, clear.reason_id, clear.score), (10, 2, 3))


class LabeledSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        cls.clf = Classifier.from_db()
        cls.slugs = dict(Category.objects.values_list("id", "slug"))
        cls.reasons = dict(Reason.objects.values_list("id", "name"))

    def predict(self, text):
        result = self.clf.classify(text)
        return self.slugs.get(result.category_id), self.reasons.get(result.reason_id)

    def test_category_accuracy(self):
        known = [(t, c) for t, c, _ in LABELED if c]
        correct = sum(self.predict(t)[0] == c for t, c in known)
        self.assertEqual(len(known), 55)
        self.assertGreaterEqual(correct / len(known), 0.8, f"верно {correct} из {len(known)}")

    def test_reason_accuracy(self):
        known = [(t, r) for t, c, r in LABELED if c]
        correct = sum(self.predict(t)[1] == r for t, r in known)
        self.assertGreaterEqual(correct / len(known), 0.75, f"верно {correct} из {len(known)}")

    def test_unclear_texts_stay_empty(self):
        unclear = [t for t, c, _ in LABELED if c is None]
        empty = sum(self.predict(t)[0] is None for t in unclear)
        self.assertEqual(len(unclear), 15)
        self.assertGreaterEqual(empty, 12)

    def test_holdout_accuracy(self):
        correct = sum(self.predict(t)[0] == c for t, c in HOLDOUT)
        self.assertGreaterEqual(correct / len(HOLDOUT), 0.8, f"верно {correct} из {len(HOLDOUT)}")

    def test_typos_in_dictionary_words(self):
        self.assertEqual(self.predict("списли два раза за один заказ")[0], "payment")
        self.assertEqual(self.predict("пастамат не открывается")[0], "delivery")
        self.assertEqual(self.predict("курьер апаздывает")[0], None)  # опечатка в первой букве не прощается
        self.assertEqual(self.predict("приложение вылитает каждый раз")[0], "app")


class AppealSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        cls.payment = Category.objects.get(slug="payment")
        cls.delivery = Category.objects.get(slug="delivery")

    def test_new_appeal_gets_category(self):
        appeal = Appeal.objects.create(text="Деньги списали дважды за один заказ")
        self.assertEqual(appeal.category, self.payment)
        self.assertEqual(appeal.reason.name, "Двойное списание")
        self.assertEqual(appeal.category_source, Appeal.Source.AUTO)
        self.assertTrue(appeal.text_norm.startswith("деньг списа"))
        self.assertIn("списали дважды", [m["phrase"] for m in appeal.category_matches])

    def test_subject_is_classified_too(self):
        appeal = Appeal.objects.create(subject="Двойное списание", text="Посмотрите, пожалуйста")
        self.assertEqual(appeal.category, self.payment)

    def test_unclear_appeal(self):
        appeal = Appeal.objects.create(text="Добрый день, подскажите")
        self.assertIsNone(appeal.category)
        self.assertEqual(appeal.category_source, Appeal.Source.NONE)

    def test_status_change_keeps_category(self):
        appeal = Appeal.objects.create(text="Деньги списали дважды")
        KeywordRule.objects.filter(phrase="списали дважды").delete()
        appeal = Appeal.objects.get(pk=appeal.pk)
        appeal.status = Appeal.Status.IN_WORK
        appeal.save()
        self.assertEqual(Appeal.objects.get(pk=appeal.pk).category, self.payment)

    def test_text_change_reclassifies(self):
        appeal = Appeal.objects.create(text="Деньги списали дважды")
        appeal = Appeal.objects.get(pk=appeal.pk)
        appeal.text = "Курьер опоздал на три часа"
        appeal.save()
        self.assertEqual(Appeal.objects.get(pk=appeal.pk).category, self.delivery)

    def test_manual_category_survives_text_change(self):
        reason = self.delivery.reasons.get(name="Задержка доставки")
        appeal = Appeal.objects.create(
            text="Деньги списали дважды", category=self.delivery, reason=reason, category_source=Appeal.Source.MANUAL
        )
        self.assertEqual(appeal.category, self.delivery)
        appeal.text = "Списали дважды, курьер ни при чем"
        appeal.save()
        self.assertEqual(Appeal.objects.get(pk=appeal.pk).category, self.delivery)
        self.assertTrue(Appeal.objects.get(pk=appeal.pk).text_norm.startswith("списа"))


class RecategorizeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())

    def test_command_skips_manual(self):
        delivery = Category.objects.get(slug="delivery")
        auto = Appeal.objects.create(text="Курьер опаздывает уже час")
        manual = Appeal.objects.create(
            text="Курьер опаздывает уже час", category=delivery, category_source=Appeal.Source.MANUAL
        )
        Appeal.objects.filter(pk__in=[auto.pk, manual.pk]).update(text_norm="")
        # Словарь поменялся: фраза про курьера теперь ведёт в обслуживание.
        service_reason = Reason.objects.get(name="Грубость сотрудника")
        KeywordRule.objects.filter(phrase__startswith="курьер").update(reason=service_reason)
        out = StringIO()
        call_command("recategorize", stdout=out)
        self.assertEqual(Appeal.objects.get(pk=auto.pk).category.slug, "service")
        self.assertEqual(Appeal.objects.get(pk=manual.pk).category, delivery)
        self.assertEqual(Appeal.objects.get(pk=manual.pk).text_norm, "")
        self.assertNotEqual(Appeal.objects.get(pk=auto.pk).text_norm, "")
        self.assertIn("категория изменилась у 1", out.getvalue())

    def test_admin_action_only_with_dictionary_permission(self):
        appeal = Appeal.objects.create(text="Курьер опаздывает")
        Appeal.objects.filter(pk=appeal.pk).update(category=None, reason=None, category_source="none")

        clerk = User.objects.create_user("clerk", is_staff=True)
        clerk.user_permissions.add(Permission.objects.get(codename="view_appeal"))
        self.client.force_login(clerk)
        self.assertNotIn("recategorize_selected", self.client.get("/admin/appeals/appeal/").content.decode())

        self.client.force_login(User.objects.get(username="admin"))
        self.assertIn("recategorize_selected", self.client.get("/admin/appeals/appeal/").content.decode())
        response = self.client.post(
            "/admin/appeals/appeal/", {"action": "recategorize_selected", "_selected_action": [appeal.pk]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appeal.objects.get(pk=appeal.pk).category.slug, "delivery")
