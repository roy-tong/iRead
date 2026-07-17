from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .settings import Account


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
    wechat_id TEXT PRIMARY KEY,
    expected_name TEXT NOT NULL,
    priority TEXT NOT NULL,
    weight REAL NOT NULL,
    influence REAL NOT NULL DEFAULT 0.5,
    reliability REAL NOT NULL DEFAULT 0.5,
    originality REAL NOT NULL DEFAULT 0.5,
    clickbait_risk REAL NOT NULL DEFAULT 0.25,
    source_type TEXT NOT NULL DEFAULT 'unknown',
    capture_method TEXT NOT NULL DEFAULT 'wechat',
    content_mode TEXT NOT NULL DEFAULT 'full_text',
    conflict_note TEXT NOT NULL DEFAULT '',
    collection_status TEXT NOT NULL DEFAULT 'active',
    inactive_reason TEXT NOT NULL DEFAULT '',
    profile_status TEXT NOT NULL DEFAULT 'provisional',
    aliases_json TEXT NOT NULL,
    werss_feed_id TEXT,
    resolved_name TEXT,
    last_seen_at INTEGER,
    article_count INTEGER NOT NULL DEFAULT 0,
    oldest_article_at INTEGER,
    newest_article_at INTEGER
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    source_article_id TEXT,
    source_wechat_id TEXT NOT NULL REFERENCES accounts(wechat_id),
    source_name TEXT NOT NULL,
    priority TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    published_at INTEGER NOT NULL,
    description TEXT,
    content_html TEXT,
    content_text TEXT,
    transcript_url TEXT,
    transcript_status TEXT,
    fingerprint TEXT NOT NULL,
    ingested_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    analysis_attempts INTEGER NOT NULL DEFAULT 0,
    analysis_error TEXT,
    analysis_model TEXT,
    analyzed_at INTEGER,
    primary_topic TEXT,
    secondary_topics_json TEXT,
    tertiary_topics_json TEXT,
    relevance INTEGER,
    ai_summary TEXT,
    facts_json TEXT,
    opinions_json TEXT,
    viewpoints_json TEXT,
    inferences_json TEXT,
    companies_json TEXT,
    people_json TEXT,
    event_types_json TEXT,
    financing_json TEXT,
    signals_json TEXT,
    event_signature TEXT,
    source_role TEXT,
    evidence_quality INTEGER,
    credibility INTEGER,
    originality_score INTEGER,
    clickbait_score INTEGER,
    verification_flags_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source_date ON articles(source_wechat_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_analysis ON articles(analysis_status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(primary_topic, published_at DESC);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    status TEXT NOT NULL,
    imported_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    period_start INTEGER NOT NULL,
    period_end INTEGER NOT NULL,
    title TEXT NOT NULL,
    markdown_path TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    notion_page_id TEXT,
    notion_url TEXT,
    notion_status TEXT,
    UNIQUE(kind, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS backfill_state (
    source_wechat_id TEXT PRIMARY KEY REFERENCES accounts(wechat_id),
    next_page INTEGER NOT NULL DEFAULT 0,
    oldest_seen_at INTEGER,
    completed INTEGER NOT NULL DEFAULT 0,
    last_requested_at INTEGER,
    last_error TEXT,
    last_recent_requested_at INTEGER,
    last_recent_error TEXT
);
"""


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def initialize(self, accounts: Sequence[Account]) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)
            for account in accounts:
                conn.execute(
                    """
                    INSERT INTO accounts (
                        wechat_id, expected_name, priority, weight, influence, reliability,
                        originality, clickbait_risk, source_type, profile_status,
                        capture_method, content_mode, conflict_note, collection_status,
                        inactive_reason, aliases_json, werss_feed_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wechat_id) DO UPDATE SET
                        expected_name=excluded.expected_name,
                        priority=excluded.priority,
                        weight=excluded.weight,
                        influence=excluded.influence,
                        reliability=excluded.reliability,
                        originality=excluded.originality,
                        clickbait_risk=excluded.clickbait_risk,
                        source_type=excluded.source_type,
                        capture_method=excluded.capture_method,
                        content_mode=excluded.content_mode,
                        conflict_note=excluded.conflict_note,
                        collection_status=excluded.collection_status,
                        inactive_reason=excluded.inactive_reason,
                        profile_status=excluded.profile_status,
                        aliases_json=excluded.aliases_json,
                        werss_feed_id=COALESCE(excluded.werss_feed_id, accounts.werss_feed_id)
                    """,
                    (
                        account.wechat_id,
                        account.name,
                        account.priority,
                        account.weight,
                        account.influence,
                        account.reliability,
                        account.originality,
                        account.clickbait_risk,
                        account.source_type,
                        account.profile_status,
                        account.capture_method,
                        account.content_mode,
                        account.conflict_note,
                        account.collection_status,
                        account.inactive_reason,
                        json.dumps(account.aliases, ensure_ascii=False),
                        account.feed_id,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO backfill_state (source_wechat_id) SELECT ? WHERE ?='wechat'",
                    (account.wechat_id, account.capture_method),
                )

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        migrations = {
            "accounts": {
                "influence": "REAL NOT NULL DEFAULT 0.5",
                "reliability": "REAL NOT NULL DEFAULT 0.5",
                "originality": "REAL NOT NULL DEFAULT 0.5",
                "clickbait_risk": "REAL NOT NULL DEFAULT 0.25",
                "source_type": "TEXT NOT NULL DEFAULT 'unknown'",
                "capture_method": "TEXT NOT NULL DEFAULT 'wechat'",
                "content_mode": "TEXT NOT NULL DEFAULT 'full_text'",
                "conflict_note": "TEXT NOT NULL DEFAULT ''",
                "collection_status": "TEXT NOT NULL DEFAULT 'active'",
                "inactive_reason": "TEXT NOT NULL DEFAULT ''",
                "profile_status": "TEXT NOT NULL DEFAULT 'provisional'",
            },
            "articles": {
                "event_signature": "TEXT",
                "viewpoints_json": "TEXT",
                "transcript_url": "TEXT",
                "transcript_status": "TEXT",
                "source_role": "TEXT",
                "evidence_quality": "INTEGER",
                "credibility": "INTEGER",
                "originality_score": "INTEGER",
                "clickbait_score": "INTEGER",
                "verification_flags_json": "TEXT",
            },
            "backfill_state": {
                "last_recent_requested_at": "INTEGER",
                "last_recent_error": "TEXT",
            },
        }
        for table, columns in migrations.items():
            existing = {
                str(row["name"])
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, query: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(query, params).fetchall())

    def row(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def start_collection(self, mode: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO collection_runs (mode, started_at, status) VALUES (?, ?, 'running')",
                (mode, now_ts()),
            )
            return int(cursor.lastrowid)

    def finish_collection(
        self,
        run_id: int,
        status: str,
        imported: int,
        changed: int,
        details: Dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collection_runs
                SET ended_at=?, status=?, imported_count=?, changed_count=?, details_json=?
                WHERE id=?
                """,
                (now_ts(), status, imported, changed, json.dumps(details, ensure_ascii=False), run_id),
            )

    def _pending_article_filter(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        require_report_content: bool = False,
        min_content_chars: int = 80,
        min_description_chars: int = 120,
    ) -> Tuple[str, List[Any]]:
        clauses = ["a.analysis_status IN ('pending', 'retry')"]
        params: List[Any] = []
        if start_ts is not None:
            clauses.append("a.published_at > ?")
            params.append(start_ts)
        if end_ts is not None:
            clauses.append("a.published_at <= ?")
            params.append(end_ts)
        if require_report_content:
            clauses.append(
                """(
                    a.transcript_status='complete'
                    OR LENGTH(TRIM(COALESCE(a.content_text, ''))) >= ?
                    OR LENGTH(TRIM(COALESCE(a.description, ''))) >= ?
                )"""
            )
            params.extend([min_content_chars, min_description_chars])
        return " AND ".join(clauses), params

    def pending_articles(
        self,
        limit: int,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        require_report_content: bool = False,
        min_content_chars: int = 80,
        min_description_chars: int = 120,
    ) -> List[sqlite3.Row]:
        where, params = self._pending_article_filter(
            start_ts,
            end_ts,
            require_report_content,
            min_content_chars,
            min_description_chars,
        )
        return self.rows(
            f"""
            WITH source_frequency AS (
                SELECT source_wechat_id, COUNT(*) AS recent_articles_30d
                FROM articles
                WHERE published_at >= ?
                GROUP BY source_wechat_id
            )
            SELECT a.*, ac.weight, ac.influence, ac.reliability, ac.originality,
                   ac.clickbait_risk, ac.source_type, ac.profile_status,
                   ac.content_mode, ac.conflict_note, ac.collection_status,
                   COALESCE(sf.recent_articles_30d, 0) AS recent_articles_30d
            FROM articles a JOIN accounts ac ON ac.wechat_id=a.source_wechat_id
            LEFT JOIN source_frequency sf ON sf.source_wechat_id=a.source_wechat_id
            WHERE {where}
            ORDER BY (a.published_at / 21600) DESC, (
                ac.weight * 100
                + ac.originality * 40
                + CASE WHEN ac.source_type LIKE '%interview%' THEN 30 ELSE 0 END
                + CASE
                    WHEN COALESCE(sf.recent_articles_30d, 0) >= 60 THEN 25
                    WHEN COALESCE(sf.recent_articles_30d, 0) >= 20 THEN 12
                    ELSE 0
                  END
            ) DESC, a.published_at DESC
            LIMIT ?
            """,
            (now_ts() - 30 * 86400, *params, limit),
        )

    def pending_article_count(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        require_report_content: bool = False,
        min_content_chars: int = 80,
        min_description_chars: int = 120,
    ) -> int:
        where, params = self._pending_article_filter(
            start_ts,
            end_ts,
            require_report_content,
            min_content_chars,
            min_description_chars,
        )
        row = self.row(f"SELECT COUNT(*) AS total FROM articles a WHERE {where}", params)
        return int(row["total"] if row else 0)

    def report_row(self, kind: str, start_ts: int, end_ts: int) -> Optional[sqlite3.Row]:
        return self.row(
            "SELECT * FROM reports WHERE kind=? AND period_start=? AND period_end=?",
            (kind, start_ts, end_ts),
        )

    def upsert_report(self, values: Dict[str, Any]) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (
                    kind, period_start, period_end, title, markdown_path, model, created_at,
                    notion_page_id, notion_url, notion_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, period_start, period_end) DO UPDATE SET
                    title=excluded.title,
                    markdown_path=excluded.markdown_path,
                    model=excluded.model,
                    created_at=excluded.created_at,
                    notion_page_id=COALESCE(excluded.notion_page_id, reports.notion_page_id),
                    notion_url=COALESCE(excluded.notion_url, reports.notion_url),
                    notion_status=COALESCE(excluded.notion_status, reports.notion_status)
                """,
                (
                    values["kind"], values["period_start"], values["period_end"],
                    values["title"], values["markdown_path"], values["model"],
                    values.get("created_at", now_ts()), values.get("notion_page_id"),
                    values.get("notion_url"), values.get("notion_status"),
                ),
            )
            row = conn.execute(
                "SELECT id FROM reports WHERE kind=? AND period_start=? AND period_end=?",
                (values["kind"], values["period_start"], values["period_end"]),
            ).fetchone()
            assert row is not None
            return int(row[0])

    def update_report_notion(
        self,
        report_id: int,
        status: str,
        page_id: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE reports SET
                    notion_status=?,
                    notion_page_id=COALESCE(?, notion_page_id),
                    notion_url=COALESCE(?, notion_url)
                WHERE id=?
                """,
                (status, page_id, url, report_id),
            )
