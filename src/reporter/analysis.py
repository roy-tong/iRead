from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .db import Database, now_ts
from .settings import Settings


LOGGER = logging.getLogger(__name__)
SENSITIVE_ENV_KEYS = {
    "NOTION_TOKEN",
    "WERSS_PASSWORD",
    "WERSS_SECRET_KEY",
    "OPENAI_API_KEY",
}


class CodexError(RuntimeError):
    pass


class CodexUsageLimitError(CodexError):
    def __init__(self, retry_at: int):
        self.retry_at = retry_at
        readable = datetime.fromtimestamp(retry_at, tz=timezone.utc).isoformat()
        super().__init__(f"Codex usage limit is active until {readable}")


def _usage_limit_state_path(settings: Settings) -> Path:
    return settings.data_dir / "state" / "codex-usage-limit.json"


def _parse_usage_limit_retry_at(settings: Settings, detail: str) -> int:
    match = re.search(
        r"try again at ([A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th)?, \d{4} \d{1,2}:\d{2} [AP]M)",
        detail,
        flags=re.IGNORECASE,
    )
    if not match:
        return now_ts() + 6 * 3600
    value = re.sub(r"(\d)(?:st|nd|rd|th)", r"\1", match.group(1), flags=re.IGNORECASE)
    parsed = datetime.strptime(value, "%b %d, %Y %I:%M %p")
    zone = ZoneInfo(str(settings.reporting.get("timezone", "Asia/Shanghai")))
    return int(parsed.replace(tzinfo=zone).timestamp())


def _record_usage_limit(settings: Settings, detail: str) -> int:
    retry_at = _parse_usage_limit_retry_at(settings, detail)
    path = _usage_limit_state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "retry_at": retry_at,
                "observed_at": now_ts(),
                "reason": "Codex CLI usage limit",
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return retry_at


