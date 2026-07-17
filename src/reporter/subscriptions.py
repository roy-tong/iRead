from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from .proposals import (
    _batch_profiles,
    _normalize_proposal,
    _slug,
    apply_research_proposal,
)
from .settings import Settings, normalize_name
from .text import normalize_url


PRODUCT_NAME = "iRead"


def _unique(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _prefixed_id(domain_id: str, value: Any, fallback: str) -> str:
    return f"{domain_id}__{_slug(str(value or fallback), fallback)}"


def _merge_policy(policies: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not policies:
        raise ValueError("Every subscription report preset must define a policy")
    return {
        "enabled": any(bool(policy.get("enabled", True)) for policy in policies),
        "reading_minutes": max(
            int(policy.get("reading_minutes", 10)) for policy in policies
        ),
        "max_items": max(int(policy.get("max_items", 10)) for policy in policies),
        "focus": _unique(
            focus
            for policy in policies
            for focus in policy.get("focus", [])
        ),
    }


def _merge_report_presets(proposals: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for preset_id in ("light", "standard", "deep"):
        matching = [
            preset
            for proposal in proposals
            for preset in proposal.get("report_presets", [])
            if isinstance(preset, dict) and preset.get("id") == preset_id
        ]
        if not matching:
            raise ValueError(f"Missing report preset in approved proposals: {preset_id}")
        result.append(
            {
                "id": preset_id,
                "name": str(matching[0].get("name") or preset_id),
                "description": str(matching[0].get("description") or ""),
                "daily": _merge_policy([item["daily"] for item in matching]),
                "weekly": _merge_policy([item["weekly"] for item in matching]),
                "monthly": _merge_policy([item["monthly"] for item in matching]),
            }
        )
    return result


def _source_key(source: Mapping[str, Any]) -> str:
    platform_id = str(source.get("platform_id") or "").strip().casefold()
    if platform_id:
        return f"platform:{platform_id}"
    feed_url = normalize_url(str(source.get("feed_url") or "")).rstrip("/")
    if feed_url:
        return f"feed:{feed_url}"
    homepage_url = normalize_url(str(source.get("homepage_url") or "")).rstrip("/")
    if homepage_url:
        return f"home:{homepage_url}"
    name = str(source.get("name") or source.get("id") or "source")
    return f"name:{normalize_name(name)}"


def _annotated_reason(domain_name: str, reason: Any) -> str:
    reason = str(reason or "").strip()
    return f"[{domain_name}] {reason}" if reason else ""


def _merge_source(existing: Dict[str, Any], incoming: Mapping[str, Any]) -> None:
    for key in (
        "coverage_domains",
        "coverage_topics",
        "languages",
        "regions",
        "discovery_evidence_urls",
        "warnings",
    ):
        existing[key] = _unique(
            list(existing.get(key, [])) + list(incoming.get(key, []))
        )

    existing["recommendation_reason"] = "；".join(
        _unique(
            [
                existing.get("recommendation_reason", ""),
                incoming.get("recommendation_reason", ""),
            ]
        )
    )
    existing["conflict_note"] = "；".join(
        _unique(
            [existing.get("conflict_note", ""), incoming.get("conflict_note", "")]
        )
    )

    works: List[Dict[str, Any]] = []
    seen_works = set()
    for work in list(existing.get("representative_works", [])) + list(
        incoming.get("representative_works", [])
    ):
        if not isinstance(work, dict):
            continue
        key = str(work.get("url") or work.get("title") or "").strip()
        if key and key not in seen_works:
            seen_works.add(key)
            works.append(dict(work))
    existing["representative_works"] = works[:3]

    existing_scores = dict(existing.get("preliminary_scores", {}))
    incoming_scores = incoming.get("preliminary_scores", {})
    existing["preliminary_scores"] = {
        key: max(float(existing_scores.get(key, 0)), float(incoming_scores.get(key, 0)))
        for key in set(existing_scores) | set(incoming_scores)
    }
    confidence_order = {"low": 0, "medium": 1, "high": 2}
    existing_confidence = str(existing.get("score_confidence") or "low")
    incoming_confidence = str(incoming.get("score_confidence") or "low")
    if confidence_order.get(incoming_confidence, 0) > confidence_order.get(
        existing_confidence, 0
    ):
        existing["score_confidence"] = incoming_confidence

    for key in ("feed_url", "homepage_url", "platform_id"):
        if not existing.get(key) and incoming.get(key):
            existing[key] = incoming[key]
    if existing.get("feed_url"):
        existing["capture_method"] = "rss"
    elif existing.get("platform_id"):
        existing["capture_method"] = "wechat"


def merge_research_subscription(
    domains: Sequence[Tuple[Mapping[str, Any], Mapping[str, Any]]],
    subscription_id: str = "iread",
    subscription_name: str = PRODUCT_NAME,
) -> Dict[str, Any]:
    if not domains:
        raise ValueError("A subscription must include at least one approved domain")

    normalized_domains: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for item, raw_proposal in domains:
        proposal = _normalize_proposal(
            copy.deepcopy(dict(raw_proposal)),
            max(1, len(raw_proposal.get("sources", []))),
        )
        normalized_domains.append((dict(item), proposal))

    profile_values = [proposal["research_profile"] for _, proposal in normalized_domains]
    domain_records: List[Dict[str, Any]] = []
    topics: List[Dict[str, Any]] = []
    event_types: Dict[str, Dict[str, Any]] = {}
    company_seeds: Dict[str, List[str]] = {}
    people: List[str] = []
    sources_by_key: Dict[str, Dict[str, Any]] = {}
    source_order: List[str] = []
    coverage_notes: List[str] = []
    known_gaps: List[str] = []

    for item, proposal in normalized_domains:
        domain_id = _slug(str(item.get("id") or item.get("field")), "domain")
        domain_profile = proposal["research_profile"]
        domain_name = str(domain_profile.get("name") or item.get("field") or domain_id)
        taxonomy = proposal["topic_taxonomy"]
        topic_map: Dict[str, str] = {}
        secondaries: List[Dict[str, Any]] = []
        for raw_topic in taxonomy.get("topics", []):
            old_topic_id = str(raw_topic.get("id") or raw_topic.get("name") or "topic")
            topic_id = _prefixed_id(domain_id, old_topic_id, "topic")
            topic_map[old_topic_id] = topic_id
            secondary = {
                "id": topic_id,
                "name": str(raw_topic.get("name") or old_topic_id),
                "description": str(raw_topic.get("description") or ""),
                "keywords": _unique(raw_topic.get("keywords", [])),
            }
            tertiaries: List[Dict[str, Any]] = []
            for raw_secondary in raw_topic.get("secondaries", []):
                old_secondary_id = str(
                    raw_secondary.get("id") or raw_secondary.get("name") or "subtopic"
                )
                tertiary_id = _prefixed_id(topic_id, old_secondary_id, "subtopic")
                topic_map[old_secondary_id] = tertiary_id
                tertiaries.append(
                    {
                        "id": tertiary_id,
                        "name": str(raw_secondary.get("name") or old_secondary_id),
                        "description": str(raw_secondary.get("description") or ""),
                        "keywords": _unique(raw_secondary.get("keywords", [])),
                    }
                )
            if tertiaries:
                secondary["tertiaries"] = tertiaries
            secondaries.append(secondary)

        topics.append(
            {
                "id": domain_id,
                "name": domain_name,
                "description": str(domain_profile.get("description") or ""),
                "keywords": _unique(
                    list(domain_profile.get("seed_keywords", []))
                    + [
                        keyword
                        for topic in taxonomy.get("topics", [])
                        for keyword in topic.get("keywords", [])
                    ]
                ),
                "secondaries": secondaries,
            }
        )
        domain_records.append(
            {
                "id": domain_id,
                "name": domain_name,
                "field": str(item.get("field") or domain_name),
                "description": str(domain_profile.get("description") or ""),
                "topic_ids": [secondary["id"] for secondary in secondaries],
            }
        )

        for event_type in taxonomy.get("event_types", []):
            event_id = _slug(str(event_type.get("id") or event_type.get("name")), "event")
            existing_event = event_types.setdefault(
                event_id,
                {
                    "id": event_id,
                    "name": str(event_type.get("name") or event_id),
                    "keywords": [],
                },
            )
            existing_event["keywords"] = _unique(
                list(existing_event["keywords"]) + list(event_type.get("keywords", []))
            )

        entity_seeds = proposal.get("entity_seeds", {})
        for company_group in entity_seeds.get("companies", []):
            old_topic_id = str(company_group.get("topic_id") or "")
            mapped_topic_id = topic_map.get(old_topic_id, domain_id)
            company_seeds[mapped_topic_id] = _unique(
                company_seeds.get(mapped_topic_id, []) + list(company_group.get("names", []))
            )
        people = _unique(people + list(entity_seeds.get("people", [])))

        strategy = proposal.get("source_strategy", {})
        coverage_notes.extend(
            _annotated_reason(domain_name, value)
            for value in strategy.get("coverage_notes", [])
        )
        known_gaps.extend(
            _annotated_reason(domain_name, value)
            for value in strategy.get("known_gaps", [])
        )

        for raw_source in proposal.get("sources", []):
            source = copy.deepcopy(dict(raw_source))
            source["id"] = f"{domain_id}--{source['id']}"
            source["coverage_domains"] = [domain_id]
            source["coverage_topics"] = _unique(
                topic_map.get(str(topic_id), domain_id)
                for topic_id in source.get("coverage_topics", [])
            ) or [domain_id]
            source["recommendation_reason"] = _annotated_reason(
                domain_name, source.get("recommendation_reason")
            )
            key = _source_key(source)
            if key in sources_by_key:
                _merge_source(sources_by_key[key], source)
            else:
                sources_by_key[key] = source
                source_order.append(key)

    subscription_slug = _slug(subscription_id, "iread")
    return {
        "proposal_version": 1,
        "research_profile": {
            "id": subscription_slug,
            "name": subscription_name.strip() or PRODUCT_NAME,
            "description": "同时追踪多个专业领域："
            + "、".join(domain["name"] for domain in domain_records),
            "seed_keywords": _unique(
                keyword
                for profile in profile_values
                for keyword in profile.get("seed_keywords", [])
            ),
            "audiences": _unique(
                value for profile in profile_values for value in profile.get("audiences", [])
            ),
            "goals": _unique(
                value for profile in profile_values for value in profile.get("goals", [])
            ),
            "languages": _unique(
                value for profile in profile_values for value in profile.get("languages", [])
            ),
            "regions": _unique(
                value for profile in profile_values for value in profile.get("regions", [])
            ),
            "exclusions": _unique(
                value for profile in profile_values for value in profile.get("exclusions", [])
            ),
            "domains": domain_records,
        },
        "topic_taxonomy": {
            "classification_rules": _unique(
                ["先判断文章主要属于哪个订阅领域，再选择该领域下的二级主题。"]
                + [
                    rule
                    for _, proposal in normalized_domains
                    for rule in proposal["topic_taxonomy"].get("classification_rules", [])
                ]
            ),
            "topics": topics,
            "event_types": list(event_types.values()),
        },
        "entity_seeds": {
            "companies": [
                {"topic_id": topic_id, "names": names}
                for topic_id, names in company_seeds.items()
            ],
            "people": people,
        },
        "source_strategy": {
            "coverage_notes": _unique(coverage_notes),
            "known_gaps": _unique(known_gaps),
        },
        "sources": [sources_by_key[key] for key in source_order],
        "report_presets": _merge_report_presets(
            [proposal for _, proposal in normalized_domains]
        ),
    }


def apply_research_subscription(
    settings: Settings,
    manifest: Mapping[str, Any],
    proposals_dir: Path,
    output_dir: Path,
    approved: Optional[Iterable[str]] = None,
    approve_all: bool = False,
    subscription_id: Optional[str] = None,
    subscription_name: Optional[str] = None,
    preset_id: Optional[str] = None,
    history_start: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    profiles = _batch_profiles(manifest)
    known_ids = {item["id"] for item in profiles}
    approved_ids = {str(value) for value in (approved or [])}
    if not approve_all and not approved_ids:
        raise ValueError("Provide approved domain ids or set approve_all=True")
    unknown_ids = sorted(approved_ids - known_ids)
    if unknown_ids:
        raise ValueError("Unknown approved domain ids: " + ", ".join(unknown_ids))

    defaults = (
        manifest.get("defaults", {})
        if isinstance(manifest.get("defaults"), dict)
        else {}
    )
    selected = [
        item for item in profiles if approve_all or item["id"] in approved_ids
    ]
    resolved_presets = {
        str(item.get("preset", defaults.get("preset", "standard"))) for item in selected
    }
    if preset_id is None and len(resolved_presets) > 1:
        raise ValueError(
            "A unified subscription needs one report preset; pass preset_id explicitly"
        )
    selected_preset = preset_id or next(iter(resolved_presets), "standard")
    resolved_history_starts = {
        str(value)
        for item in selected
        if (value := item.get("history_start", defaults.get("history_start")))
    }
    if history_start is None and len(resolved_history_starts) > 1:
        raise ValueError(
            "A unified subscription needs one history boundary; pass history_start explicitly"
        )
    selected_history_start = history_start or next(
        iter(resolved_history_starts), None
    )

    proposals_dir = proposals_dir.resolve()
    domain_proposals: List[Tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    proposal_paths: List[str] = []
    for item in selected:
        proposal_path = proposals_dir / f"{item['id']}.json"
        if not proposal_path.exists():
            raise FileNotFoundError(f"Missing proposal: {proposal_path}")
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal_batch_id = proposal.get("batch_profile_id")
        if proposal_batch_id and proposal_batch_id != item["id"]:
            raise ValueError(
                f"Proposal batch id {proposal_batch_id!r} does not match {item['id']!r}"
            )
        domain_proposals.append((item, proposal))
        proposal_paths.append(str(proposal_path))

    subscription_config = (
        manifest.get("subscription", {})
        if isinstance(manifest.get("subscription"), dict)
        else {}
    )
    merged = merge_research_subscription(
        domain_proposals,
        subscription_id=str(
            subscription_id or subscription_config.get("id") or "iread"
        ),
        subscription_name=str(
            subscription_name or subscription_config.get("name") or PRODUCT_NAME
        ),
    )
    source_candidates = sum(
        len(proposal.get("sources", [])) for _, proposal in domain_proposals
    )
    result = apply_research_proposal(
        settings,
        merged,
        output_dir,
        preset_id=selected_preset,
        history_start=selected_history_start,
        force=force,
    )

    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    metadata = {
        "version": 1,
        "product": PRODUCT_NAME,
        "id": result["profile"]["id"],
        "name": result["profile"]["name"],
        "status": "configured",
        "created_at": datetime.now(timezone).isoformat(),
        "report_preset": selected_preset,
        "history_start": json.loads(
            (Path(result["output_dir"]) / "reporting.json").read_text(encoding="utf-8")
        )["history_start"],
        "domains": result["profile"]["domains"],
        "proposal_paths": proposal_paths,
    }
    subscription_path = Path(result["output_dir"]) / "subscription.json"
    subscription_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **result,
        "product": PRODUCT_NAME,
        "domain_count": len(metadata["domains"]),
        "domains": metadata["domains"],
        "source_candidates": source_candidates,
        "deduplicated_sources": source_candidates
        - result["wechat_sources"]
        - result["external_sources"],
        "subscription_file": str(subscription_path),
    }
