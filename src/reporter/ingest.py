from __future__ import annotations

import email.utils
import html
import hashlib
import json
import logging
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .db import Database, now_ts
from .settings import Account, Settings, WeRSSNode, normalize_name
from .text import content_fingerprint, html_to_text, normalize_url


LOGGER = logging.getLogger(__name__)
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.casefold() != "a":
            return
        href = next((value for key, value in attrs if key.casefold() == "href"), None)
        if href:
            self.links.append(href)


def _transcript_url(value: str) -> str:
    decoded = html.unescape(value or "")
    parser = _LinkExtractor()
    parser.feed(decoded)
    candidates = parser.links + re.findall(r"https?://[^\s<>\"']+", decoded)
    for candidate in candidates:
        cleaned = candidate.rstrip(".,);]")
        parsed = urllib.parse.urlparse(cleaned)
        if parsed.scheme in {"http", "https"} and "transcript" in cleaned.casefold():
            return cleaned
    return ""


def _fetch_transcript(url: str, timeout: int, require_marker: bool) -> Tuple[str, str]:
    transcript_html = _http(url, timeout=timeout).decode("utf-8", errors="replace")
    transcript_text = html_to_text(transcript_html)
    marker = re.search(r"(?im)^\s*(?:full\s+)?transcript\s*$", transcript_text)
    if require_marker and marker is None and not re.search(
        r"id=[\"']transcript[\"']", transcript_html, flags=re.IGNORECASE
    ):
        return "", ""
    if marker is not None:
        transcript_text = transcript_text[marker.end():].strip()
    if len(transcript_text) < 1000:
        return "", ""
    return transcript_html, transcript_text


@dataclass
class IngestResult:
    mode: str
    imported: int = 0
    changed: int = 0
    skipped_before_start: int = 0
    matched_sources: List[str] = field(default_factory=list)
    unmatched_upstream_sources: List[str] = field(default_factory=list)
    missing_expected_sources: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    attempted_sources: int = 0
    elapsed_seconds: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "imported": self.imported,
            "changed": self.changed,
            "skipped_before_start": self.skipped_before_start,
            "matched_sources": self.matched_sources,
            "unmatched_upstream_sources": self.unmatched_upstream_sources,
            "missing_expected_sources": self.missing_expected_sources,
            "errors": self.errors,
            "attempted_sources": self.attempted_sources,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def _account_for_feed(
    feed_id: str,
    feed_name: str,
    accounts: Sequence[Account],
) -> Optional[Account]:
    for account in accounts:
        if account.feed_id and account.feed_id == feed_id:
            return account
    exact = [account for account in accounts if account.matches(feed_name)]
    if len(exact) == 1:
        return exact[0]

    candidate = normalize_name(feed_name)
    fuzzy: List[Account] = []
    if len(candidate) >= 4:
        for account in accounts:
            for name in account.match_names:
                expected = normalize_name(name)
                if len(expected) >= 4 and (candidate in expected or expected in candidate):
                    fuzzy.append(account)
                    break
    return fuzzy[0] if len(fuzzy) == 1 else None


def _article_key(account: Account, source_article_id: str, url: str, title: str) -> str:
    stable = source_article_id or normalize_url(url) or title
    digest = hashlib.sha256(stable.encode("utf-8", errors="replace")).hexdigest()[:32]
    return f"{account.wechat_id}:{digest}"


def _upsert_article(conn: sqlite3.Connection, values: Mapping[str, Any]) -> Tuple[bool, bool]:
    existing = conn.execute(
        "SELECT fingerprint, content_text FROM articles WHERE id=?", (values["id"],)
    ).fetchone()
    is_new = existing is None
    is_changed = bool(existing and existing["fingerprint"] != values["fingerprint"])
    reset_analysis = is_new or is_changed
    conn.execute(
        """
        INSERT INTO articles (
            id, source_article_id, source_wechat_id, source_name, priority, title, url,
            published_at, description, content_html, content_text, fingerprint,
            transcript_url, transcript_status, ingested_at, updated_at, analysis_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ON CONFLICT(id) DO UPDATE SET
            source_name=excluded.source_name,
            priority=excluded.priority,
            title=excluded.title,
            url=COALESCE(NULLIF(excluded.url, ''), articles.url),
            published_at=excluded.published_at,
            description=COALESCE(NULLIF(excluded.description, ''), articles.description),
            content_html=COALESCE(NULLIF(excluded.content_html, ''), articles.content_html),
            content_text=COALESCE(NULLIF(excluded.content_text, ''), articles.content_text),
            transcript_url=COALESCE(NULLIF(excluded.transcript_url, ''), articles.transcript_url),
            transcript_status=COALESCE(NULLIF(excluded.transcript_status, ''), articles.transcript_status),
            fingerprint=CASE
                WHEN excluded.content_text != '' THEN excluded.fingerprint
                ELSE articles.fingerprint
            END,
            updated_at=excluded.updated_at,
            analysis_status=CASE
                WHEN articles.fingerprint != excluded.fingerprint AND excluded.content_text != ''
                THEN 'pending'
                ELSE articles.analysis_status
            END
        """,
        (
            values["id"], values.get("source_article_id"), values["source_wechat_id"],
            values["source_name"], values["priority"], values["title"], values.get("url", ""),
            values["published_at"], values.get("description", ""), values.get("content_html", ""),
            values.get("content_text", ""), values["fingerprint"], values.get("transcript_url", ""),
            values.get("transcript_status", ""), values["ingested_at"], values["updated_at"],
        ),
    )
    return is_new, is_changed or reset_analysis


