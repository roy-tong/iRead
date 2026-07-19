from __future__ import annotations

import copy
import calendar
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .analysis import run_codex_json
from .settings import Settings


def _values(values: Optional[Iterable[str]], fallback: List[str]) -> List[str]:
    result = [str(value).strip() for value in (values or []) if str(value).strip()]
    return result or fallback


def _slug(value: str, fallback: str = "research-profile") -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if slug:
        return slug[:80]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{fallback}-{digest}"


def _is_web_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_scores(source: Dict[str, Any], warnings: List[str]) -> None:
    raw_scores = source.get("preliminary_scores", {})
    if not isinstance(raw_scores, dict) or not raw_scores:
        return
    scores = {key: float(value) for key, value in raw_scores.items()}
    highest = max(scores.values())
    scale = 1
    if highest <= 5:
        scale = 20
    elif highest <= 10:
        scale = 10
    if scale != 1:
        warnings.append(f"冷启动评分已从 {100 // scale} 分制归一化为 100 分制")
    source["preliminary_scores"] = {
        key: max(0, min(100, int(round(value * scale))))
        for key, value in scores.items()
    }


def _normalize_proposal(value: Dict[str, Any], max_sources: int) -> Dict[str, Any]:
    profile = value.get("research_profile", {})
    profile["id"] = _slug(str(profile.get("id") or profile.get("name") or "research-profile"))

    seen_ids = set()
    normalized_sources: List[Dict[str, Any]] = []
    for index, raw_source in enumerate(value.get("sources", [])):
        if not isinstance(raw_source, dict):
            continue
        source = dict(raw_source)
        source_id = _slug(str(source.get("id") or source.get("name") or f"source-{index + 1}"), "source")
        if source_id in seen_ids:
            source_id = f"{source_id}-{index + 1}"
        seen_ids.add(source_id)
        source["id"] = source_id
        source["homepage_url"] = str(source.get("homepage_url") or "").strip()
        source["feed_url"] = str(source.get("feed_url") or "").strip()
        warnings = [str(item) for item in source.get("warnings", []) if item]
        if source["homepage_url"] and not _is_web_url(source["homepage_url"]):
            warnings.append("主页 URL 格式无效，需要人工复核")
            source["homepage_url"] = ""
        if source["feed_url"] and not _is_web_url(source["feed_url"]):
            warnings.append("Feed URL 格式无效，已置空")
            source["feed_url"] = ""
        if source.get("capture_method") == "rss" and not source["feed_url"]:
            source["capture_method"] = "web"
            warnings.append("未确认 Feed URL，暂不激活 RSS 采集")
        _normalize_scores(source, warnings)
        source["warnings"] = list(dict.fromkeys(warnings))
        normalized_sources.append(source)
        if len(normalized_sources) >= max_sources:
            break
    value["sources"] = normalized_sources
    return value


