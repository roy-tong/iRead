from __future__ import annotations

import collections
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Counter, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from .analysis import run_codex_json
from .audit import coverage_audit
from .db import Database, now_ts
from .feedback import feedback_for_report
from .ranking import article_editorial_score, rank_event_clusters
from .settings import Settings


def _json_list(value: Any) -> List[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _scheduled_end(settings: Settings, now: Optional[datetime] = None) -> datetime:
    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    current = now.astimezone(timezone) if now else datetime.now(timezone)
    hour = int(settings.reporting["daily"].get("publish_hour", 18))
    minute = int(settings.reporting["daily"].get("publish_minute", 0))
    end = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return end if current >= end else end - timedelta(days=1)


def report_window(
    settings: Settings,
    kind: str,
    now: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    end = _scheduled_end(settings, now)
    if kind == "daily":
        return end - timedelta(hours=int(settings.reporting["daily"]["rolling_hours"])), end
    if kind == "weekly":
        return end - timedelta(days=int(settings.reporting["weekly"]["rolling_days"])), end
    if kind == "monthly":
        return end.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end
    raise ValueError(f"Unknown report kind: {kind}")


def due_report_kinds(settings: Settings, now: Optional[datetime] = None) -> List[str]:
    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    current = now.astimezone(timezone) if now else datetime.now(timezone)
    kinds = ["daily"] if settings.reporting["daily"].get("enabled", True) else []
    if settings.reporting["weekly"].get("enabled", True) and current.weekday() == int(
        settings.reporting["weekly"].get("weekday", 4)
    ):
        kinds.append("weekly")
    tomorrow = current + timedelta(days=1)
    if settings.reporting["monthly"].get("enabled", True) and tomorrow.month != current.month:
        kinds.append("monthly")
    return kinds


def _period_label(kind: str, start: datetime, end: datetime) -> str:
    if kind == "daily":
        return end.strftime("%Y-%m-%d")
    if kind == "weekly":
        return f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    return end.strftime("%Y年%m月")


def _report_title(settings: Settings, kind: str, start: datetime, end: datetime) -> str:
    kind_labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    prefix = settings.reporting[kind].get("title_prefix") or (
        f"{settings.profile.name}{kind_labels[kind]}"
    )
    return f"{prefix} - {_period_label(kind, start, end)}"


def _article_for_report(
    row: Mapping[str, Any],
    cluster: Optional[Mapping[str, Any]] = None,
    timezone_name: str = "Asia/Shanghai",
) -> Dict[str, Any]:
    summary = row["ai_summary"] or row["description"] or (row["content_text"] or "")[:700]
    return {
        "article_id": row["id"],
        "analysis_status": row["analysis_status"],
        "source": row["source_name"],
        "source_priority": row["priority"],
        "source_weight": row["weight"],
        "source_profile": {
            "influence": row["influence"],
            "reliability": row["reliability"],
            "originality": row["originality"],
            "clickbait_risk": row["clickbait_risk"],
            "source_type": row["source_type"],
            "content_mode": row["content_mode"],
            "conflict_note": row["conflict_note"],
            "status": row["profile_status"],
        },
        "published_at": datetime.fromtimestamp(
            int(row["published_at"]), tz=ZoneInfo(timezone_name)
        ).isoformat(),
        "title": row["title"],
        "url": row["url"],
        "transcript_url": row["transcript_url"],
        "transcript_status": row["transcript_status"],
        "primary_topic": row["primary_topic"] or "unclassified",
        "secondary_topics": _json_list(row["secondary_topics_json"]),
        "relevance": row["relevance"],
        "summary": str(summary)[:900],
        "facts": _json_list(row["facts_json"])[:5],
        "opinions": _json_list(row["opinions_json"])[:3],
        "viewpoints": _json_list(row["viewpoints_json"])[:5],
        "inferences": _json_list(row["inferences_json"])[:3],
        "companies": _json_list(row["companies_json"]),
        "people": _json_list(row["people_json"]),
        "event_types": _json_list(row["event_types_json"]),
        "event_signature": row["event_signature"] or row["title"],
        "source_role": row["source_role"] or "unknown",
        "evidence_quality": row["evidence_quality"],
        "credibility": row["credibility"],
        "originality": row["originality_score"],
        "clickbait_risk": row["clickbait_score"],
        "verification_flags": _json_list(row["verification_flags_json"]),
        "event_ranking": {
            "cluster_id": cluster["cluster_id"],
            "classification": cluster["classification"],
            "priority_score": cluster["priority_score"],
            "information_gain_score": cluster["information_gain_score"],
            "editorial_tier": cluster["editorial_tier"],
            "consensus_score": cluster["consensus_score"],
            "exclusivity_score": cluster["exclusivity_score"],
            "source_count": cluster["source_count"],
            "independent_source_count": cluster["independent_source_count"],
        } if cluster else {},
        "financing": json.loads(row["financing_json"]) if row["financing_json"] else {},
        "signals": _json_list(row["signals_json"]),
    }


def _counter(values: Iterable[str], limit: int = 30) -> List[Tuple[str, int]]:
    return collections.Counter(value for value in values if value).most_common(limit)


def _aggregates(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    topics = _counter(str(row["primary_topic"] or "unclassified") for row in rows)
    companies = _counter(
        str(value) for row in rows for value in _json_list(row["companies_json"])
    )
    people = _counter(str(value) for row in rows for value in _json_list(row["people_json"]))
    events = _counter(
        str(value) for row in rows for value in _json_list(row["event_types_json"])
    )
    sources = _counter(str(row["source_name"]) for row in rows)
    viewpoint_speakers = _counter(
        str(viewpoint.get("speaker", ""))
        for row in rows
        for viewpoint in _json_list(row["viewpoints_json"])
        if isinstance(viewpoint, dict)
    )
    financing_companies = []
    for row in rows:
        if not row["financing_json"]:
            continue
        try:
            financing = json.loads(row["financing_json"])
        except json.JSONDecodeError:
            continue
        if financing.get("is_financing") and financing.get("company"):
            financing_companies.append(str(financing["company"]))
    status_counts = collections.Counter(str(row["analysis_status"] or "unknown") for row in rows)
    analyzed_count = status_counts.get("done", 0)
    return {
        "article_count": len(rows),
        "analyzed_article_count": analyzed_count,
        "analysis_coverage": round(analyzed_count / len(rows), 3) if rows else 1.0,
        "analysis_statuses": dict(status_counts),
        "topics": topics,
        "sources": sources,
        "companies": companies,
        "people": people,
        "viewpoint_speakers": viewpoint_speakers,
        "event_types": events,
        "financing_companies": _counter(financing_companies),
    }


def _monthly_history(settings: Settings, db: Database, end_ts: int) -> List[Dict[str, Any]]:
    rows = db.rows(
        """
        SELECT a.* FROM articles a
        WHERE a.published_at >= ? AND a.published_at <= ?
        ORDER BY a.published_at
        """,
        (int(settings.history_start.timestamp()), end_ts),
    )
    groups: Dict[str, List[Mapping[str, Any]]] = collections.defaultdict(list)
    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    for row in rows:
        month = datetime.fromtimestamp(int(row["published_at"]), tz=timezone).strftime("%Y-%m")
        groups[month].append(row)
    return [{"month": month, **_aggregates(group)} for month, group in sorted(groups.items())]


def _prior_reports(db: Database, kind: str, before_ts: int, limit: int) -> List[Dict[str, str]]:
    rows = db.rows(
        """
        SELECT title, markdown_path FROM reports
        WHERE kind=? AND period_end < ? ORDER BY period_end DESC LIMIT ?
        """,
        (kind, before_ts, limit),
    )
    result: List[Dict[str, str]] = []
    for row in rows:
        path = Path(str(row["markdown_path"]))
        if path.exists():
            result.append({"title": row["title"], "markdown": path.read_text(encoding="utf-8")[:30000]})
    return result


def _strip_first_heading(markdown: str) -> str:
    return re.sub(r"\A\s*#\s+[^\n]+\n+", "", markdown.strip(), count=1)


def _compact_audit(audit: Mapping[str, Any], aggregates: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": audit["status"],
        "required_sources": audit["required_sources"],
        "all_sources": audit["all_sources"],
        "external_sources": audit.get("external_sources", {"active": 0, "total": 0}),
        "period_articles": aggregates["article_count"],
        "period_analyzed_articles": aggregates["analyzed_article_count"],
        "period_analysis_coverage": aggregates["analysis_coverage"],
        "critical_issue_count": len(audit.get("critical", [])),
        "warning_count": len(audit.get("warnings", [])),
    }


def _data_confidence_markdown(data_quality: Mapping[str, Any]) -> str:
    analyzed = int(data_quality["period_analyzed_articles"])
    total = int(data_quality["period_articles"])
    coverage = float(data_quality["period_analysis_coverage"]) * 100
    status = str(data_quality["status"])
    return (
        "## 数据置信度\n\n"
        f"本期 {total} 篇中 {analyzed} 篇已完成结构化分析（{coverage:.0f}%）；"
        f"采集健康状态为 `{status}`。该状态只用于下调结论置信度，不作为行业信号。"
    )


def _cluster_article_ids(
    clusters: Sequence[Mapping[str, Any]],
    row_by_id: Mapping[str, Mapping[str, Any]],
    max_clusters: int,
    max_articles_per_event: int,
    detail_limit: int,
) -> List[str]:
    selected: List[str] = []
    for cluster in clusters[:max_clusters]:
        member_ids = [
            str(article_id)
            for article_id in cluster["article_ids"]
            if str(article_id) in row_by_id
        ]
        member_ids.sort(
            key=lambda article_id: (
                article_editorial_score(row_by_id[article_id]),
                int(row_by_id[article_id]["published_at"]),
            ),
            reverse=True,
        )
        representative_id = str(cluster["representative_article_id"])
        ordered_ids = [representative_id] + [
            article_id for article_id in member_ids if article_id != representative_id
        ]
        selected.extend(ordered_ids[:max_articles_per_event])
        if len(selected) >= detail_limit:
            break
    return selected[:detail_limit]


def _cluster_for_prompt(cluster: Mapping[str, Any], max_article_ids: int) -> Dict[str, Any]:
    payload = dict(cluster)
    payload["article_ids"] = list(cluster["article_ids"])[:max_article_ids]
    return payload


def generate_report(
    settings: Settings,
    db: Database,
    kind: str,
    now: Optional[datetime] = None,
    force: bool = False,
) -> Dict[str, Any]:
    start, end = report_window(settings, kind, now)
    start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
    existing = db.report_row(kind, start_ts, end_ts)
    if existing and not force and Path(existing["markdown_path"]).exists():
        return {"report_id": existing["id"], "title": existing["title"], "path": existing["markdown_path"], "reused": True}

    all_rows = db.rows(
        """
        WITH source_frequency AS (
            SELECT source_wechat_id, COUNT(*) AS recent_articles_30d
            FROM articles
            WHERE published_at >= ? AND published_at <= ?
            GROUP BY source_wechat_id
        )
        SELECT a.*, ac.weight, ac.influence, ac.reliability, ac.originality,
               ac.clickbait_risk, ac.source_type, ac.profile_status,
               ac.content_mode, ac.conflict_note, ac.collection_status,
               COALESCE(sf.recent_articles_30d, 0) AS recent_articles_30d
        FROM articles a JOIN accounts ac ON ac.wechat_id=a.source_wechat_id
        LEFT JOIN source_frequency sf ON sf.source_wechat_id=a.source_wechat_id
        WHERE a.published_at > ? AND a.published_at <= ?
        ORDER BY a.published_at DESC
        """,
        (end_ts - 30 * 86400, end_ts, start_ts, end_ts),
    )
    configured_limit = int(settings.reporting[kind].get("max_articles", 1000))
    detail_limit = int(settings.reporting[kind].get("detail_articles", configured_limit))
    max_clusters = int(settings.reporting[kind].get("max_event_clusters", 100))
    max_articles_per_event = int(
        settings.reporting[kind].get(
            "max_articles_per_event",
            settings.reporting.get("editorial_policy", {}).get("max_articles_per_event", 3),
        )
    )
    candidate_rows = sorted(
        all_rows,
        key=lambda row: (article_editorial_score(row), int(row["published_at"])),
        reverse=True,
    )[:configured_limit]
    event_clusters = rank_event_clusters(candidate_rows)
    row_by_id = {str(row["id"]): row for row in candidate_rows}
    cluster_by_article_id = {
        article_id: cluster
        for cluster in event_clusters
        for article_id in cluster["article_ids"]
    }
    ranked_article_ids = _cluster_article_ids(
        event_clusters,
        row_by_id,
        max_clusters,
        max_articles_per_event,
        detail_limit,
    )
    detail_rows = [row_by_id[article_id] for article_id in ranked_article_ids]
    audit = coverage_audit(settings, db)
    period_aggregates = _aggregates(all_rows)
    data_quality = _compact_audit(audit, period_aggregates)
    history_context: Dict[str, Any] = {"monthly_aggregates": _monthly_history(settings, db, end_ts)}
    if kind == "daily":
        history_context["prior_reports"] = _prior_reports(db, "daily", start_ts, 2)
    elif kind == "weekly":
        history_context["prior_reports"] = _prior_reports(db, "weekly", start_ts, 4)
    elif kind == "monthly":
        history_context["prior_reports"] = _prior_reports(db, "monthly", start_ts, 6)

    input_payload = {
        "research_profile": settings.profile.as_dict(),
        "topic_taxonomy": settings.topics,
        "report_kind": kind,
        "report_policy": settings.reporting[kind],
        "editorial_policy": settings.reporting.get("editorial_policy", {}),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "data_quality": data_quality,
        "period_aggregates": period_aggregates,
        "event_ranking_method": {
            "dimensions": [
                "article_relevance",
                "source_influence",
                "source_reliability",
                "cross_source_consensus",
                "exclusive_value",
                "evidence_quality",
                "originality",
                "attributable_original_viewpoints",
                "clickbait_penalty",
            ],
            "source_profiles_are": "provisional priors; article evidence and cross-source verification take precedence",
        },
        "event_clusters_total": len(event_clusters),
        "event_clusters": [
            _cluster_for_prompt(cluster, max_articles_per_event)
            for cluster in event_clusters[:max_clusters]
        ],
        "history_context": history_context,
        "user_feedback": feedback_for_report(settings),
        "articles_included": len(detail_rows),
        "articles_total": len(all_rows),
        "articles": [
            _article_for_report(
                row,
                cluster_by_article_id.get(str(row["id"])),
                str(settings.reporting.get("timezone", "Asia/Shanghai")),
            )
            for row in detail_rows
        ],
    }
    common = (settings.prompt_dir / "report_common.md").read_text(encoding="utf-8")
    specific = (settings.prompt_dir / f"{kind}.md").read_text(encoding="utf-8")
    prompt = common + "\n\n" + specific + "\n\n输入数据：\n" + json.dumps(input_payload, ensure_ascii=False)
    response = run_codex_json(
        settings,
        prompt,
        settings.schema_dir / "report.schema.json",
        purpose=f"report-{kind}",
    )
    title = _report_title(settings, kind, start, end)
    body = _strip_first_heading(str(response["markdown"]))
    markdown = f"# {title}\n\n{body}\n\n---\n\n{_data_confidence_markdown(data_quality)}\n"
    output_dir = settings.data_dir / "reports" / end.strftime("%Y") / end.strftime("%m")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{end:%Y-%m-%d}-{kind}.md"
    path.write_text(markdown, encoding="utf-8")
    model = str(settings.env("CODEX_MODEL", settings.reporting["analysis"]["model"]))
    report_id = db.upsert_report(
        {
            "kind": kind,
            "period_start": start_ts,
            "period_end": end_ts,
            "title": title,
            "markdown_path": str(path),
            "model": model,
            "created_at": now_ts(),
            "notion_status": "pending",
        }
    )
    return {
        "report_id": report_id,
        "title": title,
        "path": str(path),
        "executive_summary": response["executive_summary"],
        "top_topics": response["top_topics"],
        "reused": False,
    }
