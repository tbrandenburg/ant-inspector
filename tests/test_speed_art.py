import unittest

from ant_inspector import render_speed_art


class SpeedArtTests(unittest.TestCase):
    def test_art_fills_available_height_and_stays_within_width(self):
        art = render_speed_art("42.1", width=80, height=20)
        rows = art.splitlines()

        self.assertEqual(len(rows), 20)
        self.assertLessEqual(max(map(len, rows)), 80)
        self.assertIn("█", art)

    def test_resize_scales_digits_and_tiny_terminal_falls_back(self):
        small = render_speed_art("42.1", width=80, height=20)
        large = render_speed_art("42.1", width=120, height=40)

        self.assertGreater(len(large.splitlines()), len(small.splitlines()))
        self.assertEqual(render_speed_art("42.1", width=5, height=4), "42.1")


if __name__ == "__main__":
    unittest.main()