def validate_research_proposal(
    proposal: Mapping[str, Any],
    *,
    strict: bool = True,
) -> Dict[str, Any]:
    """Validate the agent-authored parts that matter before configuration is applied."""
    errors: List[str] = []
    required_sections = (
        "research_profile",
        "topic_taxonomy",
        "entity_seeds",
        "source_strategy",
        "sources",
        "report_presets",
    )
    for section in required_sections:
        if section not in proposal:
            errors.append(f"missing section: {section}")

    profile = proposal.get("research_profile", {})
    if not isinstance(profile, Mapping):
        errors.append("research_profile must be an object")
    else:
        for key in ("id", "name", "description"):
            if not str(profile.get(key) or "").strip():
                errors.append(f"research_profile.{key} must not be empty")

    taxonomy = proposal.get("topic_taxonomy", {})
    topics = taxonomy.get("topics", []) if isinstance(taxonomy, Mapping) else []
    minimum_topics = 3 if strict else 1
    if not isinstance(topics, list) or len(topics) < minimum_topics:
        errors.append(f"topic_taxonomy.topics must contain at least {minimum_topics} item(s)")

    sources = proposal.get("sources", [])
    minimum_sources = 8 if strict else 1
    if not isinstance(sources, list) or len(sources) < minimum_sources:
        errors.append(f"sources must contain at least {minimum_sources} item(s)")
        sources = [] if not isinstance(sources, list) else sources

    allowed_roles = {
        "primary_source",
        "expert_voice",
        "independent_reporting",
        "specialist_analysis",
        "discovery_signal",
    }
    observed_roles = set()
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for key in ("id", "name", "capture_method"):
            if not str(source.get(key) or "").strip():
                errors.append(f"{prefix}.{key} must not be empty")
        role = str(source.get("role") or "")
        if role not in allowed_roles:
            errors.append(f"{prefix}.role is invalid: {role or '<empty>'}")
        else:
            observed_roles.add(role)
        locators = [
            str(source.get("homepage_url") or ""),
            str(source.get("feed_url") or ""),
            str(source.get("platform_id") or ""),
        ]
        if not any(value.strip() for value in locators):
            errors.append(f"{prefix} needs a homepage, feed, or platform id")
        for key in ("homepage_url", "feed_url"):
            value = str(source.get(key) or "").strip()
            if value and not _is_web_url(value):
                errors.append(f"{prefix}.{key} is not an HTTP(S) URL")
        works = source.get("representative_works", [])
        minimum_works = 2 if strict else 1
        if not isinstance(works, list) or len(works) < minimum_works:
            errors.append(
                f"{prefix}.representative_works must contain at least {minimum_works} item(s)"
            )
            continue
        for work_index, work in enumerate(works):
            if not isinstance(work, Mapping):
                errors.append(f"{prefix}.representative_works[{work_index}] must be an object")
                continue
            work_url = str(work.get("url") or "").strip()
            if not str(work.get("title") or "").strip() or not _is_web_url(work_url):
                errors.append(
                    f"{prefix}.representative_works[{work_index}] needs a title and HTTP(S) URL"
                )

    if strict:
        missing_roles = sorted(allowed_roles - observed_roles)
        if missing_roles:
            errors.append(
                "sources must cover every source role; missing: "
                + ", ".join(missing_roles)
            )

    presets = proposal.get("report_presets", [])
    preset_ids = {
        str(item.get("id"))
        for item in presets
        if isinstance(item, Mapping)
    } if isinstance(presets, list) else set()
    expected_presets = {"light", "standard", "deep"}
    if preset_ids != expected_presets:
        errors.append("report_presets must define light, standard, and deep exactly once")
    if isinstance(presets, list) and len(presets) != len(preset_ids):
        errors.append("report_presets contains duplicate ids")
    for preset in presets if isinstance(presets, list) else []:
        if not isinstance(preset, Mapping):
            continue
        for kind in ("daily", "weekly", "monthly"):
            policy = preset.get(kind)
            if not isinstance(policy, Mapping):
                errors.append(f"report preset {preset.get('id')} is missing {kind}")

    if errors:
        raise ValueError("Invalid research proposal:\n- " + "\n- ".join(errors))
    return {
        "status": "valid",
        "strict": strict,
        "profile_id": str(profile.get("id")),
        "profile_name": str(profile.get("name")),
        "topics": len(topics),
        "sources": len(sources),
        "source_roles": sorted(observed_roles),
        "report_presets": sorted(preset_ids),
    }


