import random
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from appeals import demo_phrases as dp
from appeals.classify import Classifier
from appeals.management.commands.load_dictionary import read_dictionary
from appeals.models import Category, Reason


def dictionary_reasons():
    return {r["name"] for c in read_dictionary()["categories"] for r in c["reasons"]}


def all_templates():
    texts = [t for items in dp.REASON_TEXTS.values() for t in items]
    return texts + dp.UNCLEAR_TEXTS + dp.INTROS + dp.OUTROS + dp.EMOTIONS + dp.LONG_FRAMES + dp.SUBJECTS


class BankStructureTests(SimpleTestCase):
    def test_bank_matches_dictionary(self):
        bank, dictionary = set(dp.REASON_TEXTS), dictionary_reasons()
        self.assertEqual(dictionary - bank, set(), "причины справочника без формулировок")
        self.assertEqual(bank - dictionary, set(), "причины в банке, которых нет в справочнике")

    def test_six_texts_per_reason(self):
        for reason, texts in dp.REASON_TEXTS.items():
            with self.subTest(reason=reason):
                self.assertGreaterEqual(len(texts), 6)

    def test_no_duplicate_texts(self):
        texts = [t.lower() for items in dp.REASON_TEXTS.values() for t in items] + [
            t.lower() for t in dp.UNCLEAR_TEXTS
        ]
        self.assertEqual(len(texts), len(set(texts)))

    def test_unclear_texts(self):
        self.assertGreaterEqual(len(dp.UNCLEAR_TEXTS), 30)

    def test_placeholders_are_known(self):
        known = set(dp.NUMBERS) | set(dp.CHOICES) | {"core"}
        for template in all_templates():
            with self.subTest(template=template):
                self.assertLessEqual(set(dp.PLACEHOLDER_RE.findall(template)), known)

    def test_long_frames_have_one_core(self):
        for frame in dp.LONG_FRAMES:
            with self.subTest(frame=frame[:40]):
                self.assertEqual(dp.PLACEHOLDER_RE.findall(frame).count("core"), 1)

    def test_fill(self):
        rnd = random.Random(7)
        text = dp.fill("Заказ {order} на {item}: {core}", rnd, core="не приехал")
        self.assertNotIn("{", text)
        self.assertTrue(text.endswith(": не приехал"))
        low, high = dp.NUMBERS["order"]
        self.assertTrue(low <= int(text.split()[1]) <= high)

    def test_numbers_agree_with_words(self):
        self.assertEqual(dp.agree("уже 14 дня, 21 дней, 1 часа, 3 раз, 5 рубля"), "уже 14 дней, 21 день, 1 час, 3 раза, 5 рублей")
        self.assertEqual(dp.agree("заказ 1234567 на 2 дня"), "заказ 1234567 на 2 дня")

    def test_names(self):
        self.assertLessEqual(dp.FEMALE_NAMES, set(dp.FIRST_NAMES))
        self.assertTrue(all(len(pair) == 2 for pair in dp.LAST_NAMES))


class BankClassificationTests(TestCase):
    """Банк проверяется тем же классификатором, что работает в приложении."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        cls.clf = Classifier.from_db()
        cls.reason_category = dict(Reason.objects.values_list("name", "category_id"))
        cls.rnd = random.Random(42)

    def category_of(self, template):
        return self.clf.classify(dp.fill(template, self.rnd, core="")).category_id

    def test_fillers_do_not_carry_category(self):
        # Вступления, концовки, эмоции и рамки длинных историй не должны сдвигать заложенную категорию.
        fillers = dp.INTROS + dp.OUTROS + dp.EMOTIONS + dp.SUBJECTS + dp.LONG_FRAMES
        for template in fillers:
            with self.subTest(template=template[:50]):
                self.assertIsNone(self.category_of(template))

    def test_unclear_texts_stay_empty(self):
        with_category = [t for t in dp.UNCLEAR_TEXTS if self.category_of(t)]
        self.assertEqual(with_category, [])

    def test_bank_is_mostly_recognized(self):
        # Предварительная оценка для шага 7: без опечаток генератора.
        pairs = [(t, self.reason_category[r]) for r, items in dp.REASON_TEXTS.items() for t in items]
        correct = sum(self.category_of(t) == cid for t, cid in pairs)
        self.assertGreaterEqual(correct / len(pairs), 0.85, f"верно {correct} из {len(pairs)}")
        self.assertEqual(Category.objects.count(), 8)