def codex_usage_limit_until(settings: Settings) -> Optional[int]:
    path = _usage_limit_state_path(settings)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        retry_at = int(value.get("retry_at", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None
    if retry_at > now_ts():
        return retry_at
    path.unlink(missing_ok=True)
    return None


def _codex_bin(settings: Settings) -> str:
    configured = settings.env("CODEX_BIN")
    if configured and Path(configured).exists():
        return configured
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex"
    if Path(bundled).exists():
        return bundled
    found = shutil.which("codex")
    if not found:
        raise CodexError("Codex CLI was not found. Set CODEX_BIN in .env")
    return found


def run_codex_json(
    settings: Settings,
    prompt: str,
    schema_path: Path,
    purpose: str,
    web_search: bool = False,
) -> Dict[str, Any]:
    blocked_until = codex_usage_limit_until(settings)
    if blocked_until:
        raise CodexUsageLimitError(blocked_until)
    state_dir = settings.data_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    output_path = state_dir / f"codex-{purpose}-{uuid.uuid4().hex}.json"
    model = str(settings.env("CODEX_MODEL", settings.reporting["analysis"]["model"]))
    effort = str(
        settings.env("CODEX_REASONING_EFFORT", settings.reporting["analysis"]["reasoning_effort"])
    )
    timeout = int(settings.reporting["analysis"].get("timeout_seconds", 1800))
    command = [
        _codex_bin(settings),
    ]
    if web_search:
        command.append("--search")
    command.extend([
        "exec",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "--cd",
        str(settings.root),
        "-",
    ])
    child_env = {key: value for key, value in os.environ.items() if key not in SENSITIVE_ENV_KEYS}
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=child_env,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown Codex failure")[-5000:]
            if "usage limit" in detail.lower():
                raise CodexUsageLimitError(_record_usage_limit(settings, detail))
            raise CodexError(f"Codex exited with {completed.returncode}: {detail}")
        if not output_path.exists():
            raise CodexError("Codex completed without writing the structured output file")
        raw = output_path.read_text(encoding="utf-8").strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodexError(f"Codex output was not valid JSON: {exc}: {raw[:1000]}") from exc
        if not isinstance(value, dict):
            raise CodexError("Codex structured output must be a JSON object")
        return value
    finally:
        output_path.unlink(missing_ok=True)


def _content_excerpt(content: str, max_chars: int, distributed: bool = False) -> str:
    if len(content) <= max_chars:
        return content
    if not distributed:
        return content[:max_chars] + "\n[正文因长度已截断]"
    chunk_count = 6
    marker_budget = 300
    chunk_size = max(500, (max_chars - marker_budget) // chunk_count)
    max_start = len(content) - chunk_size
    starts = [round(max_start * index / (chunk_count - 1)) for index in range(chunk_count)]
    chunks = [
        f"[逐字稿分段 {index + 1}/{chunk_count}，起始字符 {start}]\n"
        + content[start:start + chunk_size]
        for index, start in enumerate(starts)
    ]
    return "\n\n".join(chunks)


def _article_payload(
    row: Mapping[str, Any], max_chars: int, max_transcript_chars: int
) -> Dict[str, Any]:
    published = datetime.fromtimestamp(int(row["published_at"]), tz=timezone.utc).isoformat()
    content = str(row["content_text"] or "")
    has_transcript = row["transcript_status"] == "complete"
    content = _content_excerpt(
        content,
        max_transcript_chars if has_transcript else max_chars,
        distributed=has_transcript,
    )
    return {
        "article_id": row["id"],
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
            "recent_articles_30d": int(row["recent_articles_30d"] or 0),
        },
        "published_at": published,
        "title": row["title"],
        "url": row["url"],
        "description": row["description"],
        "transcript_url": row["transcript_url"],
        "transcript_status": row["transcript_status"],
        "content": content,
    }


def enrich_pending(
    settings: Settings,
    db: Database,
    max_batches: Optional[int] = None,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    require_report_content: bool = False,
) -> Dict[str, Any]:
    batch_size = int(settings.reporting["analysis"].get("batch_size", 10))
    max_chars = int(settings.reporting["analysis"].get("max_article_chars", 14000))
    max_transcript_chars = int(
        settings.reporting["analysis"].get("max_transcript_chars", 36000)
    )
    max_summary_chars = int(settings.reporting["analysis"].get("max_summary_chars", 900))
    model = str(settings.env("CODEX_MODEL", settings.reporting["analysis"]["model"]))
    prompt_base = (settings.prompt_dir / "enrich.md").read_text(encoding="utf-8")
    finalization = settings.reporting.get("report_finalization", {})
    min_content_chars = int(finalization.get("min_content_chars", 80))
    min_description_chars = int(finalization.get("min_description_chars", 120))
    parallel_batches = (
        max(1, int(finalization.get("parallel_batches", 3)))
        if require_report_content
        else 1
    )
    total_pending = db.pending_article_count(start_ts, end_ts)
    eligible_pending = db.pending_article_count(
        start_ts,
        end_ts,
        require_report_content,
        min_content_chars,
        min_description_chars,
    )
    blocked_until = codex_usage_limit_until(settings)
    if blocked_until:
        return {
            "eligible": eligible_pending,
            "skipped_low_material": max(0, total_pending - eligible_pending),
            "completed": 0,
            "failed_or_retry": 0,
            "remaining": eligible_pending,
            "batches": 0,
            "blocked_until": datetime.fromtimestamp(
                blocked_until,
                tz=ZoneInfo(str(settings.reporting.get("timezone", "Asia/Shanghai"))),
            ).isoformat(),
        }
    completed_count = 0
    failed_count = 0
    batches = 0

    while max_batches is None or batches < max_batches:
        batch_slots = parallel_batches
        if max_batches is not None:
            batch_slots = min(batch_slots, max_batches - batches)
        rows = db.pending_articles(
            batch_size * batch_slots,
            start_ts,
            end_ts,
            require_report_content,
            min_content_chars,
            min_description_chars,
        )
        if not rows:
            break
        chunks = [rows[index:index + batch_size] for index in range(0, len(rows), batch_size)]
        article_ids = [str(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in article_ids)
        with db.connect() as conn:
            conn.execute(
                f"""
                UPDATE articles SET
                    analysis_status='processing', analysis_attempts=analysis_attempts+1,
                    analysis_error=NULL
                WHERE id IN ({placeholders})
                """,
                article_ids,
            )

        def analyze_chunk(chunk: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
            payload = {
                "research_profile": settings.profile.as_dict(),
                "topic_taxonomy": settings.topics,
                "entity_seeds": settings.entities,
                "articles": [
                    _article_payload(row, max_chars, max_transcript_chars) for row in chunk
                ],
            }
            prompt = prompt_base + "\n\n输入数据：\n" + json.dumps(
                payload,
                ensure_ascii=False,
            )
            return run_codex_json(
                settings,
                prompt,
                settings.schema_dir / "article_enrichment.schema.json",
                purpose="enrich",
            )

        round_failed = False
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [executor.submit(analyze_chunk, chunk) for chunk in chunks]
            for chunk, future in zip(chunks, futures):
                chunk_ids = [str(row["id"]) for row in chunk]
                try:
                    response = future.result()
                    enriched = response.get("articles", [])
                    by_id = {
                        str(item.get("article_id")): item
                        for item in enriched
                        if isinstance(item, dict) and str(item.get("article_id")) in chunk_ids
                    }
                    with db.connect() as conn:
                        for article_id in chunk_ids:
                            item = by_id.get(article_id)
                            if not item:
                                conn.execute(
                                    """
                                    UPDATE articles SET analysis_status='retry', analysis_error=? WHERE id=?
                                    """,
                                    ("Codex response omitted this article", article_id),
                                )
                                failed_count += 1
                                round_failed = True
                                continue
                            conn.execute(
                                """
                                UPDATE articles SET
                                    analysis_status='done', analysis_error=NULL, analysis_model=?, analyzed_at=?,
                                    primary_topic=?, secondary_topics_json=?, tertiary_topics_json=?, relevance=?,
                                    ai_summary=?, facts_json=?, opinions_json=?, viewpoints_json=?,
                                    inferences_json=?, companies_json=?,
                                    people_json=?, event_types_json=?, financing_json=?, signals_json=?,
                                    event_signature=?, source_role=?, evidence_quality=?, credibility=?,
                                    originality_score=?, clickbait_score=?, verification_flags_json=?
                                WHERE id=?
                                """,
                                (
                                    model,
                                    now_ts(),
                                    item["primary_topic"],
                                    json.dumps(item["secondary_topics"], ensure_ascii=False),
                                    json.dumps(item["tertiary_topics"], ensure_ascii=False),
                                    int(item["relevance"]),
                                    str(item["summary"])[:max_summary_chars],
                                    json.dumps(item["facts"], ensure_ascii=False),
                                    json.dumps(item["opinions"], ensure_ascii=False),
                                    json.dumps(item["viewpoints"], ensure_ascii=False),
                                    json.dumps(item["inferences"], ensure_ascii=False),
                                    json.dumps(item["companies"], ensure_ascii=False),
                                    json.dumps(item["people"], ensure_ascii=False),
                                    json.dumps(item["event_types"], ensure_ascii=False),
                                    json.dumps(item["financing"], ensure_ascii=False),
                                    json.dumps(item["signals"], ensure_ascii=False),
                                    str(item["event_signature"])[:500],
                                    str(item["source_role"]),
                                    int(item["evidence_quality"]),
                                    int(item["credibility"]),
                                    int(item["originality"]),
                                    int(item["clickbait_risk"]),
                                    json.dumps(item["verification_flags"], ensure_ascii=False),
                                    article_id,
                                ),
                            )
                            completed_count += 1
                except CodexUsageLimitError as exc:
                    LOGGER.warning("Codex enrichment paused by usage limit: %s", exc)
                    error = str(exc)
                    with db.connect() as conn:
                        for article_id in chunk_ids:
                            conn.execute(
                                """
                                UPDATE articles SET
                                    analysis_status='retry',
                                    analysis_attempts=MAX(0, analysis_attempts-1),
                                    analysis_error=?
                                WHERE id=?
                                """,
                                (error, article_id),
                            )
                            failed_count += 1
                    round_failed = True
                    blocked_until = max(blocked_until or 0, exc.retry_at)
                except Exception as exc:
                    LOGGER.exception("Codex enrichment batch failed")
                    error = f"{type(exc).__name__}: {exc}"[-4000:]
                    with db.connect() as conn:
                        for article_id in chunk_ids:
                            row = conn.execute(
                                "SELECT analysis_attempts FROM articles WHERE id=?", (article_id,)
                            ).fetchone()
                            status = "failed" if row and int(row[0]) >= 3 else "retry"
                            conn.execute(
                                "UPDATE articles SET analysis_status=?, analysis_error=? WHERE id=?",
                                (status, error, article_id),
                            )
                            failed_count += 1
                    round_failed = True
        batches += len(chunks)
        if round_failed and max_batches is None:
            break

    remaining = db.pending_article_count(
        start_ts,
        end_ts,
        require_report_content,
        min_content_chars,
        min_description_chars,
    )
    result: Dict[str, Any] = {
        "eligible": eligible_pending,
        "skipped_low_material": max(0, total_pending - eligible_pending),
        "completed": completed_count,
        "failed_or_retry": failed_count,
        "remaining": remaining,
        "batches": batches,
    }
    if blocked_until:
        result["blocked_until"] = datetime.fromtimestamp(
            blocked_until,
            tz=ZoneInfo(str(settings.reporting.get("timezone", "Asia/Shanghai"))),
        ).isoformat()
    return result
