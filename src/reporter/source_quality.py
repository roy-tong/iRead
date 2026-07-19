from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .db import Database
from .feedback import list_feedback
from .settings import Settings


def _clamp(value: Any, minimum: float = 0.0, maximum: float = 100.0) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return minimum


def _posterior(prior: float, observed: Optional[float], samples: int, prior_samples: int) -> float:
    if observed is None or samples <= 0:
        return _clamp(prior)
    return _clamp((prior * prior_samples + float(observed) * samples) / (prior_samples + samples))


def _source_role(source_type: str) -> str:
    value = source_type.casefold()
    if "first_party" in value or any(token in value for token in ("official", "regulator", "standards")):
        return "primary_source"
    if any(token in value for token in ("media", "reporting", "journalism")):
        return "independent_reporting"
    if any(token in value for token in ("interview", "practitioner", "researcher", "author")):
        return "expert_voice"
    if any(token in value for token in ("aggregation", "repost", "community", "social")):
        return "discovery_signal"
    return "specialist_analysis"


def _grade(score: float, thresholds: Mapping[str, Any]) -> str:
    if score >= float(thresholds.get("a", 80)):
        return "A"
    if score >= float(thresholds.get("b", 65)):
        return "B"
    if score >= float(thresholds.get("c", 50)):
        return "C"
    return "D"


