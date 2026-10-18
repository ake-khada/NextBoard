"""Synthetic normalization and ranking regressions; no user text or corpus needed."""
import unittest
import unicodedata

from build_model import normalize_key, normalize_surface, tokenize_sentences


class NormalizationTest(unittest.TestCase):
    def test_french_decomposed_accents_keep_whole_words(self):
        phrase = "J’ai déjà réservé l’hôtel."
        expected = [["J'ai", "déjà", "réservé", "l'hôtel"]]
        self.assertEqual(list(tokenize_sentences(phrase)), expected)
        self.assertEqual(list(tokenize_sentences(unicodedata.normalize('NFD', phrase))), expected)

    def test_keys_agree_across_canonical_forms(self):
        for language, words in [('fr', ['CAFÉ', 'DÉJÀ', 'L’HÔTEL']), ('ru', ['ЕЩЁ', 'ВСЁ'])]:
            for word in words:
                with self.subTest(language=language, word=word):
                    self.assertEqual(normalize_key(word, language),
                                     normalize_key(unicodedata.normalize('NFD', word), language))
        self.assertEqual(normalize_key('ВСЁ', 'ru'), 'все')
        self.assertEqual(normalize_key('L’HÔTEL', 'fr'), "l'hôtel")

    def test_mixed_text_emoji_and_contractions(self):
        phrase = "I can't meet au café, потом домой 👩🏽‍💻."
        self.assertEqual(list(tokenize_sentences(phrase)),
                         [["I", "can't", "meet", "au", "café", "потом", "домой"]])
        self.assertEqual(normalize_surface('е\u0308'), 'ё')


if __name__ == '__main__':
    unittest.main()
