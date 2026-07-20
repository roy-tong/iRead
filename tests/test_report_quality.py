from __future__ import annotations

import unittest

from reporter.reports import evaluate_report_quality


class ReportQualityTests(unittest.TestCase):
    def test_daily_quality_checks_links_limits_length_and_coverage(self) -> None:
        markdown = """# 日报

## 今日精读

### 1. 重要变化

有一手证据和[原文](https://example.com/a)。

## 原创观点与一手信号

1. 具名专家的观点。

## 争议与待验证

1. 需要第二来源。
"""
        result = evaluate_report_quality(
            "daily",
            markdown,
            {
                "reading_minutes": 10,
                "must_read_limit": 5,
                "original_signal_limit": 3,
            },
            {"period_articles": 20, "period_analysis_coverage": 0.9},
        )
        self.assertEqual("pass", result["status"])
        self.assertEqual(100, result["score"])

    def test_missing_links_and_excess_items_fail(self) -> None:
        markdown = "## 今日精读\n\n" + "\n".join(
            f"### {index}. 事件" for index in range(1, 4)
        )
        result = evaluate_report_quality(
            "daily",
            markdown,
            {
                "reading_minutes": 10,
                "must_read_limit": 2,
                "original_signal_limit": 3,
            },
            {"period_articles": 10, "period_analysis_coverage": 0.4},
        )
        self.assertEqual("fail", result["status"])
        self.assertLess(result["score"], 60)


if __name__ == "__main__":
    unittest.main()