def _confidence(samples: int, thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    high = max(1, int(thresholds.get("high", 20)))
    medium = max(1, int(thresholds.get("medium", 5)))
    if samples >= high:
        label = "high"
    elif samples >= medium:
        label = "medium"
    else:
        label = "low"
    return {
        "label": label,
        "score": round(min(100.0, 15.0 + 85.0 * min(samples, high) / high), 1),
        "analyzed_articles": samples,
        "high_confidence_at": high,
    }


def _representative_score(row: Mapping[str, Any]) -> float:
    return (
        0.32 * _clamp(row["relevance"] if row["relevance"] is not None else 35)
        + 0.20 * _clamp(row["evidence_quality"] if row["evidence_quality"] is not None else 45)
        + 0.18 * _clamp(row["credibility"] if row["credibility"] is not None else 50)
        + 0.22 * _clamp(row["originality_score"] if row["originality_score"] is not None else 45)
        - 0.08 * _clamp(row["clickbait_score"] if row["clickbait_score"] is not None else 25)
    )


def _representative_reason(row: Mapping[str, Any]) -> List[str]:
    reasons: List[str] = []
    if _clamp(row["relevance"]) >= 75:
        reasons.append("与当前研究领域高度相关")
    if _clamp(row["evidence_quality"]) >= 70:
        reasons.append("证据材料较完整")
    if _clamp(row["originality_score"]) >= 70:
        reasons.append("包含较多原创信息或分析")
    if str(row["source_role"] or "") in {"first_party", "original_reporting", "interview"}:
        reasons.append("具有一手信息属性")
    return reasons or ["近期可用的代表内容"]


def _representative_works(
    db: Database,
    source_id: str,
    limit: int,
    timezone_name: str,
) -> List[Dict[str, Any]]:
    rows = db.rows(
        """
        SELECT id, title, url, published_at, relevance, evidence_quality, credibility,
               originality_score, clickbait_score, source_role
        FROM articles
        WHERE source_wechat_id=?
        ORDER BY published_at DESC
        LIMIT 300
        """,
        (source_id,),
    )
    if not rows or limit <= 0:
        return []

    quality_order = sorted(rows, key=_representative_score, reverse=True)
    originality_order = sorted(
        rows,
        key=lambda row: (
            _clamp(row["originality_score"]),
            _clamp(row["evidence_quality"]),
            int(row["published_at"]),
        ),
        reverse=True,
    )
    selected: List[Mapping[str, Any]] = []
    for candidate in [quality_order[0], rows[0], originality_order[0], *quality_order]:
        if any(str(item["id"]) == str(candidate["id"]) for item in selected):
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break

    local_timezone = ZoneInfo(timezone_name)
    return [
        {
            "article_id": str(row["id"]),
            "title": str(row["title"]),
            "url": str(row["url"] or ""),
            "published_at": datetime.fromtimestamp(
                int(row["published_at"]), tz=local_timezone
            ).isoformat(),
            "representative_score": round(_representative_score(row), 1),
            "reasons": _representative_reason(row),
        }
        for row in selected
    ]


def _collection_score(
    row: Mapping[str, Any],
    as_of_ts: int,
    stale_days: int,
) -> Dict[str, Any]:
    article_count = int(row["article_count"] or 0)
    latest_at = int(row["latest_article_at"] or 0)
    if article_count == 0:
        availability = 20.0 if str(row["capture_method"]) == "web_pending" else 0.0
        freshness = 0.0
        days_since_latest: Optional[float] = None
    else:
        availability = 100.0 if str(row["capture_method"]) in {"rss", "wechat"} else 60.0
        days_since_latest = max(0.0, (as_of_ts - latest_at) / 86400)
        grace = max(1, stale_days)
        freshness = 100.0 if days_since_latest <= grace else max(
            0.0, 100.0 - (days_since_latest - grace) * 100.0 / (grace * 2)
        )
    content_coverage = _clamp(row["content_coverage"])
    archive_depth = min(100.0, article_count * 5.0)
    score = 0.35 * availability + 0.30 * freshness + 0.25 * content_coverage + 0.10 * archive_depth
    return {
        "score": round(score, 1),
        "article_count": article_count,
        "days_since_latest": round(days_since_latest, 1) if days_since_latest is not None else None,
        "content_coverage": round(content_coverage, 1),
        "capture_method": str(row["capture_method"]),
    }


def review_sources(
    settings: Settings,
    db: Database,
    representative_works: Optional[int] = None,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    policy = settings.source_policy.get("rating", {})
    prior_samples = max(1, int(policy.get("prior_sample_size", 20)))
    confidence_thresholds = policy.get("confidence_samples", {})
    grade_thresholds = policy.get("grade_thresholds", {})
    weights = policy.get(
        "overall_weights",
        {"domain_fit": 0.4, "content_quality": 0.4, "collection_quality": 0.2},
    )
    weight_total = sum(max(0.0, float(value)) for value in weights.values()) or 1.0
    work_limit = int(
        representative_works
        if representative_works is not None
        else settings.source_policy.get("portfolio", {}).get("representative_works", 3)
    )
    current = as_of or datetime.now(timezone.utc)
    as_of_ts = int(current.timestamp())
    timezone_name = str(settings.reporting.get("timezone", "Asia/Shanghai"))
    configured_sources = {source.wechat_id: source for source in settings.all_sources}
    source_feedback: Dict[str, List[Dict[str, Any]]] = {}
    for item in list_feedback(settings, target="source", limit=100)["items"]:
        target_id = str(item.get("target_id") or "")
        if target_id:
            source_feedback.setdefault(target_id, []).append(item)
    fit_priors = policy.get(
        "domain_fit_priors",
        {"required": 85, "preferred": 68, "watch": 50},
    )

    rows = db.rows(
        """
        SELECT ac.*,
               COUNT(a.id) AS article_count,
               SUM(CASE WHEN a.analysis_status='done' THEN 1 ELSE 0 END) AS analyzed_count,
               AVG(CASE WHEN a.analysis_status='done' THEN a.relevance END) AS observed_relevance,
               AVG(CASE WHEN a.analysis_status='done' THEN a.evidence_quality END) AS observed_evidence,
               AVG(CASE WHEN a.analysis_status='done' THEN a.credibility END) AS observed_credibility,
               AVG(CASE WHEN a.analysis_status='done' THEN a.originality_score END) AS observed_originality,
               AVG(CASE WHEN a.analysis_status='done' THEN a.clickbait_score END) AS observed_clickbait,
               MAX(a.published_at) AS latest_article_at,
               AVG(CASE WHEN a.id IS NULL THEN NULL
                        WHEN LENGTH(TRIM(COALESCE(a.content_text, ''))) >= 100 THEN 100.0
                        ELSE 0.0 END) AS content_coverage
        FROM accounts ac
        LEFT JOIN articles a ON a.source_wechat_id=ac.wechat_id
        GROUP BY ac.wechat_id
        """
    )

    sources: List[Dict[str, Any]] = []
    collection_config = settings.reporting.get("collection", {})
    for row in rows:
        analyzed_count = int(row["analyzed_count"] or 0)
        prior_fit = _clamp(fit_priors.get(str(row["priority"]), 50))
        domain_fit = _posterior(
            prior_fit,
            float(row["observed_relevance"]) if row["observed_relevance"] is not None else None,
            analyzed_count,
            prior_samples,
        )
        prior_content = 100 * (
            0.40 * float(row["reliability"])
            + 0.25 * float(row["originality"])
            + 0.15 * float(row["influence"])
            + 0.20 * (1.0 - float(row["clickbait_risk"]))
        )
        observed_content: Optional[float] = None
        if analyzed_count:
            observed_content = (
                0.30 * _clamp(row["observed_evidence"])
                + 0.35 * _clamp(row["observed_credibility"])
                + 0.25 * _clamp(row["observed_originality"])
                + 0.10 * (100.0 - _clamp(row["observed_clickbait"]))
            )
        content_quality = _posterior(
            prior_content, observed_content, analyzed_count, prior_samples
        )
        stale_key = "stale_required_days" if str(row["priority"]) == "required" else "stale_other_days"
        collection = _collection_score(
            row,
            as_of_ts,
            int(collection_config.get(stale_key, 30)),
        )
        dimensions = {
            "domain_fit": round(domain_fit, 1),
            "content_quality": round(content_quality, 1),
            "collection_quality": collection["score"],
        }
        overall = sum(
            dimensions.get(name, 0.0) * max(0.0, float(weight))
            for name, weight in weights.items()
        ) / weight_total
        if overall >= 75 and domain_fit >= 65 and collection["score"] >= 50:
            recommended_tier = "required"
        elif overall >= 60 and domain_fit >= 50:
            recommended_tier = "preferred"
        else:
            recommended_tier = "watch"
        warnings: List[str] = []
        if int(row["article_count"] or 0) == 0:
            warnings.append("尚未采集到文章")
        if analyzed_count < int(confidence_thresholds.get("medium", 5)):
            warnings.append("实测样本不足，当前评级主要依赖人工先验")
        if str(row["capture_method"]) == "web_pending":
            warnings.append("采集连接器尚未激活")
        user_feedback = source_feedback.get(str(row["wechat_id"]), [])
        if any(item.get("rating") == "down" for item in user_feedback):
            warnings.append("用户对该信源有未处理的负向反馈，调整层级前需要人工确认")

        configured = configured_sources.get(str(row["wechat_id"]))
        sources.append(
            {
                "id": str(row["wechat_id"]),
                "name": str(row["expected_name"]),
                "source_type": str(row["source_type"]),
                "role": _source_role(str(row["source_type"])),
                "homepage_url": str(configured.homepage_url or "") if configured else "",
                "feed_url": str(configured.feed_url or "") if configured else "",
                "content_mode": str(row["content_mode"]),
                "conflict_note": str(row["conflict_note"]),
                "configured_tier": str(row["priority"]),
                "recommended_tier": recommended_tier,
                "grade": _grade(overall, grade_thresholds),
                "overall_score": round(overall, 1),
                "dimensions": dimensions,
                "confidence": _confidence(analyzed_count, confidence_thresholds),
                "collection": collection,
                "observed_metrics": {
                    "relevance": round(float(row["observed_relevance"]), 1)
                    if row["observed_relevance"] is not None
                    else None,
                    "evidence_quality": round(float(row["observed_evidence"]), 1)
                    if row["observed_evidence"] is not None
                    else None,
                    "credibility": round(float(row["observed_credibility"]), 1)
                    if row["observed_credibility"] is not None
                    else None,
                    "originality": round(float(row["observed_originality"]), 1)
                    if row["observed_originality"] is not None
                    else None,
                    "clickbait_risk": round(float(row["observed_clickbait"]), 1)
                    if row["observed_clickbait"] is not None
                    else None,
                },
                "representative_works": _representative_works(
                    db, str(row["wechat_id"]), work_limit, timezone_name
                ),
                "user_feedback": user_feedback,
                "warnings": warnings,
            }
        )

    sources.sort(key=lambda item: (item["overall_score"], item["collection"]["article_count"]), reverse=True)
    tier_counts = {
        tier: sum(item["recommended_tier"] == tier for item in sources)
        for tier in ("required", "preferred", "watch")
    }
    return {
        "profile": settings.profile.as_dict(),
        "generated_at": current.astimezone(ZoneInfo(timezone_name)).isoformat(),
        "methodology": {
            "version": 1,
            "prior_sample_size": prior_samples,
            "overall_weights": weights,
            "note": "信源画像是先验；文章级实测会随样本量增加逐步接管评级。用户反馈会单独披露，不会未经确认直接改写评分。",
        },
        "summary": {
            "source_count": len(sources),
            "sources_with_articles": sum(item["collection"]["article_count"] > 0 for item in sources),
            "sources_with_observed_quality": sum(item["confidence"]["analyzed_articles"] > 0 for item in sources),
            "sources_with_user_feedback": sum(bool(item["user_feedback"]) for item in sources),
            "recommended_tiers": tier_counts,
        },
        "sources": sources,
    }
