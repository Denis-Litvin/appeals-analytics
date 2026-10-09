from django.test import SimpleTestCase

from appeals.text import normalize, phrase_stems, stems, tokens


class TextTests(SimpleTestCase):
    def test_tokens(self):
        self.assertEqual(tokens("Ещё раз: ТРЕК-номер 12345!"), ["еще", "раз", "трек", "номер", "12345"])

    def test_word_forms_share_stem(self):
        self.assertEqual(stems("оплата")[0], stems("оплаты")[0])
        self.assertEqual(stems("курьер")[0], stems("курьера")[0])

    def test_negation_is_kept(self):
        self.assertEqual(normalize("Не приходит код"), "не приход код")

    def test_phrase_stems_drop_service_words(self):
        self.assertEqual(phrase_stems("жалоба на курьера"), phrase_stems("жалоба курьера"))
        self.assertIn("не", phrase_stems("не по адресу"))

    def test_phrase_of_service_words_is_not_lost(self):
        self.assertEqual(phrase_stems("а и но"), stems("а и но"))