def propose_research_setup(
    settings: Settings,
    field: str,
    audiences: Optional[List[str]] = None,
    goals: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    max_sources: int = 20,
) -> Dict[str, Any]:
    field = field.strip()
    if not field:
        raise ValueError("field must not be empty")
    max_sources = max(8, min(40, int(max_sources)))
    request = {
        "field": field,
        "audiences": _values(audiences, ["research"]),
        "goals": _values(goals, ["material_changes", "trend_detection", "source_verification"]),
        "languages": _values(languages, ["zh-CN", "en"]),
        "regions": _values(regions, ["global"]),
        "maximum_source_candidates": max_sources,
        "current_date": datetime.now(ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))).date().isoformat(),
    }
    prompt_base = (settings.prompt_dir / "propose.md").read_text(encoding="utf-8")
    prompt = prompt_base + "\n\n用户输入：\n" + json.dumps(request, ensure_ascii=False, indent=2)
    response = run_codex_json(
        settings,
        prompt,
        settings.schema_dir / "research_proposal.schema.json",
        purpose="research-proposal",
        web_search=True,
    )
    normalized = _normalize_proposal(response, max_sources)
    generated_at = datetime.now(ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai")))
    return {
        "proposal_version": 1,
        "generated_at": generated_at.isoformat(),
        "request": request,
        **normalized,
    }


def _source_tier(source: Mapping[str, Any]) -> str:
    scores = source.get("preliminary_scores", {})
    composite = (
        0.35 * float(scores.get("domain_fit", 50))
        + 0.25 * float(scores.get("authority", 50))
        + 0.15 * float(scores.get("originality", 50))
        + 0.15 * float(scores.get("evidence_discipline", 50))
        + 0.10 * float(scores.get("captureability", 50))
    )
    if composite >= 78:
        return "required"
    if composite >= 62:
        return "preferred"
    return "watch"


def _source_common(source: Mapping[str, Any]) -> Dict[str, Any]:
    scores = source.get("preliminary_scores", {})
    return {
        "priority": _source_tier(source),
        "source_type": str(source.get("source_type") or source.get("role") or "unknown"),
        "profile_status": "proposed",
        "influence": round(float(scores.get("authority", 50)) / 100, 2),
        "reliability": round(float(scores.get("evidence_discipline", 50)) / 100, 2),
        "originality": round(float(scores.get("originality", 50)) / 100, 2),
        "clickbait_risk": 0.25,
        "conflict_note": str(source.get("conflict_note") or ""),
        "discovery": {
            "role": source.get("role"),
            "coverage_domains": source.get("coverage_domains", []),
            "coverage_topics": source.get("coverage_topics", []),
            "recommendation_reason": source.get("recommendation_reason", ""),
            "preliminary_scores": scores,
            "score_confidence": source.get("score_confidence", "low"),
            "evidence_urls": source.get("discovery_evidence_urls", []),
            "representative_works": source.get("representative_works", []),
            "warnings": source.get("warnings", []),
        },
    }


def _reporting_config(
    settings: Settings,
    proposal: Mapping[str, Any],
    preset_id: str,
    history_start: str,
) -> Dict[str, Any]:
    presets = {
        str(item.get("id")): item
        for item in proposal.get("report_presets", [])
        if isinstance(item, dict)
    }
    if preset_id not in presets:
        raise ValueError(f"Unknown report preset: {preset_id}")
    selected = presets[preset_id]
    reporting = copy.deepcopy(settings.reporting)
    collection = reporting.setdefault("collection", {})
    collection.update(
        {
            "werss_workers": [],
            "backfill_nodes": ["main"],
            "recent_refresh_nodes": ["main"],
            "initial_backfill_pages": 10,
            "recent_refresh_batch_accounts": 3,
            "historical_backfill_batch_accounts": 1,
        }
    )
    reporting["history_start"] = history_start
    reporting["strategy_preset"] = preset_id
    reporting.setdefault("notion", {})["auto_publish"] = False
    article_multipliers = {"daily": 25, "weekly": 60, "monthly": 120}
    for kind in ("daily", "weekly", "monthly"):
        policy = selected[kind]
        reporting[kind].pop("title_prefix", None)
        reporting[kind]["enabled"] = bool(policy["enabled"])
        reporting[kind]["reading_minutes"] = int(policy["reading_minutes"])
        reporting[kind]["focus"] = list(policy["focus"])
        reporting[kind]["max_items"] = int(policy["max_items"])
        reporting[kind]["max_articles"] = max(
            50,
            int(policy["max_items"]) * article_multipliers[kind],
        )
    return reporting


def _one_calendar_month_ago(value: datetime) -> datetime:
    if value.month == 1:
        year, month = value.year - 1, 12
    else:
        year, month = value.year, value.month - 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def apply_research_proposal(
    settings: Settings,
    proposal: Mapping[str, Any],
    output_dir: Path,
    preset_id: str = "standard",
    history_start: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    proposal = _normalize_proposal(
        copy.deepcopy(dict(proposal)),
        max(1, len(proposal.get("sources", []))),
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    default_start = _one_calendar_month_ago(datetime.now(timezone)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    start = history_start or default_start

    profile = dict(proposal["research_profile"])
    taxonomy = proposal["topic_taxonomy"]
    topics = {
        "version": 1,
        "classification_rules": list(taxonomy.get("classification_rules", [])),
        "topics": list(taxonomy.get("topics", [])),
        "event_keywords": {
            str(item["id"]): list(item.get("keywords", []))
            for item in taxonomy.get("event_types", [])
        },
    }
    entity_seeds = proposal.get("entity_seeds", {})
    entities = {
        "note": "这是根据用户研究领域生成的冷启动种子，不是封闭词表。",
        "companies": {
            str(item["topic_id"]): list(item.get("names", []))
            for item in entity_seeds.get("companies", [])
        },
        "people": list(entity_seeds.get("people", [])),
    }

    accounts: List[Dict[str, Any]] = []
    external_sources: List[Dict[str, Any]] = []
    for source in proposal.get("sources", []):
        common = _source_common(source)
        if source.get("capture_method") == "wechat" and source.get("platform_id"):
            accounts.append(
                {
                    "name": source["name"],
                    "wechat_id": source["platform_id"],
                    **common,
                }
            )
            continue
        feed_url = str(source.get("feed_url") or "")
        capture_method = "rss" if source.get("capture_method") == "rss" and feed_url else "web_pending"
        external_sources.append(
            {
                "id": source["id"],
                "name": source["name"],
                **common,
                "homepage_url": str(source.get("homepage_url") or ""),
                "feed_url": feed_url or None,
                "capture_method": capture_method,
                "content_mode": str(source.get("content_mode") or "summary_or_link"),
            }
        )

    files: Dict[str, Any] = {
        "profile.json": profile,
        "topics.json": topics,
        "entities.bootstrap.json": entities,
        "accounts.json": {
            "history_start": start,
            "priorities": copy.deepcopy(settings.accounts_config.get("priorities", {})),
            "accounts": accounts,
        },
        "external_sources.json": {"sources": external_sources},
        "source_policy.json": copy.deepcopy(settings.source_policy),
        "reporting.json": _reporting_config(settings, proposal, preset_id, start),
        "runtime.json": {
            "data_dir": f"data/profiles/{profile['id']}",
            "logs_dir": f"logs/profiles/{profile['id']}",
        },
    }
    existing = [str(output_dir / name) for name in files if (output_dir / name).exists()]
    if existing and not force:
        raise FileExistsError(
            "Refusing to overwrite existing profile files: " + ", ".join(existing)
        )
    for name, payload in files.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "output_dir": str(output_dir),
        "profile": profile,
        "report_preset": preset_id,
        "wechat_sources": len(accounts),
        "external_sources": len(external_sources),
        "files": [str(output_dir / name) for name in files],
    }


def _batch_profiles(manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_profiles = manifest.get("domains", manifest.get("profiles", []))
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("Batch manifest must contain a non-empty domains or profiles array")
    profiles: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_profiles:
        item = {"field": raw} if isinstance(raw, str) else dict(raw)
        field = str(item.get("field") or "").strip()
        if not field:
            raise ValueError("Every batch profile must define field")
        key = _slug(str(item.get("id") or field), "research-profile")
        if key in seen:
            raise ValueError(f"Duplicate batch profile id: {key}")
        seen.add(key)
        profiles.append({**item, "id": key, "field": field})
    return profiles


def _merged_list(
    item: Mapping[str, Any],
    defaults: Mapping[str, Any],
    key: str,
    fallback: List[str],
) -> List[str]:
    value = item.get(key, defaults.get(key, fallback))
    if isinstance(value, str):
        return [value]
    return _values(list(value or []), fallback)


def propose_research_batch(
    settings: Settings,
    manifest: Mapping[str, Any],
    output_dir: Path,
    resume: bool = True,
    force: bool = False,
    continue_on_error: bool = True,
) -> Dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    defaults = manifest.get("defaults", {}) if isinstance(manifest.get("defaults"), dict) else {}
    results: List[Dict[str, Any]] = []
    for item in _batch_profiles(manifest):
        output_path = output_dir / f"{item['id']}.json"
        if output_path.exists() and resume and not force:
            results.append({"id": item["id"], "field": item["field"], "status": "reused", "output": str(output_path)})
            continue
        try:
            proposal = propose_research_setup(
                settings,
                item["field"],
                audiences=_merged_list(item, defaults, "audiences", ["research"]),
                goals=_merged_list(
                    item,
                    defaults,
                    "goals",
                    ["material_changes", "trend_detection", "source_verification"],
                ),
                languages=_merged_list(item, defaults, "languages", ["zh-CN", "en"]),
                regions=_merged_list(item, defaults, "regions", ["global"]),
                max_sources=int(item.get("max_sources", defaults.get("max_sources", 20))),
            )
            proposal["batch_profile_id"] = item["id"]
            output_path.write_text(
                json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            results.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "status": "proposed",
                    "source_candidates": len(proposal["sources"]),
                    "output": str(output_path),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if not continue_on_error:
                raise
    summary = {
        "batch_version": 1,
        "output_dir": str(output_dir),
        "requested": len(results),
        "proposed": sum(item["status"] == "proposed" for item in results),
        "reused": sum(item["status"] == "reused" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    (output_dir / "batch-results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def apply_research_batch(
    settings: Settings,
    manifest: Mapping[str, Any],
    proposals_dir: Path,
    profiles_dir: Path,
    approved: Optional[Iterable[str]] = None,
    approve_all: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    proposals_dir = proposals_dir.resolve()
    profiles_dir = profiles_dir.resolve()
    profiles_dir.mkdir(parents=True, exist_ok=True)
    approved_ids = {str(value) for value in (approved or [])}
    if not approve_all and not approved_ids:
        raise ValueError("Provide approved profile ids or set approve_all=True")
    defaults = manifest.get("defaults", {}) if isinstance(manifest.get("defaults"), dict) else {}
    profiles = _batch_profiles(manifest)
    known_ids = {item["id"] for item in profiles}
    unknown_ids = sorted(approved_ids - known_ids)
    if unknown_ids:
        raise ValueError("Unknown approved profile ids: " + ", ".join(unknown_ids))
    results: List[Dict[str, Any]] = []
    for item in profiles:
        if not approve_all and item["id"] not in approved_ids:
            results.append({"id": item["id"], "field": item["field"], "status": "not_approved"})
            continue
        proposal_path = proposals_dir / f"{item['id']}.json"
        if not proposal_path.exists():
            results.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "status": "failed",
                    "error": f"Missing proposal: {proposal_path}",
                }
            )
            continue
        try:
            preset_id = item.get("preset", defaults.get("preset"))
            if not preset_id:
                raise ValueError(
                    f"No report preset selected for approved profile {item['id']!r}"
                )
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            proposal_batch_id = proposal.get("batch_profile_id")
            if proposal_batch_id and proposal_batch_id != item["id"]:
                raise ValueError(
                    f"Proposal batch id {proposal_batch_id!r} does not match {item['id']!r}"
                )
            proposal["research_profile"] = dict(proposal["research_profile"])
            proposal["research_profile"]["id"] = item["id"]
            applied = apply_research_proposal(
                settings,
                proposal,
                profiles_dir / item["id"],
                preset_id=str(preset_id),
                history_start=item.get("history_start", defaults.get("history_start")),
                force=force,
            )
            results.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "status": "applied",
                    "profile_name": applied["profile"]["name"],
                    "config_dir": applied["output_dir"],
                    "source_count": applied["wechat_sources"] + applied["external_sources"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    index = {
        "version": 1,
        "profiles": [
            {
                "id": item["id"],
                "name": item.get("profile_name", item["field"]),
                "config_dir": item.get("config_dir", ""),
                "source_count": item.get("source_count", 0),
            }
            for item in results
            if item["status"] == "applied"
        ],
    }
    (profiles_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "profiles_dir": str(profiles_dir),
        "applied": sum(item["status"] == "applied" for item in results),
        "not_approved": sum(item["status"] == "not_approved" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
