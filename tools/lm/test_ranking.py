"""Static prediction ordering regressions using synthetic candidates."""
import unittest

from eval_model import Candidate, rank_predictions


class RankingTest(unittest.TestCase):
    def test_quantization_does_not_reorder_see_you_continuations(self):
        candidates = [Candidate('later', 231), Candidate('again', 229), Candidate('in', 226)]
        self.assertEqual(rank_predictions(candidates, 'legacy-static')[0].word, 'again')
        for weight in (1.0, 0.85, 0.5, 0.01, 0.0):
            self.assertEqual(rank_predictions(candidates, 'static', weight), candidates)

    def test_backoff_does_not_displace_a_more_specific_context(self):
        candidates = [Candidate('specific', 100), Candidate('fallback', 200)]
        self.assertEqual(rank_predictions(candidates, 'static'), candidates)
        self.assertEqual(rank_predictions([], 'static'), [])


if __name__ == '__main__':
    unittest.main()
