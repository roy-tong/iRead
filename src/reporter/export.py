from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .db import Database
from .settings import Account, Settings


FULLTEXT_EXPORT_CONFIRMATION = "I_HAVE_RIGHTS_TO_PUBLISH_FULLTEXT"


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _iso_timestamp(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()


def _source_record(source: Account) -> Dict[str, Any]:
    return {
        "id": source.wechat_id,
        "name": source.name,
        "priority": source.priority,
        "source_type": source.source_type,
        "capture_method": source.capture_method,
        "content_mode": source.content_mode,
        "homepage_url": source.homepage_url,
        "feed_url": source.feed_url,
        "aliases": source.aliases,
        "profile_status": source.profile_status,
        "conflict_note": source.conflict_note,
        "scores": {
            "weight": source.weight,
            "influence": source.influence,
            "reliability": source.reliability,
            "originality": source.originality,
            "clickbait_risk": source.clickbait_risk,
        },
    }


def _article_record(
    row: Mapping[str, Any],
    include_content: bool,
    max_content_chars: Optional[int],
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": row["id"],
        "source_article_id": row["source_article_id"],
        "source_id": row["source_wechat_id"],
        "source_name": row["source_name"],
        "source_priority": row["priority"],
        "title": row["title"],
        "url": row["url"],
        "published_at": _iso_timestamp(row["published_at"]),
        "description": row["description"],
        "transcript_url": row["transcript_url"],
        "transcript_status": row["transcript_status"],
        "primary_topic": row["primary_topic"],
        "secondary_topics": _json_value(row["secondary_topics_json"], []),
        "tertiary_topics": _json_value(row["tertiary_topics_json"], []),
        "relevance": row["relevance"],
        "ai_summary": row["ai_summary"],
        "facts": _json_value(row["facts_json"], []),
        "opinions": _json_value(row["opinions_json"], []),
        "viewpoints": _json_value(row["viewpoints_json"], []),
        "inferences": _json_value(row["inferences_json"], []),
        "companies": _json_value(row["companies_json"], []),
        "people": _json_value(row["people_json"], []),
        "event_types": _json_value(row["event_types_json"], []),
        "financing": _json_value(row["financing_json"], {}),
        "signals": _json_value(row["signals_json"], []),
        "event_signature": row["event_signature"],
        "source_role": row["source_role"],
        "evidence_quality": row["evidence_quality"],
        "credibility": row["credibility"],
        "originality_score": row["originality_score"],
        "clickbait_score": row["clickbait_score"],
        "verification_flags": _json_value(row["verification_flags_json"], []),
        "analysis_status": row["analysis_status"],
        "analysis_model": row["analysis_model"],
        "analyzed_at": _iso_timestamp(row["analyzed_at"]),
        "ingested_at": _iso_timestamp(row["ingested_at"]),
        "updated_at": _iso_timestamp(row["updated_at"]),
    }
    if include_content:
        content_text = row["content_text"] or ""
        content_html = row["content_html"] or ""
        if max_content_chars is not None:
            content_text = content_text[:max_content_chars]
            content_html = content_html[:max_content_chars]
        record["content_text"] = content_text
        record["content_html"] = content_html
    return record


def export_public_archive(
    settings: Settings,
    db: Database,
    output_dir: Path,
    include_content: bool = False,
    rights_confirmed: bool = False,
    max_content_chars: Optional[int] = None,
) -> Dict[str, Any]:
    if include_content and not rights_confirmed:
        raise RuntimeError(
            "Full-text export requires --rights-confirmed. "
            "Only use it for sources where you have permission or a compatible license."
        )

    output_dir = settings.resolve_path(str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    sources_path = output_dir / "sources.json"
    articles_path = output_dir / "articles.jsonl"
    reports_path = output_dir / "reports.json"
    manifest_path = output_dir / "manifest.json"

    sources = [_source_record(source) for source in settings.all_sources]
    sources_path.write_text(
        json.dumps({"sources": sources}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    article_count = 0
    with articles_path.open("w", encoding="utf-8") as handle:
        for row in db.rows("SELECT * FROM articles ORDER BY published_at DESC, id"):
            handle.write(
                json.dumps(
                    _article_record(row, include_content, max_content_chars),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            article_count += 1

    report_rows = db.rows(
        """
        SELECT id, kind, period_start, period_end, title, markdown_path, model,
               created_at, notion_url, notion_status
        FROM reports ORDER BY period_end DESC, id DESC
        """
    )
    reports = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "period_start": _iso_timestamp(row["period_start"]),
            "period_end": _iso_timestamp(row["period_end"]),
            "title": row["title"],
            "markdown_path": row["markdown_path"],
            "model": row["model"],
            "created_at": _iso_timestamp(row["created_at"]),
            "notion_url": row["notion_url"],
            "notion_status": row["notion_status"],
        }
        for row in report_rows
    ]
    reports_path.write_text(
        json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "article_count": article_count,
        "source_count": len(sources),
        "report_count": len(reports),
        "includes_full_text": include_content,
        "rights_confirmation": FULLTEXT_EXPORT_CONFIRMATION if include_content else None,
        "content_policy": (
            "Code is MIT licensed. Article copyrights remain with their original publishers. "
            "The default archive exports metadata, links, and generated analysis, not full article text."
        ),
        "files": {
            "sources": sources_path.name,
            "articles": articles_path.name,
            "reports": reports_path.name,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "sources": len(sources),
        "articles": article_count,
        "reports": len(reports),
        "includes_full_text": include_content,
        "files": [sources_path.name, articles_path.name, reports_path.name, manifest_path.name],
    }
