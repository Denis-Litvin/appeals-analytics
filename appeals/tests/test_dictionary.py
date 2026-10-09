from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from appeals.management.commands.load_dictionary import read_dictionary, validate
from appeals.models import Appeal, Category, KeywordRule, Reason, Tag


def counts():
    return (Category.objects.count(), Reason.objects.count(), KeywordRule.objects.count(), Tag.objects.count())


class DictionaryFileTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = read_dictionary()

    def test_file_has_no_errors(self):
        self.assertEqual(validate(self.data), [])

    def test_size(self):
        reasons = [r for c in self.data["categories"] for r in c["reasons"]]
        phrases = [p for r in reasons for p in r["phrases"]]
        self.assertEqual(len(self.data["categories"]), 8)
        self.assertEqual(len(reasons), 30)
        self.assertGreaterEqual(len(phrases), 250)
        self.assertEqual(len(self.data["tags"]), 10)

    def test_every_reason_has_five_phrases(self):
        for category in self.data["categories"]:
            for reason in category["reasons"]:
                with self.subTest(reason=reason["name"]):
                    self.assertGreaterEqual(len(reason["phrases"]), 5)

    def test_every_reason_has_strong_phrase(self):
        for category in self.data["categories"]:
            for reason in category["reasons"]:
                with self.subTest(reason=reason["name"]):
                    self.assertIn(3, [weight for _, weight in reason["phrases"]])

    def test_validate_catches_problems(self):
        broken = {
            "categories": [
                {
                    "name": "Оплата",
                    "slug": "payment",
                    "color": "синий",
                    "reasons": [
                        {"name": "А", "phrases": [["Списали дважды", 3], ["оплата", 5]]},
                        {"name": "Б", "phrases": [["списали  дважды", 2], "не пара"]},
                    ],
                }
            ],
            "tags": [{"name": "VIP"}, {"name": "VIP"}],
        }
        text = "\n".join(validate(broken))
        self.assertIn("цвет", text)
        self.assertIn("вес 5", text)
        self.assertIn("есть и в 'А', и в 'Б'", text)
        self.assertIn("парой", text)
        self.assertIn("повторный тег", text)


class LoadDictionaryTests(TestCase):
    def load(self, *args):
        call_command("load_dictionary", *args, stdout=StringIO())

    def test_reload_keeps_counts(self):
        self.load()
        first = counts()
        self.load()
        self.assertEqual(counts(), first)
        data = read_dictionary()
        phrases = sum(len(r["phrases"]) for c in data["categories"] for r in c["reasons"])
        self.assertEqual(first, (8, 30, phrases, 10))

    def test_reload_restores_weight_and_keeps_manual_rules(self):
        self.load()
        rule = KeywordRule.objects.get(phrase="списали дважды")
        rule.weight = 1
        rule.save()
        manual = KeywordRule.objects.create(reason=rule.reason, phrase="минус два раза", weight=2)
        self.load()
        self.assertEqual(KeywordRule.objects.get(pk=rule.pk).weight, 3)
        self.assertTrue(KeywordRule.objects.filter(pk=manual.pk).exists())

    def test_prune_removes_rules_missing_from_file(self):
        self.load()
        reason = Reason.objects.get(name="Двойное списание")
        manual = KeywordRule.objects.create(reason=reason, phrase="минус два раза", weight=2)
        self.load("--prune")
        self.assertFalse(KeywordRule.objects.filter(pk=manual.pk).exists())
        self.assertTrue(KeywordRule.objects.filter(phrase="списали дважды").exists())

    def test_reload_with_linked_appeals(self):
        self.load()
        reason = Reason.objects.get(name="Двойное списание")
        Appeal.objects.create(
            text="Списали два раза", category=reason.category, reason=reason, category_source=Appeal.Source.AUTO
        )
        self.load("--prune")
        self.assertEqual(Appeal.objects.get().reason, reason)

    def test_categories_ordered_as_in_file(self):
        self.load()
        slugs = list(Category.objects.values_list("slug", flat=True))
        self.assertEqual(slugs[:3], ["payment", "delivery", "returns"])

    def test_broken_file_rejected(self):
        with self.assertRaises(CommandError):
            self.load("/nonexistent/dictionary.json")