def _refresh_account_stats(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE accounts SET
            article_count=(SELECT COUNT(*) FROM articles a WHERE a.source_wechat_id=accounts.wechat_id),
            oldest_article_at=(SELECT MIN(published_at) FROM articles a WHERE a.source_wechat_id=accounts.wechat_id),
            newest_article_at=(SELECT MAX(published_at) FROM articles a WHERE a.source_wechat_id=accounts.wechat_id)
        """
    )


def _ingest_from_werss_db(
    settings: Settings,
    db: Database,
    source_path: Path,
    node_name: str,
) -> IngestResult:
    result = IngestResult(mode=f"werss_db:{node_name}")
    if not source_path.exists():
        raise FileNotFoundError(f"We-MP-RSS database does not exist: {source_path}")

    uri = f"file:{urllib.parse.quote(str(source_path))}?mode=ro"
    source = sqlite3.connect(uri, uri=True, timeout=30)
    source.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if not {"feeds", "articles"}.issubset(tables):
            raise RuntimeError("We-MP-RSS database is missing feeds/articles tables")

        feeds = list(
            source.execute(
                "SELECT id, mp_name, faker_id, status FROM feeds WHERE id != 'MP_WXS_FEATURED_ARTICLES'"
            ).fetchall()
        )
        mapping: Dict[str, Account] = {}
        for feed in feeds:
            account = _account_for_feed(str(feed["id"]), str(feed["mp_name"] or ""), settings.accounts)
            if account:
                mapping[str(feed["id"])] = account
                result.matched_sources.append(account.wechat_id)
            else:
                result.unmatched_upstream_sources.append(str(feed["mp_name"] or feed["id"]))

        result.missing_expected_sources = sorted(
            account.wechat_id for account in settings.accounts if account.wechat_id not in result.matched_sources
        )
        start_ts = int(settings.history_start.timestamp())
        rows = source.execute(
            """
            SELECT
                f.id AS feed_id, f.mp_name, a.id AS article_id, a.title, a.url,
                a.publish_time, a.description, a.content, a.content_html
            FROM articles a
            JOIN feeds f ON f.id=a.mp_id
            WHERE a.publish_time >= ? AND COALESCE(a.status, 1) != 1000
            ORDER BY a.publish_time ASC
            """,
            (start_ts,),
        )
        with db.transaction() as target:
            timestamp = now_ts()
            for row in rows:
                account = mapping.get(str(row["feed_id"]))
                if not account:
                    continue
                content_html = str(row["content_html"] or row["content"] or "")
                content_text = html_to_text(content_html)
                title = str(row["title"] or "").strip() or "（无标题）"
                url = normalize_url(str(row["url"] or ""))
                source_id = str(row["article_id"] or "")
                values = {
                    "id": _article_key(account, source_id, url, title),
                    "source_article_id": source_id,
                    "source_wechat_id": account.wechat_id,
                    "source_name": str(row["mp_name"] or account.name),
                    "priority": account.priority,
                    "title": title,
                    "url": url,
                    "published_at": int(row["publish_time"]),
                    "description": str(row["description"] or ""),
                    "content_html": content_html,
                    "content_text": content_text,
                    "fingerprint": content_fingerprint(title, content_text, url),
                    "ingested_at": timestamp,
                    "updated_at": timestamp,
                }
                is_new, changed = _upsert_article(target, values)
                result.imported += int(is_new)
                result.changed += int(changed and not is_new)

            for feed_id, account in mapping.items():
                resolved = next(str(feed["mp_name"]) for feed in feeds if str(feed["id"]) == feed_id)
                target.execute(
                    """
                    UPDATE accounts SET werss_feed_id=?, resolved_name=?, last_seen_at=?
                    WHERE wechat_id=?
                    """,
                    (feed_id, resolved, timestamp, account.wechat_id),
                )
            _refresh_account_stats(target)
    finally:
        source.close()
    return result


def ingest_from_werss_db(settings: Settings, db: Database) -> IngestResult:
    return _ingest_from_werss_db(settings, db, settings.werss_db_path, "main")


def ingest_from_werss_nodes(settings: Settings, db: Database) -> IngestResult:
    result = IngestResult(mode="werss_db_nodes")
    matched: set[str] = set()
    unmatched: set[str] = set()
    available_nodes = 0
    for node in settings.werss_nodes:
        if not node.db_path.exists():
            result.errors.append(f"{node.name}: database not found: {node.db_path}")
            continue
        available_nodes += 1
        try:
            current = _ingest_from_werss_db(settings, db, node.db_path, node.name)
        except Exception as exc:
            result.errors.append(f"{node.name}: {type(exc).__name__}: {exc}")
            continue
        result.imported += current.imported
        result.changed += current.changed
        result.skipped_before_start += current.skipped_before_start
        matched.update(current.matched_sources)
        unmatched.update(current.unmatched_upstream_sources)
        result.errors.extend(current.errors)
    if available_nodes == 0:
        raise FileNotFoundError("No We-MP-RSS node databases are available")
    result.mode = f"werss_db_nodes:{available_nodes}"
    result.matched_sources = sorted(matched)
    result.unmatched_upstream_sources = sorted(unmatched)
    result.missing_expected_sources = sorted(
        account.wechat_id for account in settings.accounts if account.wechat_id not in matched
    )
    return result


def _http(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 45,
) -> bytes:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _xml_text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed_index(payload: bytes) -> List[Tuple[str, str]]:
    root = ET.fromstring(payload)
    return [(_xml_text(item, "id"), _xml_text(item, "title")) for item in root.findall("./channel/item")]


def _parse_articles(payload: bytes) -> List[Dict[str, Any]]:
    root = ET.fromstring(payload)
    result: List[Dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        date_value = _xml_text(item, "pubDate")
        parsed = email.utils.parsedate_to_datetime(date_value) if date_value else None
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        content = _xml_text(item, CONTENT_NS)
        result.append(
            {
                "id": _xml_text(item, "id") or _xml_text(item, "guid"),
                "title": _xml_text(item, "title"),
                "url": _xml_text(item, "link") or _xml_text(item, "guid"),
                "description": _xml_text(item, "description"),
                "content": content,
                "published_at": int(parsed.timestamp()),
            }
        )
    return result


def _local_tag(node: ET.Element) -> str:
    return str(node.tag).rsplit("}", 1)[-1].casefold()


def _entry_text(node: ET.Element, *names: str) -> str:
    expected = {name.casefold() for name in names}
    for child in list(node):
        if _local_tag(child) in expected:
            return "".join(child.itertext()).strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    fallback = ""
    for child in list(node):
        if _local_tag(child) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        rel = str(child.attrib.get("rel") or "alternate").casefold()
        if href and rel == "alternate":
            return href
        fallback = href or (child.text or "").strip() or fallback
    return fallback


def _entry_attribute(node: ET.Element, name: str, attribute: str) -> str:
    expected = name.casefold()
    for child in list(node):
        if _local_tag(child) == expected:
            return str(child.attrib.get(attribute) or "").strip()
    return ""


def _feed_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _parse_external_feed(payload: bytes) -> List[Dict[str, Any]]:
    root = ET.fromstring(payload)
    entries = [node for node in root.iter() if _local_tag(node) in {"item", "entry"}]
    result: List[Dict[str, Any]] = []
    for entry in entries:
        date_value = _entry_text(entry, "pubDate", "published", "updated", "date")
        published = _feed_datetime(date_value)
        if published is None:
            continue
        url = _entry_link(entry) or _entry_text(entry, "link", "guid", "id")
        result.append(
            {
                "id": _entry_text(entry, "guid", "id") or url,
                "title": _entry_text(entry, "title"),
                "url": url,
                "description": _entry_text(entry, "description", "summary"),
                "content": _entry_text(entry, "encoded", "content"),
                "transcript_url": _entry_attribute(entry, "transcript", "url"),
                "published_at": int(published.timestamp()),
            }
        )
    return result


def ingest_external_feeds(settings: Settings, db: Database) -> IngestResult:
    result = IngestResult(mode="external_rss")
    started_at = time.monotonic()
    start_ts = int(settings.history_start.timestamp())
    timeout = int(settings.reporting["collection"].get("external_request_timeout_seconds", 20))
    timestamp = now_ts()
    accounts = [
        account
        for account in settings.external_sources
        if account.capture_method == "rss" and account.feed_url
    ]
    result.attempted_sources = len(accounts)
    worker_count = min(
        len(accounts) or 1,
        max(
            1,
            int(
                settings.reporting["collection"].get(
                    "external_fetch_workers", 6
                )
            ),
        ),
    )
    retries = max(
        0,
        int(settings.reporting["collection"].get("external_fetch_retries", 1)),
    )

    def fetch(account: Account) -> Tuple[Account, Optional[List[Dict[str, Any]]], Optional[Exception]]:
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                articles = _parse_external_feed(_http(account.feed_url, timeout=timeout))
                if not articles:
                    raise RuntimeError("feed contained no dated RSS/Atom entries")
                return account, articles, None
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.25 * (attempt + 1))
        return account, None, last_error

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        fetched = list(executor.map(fetch, accounts))

    for account, articles, fetch_error in fetched:
        if fetch_error is not None or articles is None:
            exc = fetch_error or RuntimeError("feed fetch returned no result")
            result.errors.append(f"{account.name}: {type(exc).__name__}: {exc}")
            continue
        try:
            with db.transaction() as conn:
                for article in articles:
                    if article["published_at"] < start_ts:
                        result.skipped_before_start += 1
                        continue
                    content_html = article["content"] or article["description"]
                    content_text = html_to_text(content_html)
                    title = article["title"] or "（无标题）"
                    raw_url = (
                        article["url"]
                        if str(article["url"]).startswith(("http://", "https://"))
                        else ""
                    )
                    article_url = normalize_url(raw_url or account.homepage_url or "")
                    article_id = _article_key(account, article["id"], article_url, title)
                    transcript_url = ""
                    transcript_status = ""
                    if "episode_notes" in account.content_mode:
                        transcript_status = "unavailable"
                    if (
                        "transcript_link" in account.content_mode
                        or "page_transcript" in account.content_mode
                    ):
                        existing = conn.execute(
                            """
                            SELECT content_html, content_text, transcript_url, transcript_status
                            FROM articles WHERE id=?
                            """,
                            (article_id,),
                        ).fetchone()
                        if existing and existing["transcript_status"] == "complete":
                            content_html = str(existing["content_html"] or content_html)
                            content_text = str(existing["content_text"] or content_text)
                            transcript_url = str(existing["transcript_url"] or "")
                            transcript_status = "complete"
                        else:
                            direct_url = article.get("transcript_url") or _transcript_url(content_html)
                            page_url = (
                                article_url
                                if "page_transcript" in account.content_mode and raw_url
                                else ""
                            )
                            candidate_url = direct_url or page_url
                            if candidate_url:
                                transcript_status = "failed"
                                try:
                                    transcript_html, transcript_text = _fetch_transcript(
                                        candidate_url,
                                        timeout,
                                        require_marker=not bool(direct_url),
                                    )
                                    if transcript_text:
                                        notes_text = html_to_text(content_html)
                                        content_html = content_html + "\n<hr>\n" + transcript_html
                                        content_text = (
                                            "[节目简介]\n"
                                            + notes_text
                                            + "\n\n[官方逐字稿]\n"
                                            + transcript_text
                                        )
                                        transcript_url = candidate_url
                                        transcript_status = "complete"
                                    else:
                                        transcript_status = "unavailable"
                                except Exception as exc:
                                    LOGGER.warning("Could not fetch transcript for %s: %s", title, exc)
                    values = {
                        "id": article_id,
                        "source_article_id": article["id"],
                        "source_wechat_id": account.wechat_id,
                        "source_name": account.name,
                        "priority": account.priority,
                        "title": title,
                        "url": article_url,
                        "published_at": article["published_at"],
                        "description": article["description"],
                        "content_html": content_html,
                        "content_text": content_text,
                        "transcript_url": transcript_url,
                        "transcript_status": transcript_status,
                        "fingerprint": content_fingerprint(title, content_text, article_url),
                        "ingested_at": timestamp,
                        "updated_at": timestamp,
                    }
                    is_new, changed = _upsert_article(conn, values)
                    result.imported += int(is_new)
                    result.changed += int(changed and not is_new)
                conn.execute(
                    """
                    UPDATE accounts SET resolved_name=?, last_seen_at=? WHERE wechat_id=?
                    """,
                    (account.name, timestamp, account.wechat_id),
                )
                _refresh_account_stats(conn)
            result.matched_sources.append(account.wechat_id)
        except Exception as exc:
            result.errors.append(f"{account.name}: {type(exc).__name__}: {exc}")
    result.elapsed_seconds = time.monotonic() - started_at
    return result


def ingest_from_rss(settings: Settings, db: Database) -> IngestResult:
    result = IngestResult(mode="rss")
    base = settings.werss_base_url
    timeout = int(settings.reporting["collection"].get("request_timeout_seconds", 45))
    page_size = int(settings.reporting["collection"].get("rss_page_size", 100))

    feeds: List[Tuple[str, str]] = []
    offset = 0
    while True:
        url = f"{base}/rss?limit=30&offset={offset}"
        page = _parse_feed_index(_http(url, timeout=timeout))
        if not page:
            break
        feeds.extend(page)
        if len(page) < 30:
            break
        offset += 30

    mapping: Dict[str, Account] = {}
    for feed_id, feed_name in feeds:
        account = _account_for_feed(feed_id, feed_name, settings.accounts)
        if account:
            mapping[feed_id] = account
            result.matched_sources.append(account.wechat_id)
        else:
            result.unmatched_upstream_sources.append(feed_name or feed_id)
    result.missing_expected_sources = sorted(
        account.wechat_id for account in settings.accounts if account.wechat_id not in result.matched_sources
    )

    start_ts = int(settings.history_start.timestamp())
    with db.transaction() as conn:
        timestamp = now_ts()
        for feed_id, account in mapping.items():
            feed_name = next(name for current_id, name in feeds if current_id == feed_id)
            offset = 0
            while True:
                url = f"{base}/rss/{urllib.parse.quote(feed_id)}?limit={page_size}&offset={offset}"
                articles = _parse_articles(_http(url, timeout=timeout))
                if not articles:
                    break
                reached_start = False
                for article in articles:
                    if article["published_at"] < start_ts:
                        result.skipped_before_start += 1
                        reached_start = True
                        continue
                    content_html = article["content"] or article["description"]
                    content_text = html_to_text(content_html)
                    title = article["title"] or "（无标题）"
                    article_url = normalize_url(article["url"])
                    values = {
                        "id": _article_key(account, article["id"], article_url, title),
                        "source_article_id": article["id"],
                        "source_wechat_id": account.wechat_id,
                        "source_name": feed_name or account.name,
                        "priority": account.priority,
                        "title": title,
                        "url": article_url,
                        "published_at": article["published_at"],
                        "description": article["description"],
                        "content_html": content_html,
                        "content_text": content_text,
                        "fingerprint": content_fingerprint(title, content_text, article_url),
                        "ingested_at": timestamp,
                        "updated_at": timestamp,
                    }
                    is_new, changed = _upsert_article(conn, values)
                    result.imported += int(is_new)
                    result.changed += int(changed and not is_new)
                if reached_start or len(articles) < page_size:
                    break
                offset += page_size

            conn.execute(
                """
                UPDATE accounts SET werss_feed_id=?, resolved_name=?, last_seen_at=?
                WHERE wechat_id=?
                """,
                (feed_id, feed_name, timestamp, account.wechat_id),
            )
        _refresh_account_stats(conn)
    return result


def ingest(
    settings: Settings,
    db: Database,
    mode: str = "auto",
    include_external: bool = True,
) -> IngestResult:
    wechat_enabled = bool(
        settings.reporting.get("collection", {}).get("wechat_enabled", True)
    )
    if not wechat_enabled:
        run_id = db.start_collection("external_rss")
        try:
            result = (
                ingest_external_feeds(settings, db)
                if include_external
                else IngestResult(mode="disabled")
            )
            status = "ok" if not result.errors else "partial"
            db.finish_collection(
                run_id,
                status,
                result.imported,
                result.changed,
                result.as_dict(),
            )
            return result
        except Exception as exc:
            db.finish_collection(
                run_id,
                "failed",
                0,
                0,
                {"error": f"{type(exc).__name__}: {exc}"},
            )
            raise
    selected = "werss_db" if mode == "auto" and settings.werss_db_path.exists() else mode
    if selected == "auto":
        selected = "rss"
    run_id = db.start_collection(selected)
    try:
        result = ingest_from_werss_nodes(settings, db) if selected == "werss_db" else ingest_from_rss(settings, db)
        if include_external:
            external = ingest_external_feeds(settings, db)
            result.mode = f"{result.mode}+external_rss"
            result.imported += external.imported
            result.changed += external.changed
            result.skipped_before_start += external.skipped_before_start
            result.matched_sources.extend(external.matched_sources)
            result.errors.extend(external.errors)
            result.attempted_sources += external.attempted_sources
            result.elapsed_seconds += external.elapsed_seconds
        status = "ok" if not result.errors else "partial"
        db.finish_collection(run_id, status, result.imported, result.changed, result.as_dict())
        return result
    except Exception as exc:
        details = {"error": f"{type(exc).__name__}: {exc}"}
        db.finish_collection(run_id, "failed", 0, 0, details)
        raise


def _json_api(
    settings: Settings,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    form: bool = False,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    data: Optional[bytes] = None
    if payload is not None:
        if form:
            data = urllib.parse.urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = _http(
        f"{(base_url or settings.werss_base_url).rstrip('/')}{path}",
        method=method,
        data=data,
        headers=headers,
        timeout=int(settings.reporting["collection"].get("request_timeout_seconds", 45)),
    )
    response = json.loads(raw.decode("utf-8"))
    if isinstance(response, dict):
        code = response.get("code")
        if code is not None and code != 0:
            raise RuntimeError(f"We-MP-RSS API error {code}: {response.get('message', response)}")
        if "detail" in response and "data" not in response:
            raise RuntimeError(f"We-MP-RSS API error: {response['detail']}")
    return response


def werss_admin_token(settings: Settings, base_url: Optional[str] = None) -> str:
    username = settings.env("WERSS_USERNAME")
    password = settings.env("WERSS_PASSWORD")
    if not username or not password:
        raise RuntimeError("WERSS_USERNAME and WERSS_PASSWORD are required in .env")
    response = _json_api(
        settings,
        "/api/v1/wx/auth/token",
        method="POST",
        payload={"username": username, "password": password},
        form=True,
        base_url=base_url,
    )
    body = response.get("data", response)
    token = body.get("access_token") if isinstance(body, dict) else None
    if not token:
        raise RuntimeError(f"We-MP-RSS admin login failed: {response.get('message', response)}")
    return str(token)


def _unwrap(response: Dict[str, Any]) -> Any:
    return response.get("data", response)


def werss_wechat_auth_status(settings: Settings) -> Dict[str, Any]:
    token = werss_admin_token(settings)
    response = _json_api(
        settings,
        "/api/v1/wx/auth/qr/status",
        token=token,
    )
    body = _unwrap(response)
    authorized = bool(isinstance(body, dict) and body.get("login_status"))
    qr_pending = bool(isinstance(body, dict) and body.get("qr_code"))
    return {
        "status": "authorized" if authorized else ("awaiting_scan" if qr_pending else "needs_auth"),
        "authorized": authorized,
        "qr_pending": qr_pending,
    }


def start_werss_wechat_auth(
    settings: Settings,
    qr_output: Optional[Path] = None,
    image_timeout_seconds: int = 30,
) -> Dict[str, Any]:
    current = werss_wechat_auth_status(settings)
    if current["authorized"]:
        return current

    token = werss_admin_token(settings)
    response = _json_api(
        settings,
        "/api/v1/wx/auth/qr/code",
        token=token,
    )
    body = _unwrap(response)
    code_path = str(body.get("code") or "") if isinstance(body, dict) else ""
    if not code_path:
        raise RuntimeError("We-MP-RSS did not return a WeChat authorization QR code")
    qr_url = urllib.parse.urljoin(settings.werss_base_url + "/", code_path.lstrip("/"))
    output = (qr_output or settings.data_dir / "state" / "wechat-auth-qr.png").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + max(1, image_timeout_seconds)
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            image = _http(qr_url, timeout=5)
            if image.startswith(b"\x89PNG") or image.startswith(b"\xff\xd8"):
                output.write_bytes(image)
                return {
                    "status": "awaiting_scan",
                    "authorized": False,
                    "qr_pending": True,
                    "qr_image": str(output),
                    "qr_url": qr_url,
                    "expires_in_seconds": 300,
                }
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    detail = f": {type(last_error).__name__}" if last_error else ""
    raise TimeoutError(f"WeChat authorization QR image was not ready{detail}")


def wait_for_werss_wechat_auth(
    settings: Settings,
    timeout_seconds: int = 300,
    poll_seconds: float = 2.0,
) -> Dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        status = werss_wechat_auth_status(settings)
        if status["authorized"]:
            return status
        time.sleep(max(0.2, poll_seconds))
    return {
        "status": "auth_timeout",
        "authorized": False,
        "qr_pending": False,
        "retryable": True,
    }


def _candidate_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("list", "search_list", "items"):
        if isinstance(value.get(key), list):
            return [item for item in value[key] if isinstance(item, dict)]
    for key in ("publish_page", "data"):
        nested = _candidate_list(value.get(key))
        if nested:
            return nested
    return []


def _candidate_score(account: Account, candidate: Mapping[str, Any]) -> int:
    for key in ("alias", "username", "wechat_id", "account"):
        candidate_id = normalize_name(str(candidate.get(key) or ""))
        if candidate_id and candidate_id == normalize_name(account.wechat_id):
            return 120
    candidate_name = str(candidate.get("nickname") or candidate.get("mp_name") or candidate.get("name") or "")
    normalized = normalize_name(candidate_name)
    scores: List[int] = []
    for name in account.match_names:
        expected = normalize_name(name)
        if normalized == expected:
            scores.append(100)
        elif expected and (expected in normalized or normalized in expected):
            scores.append(70)
    return max(scores or [0])


def subscribe_accounts(settings: Settings, dry_run: bool = False) -> Dict[str, Any]:
    token = werss_admin_token(settings)
    existing_response = _json_api(settings, "/api/v1/wx/mps?limit=100&offset=0", token=token)
    existing = _candidate_list(_unwrap(existing_response))
    existing_names = {
        normalize_name(str(item.get("mp_name") or item.get("nickname") or item.get("name") or ""))
        for item in existing
    }
    delay = int(settings.reporting["collection"].get("subscription_delay_seconds", 8))
    outcome: Dict[str, Any] = {
        "added": [],
        "existing": [],
        "inactive": [],
        "unresolved": [],
        "errors": [],
    }

    for account in settings.accounts:
        if account.collection_status != "active":
            outcome["inactive"].append(account.wechat_id)
            continue
        if any(normalize_name(name) in existing_names for name in account.match_names):
            outcome["existing"].append(account.wechat_id)
            continue
        try:
            query = urllib.parse.quote(account.name)
            response = _json_api(
                settings,
                f"/api/v1/wx/mps/search/{query}?limit=10&offset=0",
                token=token,
            )
            candidates = _candidate_list(_unwrap(response))
            ranked = sorted(
                ((_candidate_score(account, candidate), candidate) for candidate in candidates),
                key=lambda pair: pair[0],
                reverse=True,
            )
            if not ranked or ranked[0][0] < 70:
                outcome["unresolved"].append(
                    {
                        "wechat_id": account.wechat_id,
                        "name": account.name,
                        "candidates": [
                            str(item.get("nickname") or item.get("mp_name") or "") for item in candidates[:5]
                        ],
                    }
                )
                continue
            score, candidate = ranked[0]
            fakeid = candidate.get("fakeid") or candidate.get("mp_id")
            if not fakeid:
                outcome["unresolved"].append(
                    {"wechat_id": account.wechat_id, "name": account.name, "reason": "candidate has no fakeid"}
                )
                continue
            selected = {
                "wechat_id": account.wechat_id,
                "requested_name": account.name,
                "matched_name": candidate.get("nickname") or candidate.get("mp_name"),
                "score": score,
            }
            if not dry_run:
                _json_api(
                    settings,
                    "/api/v1/wx/mps",
                    method="POST",
                    token=token,
                    payload={
                        "mp_name": candidate.get("nickname") or account.name,
                        "mp_id": fakeid,
                        "avatar": candidate.get("round_head_img") or candidate.get("avatar") or "",
                        "mp_intro": candidate.get("signature") or candidate.get("mp_intro") or "",
                    },
                )
            outcome["added"].append(selected)
        except Exception as exc:
            outcome["errors"].append(
                {"wechat_id": account.wechat_id, "error": f"{type(exc).__name__}: {exc}"}
            )
        time.sleep(delay)
    return outcome


def sync_werss_worker_feeds(settings: Settings) -> Dict[str, Any]:
    nodes = settings.werss_nodes
    if len(nodes) < 2:
        return {"status": "idle", "source_feeds": 0, "nodes": []}
    primary = nodes[0]
    if not primary.db_path.exists():
        raise FileNotFoundError(f"Primary WeRSS database does not exist: {primary.db_path}")

    uri = f"file:{urllib.parse.quote(str(primary.db_path))}?mode=ro"
    source = sqlite3.connect(uri, uri=True, timeout=30)
    source.row_factory = sqlite3.Row
    try:
        feeds = list(
            source.execute(
                """
                SELECT id, mp_name, mp_cover, mp_intro, faker_id
                FROM feeds
                WHERE id != 'MP_WXS_FEATURED_ARTICLES' AND COALESCE(status, 1) != 0
                ORDER BY mp_name
                """
            ).fetchall()
        )
    finally:
        source.close()

    delay = float(
        settings.reporting["collection"].get("worker_feed_sync_delay_seconds", 0.15)
    )
    node_results: List[Dict[str, Any]] = []
    for node in nodes[1:]:
        added: List[str] = []
        errors: List[Dict[str, str]] = []
        existing: set[str] = set()
        if node.db_path.exists():
            worker = sqlite3.connect(str(node.db_path), timeout=30)
            try:
                existing = {
                    str(row[0])
                    for row in worker.execute(
                        "SELECT id FROM feeds WHERE id != 'MP_WXS_FEATURED_ARTICLES'"
                    ).fetchall()
                }
            finally:
                worker.close()
        try:
            token = werss_admin_token(settings, node.base_url)
        except Exception as exc:
            node_results.append(
                {
                    "name": node.name,
                    "base_url": node.base_url,
                    "added": added,
                    "existing": len(existing),
                    "errors": [{"feed": "*", "error": f"{type(exc).__name__}: {exc}"}],
                }
            )
            continue

        for feed in feeds:
            feed_id = str(feed["id"])
            if feed_id in existing:
                continue
            try:
                _json_api(
                    settings,
                    "/api/v1/wx/mps",
                    method="POST",
                    token=token,
                    base_url=node.base_url,
                    payload={
                        "mp_name": str(feed["mp_name"] or feed_id),
                        "mp_id": str(feed["faker_id"] or ""),
                        "avatar": str(feed["mp_cover"] or ""),
                        "mp_intro": str(feed["mp_intro"] or ""),
                    },
                )
                added.append(feed_id)
                if delay > 0:
                    time.sleep(delay)
            except Exception as exc:
                errors.append(
                    {
                        "feed": str(feed["mp_name"] or feed_id),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        node_results.append(
            {
                "name": node.name,
                "base_url": node.base_url,
                "added": added,
                "existing": len(existing),
                "errors": errors,
            }
        )
    return {
        "status": "ok" if not any(item["errors"] for item in node_results) else "partial",
        "source_feeds": len(feeds),
        "nodes": node_results,
    }


def _backfill_window(
    oldest_article_at: Optional[int],
    stored_next_page: int,
    initial_pages: int,
    batch_pages: int,
) -> Tuple[int, int]:
    if oldest_article_at is None:
        # Empty sources need short, fair batches. A stored value equal to the
        # old initial-page setting came from the former 0-80 request strategy,
        # so restart those sources at page zero once.
        start_page = stored_next_page if 0 < stored_next_page < initial_pages else 0
        return start_page, min(start_page + batch_pages, initial_pages)
    start_page = stored_next_page or initial_pages
    return start_page, start_page + batch_pages


def _werss_is_busy(source_path: Path, quiet_seconds: int, current_time: Optional[float] = None) -> bool:
    cutoff = (current_time if current_time is not None else time.time()) - quiet_seconds
    candidates = [source_path, Path(f"{source_path}-wal")]
    return any(path.exists() and path.stat().st_mtime >= cutoff for path in candidates)


def _available_werss_nodes(
    settings: Settings,
    quiet_seconds: int,
    configured_names: Sequence[str],
) -> Tuple[List[Tuple[WeRSSNode, str]], List[Dict[str, Any]]]:
    selected = set(configured_names)
    node_status: List[Dict[str, Any]] = []
    available_nodes: List[Tuple[WeRSSNode, str]] = []
    for node in settings.werss_nodes:
        if selected and node.name not in selected:
            node_status.append({"name": node.name, "status": "reserved"})
            continue
        if not node.db_path.exists():
            node_status.append({"name": node.name, "status": "missing_database"})
            continue
        if _werss_is_busy(node.db_path, quiet_seconds):
            node_status.append({"name": node.name, "status": "busy"})
            continue
        try:
            token = werss_admin_token(settings, node.base_url)
            login = _unwrap(
                _json_api(
                    settings,
                    "/api/v1/wx/auth/qr/status",
                    token=token,
                    base_url=node.base_url,
                )
            )
            memory_login = bool(isinstance(login, dict) and login.get("login_status"))
            auth_file = node.db_path.parent / "wx.lic"
            persisted_auth = auth_file.exists() and auth_file.stat().st_size > 10
            if not memory_login and not persisted_auth:
                node_status.append({"name": node.name, "status": "not_logged_in"})
                continue
            available_nodes.append((node, token))
            node_status.append(
                {
                    "name": node.name,
                    "status": "available",
                    "auth": "memory" if memory_login else "persisted",
                }
            )
        except Exception as exc:
            node_status.append(
                {"name": node.name, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
    return available_nodes, node_status


def _raw_article_coverage(settings: Settings) -> Dict[str, Dict[str, int]]:
    articles: Dict[str, Dict[str, Tuple[int, bool]]] = {}
    history_ts = int(settings.history_start.timestamp())
    for node in settings.werss_nodes:
        if not node.db_path.exists():
            continue
        uri = f"file:{urllib.parse.quote(str(node.db_path))}?mode=ro"
        source = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            rows = source.execute(
                """
                SELECT id, mp_id, publish_time,
                       CASE WHEN LENGTH(TRIM(COALESCE(content, ''))) > 0
                                  OR LENGTH(TRIM(COALESCE(content_html, ''))) > 0
                            THEN 1 ELSE 0 END AS has_content
                FROM articles
                WHERE COALESCE(status, 1) != 1000
                """
            ).fetchall()
            for row in rows:
                article_id, feed_id, timestamp, has_content = row
                if timestamp is None:
                    continue
                feed = articles.setdefault(str(feed_id), {})
                key = str(article_id)
                previous = feed.get(key)
                feed[key] = (
                    int(timestamp),
                    bool(has_content) or bool(previous and previous[1]),
                )
        finally:
            source.close()

    coverage: Dict[str, Dict[str, int]] = {}
    for feed_id, feed_articles in articles.items():
        values = list(feed_articles.values())
        missing_times = [
            timestamp
            for timestamp, has_content in values
            if timestamp >= history_ts and not has_content
        ]
        repair_page = 0
        if missing_times:
            newest_missing = max(missing_times)
            newer_events = {
                timestamp for timestamp, _ in values if timestamp > newest_missing
            }
            repair_page = len(newer_events) // 5
        coverage[feed_id] = {
            "oldest": min(timestamp for timestamp, _ in values),
            "missing_content": len(missing_times),
            "repair_page": repair_page,
        }
    return coverage


def _raw_oldest_articles(settings: Settings) -> Dict[str, int]:
    return {
        feed_id: values["oldest"]
        for feed_id, values in _raw_article_coverage(settings).items()
    }


def _backfill_priority_key(
    row: Mapping[str, Any],
    raw_coverage: Mapping[str, Mapping[str, int]],
    history_ts: int,
) -> Tuple[int, int, int, float, int]:
    coverage = raw_coverage.get(str(row["werss_feed_id"]), {})
    oldest = coverage.get("oldest", row["oldest_article_at"])
    boundary_reached = oldest is not None and int(oldest) <= history_ts
    priority_rank = {"required": 0, "preferred": 1, "watch": 2}.get(
        str(row["priority"]),
        3,
    )
    return (
        1 if boundary_reached else 0,
        priority_rank,
        int(row["last_requested_at"] or 0),
        -float(row["weight"] or 0),
        int(row["next_page"] or 0),
    )


def request_backfill(settings: Settings, db: Database, max_accounts: int = 1) -> Dict[str, Any]:
    batch = int(settings.reporting["collection"].get("backfill_batch_pages", 10))
    initial_pages = int(settings.reporting["collection"].get("initial_backfill_pages", 80))
    quiet_seconds = int(settings.reporting["collection"].get("backfill_quiet_seconds", 300))
    configured_nodes = list(
        settings.reporting["collection"].get("backfill_nodes", ["main"])
    )
    available_nodes, node_status = _available_werss_nodes(
        settings, quiet_seconds, configured_nodes
    )
    if not available_nodes:
        return {
            "status": "deferred",
            "reason": "No logged-in WeRSS node is currently idle",
            "requested": [],
            "nodes": node_status,
        }
    per_node_limit = int(
        settings.reporting["collection"].get("backfill_max_accounts_per_node", 3)
    )
    request_limit = min(max_accounts, len(available_nodes) * per_node_limit)
    history_ts = int(settings.history_start.timestamp())
    raw_coverage = _raw_article_coverage(settings)
    rows = db.rows(
        """
        SELECT b.*, a.werss_feed_id, a.expected_name, a.priority, a.oldest_article_at, a.weight
        FROM backfill_state b JOIN accounts a ON a.wechat_id=b.source_wechat_id
        WHERE b.completed=0 AND a.werss_feed_id IS NOT NULL
          AND a.collection_status='active'
        ORDER BY
            CASE WHEN a.oldest_article_at IS NULL THEN 0 ELSE 1 END,
            CASE a.priority WHEN 'required' THEN 0 WHEN 'preferred' THEN 1 ELSE 2 END,
            COALESCE(b.last_requested_at, 0) ASC,
            a.weight DESC,
            b.next_page ASC
        """
    )
    if settings.reporting["collection"].get("backfill_priority") == "history_first":
        rows = sorted(
            rows,
            key=lambda row: _backfill_priority_key(row, raw_coverage, history_ts),
        )
    requested: List[Dict[str, Any]] = []
    for row in rows:
        if len(requested) >= request_limit:
            break
        feed_key = str(row["werss_feed_id"])
        coverage = raw_coverage.get(feed_key, {})
        oldest = coverage.get("oldest", row["oldest_article_at"])
        missing_content = int(coverage.get("missing_content", 0))
        boundary_reached = oldest is not None and int(oldest) <= history_ts
        if boundary_reached and missing_content == 0:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE backfill_state SET completed=1, oldest_seen_at=? WHERE source_wechat_id=?",
                    (int(oldest), row["source_wechat_id"]),
                )
            continue
        purpose = "history"
        if boundary_reached and missing_content:
            purpose = "content_repair"
            start_page = int(coverage.get("repair_page", 0))
            end_page = start_page + batch
        else:
            # Empty sources always begin at page zero. Older versions accidentally
            # treated initial_backfill_pages as a start offset.
            start_page, end_page = _backfill_window(
                int(oldest) if oldest is not None else None,
                int(row["next_page"]),
                initial_pages,
                batch,
            )
        try:
            node, token = available_nodes[len(requested) % len(available_nodes)]
            feed_id = urllib.parse.quote(str(row["werss_feed_id"]))
            response = _json_api(
                settings,
                f"/api/v1/wx/mps/update/{feed_id}?start_page={start_page}&end_page={end_page}",
                token=token,
                base_url=node.base_url,
            )
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE backfill_state SET next_page=?, last_requested_at=?, last_error=NULL
                    WHERE source_wechat_id=?
                    """,
                    (end_page, now_ts(), row["source_wechat_id"]),
                )
            requested.append(
                {
                    "wechat_id": row["source_wechat_id"],
                    "name": row["expected_name"],
                    "start_page": start_page,
                    "end_page": end_page,
                    "node": node.name,
                    "purpose": purpose,
                    "missing_content": missing_content,
                    "response_code": response.get("code"),
                }
            )
        except Exception as exc:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE backfill_state SET last_requested_at=?, last_error=? WHERE source_wechat_id=?",
                    (now_ts(), f"{type(exc).__name__}: {exc}", row["source_wechat_id"]),
                )
            requested.append(
                {
                    "wechat_id": row["source_wechat_id"],
                    "node": node.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "status": "requested" if requested else "idle",
        "requested": requested,
        "remaining": max(0, len(rows) - len(requested)),
        "nodes": node_status,
    }


def _recent_refresh_interval_seconds(
    row: Mapping[str, Any], collection: Mapping[str, Any]
) -> int:
    recent_count = int(row["recent_articles_30d"] or 0)
    high_threshold = int(collection.get("recent_frequency_high_threshold", 60))
    medium_threshold = int(collection.get("recent_frequency_medium_threshold", 20))
    if recent_count >= high_threshold:
        return int(collection.get("recent_refresh_high_interval_seconds", 900))
    if recent_count >= medium_threshold:
        return int(collection.get("recent_refresh_medium_interval_seconds", 1800))
    return int(collection.get("recent_refresh_low_interval_seconds", 3600))


def _recent_refresh_priority_key(
    row: Mapping[str, Any], collection: Mapping[str, Any], current_ts: int
) -> Tuple[float, int, int, int, str]:
    interval = _recent_refresh_interval_seconds(row, collection)
    last_requested = int(row["last_recent_requested_at"] or 0)
    elapsed = current_ts - last_requested if last_requested else current_ts
    urgency = elapsed / max(1, interval)
    priority_rank = {"required": 0, "preferred": 1, "watch": 2}.get(
        str(row["priority"]), 3
    )
    return (
        -urgency,
        priority_rank,
        -int(row["recent_articles_30d"] or 0),
        int(row["newest_article_at"] or 0),
        str(row["expected_name"]),
    )


def request_recent_refresh(
    settings: Settings,
    db: Database,
    max_accounts: int = 9,
) -> Dict[str, Any]:
    quiet_seconds = int(settings.reporting["collection"].get("backfill_quiet_seconds", 90))
    configured_nodes = list(
        settings.reporting["collection"].get("recent_refresh_nodes", ["main"])
    )
    available_nodes, node_status = _available_werss_nodes(
        settings, quiet_seconds, configured_nodes
    )
    if not available_nodes:
        return {
            "status": "deferred",
            "reason": "No recent-refresh WeRSS node is currently idle",
            "requested": [],
            "nodes": node_status,
        }

    collection = settings.reporting["collection"]
    current_ts = now_ts()
    window_days = int(collection.get("recent_frequency_window_days", 30))
    rows = db.rows(
        """
        SELECT b.source_wechat_id, b.last_recent_requested_at,
               a.werss_feed_id, a.expected_name, a.priority, a.newest_article_at,
               COUNT(recent.id) AS recent_articles_30d
        FROM backfill_state b JOIN accounts a ON a.wechat_id=b.source_wechat_id
        LEFT JOIN articles recent
          ON recent.source_wechat_id=a.wechat_id AND recent.published_at>=?
        WHERE a.werss_feed_id IS NOT NULL AND a.collection_status='active'
        GROUP BY b.source_wechat_id, b.last_recent_requested_at,
                 a.werss_feed_id, a.expected_name, a.priority, a.newest_article_at
        """,
        (current_ts - window_days * 86400,),
    )
    due_rows = [
        row
        for row in rows
        if not row["last_recent_requested_at"]
        or current_ts - int(row["last_recent_requested_at"])
        >= _recent_refresh_interval_seconds(row, collection)
    ]
    due_rows = sorted(
        due_rows,
        key=lambda row: _recent_refresh_priority_key(row, collection, current_ts),
    )
    requested: List[Dict[str, Any]] = []
    for row in due_rows[:max_accounts]:
        node, token = available_nodes[len(requested) % len(available_nodes)]
        try:
            feed_id = urllib.parse.quote(str(row["werss_feed_id"]))
            response = _json_api(
                settings,
                f"/api/v1/wx/mps/update/{feed_id}?start_page=0&end_page=1",
                token=token,
                base_url=node.base_url,
            )
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE backfill_state
                    SET last_recent_requested_at=?, last_recent_error=NULL
                    WHERE source_wechat_id=?
                    """,
                    (now_ts(), row["source_wechat_id"]),
                )
            requested.append(
                {
                    "wechat_id": row["source_wechat_id"],
                    "name": row["expected_name"],
                    "node": node.name,
                    "recent_articles_30d": int(row["recent_articles_30d"] or 0),
                    "refresh_interval_seconds": _recent_refresh_interval_seconds(
                        row, collection
                    ),
                    "response_code": response.get("code"),
                }
            )
        except Exception as exc:
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE backfill_state
                    SET last_recent_requested_at=?, last_recent_error=?
                    WHERE source_wechat_id=?
                    """,
                    (now_ts(), f"{type(exc).__name__}: {exc}", row["source_wechat_id"]),
                )
            requested.append(
                {
                    "wechat_id": row["source_wechat_id"],
                    "name": row["expected_name"],
                    "node": node.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "status": "requested" if requested else "idle",
        "requested": requested,
        "remaining": max(0, len(due_rows) - len(requested)),
        "not_due": len(rows) - len(due_rows),
        "nodes": node_status,
    }
