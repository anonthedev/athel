import unittest

from app.nodes.report import ensure_heading


class HeadingTests(unittest.TestCase):
    def test_missing_title_uses_the_topic(self):
        report = ensure_heading("## Overview\n\nCaffeine.", "Effects of caffeine")
        self.assertTrue(report.startswith("# Effects of caffeine\n\n## Overview"))

    def test_existing_title_is_kept(self):
        report = ensure_heading("# Caffeine\n\n## Overview\n", "Effects of caffeine")
        self.assertTrue(report.startswith("# Caffeine\n"))
        self.assertNotIn("# Effects of caffeine", report)
