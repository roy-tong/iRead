from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .db import Database
from .settings import Settings


def _iso(timestamp: Optional[int]) -> Optional[str]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()


def coverage_audit(settings: Settings, db: Database) -> Dict[str, Any]:
    history_ts = int(settings.history_start.timestamp())
    account_rows = db.rows(
        "SELECT * FROM accounts WHERE capture_method='wechat' ORDER BY weight DESC, expected_name"
    )
    external_rows = db.rows(
        "SELECT * FROM accounts WHERE capture_method!='wechat' ORDER BY weight DESC, expected_name"
    )
    details: List[Dict[str, Any]] = []
    critical: List[str] = []
    warnings: List[str] = []

    for row in account_rows:
        account_id = row["wechat_id"]
        active = row["collection_status"] == "active"
        articles = db.rows(
            "SELECT published_at, LENGTH(COALESCE(content_text, '')) AS body_len FROM articles WHERE source_wechat_id=? ORDER BY published_at",
            (account_id,),
        )
        timestamps = [int(article["published_at"]) for article in articles]
        missing_body = sum(1 for article in articles if int(article["body_len"] or 0) < 80)
        gaps: List[float] = []
        if len(timestamps) >= 3:
            gaps = [(right - left) / 86400 for left, right in zip(timestamps, timestamps[1:])]
        median_gap = statistics.median(gaps) if gaps else None
        max_gap = max(gaps) if gaps else None
        boundary_reached = bool(timestamps and timestamps[0] <= history_ts + 7 * 86400)
        resolved = bool(row["werss_feed_id"])
        item = {
            "wechat_id": account_id,
            "name": row["expected_name"],
            "priority": row["priority"],
            "collection_status": row["collection_status"],
            "inactive_reason": row["inactive_reason"],
            "resolved": resolved,
            "article_count": len(articles),
            "oldest_article_at": _iso(timestamps[0] if timestamps else None),
            "newest_article_at": _iso(timestamps[-1] if timestamps else None),
            "history_boundary_reached": boundary_reached,
            "missing_body_count": missing_body,
            "median_gap_days": round(median_gap, 1) if median_gap is not None else None,
            "max_gap_days": round(max_gap, 1) if max_gap is not None else None,
        }
        details.append(item)

        if not active:
            continue

        label = f"{row['expected_name']}({account_id})"
        if row["priority"] == "required" and not resolved:
            critical.append(f"必抓源尚未匹配: {label}")
        elif not resolved:
            warnings.append(f"来源尚未匹配: {label}")
        if row["priority"] == "required" and not articles:
            critical.append(f"必抓源暂无历史文章: {label}")
        elif not articles:
            warnings.append(f"来源暂无历史文章: {label}")
        if articles and not boundary_reached:
            warnings.append(
                f"尚不能证明已回溯到{settings.history_start.date().isoformat()}: {label}"
            )
        if missing_body:
            message = f"存在{missing_body}篇正文过短或缺失: {label}"
            (critical if row["priority"] == "required" else warnings).append(message)
        if median_gap and max_gap and max_gap > max(14, median_gap * 4):
            warnings.append(f"出现异常长发布间隔({max_gap:.1f}天): {label}")

    pending_row = db.row(
        "SELECT COUNT(*) AS total FROM articles WHERE analysis_status IN ('pending', 'retry')"
    )
    failed_row = db.row("SELECT COUNT(*) AS total FROM articles WHERE analysis_status='failed'")
    duplicate_row = db.row(
        """
        SELECT COUNT(*) AS total FROM (
            SELECT url FROM articles WHERE COALESCE(url, '') != '' GROUP BY url HAVING COUNT(*) > 1
        )
        """
    )
    active_rows = [row for row in account_rows if row["collection_status"] == "active"]
    required_total = sum(1 for row in active_rows if row["priority"] == "required")
    required_resolved = sum(
        1 for row in active_rows if row["priority"] == "required" and row["werss_feed_id"]
    )
    total_row = db.row("SELECT COUNT(*) AS total FROM articles")
    total_articles = int(total_row["total"] if total_row else 0)
    external_details = [
        {
            "id": row["wechat_id"],
            "name": row["expected_name"],
            "priority": row["priority"],
            "source_type": row["source_type"],
            "capture_method": row["capture_method"],
            "active": bool(row["resolved_name"]),
            "article_count": int(row["article_count"] or 0),
            "last_seen_at": _iso(row["last_seen_at"]),
        }
        for row in external_rows
    ]
    for item in external_details:
        if item["active"]:
            continue
        label = f"{item['name']}({item['id']})"
        if item["priority"] == "required":
            warnings.append(f"必抓外部源尚未激活: {label}")
        else:
            warnings.append(f"外部源尚未激活: {label}")
    return {
        "status": "critical" if critical else ("warning" if warnings else "ok"),
        "history_start": settings.history_start.isoformat(),
        "required_sources": {"resolved": required_resolved, "total": required_total},
        "all_sources": {
            "resolved": sum(1 for row in active_rows if row["werss_feed_id"]),
            "total": len(active_rows),
            "archived": len(account_rows) - len(active_rows),
        },
        "external_sources": {
            "active": sum(1 for item in external_details if item["active"]),
            "total": len(external_details),
        },
        "article_count": total_articles,
        "pending_analysis": int(pending_row["total"] if pending_row else 0),
        "failed_analysis": int(failed_row["total"] if failed_row else 0),
        "duplicate_url_groups": int(duplicate_row["total"] if duplicate_row else 0),
        "critical": critical,
        "warnings": warnings,
        "sources": details,
        "external_source_details": external_details,
    }


def audit_markdown(audit: Dict[str, Any]) -> str:
    required = audit["required_sources"]
    all_sources = audit["all_sources"]
    external = audit.get("external_sources", {"active": 0, "total": 0})
    lines = [
        "## 采集完整性",
        "",
        f"- 状态：{audit['status']}",
        f"- 必抓源匹配：{required['resolved']}/{required['total']}",
        f"- 全部来源匹配：{all_sources['resolved']}/{all_sources['total']}",
        f"- 已归档停更来源：{all_sources.get('archived', 0)}",
        f"- 海外/外部源已激活：{external['active']}/{external['total']}",
        f"- 历史文章：{audit['article_count']} 篇",
        f"- 待分析：{audit['pending_analysis']} 篇；分析失败：{audit['failed_analysis']} 篇",
        f"- 重复 URL 组：{audit['duplicate_url_groups']}",
    ]
    if audit["critical"]:
        lines.extend(["", "### 必须处理"])
        lines.extend(f"- {item}" for item in audit["critical"])
    if audit["warnings"]:
        lines.extend(["", "### 尚未证明完整"])
        lines.extend(f"- {item}" for item in audit["warnings"][:50])
    return "\n".join(lines) + "\n"
