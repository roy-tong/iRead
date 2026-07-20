from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from reporter.db import Database
from reporter.ingest import ingest_external_feeds
from reporter.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


class ExternalIngestPerformanceTests(unittest.TestCase):
    def test_external_feeds_are_fetched_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            config.mkdir()
            sources = json.loads(
                (ROOT / "config/external_sources.json").read_text(encoding="utf-8")
            )
            sources["sources"] = [
                {
                    **source,
                    "id": f"benchmark-{index}",
                    "feed_url": f"https://example.com/{index}.xml",
                    "capture_method": "rss",
                    "content_mode": "summary_or_link",
                }
                for index, source in enumerate(sources["sources"][:6])
            ]
            (config / "external_sources.json").write_text(
                json.dumps(sources, ensure_ascii=False), encoding="utf-8"
            )
            (config / "accounts.json").write_text(
                json.dumps({"accounts": []}), encoding="utf-8"
            )
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            reporting = json.loads(
                (ROOT / "config/reporting.json").read_text(encoding="utf-8")
            )
            reporting["collection"]["external_fetch_workers"] = 6
            reporting["history_start"] = "2026-06-01T00:00:00+08:00"
            (config / "reporting.json").write_text(
                json.dumps(reporting, ensure_ascii=False), encoding="utf-8"
            )
            settings = Settings.load(ROOT, config)
            db = Database(settings.db_path)
            db.initialize(settings.all_sources)
            payload = b"""<?xml version='1.0'?><rss><channel><item>
              <guid>one</guid><title>Example</title>
              <link>https://example.com/article</link>
              <pubDate>Sun, 19 Jul 2026 10:00:00 GMT</pubDate>
              <description>Useful evidence</description>
            </item></channel></rss>"""

            def delayed_http(*args, **kwargs):
                time.sleep(0.08)
                return payload

            started = time.monotonic()
            with patch("reporter.ingest._http", side_effect=delayed_http):
                result = ingest_external_feeds(settings, db)
            elapsed = time.monotonic() - started

            self.assertEqual(6, result.attempted_sources)
            self.assertEqual(6, len(result.matched_sources))
            self.assertLess(elapsed, 0.35)
            self.assertLess(result.elapsed_seconds, 0.35)


if __name__ == "__main__":
    unittest.main()
