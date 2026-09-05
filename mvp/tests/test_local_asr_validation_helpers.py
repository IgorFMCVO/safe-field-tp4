from __future__ import annotations

import unittest

from mvp.tests.run_local_asr_validation import nearest_rank


class LocalASRValidationHelperTests(unittest.TestCase):
    def test_nearest_rank_keeps_cold_outlier_in_small_p95(self) -> None:
        values = [100.0] * 15 + [5000.0]

        self.assertEqual(nearest_rank(values, 0.95), 5000.0)

    def test_nearest_rank_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            nearest_rank([], 0.95)
        with self.assertRaises(ValueError):
            nearest_rank([1.0], 0.0)
        with self.assertRaises(ValueError):
            nearest_rank([1.0], 1.01)


if __name__ == "__main__":
    unittest.main()
