from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Mapping, Sequence, Set


INDEPENDENT_ROLES = {"first_party", "original_reporting", "interview"}
REPOST_ROLES = {"aggregation", "repost"}


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _json_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed if item] if isinstance(parsed, list) else []


def _json_dict(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _ngrams(value: Any, size: int = 2) -> Set[str]:
    text = _normalized(value)
    if len(text) <= size:
        return {text} if text else set()
    return {text[index:index + size] for index in range(len(text) - size + 1)}


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _score(row: Mapping[str, Any], field: str, fallback: float) -> float:
    try:
        return max(0.0, min(100.0, float(_value(row, field, fallback))))
    except (TypeError, ValueError):
        return fallback


def _profile_score(row: Mapping[str, Any], field: str, fallback: float) -> float:
    try:
        return max(0.0, min(1.0, float(_value(row, field, fallback)))) * 100
    except (TypeError, ValueError):
        return fallback * 100


def _is_analyzed(row: Mapping[str, Any]) -> bool:
    status = _value(row, "analysis_status")
    if status is not None:
        return str(status) == "done"
    return any(
        _value(row, field) is not None
        for field in (
            "relevance",
            "evidence_quality",
            "credibility",
            "originality_score",
            "clickbait_score",
        )
    )


def publication_frequency_score(row: Mapping[str, Any]) -> float:
    """Convert a rolling 30-day article count into an attention score."""
    try:
        count = max(0, int(_value(row, "recent_articles_30d", 0)))
    except (TypeError, ValueError):
        count = 0
    return round(min(100.0, count * 100.0 / 60.0), 2)


def article_editorial_score(row: Mapping[str, Any]) -> float:
    """Rank research value without letting source popularity stand in for evidence."""
    influence = _profile_score(row, "influence", 0.5)
    reliability = _profile_score(row, "reliability", 0.5)
    source_originality = _profile_score(row, "originality", 0.5)
    source_clickbait = _profile_score(row, "clickbait_risk", 0.25)
    frequency_attention = publication_frequency_score(row) * (
        0.35 + 0.65 * reliability / 100.0
    )
    priority_bonus = {"required": 6.0, "preferred": 3.0, "watch": 0.0}.get(
        str(_value(row, "priority", "watch")),
        0.0,
    )

    if not _is_analyzed(row):
        discovery_score = (
            0.22 * influence
            + 0.28 * reliability
            + 0.30 * source_originality
            + 0.08 * frequency_attention
            - 0.24 * source_clickbait
            + priority_bonus
            - 24.0
        )
        return round(max(0.0, min(100.0, discovery_score)), 2)

    role = str(_value(row, "source_role", "unknown"))
    role_bonus = {
        "first_party": 5.0,
        "original_reporting": 7.0,
        "interview": 9.0,
        "analysis": 4.0,
        "aggregation": -5.0,
        "repost": -9.0,
    }.get(role, 0.0)
    viewpoint_bonus = 7.0 if _json_list(_value(row, "viewpoints_json")) else 0.0
    score = (
        0.24 * _score(row, "relevance", 0)
        + 0.18 * _score(row, "evidence_quality", 0)
        + 0.16 * _score(row, "credibility", 0)
        + 0.16 * _score(row, "originality_score", 0)
        + 0.08 * influence
        + 0.07 * reliability
        + 0.06 * source_originality
        + 0.08 * frequency_attention
        - 0.12 * _score(row, "clickbait_score", 50)
        - 0.05 * source_clickbait
        + role_bonus
        + viewpoint_bonus
        + priority_bonus
    )
    return round(max(0.0, min(100.0, score)), 2)


def _same_event(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_time = int(_value(left, "published_at", 0))
    right_time = int(_value(right, "published_at", 0))
    if abs(left_time - right_time) > 10 * 86400:
        return False

    left_signature = _normalized(_value(left, "event_signature", ""))
    right_signature = _normalized(_value(right, "event_signature", ""))
    signature_similarity = (
        SequenceMatcher(None, left_signature, right_signature).ratio()
        if left_signature and right_signature
        else 0.0
    )
    if signature_similarity >= 0.78:
        return True

    left_financing = _json_dict(_value(left, "financing_json"))
    right_financing = _json_dict(_value(right, "financing_json"))
    left_company = _normalized(left_financing.get("company"))
    right_company = _normalized(right_financing.get("company"))
    if (
        left_financing.get("is_financing")
        and right_financing.get("is_financing")
        and left_company
        and left_company == right_company
    ):
        return True

    left_companies = {_normalized(item) for item in _json_list(_value(left, "companies_json"))}
    right_companies = {_normalized(item) for item in _json_list(_value(right, "companies_json"))}
    shared_companies = (left_companies & right_companies) - {""}
    left_events = {_normalized(item) for item in _json_list(_value(left, "event_types_json"))}
    right_events = {_normalized(item) for item in _json_list(_value(right, "event_types_json"))}
    shared_events = (left_events & right_events) - {""}
    title_similarity = _jaccard(
        _ngrams(_value(left, "title", "")), _ngrams(_value(right, "title", ""))
    )
    if shared_companies and shared_events and (title_similarity >= 0.12 or signature_similarity >= 0.45):
        return True
    return title_similarity >= 0.56


def _representative_score(row: Mapping[str, Any]) -> float:
    role = str(_value(row, "source_role", "unknown"))
    role_bonus = {
        "first_party": 5.0,
        "original_reporting": 7.0,
        "interview": 9.0,
        "aggregation": -4.0,
        "repost": -7.0,
    }.get(role, 0.0)
    return article_editorial_score(row) + role_bonus


def _cluster_payload(members: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    representative = max(members, key=_representative_score)
    analyzed_members = [row for row in members if _is_analyzed(row)]
    sources = sorted({str(_value(row, "source_name", "")) for row in members if _value(row, "source_name")})
    roles = [str(_value(row, "source_role", "unknown")) for row in analyzed_members]
    independent_sources = {
        str(_value(row, "source_name", ""))
        for row in analyzed_members
        if str(_value(row, "source_role", "unknown")) in INDEPENDENT_ROLES
    }
    source_count = len(sources)
    independent_count = len(independent_sources)
    repost_count = sum(1 for role in roles if role in REPOST_ROLES)
    relevance = max((_score(row, "relevance", 0) for row in analyzed_members), default=0.0)
    evidence = (
        sum(_score(row, "evidence_quality", 0) for row in analyzed_members) / len(analyzed_members)
        if analyzed_members
        else 0.0
    )
    credibility = (
        sum(_score(row, "credibility", 0) for row in analyzed_members) / len(analyzed_members)
        if analyzed_members
        else 0.0
    )
    originality = max(
        (_score(row, "originality_score", 0) for row in analyzed_members),
        default=0.0,
    )
    clickbait = (
        sum(_score(row, "clickbait_score", 50) for row in analyzed_members) / len(analyzed_members)
        if analyzed_members
        else max(_profile_score(row, "clickbait_risk", 0.25) for row in members)
    )
    influence = max(_profile_score(row, "influence", 0.5) for row in members)
    reliability = max(_profile_score(row, "reliability", 0.5) for row in members)
    viewpoint_count = sum(
        bool(_json_list(_value(row, "viewpoints_json"))) for row in analyzed_members
    )
    viewpoint_value = 100.0 if viewpoint_count else 0.0
    independent_breadth = min(1.0, independent_count / 3)
    repost_ratio = repost_count / max(1, len(analyzed_members))
    consensus = 100 * (
        0.75 * independent_breadth
        + 0.15 * min(1.0, independent_count / 2)
        + 0.10 * (influence / 100)
    ) * max(0.25, 1.0 - 0.75 * repost_ratio)
    exclusivity = 0.0
    if source_count == 1:
        exclusivity = max(
            0.0,
            min(
                100.0,
                0.35 * evidence
                + 0.25 * credibility
                + 0.25 * originality
                + 0.15 * reliability
                - 0.25 * clickbait,
            ),
        )
    if analyzed_members:
        priority = max(
            0.0,
            min(
                100.0,
                0.23 * relevance
                + 0.16 * consensus
                + 0.10 * influence
                + 0.14 * evidence
                + 0.12 * credibility
                + 0.12 * originality
                + 0.08 * exclusivity
                + 0.09 * viewpoint_value
                - 0.12 * clickbait,
            ),
        )
    else:
        priority = max(article_editorial_score(row) for row in members)
    information_gain = max(
        0.0,
        min(
            100.0,
            0.24 * originality
            + 0.20 * evidence
            + 0.16 * credibility
            + 0.14 * exclusivity
            + 0.12 * relevance
            + 0.10 * viewpoint_value
            + 0.04 * consensus
            - 0.10 * clickbait,
        ),
    )
    flags = sorted(
        {
            flag
            for row in members
            for flag in _json_list(_value(row, "verification_flags_json"))
        }
    )
    if not analyzed_members:
        classification = "unreviewed"
    elif (
        clickbait >= 60
        or credibility < 45
        or evidence < 30
        or (flags and source_count == 1 and credibility < 55 and evidence < 50)
    ):
        classification = "verification_needed"
    elif independent_count >= 2:
        classification = "cross_source_consensus"
    elif source_count == 1 and exclusivity >= 60 and evidence >= 55 and credibility >= 55:
        classification = "exclusive_candidate"
    else:
        classification = "normal"

    if classification == "unreviewed":
        editorial_tier = "discovery"
    elif classification == "verification_needed":
        editorial_tier = "watch"
    elif relevance >= 55 and evidence >= 55 and credibility >= 55 and (
        classification in {"cross_source_consensus", "exclusive_candidate"} or priority >= 58
    ):
        editorial_tier = "core"
    else:
        editorial_tier = "context"

    label = str(_value(representative, "event_signature", "")).strip() or str(
        _value(representative, "title", "未命名事件")
    )
    digest_input = "|".join(sorted(str(_value(row, "id", "")) for row in members))
    cluster_id = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12]
    return {
        "cluster_id": cluster_id,
        "event": label,
        "classification": classification,
        "editorial_tier": editorial_tier,
        "priority_score": round(priority, 1),
        "information_gain_score": round(information_gain, 1),
        "consensus_score": round(consensus, 1),
        "exclusivity_score": round(exclusivity, 1),
        "evidence_quality": round(evidence, 1),
        "credibility": round(credibility, 1),
        "clickbait_risk": round(clickbait, 1),
        "source_count": source_count,
        "independent_source_count": independent_count,
        "article_count": len(members),
        "analyzed_article_count": len(analyzed_members),
        "analysis_coverage": round(len(analyzed_members) / len(members), 3),
        "repost_or_aggregation_count": repost_count,
        "viewpoint_article_count": viewpoint_count,
        "sources": sources,
        "verification_flags": flags,
        "representative_article_id": str(_value(representative, "id", "")),
        "article_ids": [str(_value(row, "id", "")) for row in members],
    }


def rank_event_clusters(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: List[List[Mapping[str, Any]]] = []
    ordered = sorted(rows, key=lambda row: int(_value(row, "published_at", 0)), reverse=True)
    for row in ordered:
        match = next(
            (cluster for cluster in grouped if any(_same_event(row, member) for member in cluster)),
            None,
        )
        if match is None:
            grouped.append([row])
        else:
            match.append(row)
    return sorted(
        (_cluster_payload(cluster) for cluster in grouped),
        key=lambda item: (item["priority_score"], item["source_count"]),
        reverse=True,
    )
