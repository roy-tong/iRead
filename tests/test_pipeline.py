from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reporter.analysis import _content_excerpt, _parse_usage_limit_retry_at
from reporter.db import Database
from reporter.export import export_public_archive
from reporter.ingest import (
    _backfill_window,
    _backfill_priority_key,
    _parse_external_feed,
    _raw_article_coverage,
    _recent_refresh_interval_seconds,
    _recent_refresh_priority_key,
    _transcript_url,
    _werss_is_busy,
    ingest_from_werss_db,
    ingest_from_werss_nodes,
)
from reporter.notion import markdown_to_blocks, resolve_report_parent
from reporter.proposals import (
    _batch_profiles,
    _normalize_proposal,
    apply_research_batch,
    apply_research_proposal,
    propose_research_batch,
)
from reporter.ranking import (
    article_editorial_score,
    publication_frequency_score,
    rank_event_clusters,
)
from reporter.reports import due_report_kinds
from reporter.settings import Settings
from reporter.source_quality import review_sources
from reporter.text import html_to_text, normalize_url
from reporter.viewer import LibraryStore


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_notion_reports_resolve_to_kind_folders(self) -> None:
        settings = Settings.load(ROOT)

        class FakeNotionClient:
            def list_child_pages(self, parent_page_id: str):
                self.parent_page_id = parent_page_id
                return [
                    {"id": "daily-id", "title": "日报"},
                    {"id": "weekly-id", "title": "周报"},
                    {"id": "monthly-id", "title": "月报"},
                ]

        client = FakeNotionClient()
        self.assertEqual(
            "dailyid",
            resolve_report_parent(settings, client, "root-id", "daily"),
        )
        self.assertEqual("root-id", client.parent_page_id)

    def test_notion_report_folder_is_required(self) -> None:
        settings = Settings.load(ROOT)

        class EmptyNotionClient:
            def list_child_pages(self, parent_page_id: str):
                return []

        with self.assertRaisesRegex(RuntimeError, "日报"):
            resolve_report_parent(settings, EmptyNotionClient(), "root-id", "daily")

    def test_codex_usage_limit_retry_time_parses_in_reporting_timezone(self) -> None:
        settings = Settings.load(ROOT)
        parsed = _parse_usage_limit_retry_at(
            settings,
            "You've hit your usage limit. You can try again at Jul 23rd, 2026 12:39 PM.",
        )
        expected = int(
            datetime(2026, 7, 23, 12, 39, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        )
        self.assertEqual(expected, parsed)

    def test_configuration_has_all_accounts(self) -> None:
        settings = Settings.load(ROOT)
        self.assertEqual(72, len(settings.accounts))
        self.assertEqual(40, len(settings.external_sources))
        self.assertEqual(32, sum(source.capture_method == "rss" for source in settings.external_sources))
        required = [account for account in settings.accounts if account.priority == "required"]
        self.assertGreaterEqual(len(required), 35)
        self.assertEqual("2026-01-01", settings.history_start.date().isoformat())
        self.assertTrue(all(0 <= account.influence <= 1 for account in settings.accounts))
        self.assertTrue(all(account.profile_status == "provisional" for account in settings.accounts))
        self.assertEqual(
            "interview",
            next(account.source_type for account in settings.accounts if account.wechat_id == "languageisworld"),
        )
        self.assertTrue(
            next(
                source.conflict_note
                for source in settings.external_sources
                if source.wechat_id == "external:no-priors"
            )
        )
        self.assertEqual("ai-embodied-hardware", settings.profile.id)
        self.assertEqual("AI与具身研究", settings.profile.name)
        self.assertEqual(["main", "worker-2", "worker-3"], [node.name for node in settings.werss_nodes])
        self.assertEqual(
            ["main", "worker-2", "worker-3"],
            settings.reporting["collection"]["backfill_nodes"],
        )
        self.assertEqual(["main"], settings.reporting["collection"]["recent_refresh_nodes"])
        inactive = {
            account.wechat_id
            for account in settings.accounts
            if account.collection_status == "inactive"
        }
        self.assertEqual(
            {"gh_388882297", "gh_3198736570", "Lynndacapo"},
            inactive,
        )

    def test_werss_publish_info_patch_keeps_valid_articles_reachable(self) -> None:
        patch = (ROOT / "patches" / "we-mp-rss-malformed-publish-info.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn('+                        if "appmsgex" in publish_info:', patch)
        self.assertNotIn('+                            if "appmsgex" in publish_info:', patch)

        repair_patch = (
            ROOT / "patches" / "we-mp-rss-existing-content-repair.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("art.content and not existing_article.content", repair_patch)
        self.assertIn("Repaired article content", repair_patch)

    def test_background_codex_runs_are_trusted_bounded_and_recurring(self) -> None:
        analysis_source = (ROOT / "src" / "reporter" / "analysis.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--skip-git-repo-check"', analysis_source)

        report_plist = (
            ROOT / "launchd" / "com.local.research-reporter.report.plist.template"
        ).read_text(encoding="utf-8")
        self.assertNotIn("--max-batches", report_plist)
        self.assertNotIn("--skip-sync", report_plist)
        self.assertIn("<integer>18</integer>", report_plist)

        analysis_plist = (
            ROOT / "launchd" / "com.local.research-reporter.analysis.plist.template"
        ).read_text(encoding="utf-8")
        self.assertIn("<integer>900</integer>", analysis_plist)

        installer = (ROOT / "scripts" / "install_launchd.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("IREAD_ALLOW_CONFIG_SWITCH", installer)
        self.assertIn("Refusing to replace active iRead config", installer)

    def test_pending_articles_can_be_limited_to_report_ready_window(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "research.db")
            db.initialize(settings.all_sources)
            with db.connect() as conn:
                for article_id, published_at, content in (
                    ("before", 100, "正文" * 100),
                    ("ready", 200, "正文" * 100),
                    ("short", 210, "短"),
                    ("after", 300, "正文" * 100),
                ):
                    conn.execute(
                        """
                        INSERT INTO articles (
                            id, source_wechat_id, source_name, priority, title, published_at,
                            content_text, fingerprint, ingested_at, updated_at
                        ) VALUES (?, ?, ?, 'required', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            article_id,
                            "AI_Whitepaper",
                            "AI产品白皮书",
                            article_id,
                            published_at,
                            content,
                            article_id,
                            published_at,
                            published_at,
                        ),
                    )
            rows = db.pending_articles(
                10,
                start_ts=100,
                end_ts=250,
                require_report_content=True,
            )
            self.assertEqual(["ready"], [row["id"] for row in rows])
            self.assertEqual(
                1,
                db.pending_article_count(100, 250, require_report_content=True),
            )

    def test_settings_can_use_custom_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "config"
            config.mkdir()
            (config / "accounts.json").write_text(
                json.dumps(
                    {
                        "history_start": "2026-07-01T00:00:00+08:00",
                        "priorities": {
                            "required": {
                                "label": "必抓",
                                "weight": 1.0,
                                "influence": 0.7,
                                "reliability": 0.7,
                                "originality": 0.7,
                                "clickbait_risk": 0.2,
                            }
                        },
                        "accounts": [
                            {
                                "name": "自定义作者",
                                "wechat_id": "custom_author",
                                "priority": "required",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            self.assertEqual(config.resolve(), settings.config_dir)
            self.assertEqual(["自定义作者"], [account.name for account in settings.accounts])
            self.assertGreaterEqual(len(settings.external_sources), 1)
            self.assertEqual("AI应用（纯软件）", next(settings.topic_names()))

    def test_enrichment_schema_accepts_profile_defined_topics(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "article_enrichment.schema.json").read_text(encoding="utf-8")
        )
        primary_topic = schema["properties"]["articles"]["items"]["properties"][
            "primary_topic"
        ]
        self.assertNotIn("enum", primary_topic)
        self.assertEqual(1, primary_topic["minLength"])

    def test_database_has_structured_viewpoint_fields(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "research.db")
            db.initialize(settings.all_sources)
            article_columns = {
                row["name"] for row in db.rows("PRAGMA table_info(articles)")
            }
            account_columns = {
                row["name"] for row in db.rows("PRAGMA table_info(accounts)")
            }
            backfill_columns = {
                row["name"] for row in db.rows("PRAGMA table_info(backfill_state)")
            }
            self.assertIn("viewpoints_json", article_columns)
            self.assertIn("transcript_status", article_columns)
            self.assertIn("content_mode", account_columns)
            self.assertIn("conflict_note", account_columns)
            self.assertIn("last_recent_requested_at", backfill_columns)
            self.assertIn("last_recent_error", backfill_columns)

    def test_public_archive_export_omits_content_by_default(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            settings.data_dir = temp / "data"
            settings.logs_dir = temp / "logs"
            settings.data_dir.mkdir()
            settings.logs_dir.mkdir()
            db = Database(settings.db_path)
            db.initialize(settings.all_sources)
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO articles (
                        id, source_article_id, source_wechat_id, source_name, priority,
                        title, url, published_at, description, content_html, content_text,
                        fingerprint, ingested_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "article-export-1",
                        "upstream-1",
                        "AI_Whitepaper",
                        "AI产品白皮书",
                        "required",
                        "导出测试",
                        "https://example.com/a",
                        1784040000,
                        "摘要",
                        "<p>不应默认公开的正文</p>",
                        "不应默认公开的正文",
                        "fingerprint",
                        1784040001,
                        1784040002,
                    ),
                )
            result = export_public_archive(settings, db, temp / "public")
            self.assertEqual(1, result["articles"])
            line = (temp / "public" / "articles.jsonl").read_text(encoding="utf-8").strip()
            article = json.loads(line)
            self.assertNotIn("content_text", article)
            with self.assertRaises(RuntimeError):
                export_public_archive(settings, db, temp / "full", include_content=True)

    def test_html_and_url_normalization(self) -> None:
        self.assertEqual("标题\n\n正文", html_to_text("<h1>标题</h1><p>正文<script>x</script></p>"))
        self.assertEqual(
            "https://mp.weixin.qq.com/s/abc?x=1",
            normalize_url("https://mp.weixin.qq.com/s/abc?utm_source=a&x=1#part"),
        )

    def test_long_transcript_excerpt_samples_the_full_range(self) -> None:
        content = "".join(str(index % 10) for index in range(100000))
        excerpt = _content_excerpt(content, 12000, distributed=True)
        self.assertIn("逐字稿分段 1/6", excerpt)
        self.assertIn("逐字稿分段 6/6", excerpt)
        self.assertLessEqual(len(excerpt), 12300)

    def test_unified_library_filters_external_articles(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "research.db")
            db.initialize(settings.all_sources)
            with db.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO articles (
                        id, source_wechat_id, source_name, priority, title,
                        published_at, content_text, fingerprint, ingested_at, updated_at
                    ) VALUES (?, ?, ?, 'required', ?, 1784160000, ?, ?, 1784160000, 1784160000)
                    """,
                    [
                        ("wechat-1", "AI_Whitepaper", "AI产品白皮书", "公众号文章", "中文正文", "fp1"),
                        (
                            "external-1",
                            "external:cognitive-revolution",
                            "The Cognitive Revolution",
                            "Overseas interview",
                            "Transcript body",
                            "fp2",
                        ),
                    ],
                )
            store = LibraryStore(db.path)
            result = store.list_articles({"type": "external"})
            self.assertEqual(1, result["total"])
            self.assertEqual("external-1", result["items"][0]["id"])
            self.assertEqual("Transcript body", store.article("external-1")["content"])
            configured_store = LibraryStore(db.path, settings)
            self.assertEqual("AI与具身研究", configured_store.ui_config()["profile_name"])
            self.assertEqual(
                "具身智能",
                configured_store.ui_config()["topic_labels"]["embodied_ai"],
            )

    def test_source_review_combines_priors_with_observed_articles(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "research.db")
            db.initialize(settings.all_sources)
            with db.connect() as conn:
                for index in range(6):
                    conn.execute(
                        """
                        INSERT INTO articles (
                            id, source_wechat_id, source_name, priority, title, url,
                            published_at, content_text, fingerprint, ingested_at, updated_at,
                            analysis_status, relevance, evidence_quality, credibility,
                            originality_score, clickbait_score, source_role
                        ) VALUES (?, 'AI_Whitepaper', 'AI产品白皮书', 'required', ?, ?, ?, ?, ?, ?, ?,
                                  'done', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"quality-{index}",
                            f"代表文章 {index}",
                            f"https://example.com/{index}",
                            1784100000 + index * 3600,
                            "正文" * 100,
                            f"fingerprint-{index}",
                            1784100000 + index * 3600,
                            1784100000 + index * 3600,
                            90 - index,
                            75 - index,
                            80 - index,
                            85 - index,
                            10 + index,
                            "original_reporting",
                        ),
                    )
            review = review_sources(
                settings,
                db,
                representative_works=3,
                as_of=datetime(2026, 7, 16, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            source = next(item for item in review["sources"] if item["id"] == "AI_Whitepaper")
            self.assertEqual("medium", source["confidence"]["label"])
            self.assertEqual(6, source["confidence"]["analyzed_articles"])
            self.assertEqual(3, len(source["representative_works"]))
            self.assertGreater(source["dimensions"]["content_quality"], 65)
            self.assertEqual("https://example.com/5", source["representative_works"][1]["url"])

    def test_reviewed_proposal_creates_an_isolated_profile(self) -> None:
        settings = Settings.load(ROOT)
        report_policy = {
            "enabled": True,
            "reading_minutes": 10,
            "max_items": 8,
            "focus": ["material_changes"],
        }
        proposal = {
            "research_profile": {
                "id": "semiconductor",
                "name": "半导体研究",
                "description": "跟踪半导体产业。",
                "seed_keywords": ["半导体"],
                "audiences": ["research"],
                "goals": ["trend_detection"],
                "languages": ["zh-CN", "en"],
                "regions": ["global"],
                "exclusions": [],
            },
            "topic_taxonomy": {
                "classification_rules": ["使用最相关的一级主题。"],
                "topics": [
                    {
                        "id": "chip_design",
                        "name": "芯片设计",
                        "description": "设计与 EDA",
                        "keywords": ["EDA"],
                        "secondaries": [],
                    }
                ],
                "event_types": [
                    {"id": "product", "name": "产品发布", "keywords": ["发布"]}
                ],
            },
            "entity_seeds": {
                "companies": [{"topic_id": "chip_design", "names": ["样例公司"]}],
                "people": ["样例人物"],
            },
            "sources": [
                {
                    "id": "official-feed",
                    "name": "Official Feed",
                    "role": "primary_source",
                    "source_type": "first_party",
                    "homepage_url": "https://example.com",
                    "feed_url": "https://example.com/feed.xml",
                    "platform_id": "",
                    "capture_method": "rss",
                    "content_mode": "summary_or_link",
                    "coverage_topics": ["chip_design"],
                    "recommendation_reason": "一手发布",
                    "conflict_note": "官方立场",
                    "preliminary_scores": {
                        "domain_fit": 90,
                        "authority": 90,
                        "originality": 80,
                        "evidence_discipline": 80,
                        "captureability": 90,
                    },
                    "score_confidence": "medium",
                    "discovery_evidence_urls": ["https://example.com/about"],
                    "representative_works": [],
                    "warnings": [],
                },
                {
                    "id": "web-source",
                    "name": "Web Source",
                    "role": "specialist_analysis",
                    "source_type": "industry_research",
                    "homepage_url": "https://research.example.com",
                    "feed_url": "",
                    "platform_id": "",
                    "capture_method": "web",
                    "content_mode": "summary_or_link",
                    "coverage_topics": ["chip_design"],
                    "recommendation_reason": "专业研究",
                    "conflict_note": "",
                    "preliminary_scores": {
                        "domain_fit": 75,
                        "authority": 65,
                        "originality": 75,
                        "evidence_discipline": 70,
                        "captureability": 40,
                    },
                    "score_confidence": "low",
                    "discovery_evidence_urls": [],
                    "representative_works": [],
                    "warnings": [],
                },
                {
                    "id": "wechat-source",
                    "name": "微信样例",
                    "role": "expert_voice",
                    "source_type": "practitioner",
                    "homepage_url": "",
                    "feed_url": "",
                    "platform_id": "wechat_sample",
                    "capture_method": "wechat",
                    "content_mode": "full_text",
                    "coverage_topics": ["chip_design"],
                    "recommendation_reason": "从业者观点",
                    "conflict_note": "",
                    "preliminary_scores": {
                        "domain_fit": 70,
                        "authority": 60,
                        "originality": 75,
                        "evidence_discipline": 60,
                        "captureability": 70,
                    },
                    "score_confidence": "low",
                    "discovery_evidence_urls": [],
                    "representative_works": [],
                    "warnings": [],
                },
            ],
            "report_presets": [
                {
                    "id": preset,
                    "name": preset,
                    "description": preset,
                    "daily": dict(report_policy),
                    "weekly": dict(report_policy),
                    "monthly": dict(report_policy),
                }
                for preset in ("light", "standard", "deep")
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "profile"
            result = apply_research_proposal(
                settings,
                proposal,
                output,
                preset_id="standard",
                history_start="2026-01-01T00:00:00+08:00",
            )
            self.assertEqual(1, result["wechat_sources"])
            self.assertEqual(2, result["external_sources"])
            custom = Settings.load(ROOT, output)
            self.assertEqual("半导体研究", custom.profile.name)
            self.assertEqual(["微信样例"], [item.name for item in custom.accounts])
            self.assertEqual(
                ["rss", "web_pending"],
                [item.capture_method for item in custom.external_sources],
            )
            self.assertNotIn("title_prefix", custom.reporting["daily"])
            self.assertEqual(
                (ROOT / "data" / "profiles" / "semiconductor").resolve(),
                custom.data_dir.resolve(),
            )
            self.assertEqual(
                (ROOT / "logs" / "profiles" / "semiconductor").resolve(),
                custom.logs_dir.resolve(),
            )

            proposals_dir = Path(temp_dir) / "proposals"
            proposals_dir.mkdir()
            (proposals_dir / "semiconductor.json").write_text(
                json.dumps(proposal, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest = {
                "defaults": {"preset": "standard"},
                "profiles": [
                    {"id": "batch-semiconductor", "field": "半导体"},
                    {"id": "not-approved", "field": "低空经济"},
                ],
            }
            (proposals_dir / "batch-semiconductor.json").write_text(
                json.dumps(proposal, ensure_ascii=False),
                encoding="utf-8",
            )
            resumed = propose_research_batch(
                settings,
                {"profiles": [manifest["profiles"][0]]},
                proposals_dir,
                resume=True,
            )
            self.assertEqual(1, resumed["reused"])
            self.assertEqual(0, resumed["failed"])
            batch = apply_research_batch(
                settings,
                manifest,
                proposals_dir,
                Path(temp_dir) / "profiles",
                approved=["batch-semiconductor"],
            )
            self.assertEqual(1, batch["applied"])
            self.assertEqual(1, batch["not_approved"])
            index = json.loads(
                (Path(temp_dir) / "profiles" / "index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["batch-semiconductor"],
                [item["id"] for item in index["profiles"]],
            )
            batch_profile = Settings.load(
                ROOT,
                Path(temp_dir) / "profiles" / "batch-semiconductor",
            )
            self.assertEqual("batch-semiconductor", batch_profile.profile.id)
            with self.assertRaisesRegex(ValueError, "Unknown approved profile ids"):
                apply_research_batch(
                    settings,
                    manifest,
                    proposals_dir,
                    Path(temp_dir) / "profiles-unknown",
                    approved=["typo"],
                )

    def test_proposal_normalizes_score_scales_and_batch_ids(self) -> None:
        normalized = _normalize_proposal(
            {
                "research_profile": {"name": "低空经济"},
                "sources": [
                    {
                        "id": "official",
                        "homepage_url": "https://example.com",
                        "feed_url": "",
                        "capture_method": "web",
                        "preliminary_scores": {
                            "domain_fit": 5,
                            "authority": 4,
                            "originality": 3,
                            "evidence_discipline": 4,
                            "captureability": 2,
                        },
                        "warnings": [],
                    }
                ],
            },
            20,
        )
        source = normalized["sources"][0]
        self.assertEqual(100, source["preliminary_scores"]["domain_fit"])
        self.assertEqual(40, source["preliminary_scores"]["captureability"])
        self.assertTrue(any("归一化" in warning for warning in source["warnings"]))
        batch = _batch_profiles(
            {"profiles": [{"id": "../../unsafe", "field": "产业研究"}]}
        )
        self.assertEqual("unsafe", batch[0]["id"])

    def test_markdown_blocks_obey_notion_limits(self) -> None:
        blocks = markdown_to_blocks("# 标题\n\n- 条目\n- [ ] 待确认\n\n" + ("很长的正文" * 1000))
        self.assertGreaterEqual(len(blocks), 3)
        self.assertTrue(any(block["type"] == "to_do" for block in blocks))
        for block in blocks:
            value = block.get(block["type"], {})
            for rich in value.get("rich_text", []):
                self.assertLessEqual(len(rich["text"]["content"]), 2000)

    def test_due_reports(self) -> None:
        settings = Settings.load(ROOT)
        timezone = ZoneInfo("Asia/Shanghai")
        friday = datetime(2026, 7, 31, 18, 0, tzinfo=timezone)
        self.assertEqual(["daily", "weekly", "monthly"], due_report_kinds(settings, friday))

    def test_direct_werss_ingestion(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source_path = temp / "werss.db"
            source = sqlite3.connect(source_path)
            source.executescript(
                """
                CREATE TABLE feeds (id TEXT PRIMARY KEY, mp_name TEXT, faker_id TEXT, status INTEGER);
                CREATE TABLE articles (
                    id TEXT PRIMARY KEY, mp_id TEXT, title TEXT, url TEXT, publish_time INTEGER,
                    description TEXT, content TEXT, content_html TEXT, status INTEGER
                );
                """
            )
            source.execute(
                "INSERT INTO feeds VALUES (?, ?, ?, 1)",
                ("MP_WXS_test", "AI产品白皮书", "fake",),
            )
            source.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    "article-1", "MP_WXS_test", "测试文章", "https://mp.weixin.qq.com/s/a",
                    int(datetime(2026, 6, 1, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()),
                    "摘要", "<p>正文内容足够用于测试。</p>", "",
                ),
            )
            source.commit()
            source.close()

            settings.data_dir = temp / "data"
            settings.logs_dir = temp / "logs"
            settings.data_dir.mkdir()
            settings.logs_dir.mkdir()
            old_path = os.environ.get("WERSS_DB_PATH")
            os.environ["WERSS_DB_PATH"] = str(source_path)
            try:
                target = Database(settings.db_path)
                target.initialize(settings.all_sources)
                result = ingest_from_werss_db(settings, target)
                self.assertEqual(1, result.imported)
                row = target.row("SELECT * FROM articles")
                self.assertIsNotNone(row)
                self.assertEqual("AI_Whitepaper", row["source_wechat_id"])
            finally:
                if old_path is None:
                    os.environ.pop("WERSS_DB_PATH", None)
                else:
                    os.environ["WERSS_DB_PATH"] = old_path

    def test_multi_node_werss_ingestion_merges_and_deduplicates(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            primary_path = temp / "primary.db"
            worker_path = temp / "worker.db"

            def create_source(path: Path, article_ids: list[str]) -> None:
                source = sqlite3.connect(path)
                source.executescript(
                    """
                    CREATE TABLE feeds (id TEXT PRIMARY KEY, mp_name TEXT, faker_id TEXT, status INTEGER);
                    CREATE TABLE articles (
                        id TEXT PRIMARY KEY, mp_id TEXT, title TEXT, url TEXT, publish_time INTEGER,
                        description TEXT, content TEXT, content_html TEXT, status INTEGER
                    );
                    """
                )
                source.execute(
                    "INSERT INTO feeds VALUES (?, ?, ?, 1)",
                    ("MP_WXS_test", "AI产品白皮书", "fake"),
                )
                for article_id in article_ids:
                    source.execute(
                        "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                        (
                            article_id,
                            "MP_WXS_test",
                            f"测试文章 {article_id}",
                            f"https://mp.weixin.qq.com/s/{article_id}",
                            int(datetime(2026, 6, 1, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()),
                            "摘要",
                            "<p>正文内容足够用于测试。</p>",
                            "",
                        ),
                    )
                source.commit()
                source.close()

            create_source(primary_path, ["article-1"])
            create_source(worker_path, ["article-1", "article-2"])
            settings.data_dir = temp / "data"
            settings.logs_dir = temp / "logs"
            settings.data_dir.mkdir()
            settings.logs_dir.mkdir()
            settings.reporting["collection"]["werss_workers"] = [
                {
                    "name": "worker",
                    "base_url": "http://127.0.0.1:9999",
                    "db_path": str(worker_path),
                }
            ]
            old_path = os.environ.get("WERSS_DB_PATH")
            os.environ["WERSS_DB_PATH"] = str(primary_path)
            try:
                target = Database(settings.db_path)
                target.initialize(settings.all_sources)
                result = ingest_from_werss_nodes(settings, target)
                self.assertEqual(2, result.imported)
                self.assertEqual(2, target.row("SELECT COUNT(*) AS count FROM articles")["count"])
                self.assertEqual(["AI_Whitepaper"], result.matched_sources)
            finally:
                if old_path is None:
                    os.environ.pop("WERSS_DB_PATH", None)
                else:
                    os.environ["WERSS_DB_PATH"] = old_path

    def test_raw_coverage_targets_the_first_missing_content_page(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "werss.db"
            source = sqlite3.connect(source_path)
            source.executescript(
                """
                CREATE TABLE articles (
                    id TEXT PRIMARY KEY, mp_id TEXT, publish_time INTEGER,
                    content TEXT, content_html TEXT, status INTEGER
                );
                """
            )
            for index in range(11):
                source.execute(
                    "INSERT INTO articles VALUES (?, 'feed', ?, ?, '', 1)",
                    (
                        f"article-{index}",
                        2_000_000_000 - index,
                        "" if index == 5 else "正文",
                    ),
                )
            source.commit()
            source.close()

            settings.reporting["collection"]["werss_workers"] = []
            old_path = os.environ.get("WERSS_DB_PATH")
            os.environ["WERSS_DB_PATH"] = str(source_path)
            try:
                coverage = _raw_article_coverage(settings)["feed"]
                self.assertEqual(1, coverage["missing_content"])
                self.assertEqual(1, coverage["repair_page"])
            finally:
                if old_path is None:
                    os.environ.pop("WERSS_DB_PATH", None)
                else:
                    os.environ["WERSS_DB_PATH"] = old_path

    def test_external_feed_parser_supports_rss_and_atom(self) -> None:
        rss = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item><guid>rss-1</guid><title>RSS title</title>
        <link>https://example.com/rss</link><pubDate>Wed, 15 Jul 2026 10:00:00 GMT</pubDate>
        <description><![CDATA[<p>RSS body</p>]]></description></item></channel></rss>"""
        atom = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><entry><id>atom-1</id><title>Atom title</title>
        <link rel="alternate" href="https://example.com/atom"/><updated>2026-07-15T10:00:00Z</updated>
        <summary>Atom body</summary></entry></feed>"""
        rss_rows = _parse_external_feed(rss)
        atom_rows = _parse_external_feed(atom)
        self.assertEqual("https://example.com/rss", rss_rows[0]["url"])
        self.assertEqual("<p>RSS body</p>", rss_rows[0]["description"])
        self.assertEqual("https://example.com/atom", atom_rows[0]["url"])
        self.assertEqual("Atom body", atom_rows[0]["description"])

    def test_transcript_url_extraction(self) -> None:
        self.assertEqual(
            "https://example.com/episode/transcript.html",
            _transcript_url(
                '<p><a href="https://example.com/episode/transcript.html">Transcript</a></p>'
            ),
        )
        self.assertEqual("", _transcript_url("https://example.com/episode.mp3"))

        podcast = b"""<?xml version="1.0"?>
        <rss xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel><item>
        <guid>podcast-1</guid><title>Episode</title><pubDate>Wed, 15 Jul 2026 10:00:00 GMT</pubDate>
        <podcast:transcript url="https://example.com/episode/transcript.json" type="application/json" />
        </item></channel></rss>"""
        self.assertEqual(
            "https://example.com/episode/transcript.json",
            _parse_external_feed(podcast)[0]["transcript_url"],
        )

    def test_empty_backfill_source_starts_at_page_zero(self) -> None:
        self.assertEqual((0, 10), _backfill_window(None, 80, 80, 10))
        self.assertEqual((10, 20), _backfill_window(None, 10, 80, 10))
        self.assertEqual((80, 90), _backfill_window(1767225600, 0, 80, 10))
        self.assertEqual((90, 100), _backfill_window(1767225600, 90, 80, 10))

    def test_history_backfill_precedes_content_repair(self) -> None:
        history_ts = 1767196800
        history_row = {
            "werss_feed_id": "history",
            "oldest_article_at": 1770000000,
            "priority": "preferred",
            "last_requested_at": 20,
            "weight": 0.7,
            "next_page": 10,
        }
        repair_row = {
            "werss_feed_id": "repair",
            "oldest_article_at": 1760000000,
            "priority": "required",
            "last_requested_at": 10,
            "weight": 1.0,
            "next_page": 100,
        }
        coverage = {
            "history": {"oldest": 1770000000},
            "repair": {"oldest": 1760000000, "missing_content": 100},
        }
        ordered = sorted(
            [repair_row, history_row],
            key=lambda row: _backfill_priority_key(row, coverage, history_ts),
        )
        self.assertEqual("history", ordered[0]["werss_feed_id"])

    def test_high_frequency_sources_refresh_sooner(self) -> None:
        collection = {
            "recent_frequency_high_threshold": 60,
            "recent_frequency_medium_threshold": 20,
            "recent_refresh_high_interval_seconds": 900,
            "recent_refresh_medium_interval_seconds": 1800,
            "recent_refresh_low_interval_seconds": 3600,
        }
        high = {
            "recent_articles_30d": 70,
            "last_recent_requested_at": 1000,
            "priority": "preferred",
            "newest_article_at": 1100,
            "expected_name": "高频源",
        }
        low = {
            **high,
            "recent_articles_30d": 5,
            "expected_name": "低频源",
        }
        self.assertEqual(900, _recent_refresh_interval_seconds(high, collection))
        self.assertEqual(3600, _recent_refresh_interval_seconds(low, collection))
        ordered = sorted(
            [low, high],
            key=lambda row: _recent_refresh_priority_key(row, collection, 5000),
        )
        self.assertEqual("高频源", ordered[0]["expected_name"])

    def test_publication_frequency_is_a_quality_gated_attention_factor(self) -> None:
        base = {
            "analysis_status": "done",
            "priority": "preferred",
            "influence": 0.6,
            "reliability": 0.7,
            "originality": 0.7,
            "clickbait_risk": 0.15,
            "relevance": 80,
            "evidence_quality": 70,
            "credibility": 75,
            "originality_score": 70,
            "clickbait_score": 15,
            "source_role": "analysis",
            "viewpoints_json": "[]",
        }
        low = {**base, "recent_articles_30d": 3}
        high = {**base, "recent_articles_30d": 60}
        self.assertEqual(100.0, publication_frequency_score(high))
        self.assertGreater(article_editorial_score(high), article_editorial_score(low))

    def test_backfill_defers_while_werss_is_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "werss.db"
            source.touch()
            modified = source.stat().st_mtime
            self.assertTrue(_werss_is_busy(source, 300, modified + 60))
            self.assertFalse(_werss_is_busy(source, 300, modified + 301))

    def test_werss_node_persisted_auth_files_are_kept_with_node_data(self) -> None:
        settings = Settings.load(ROOT)
        workers = settings.werss_nodes[1:]
        self.assertEqual(
            ["data/we-mp-rss-worker-2", "data/we-mp-rss-worker-3"],
            [str(node.db_path.parent.relative_to(ROOT)) for node in workers],
        )

    def test_event_ranking_separates_consensus_and_exclusive_candidates(self) -> None:
        base = {
            "published_at": 1784040000,
            "priority": "required",
            "weight": 1.0,
            "influence": 0.8,
            "reliability": 0.7,
            "originality": 0.5,
            "clickbait_risk": 0.2,
            "relevance": 90,
            "evidence_quality": 80,
            "credibility": 82,
            "originality_score": 65,
            "clickbait_score": 10,
            "companies_json": '["测试机器人"]',
            "event_types_json": '["financing"]',
            "financing_json": '{"is_financing": true, "company": "测试机器人"}',
            "verification_flags_json": "[]",
            "title": "测试机器人完成融资",
            "event_signature": "测试机器人｜融资｜A轮｜2026-07",
        }
        rows = [
            {**base, "id": "a", "source_name": "来源甲", "source_role": "original_reporting"},
            {**base, "id": "b", "source_name": "来源乙", "source_role": "first_party"},
            {
                **base,
                "id": "c",
                "source_name": "小型独家源",
                "source_role": "original_reporting",
                "title": "独家实测某灵巧手",
                "event_signature": "某灵巧手｜实测｜耐久数据｜2026-07",
                "companies_json": '["另一家公司"]',
                "event_types_json": '["product_test"]',
                "financing_json": '{}',
                "influence": 0.35,
                "originality_score": 92,
            },
            {
                **base,
                "id": "d",
                "source_name": "待核验源",
                "source_role": "unknown",
                "title": "匿名消息称某公司即将量产",
                "event_signature": "第三家公司｜量产｜未披露产品｜2026-07",
                "companies_json": '["第三家公司"]',
                "event_types_json": '["mass_production"]',
                "financing_json": '{}',
                "evidence_quality": 20,
                "credibility": 35,
                "clickbait_score": 70,
                "verification_flags_json": '["仅有匿名信源"]',
            },
        ]
        clusters = rank_event_clusters(rows)
        classifications = {cluster["classification"] for cluster in clusters}
        self.assertIn("cross_source_consensus", classifications)
        self.assertIn("exclusive_candidate", classifications)
        self.assertIn("verification_needed", classifications)
        consensus = next(item for item in clusters if item["classification"] == "cross_source_consensus")
        self.assertEqual(2, consensus["independent_source_count"])

    def test_unreviewed_articles_do_not_receive_default_evidence(self) -> None:
        unreviewed = {
            "id": "pending",
            "analysis_status": "pending",
            "published_at": 1784040000,
            "priority": "required",
            "source_name": "高影响来源",
            "influence": 0.95,
            "reliability": 0.8,
            "originality": 0.6,
            "clickbait_risk": 0.2,
            "title": "某公司发布新产品",
            "event_signature": "某公司发布新产品",
        }
        analyzed = {
            **unreviewed,
            "id": "done",
            "analysis_status": "done",
            "title": "另一家公司公布原始实测",
            "event_signature": "另一家公司｜实测｜产品｜2026-07",
            "relevance": 90,
            "evidence_quality": 78,
            "credibility": 80,
            "originality_score": 82,
            "clickbait_score": 8,
            "source_role": "original_reporting",
            "viewpoints_json": "[]",
            "companies_json": "[]",
            "event_types_json": "[]",
            "financing_json": "{}",
            "verification_flags_json": "[]",
        }
        clusters = rank_event_clusters([unreviewed, analyzed])
        pending_cluster = next(item for item in clusters if item["representative_article_id"] == "pending")
        self.assertEqual("unreviewed", pending_cluster["classification"])
        self.assertEqual(0, pending_cluster["evidence_quality"])
        self.assertEqual("discovery", pending_cluster["editorial_tier"])
        self.assertLess(article_editorial_score(unreviewed), article_editorial_score(analyzed))

        off_topic = {
            **analyzed,
            "id": "off-topic",
            "title": "高质量但与研究无关的访谈",
            "event_signature": "某人｜访谈｜无关主题｜2026-07",
            "source_role": "interview",
            "relevance": 12,
            "evidence_quality": 90,
            "credibility": 90,
            "originality_score": 90,
        }
        off_topic_cluster = rank_event_clusters([off_topic])[0]
        self.assertNotEqual("core", off_topic_cluster["editorial_tier"])

    def test_reposts_do_not_count_as_independent_consensus(self) -> None:
        base = {
            "analysis_status": "done",
            "published_at": 1784040000,
            "priority": "required",
            "influence": 0.9,
            "reliability": 0.7,
            "originality": 0.3,
            "clickbait_risk": 0.2,
            "relevance": 85,
            "evidence_quality": 60,
            "credibility": 65,
            "originality_score": 25,
            "clickbait_score": 15,
            "companies_json": '["同一公司"]',
            "event_types_json": '["product"]',
            "financing_json": "{}",
            "verification_flags_json": "[]",
            "viewpoints_json": "[]",
            "title": "同一公司发布同一产品",
            "event_signature": "同一公司｜发布｜同一产品｜2026-07",
            "source_role": "repost",
        }
        rows = [
            {**base, "id": str(index), "source_name": f"转载源{index}"}
            for index in range(3)
        ]
        cluster = rank_event_clusters(rows)[0]
        self.assertEqual(0, cluster["independent_source_count"])
        self.assertNotEqual("cross_source_consensus", cluster["classification"])


if __name__ == "__main__":
    unittest.main()
