from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reporter.cli import build_parser
from reporter.proposals import validate_research_proposal
from reporter.settings import Settings, parse_datetime
from reporter.subscriptions import apply_research_subscription


ROOT = Path(__file__).resolve().parents[1]


def _report_presets():
    return [
        {
            "id": preset_id,
            "name": preset_id,
            "description": preset_id,
            "daily": {
                "enabled": True,
                "reading_minutes": 10,
                "max_items": 10,
                "focus": ["material_changes"],
            },
            "weekly": {
                "enabled": True,
                "reading_minutes": 25,
                "max_items": 20,
                "focus": ["trend_change"],
            },
            "monthly": {
                "enabled": True,
                "reading_minutes": 45,
                "max_items": 30,
                "focus": ["structural_change"],
            },
        }
        for preset_id in ("light", "standard", "deep")
    ]


def _source(source_id: str, name: str, *, feed_url: str = "", platform_id: str = ""):
    return {
        "id": source_id,
        "name": name,
        "role": "primary_source",
        "source_type": "first_party",
        "homepage_url": "https://example.com",
        "feed_url": feed_url,
        "platform_id": platform_id,
        "capture_method": "rss" if feed_url else "wechat",
        "content_mode": "full_text",
        "languages": ["zh-CN"],
        "regions": ["global"],
        "coverage_topics": ["core"],
        "recommendation_reason": "一手信息",
        "conflict_note": "官方立场",
        "preliminary_scores": {
            "domain_fit": 90,
            "authority": 90,
            "originality": 80,
            "evidence_discipline": 85,
            "captureability": 90,
        },
        "score_confidence": "medium",
        "discovery_evidence_urls": ["https://example.com/about"],
        "representative_works": [
            {
                "title": "代表内容 A",
                "url": f"https://example.com/{source_id}/a",
                "published_at": "2026-07-01",
                "why_representative": "展示长期覆盖能力",
            },
            {
                "title": "代表内容 B",
                "url": f"https://example.com/{source_id}/b",
                "published_at": "2026-07-02",
                "why_representative": "展示证据质量",
            },
        ],
        "warnings": [],
    }


def _proposal(profile_id: str, name: str, sources):
    return {
        "batch_profile_id": profile_id,
        "research_profile": {
            "id": profile_id,
            "name": name,
            "description": f"跟踪{name}",
            "seed_keywords": [name],
            "audiences": ["research"],
            "goals": ["material_changes"],
            "languages": ["zh-CN"],
            "regions": ["global"],
            "exclusions": [],
        },
        "topic_taxonomy": {
            "classification_rules": ["选择最相关主题"],
            "topics": [
                {
                    "id": "core",
                    "name": f"{name}核心进展",
                    "description": "核心主题",
                    "keywords": [name],
                    "secondaries": [
                        {
                            "id": "products",
                            "name": "产品",
                            "description": "产品进展",
                            "keywords": ["产品"],
                        }
                    ],
                },
                {
                    "id": "policy",
                    "name": "政策与监管",
                    "description": "政策主题",
                    "keywords": ["政策"],
                    "secondaries": [],
                },
                {
                    "id": "market",
                    "name": "市场与组织",
                    "description": "市场主题",
                    "keywords": ["市场"],
                    "secondaries": [],
                },
            ],
            "event_types": [
                {"id": "product", "name": "产品发布", "keywords": ["发布"]}
            ],
        },
        "entity_seeds": {
            "companies": [{"topic_id": "core", "names": [f"{name}公司"]}],
            "people": [],
        },
        "source_strategy": {"coverage_notes": [], "known_gaps": []},
        "sources": sources,
        "report_presets": _report_presets(),
    }


class SubscriptionTests(unittest.TestCase):
    def test_multiple_domains_merge_into_one_subscription(self) -> None:
        settings = Settings.load(ROOT)
        manifest = {
            "defaults": {"preset": "standard"},
            "profiles": [
                {"id": "medical-devices", "field": "医疗器械监管"},
                {"id": "energy-markets", "field": "新能源电力市场"},
            ],
        }
        shared_feed = "https://example.com/feed.xml"
        proposals = {
            "medical-devices": _proposal(
                "medical-devices",
                "医疗器械监管",
                [_source("shared-medical", "共享官方源", feed_url=shared_feed)],
            ),
            "energy-markets": _proposal(
                "energy-markets",
                "新能源电力市场",
                [
                    _source("shared-energy", "共享官方源", feed_url=shared_feed),
                    _source("energy-wechat", "能源公众号", platform_id="energy_wechat"),
                ],
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            proposals_dir = temp / "proposals"
            proposals_dir.mkdir()
            for profile_id, proposal in proposals.items():
                (proposals_dir / f"{profile_id}.json").write_text(
                    json.dumps(proposal, ensure_ascii=False),
                    encoding="utf-8",
                )

            output_dir = temp / "iread"
            result = apply_research_subscription(
                settings,
                manifest,
                proposals_dir,
                output_dir,
                approve_all=True,
                subscription_name="我的 iRead",
            )

            self.assertEqual("iRead", result["product"])
            self.assertEqual(2, result["domain_count"])
            self.assertEqual(1, result["deduplicated_sources"])
            self.assertEqual(1, result["wechat_sources"])
            self.assertEqual(1, result["external_sources"])

            configured = Settings.load(ROOT, output_dir)
            self.assertEqual("我的 iRead", configured.profile.name)
            self.assertEqual(
                ["medical-devices", "energy-markets"],
                [d["id"] for d in configured.profile.domains],
            )
            self.assertEqual(
                ["medical-devices", "energy-markets"],
                [topic["id"] for topic in configured.topics["topics"]],
            )
            self.assertEqual(
                "medical-devices__core",
                configured.topics["topics"][0]["secondaries"][0]["id"],
            )

            external = json.loads(
                (output_dir / "external_sources.json").read_text(encoding="utf-8")
            )["sources"][0]
            self.assertEqual(
                ["medical-devices", "energy-markets"],
                external["discovery"]["coverage_domains"],
            )
            reporting = json.loads(
                (output_dir / "reporting.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], reporting["collection"]["werss_workers"])
            self.assertEqual(["main"], reporting["collection"]["backfill_nodes"])
            metadata = json.loads(
                (output_dir / "subscription.json").read_text(encoding="utf-8")
            )
            self.assertEqual("configured", metadata["status"])

            timezone = ZoneInfo("Asia/Shanghai")
            history_start = parse_datetime(metadata["history_start"])
            age_days = (datetime.now(timezone).date() - history_start.date()).days
            self.assertIn(age_days, (30, 31))

    def test_unknown_approved_domain_is_rejected(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "Unknown approved domain ids"):
                apply_research_subscription(
                    settings,
                    {"profiles": [{"id": "example", "field": "示例领域"}]},
                    Path(temp_dir),
                    Path(temp_dir) / "output",
                    approved=["typo"],
                )

    def test_cli_uses_iread_product_name(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("usage: iread", help_text)
        self.assertIn("apply-subscription", help_text)

    def test_strict_proposal_validation_is_domain_agnostic(self) -> None:
        proposal = _proposal(
            "urban-water",
            "城市水务治理",
            [
                _source(f"water-{index}", f"水务信源 {index}", feed_url=f"https://example.com/{index}.xml")
                for index in range(8)
            ],
        )
        result = validate_research_proposal(proposal)
        self.assertEqual("valid", result["status"])
        self.assertEqual(8, result["sources"])


if __name__ == "__main__":
    unittest.main()
