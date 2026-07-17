from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import Database
from .settings import Settings
from .text import split_text


LOGGER = logging.getLogger(__name__)
NOTION_API = "https://api.notion.com/v1"


def _rich_text(value: str) -> List[Dict[str, Any]]:
    patterns = re.compile(r"(\[[^\]]+\]\(https?://[^)]+\)|`[^`]+`|\*\*[^*]+\*\*)")
    parts: List[Dict[str, Any]] = []
    for token in patterns.split(value):
        if not token:
            continue
        link = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", token)
        if link:
            parts.append(
                {"type": "text", "text": {"content": link.group(1), "link": {"url": link.group(2)}}}
            )
        elif token.startswith("`") and token.endswith("`"):
            parts.append(
                {
                    "type": "text",
                    "text": {"content": token[1:-1]},
                    "annotations": {"code": True},
                }
            )
        elif token.startswith("**") and token.endswith("**"):
            parts.append(
                {
                    "type": "text",
                    "text": {"content": token[2:-2]},
                    "annotations": {"bold": True},
                }
            )
        else:
            for chunk in split_text(token, 1900):
                parts.append({"type": "text", "text": {"content": chunk}})
    return parts


def _text_block(block_type: str, value: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(value), "color": "default"},
    }


def markdown_to_blocks(markdown: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    paragraph: List[str] = []
    code_lines: List[str] = []
    code_language = "plain text"
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = " ".join(line.strip() for line in paragraph).strip()
        paragraph.clear()
        for chunk in split_text(text, 1900):
            blocks.append(_text_block("paragraph", chunk))

    def flush_code() -> None:
        nonlocal code_lines
        value = "\n".join(code_lines)
        code_lines = []
        for chunk in split_text(value, 1900):
            blocks.append(
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        "language": code_language,
                    },
                }
            )

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_paragraph()
                code_language = line[3:].strip() or "plain text"
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if re.fullmatch(r"\s*---+\s*", line):
            flush_paragraph()
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            blocks.append(_text_block(f"heading_{len(heading.group(1))}", heading.group(2)))
            continue
        checkbox = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)$", line)
        if checkbox:
            flush_paragraph()
            for chunk in split_text(checkbox.group(2), 1900):
                blocks.append(
                    {
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": _rich_text(chunk),
                            "checked": checkbox.group(1).lower() == "x",
                            "color": "default",
                        },
                    }
                )
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            for chunk in split_text(bullet.group(1), 1900):
                blocks.append(_text_block("bulleted_list_item", chunk))
            continue
        numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if numbered:
            flush_paragraph()
            for chunk in split_text(numbered.group(1), 1900):
                blocks.append(_text_block("numbered_list_item", chunk))
            continue
        quote = re.match(r"^>\s?(.*)$", line)
        if quote:
            flush_paragraph()
            for chunk in split_text(quote.group(1), 1900):
                blocks.append(_text_block("quote", chunk))
            continue
        paragraph.append(line)

    if in_code:
        flush_code()
    flush_paragraph()
    return blocks


class NotionClient:
    def __init__(self, token: str, version: str = "2026-03-11") -> None:
        self.token = token
        self.version = version

    def request(
        self,
        path: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }
        for attempt in range(6):
            request = urllib.request.Request(
                f"{NOTION_API}{path}", data=data, method=method, headers=headers
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or exc.code >= 500:
                    retry_after = exc.headers.get("Retry-After")
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 20)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Notion API {exc.code}: {body}") from exc
            except urllib.error.URLError:
                if attempt == 5:
                    raise
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError("Notion API retry budget exhausted")

    def create_page(
        self,
        parent_page_id: str,
        title: str,
        initial_blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self.request(
            "/pages",
            method="POST",
            payload={
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "properties": {
                    "title": {"type": "title", "title": [{"type": "text", "text": {"content": title[:1900]}}]}
                },
                "children": initial_blocks,
            },
        )

    def append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> None:
        for index in range(0, len(blocks), 80):
            self.request(
                f"/blocks/{page_id}/children",
                method="PATCH",
                payload={"children": blocks[index:index + 80]},
            )
            time.sleep(0.35)

    def trash_page(self, page_id: str) -> None:
        self.request(f"/pages/{page_id}", method="PATCH", payload={"in_trash": True})

    def retrieve_page(self, page_id: str) -> Dict[str, Any]:
        return self.request(f"/pages/{page_id}")

    def list_child_pages(self, parent_page_id: str) -> List[Dict[str, str]]:
        pages: List[Dict[str, str]] = []
        cursor: Optional[str] = None
        while True:
            path = f"/blocks/{parent_page_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={urllib.parse.quote(cursor)}"
            response = self.request(path)
            for item in response.get("results", []):
                if item.get("type") != "child_page":
                    continue
                page = item.get("child_page", {})
                pages.append(
                    {
                        "id": str(item.get("id", "")).replace("-", ""),
                        "title": str(page.get("title", "")).strip(),
                    }
                )
            if not response.get("has_more"):
                return pages
            cursor = str(response.get("next_cursor") or "")
            if not cursor:
                return pages


def notion_client(settings: Settings) -> Tuple[NotionClient, str]:
    token = settings.env("NOTION_TOKEN")
    parent = settings.env("NOTION_PARENT_PAGE_ID")
    if not token or not parent or token == "secret_xxx":
        raise RuntimeError("NOTION_TOKEN is missing in .env")
    if not parent or parent.startswith("xxxx"):
        raise RuntimeError("NOTION_PARENT_PAGE_ID is missing in .env")
    version = str(settings.env("NOTION_VERSION", "2026-03-11"))
    return NotionClient(token, version), parent.replace("-", "")


def verify_notion(settings: Settings) -> Dict[str, Any]:
    client, parent = notion_client(settings)
    page = client.retrieve_page(parent)
    children = client.list_child_pages(parent)
    return {
        "id": page.get("id"),
        "url": page.get("url"),
        "in_trash": page.get("in_trash", False),
        "report_parents": {
            kind: resolve_report_parent(settings, client, parent, kind, children)
            for kind in ("daily", "weekly", "monthly")
        },
    }


def resolve_report_parent(
    settings: Settings,
    client: NotionClient,
    root_parent: str,
    report_kind: str,
    child_pages: Optional[List[Dict[str, str]]] = None,
) -> str:
    env_name = f"NOTION_{report_kind.upper()}_PARENT_PAGE_ID"
    if configured := settings.env(env_name):
        return str(configured).replace("-", "")

    notion_config = settings.reporting.get("notion", {})
    titles = notion_config.get("report_parent_titles", {})
    target_title = str(titles.get(report_kind, "")).strip()
    if not target_title:
        return root_parent

    pages = child_pages if child_pages is not None else client.list_child_pages(root_parent)
    matches = [page for page in pages if page.get("title") == target_title]
    if len(matches) == 1:
        return str(matches[0]["id"]).replace("-", "")
    if len(matches) > 1:
        raise RuntimeError(
            f"Notion contains multiple child pages named {target_title!r}; cannot choose report parent"
        )
    if notion_config.get("require_report_parent", False):
        raise RuntimeError(
            f"Notion report folder {target_title!r} was not found below the configured parent page"
        )
    return root_parent


def publish_report(
    settings: Settings,
    db: Database,
    report_id: int,
    force: bool = False,
) -> Dict[str, Any]:
    row = db.row("SELECT * FROM reports WHERE id=?", (report_id,))
    if not row:
        raise RuntimeError(f"Report not found: {report_id}")
    if row["notion_status"] == "complete" and row["notion_url"] and not force:
        return {"page_id": row["notion_page_id"], "url": row["notion_url"], "reused": True}
    client, root_parent = notion_client(settings)
    parent = resolve_report_parent(settings, client, root_parent, str(row["kind"]))
    if force and row["notion_page_id"]:
        try:
            client.trash_page(str(row["notion_page_id"]))
        except Exception:
            LOGGER.warning("Could not trash prior Notion report page", exc_info=True)
    markdown = Path(str(row["markdown_path"])).read_text(encoding="utf-8")
    blocks = markdown_to_blocks(markdown)
    try:
        page = client.create_page(parent, str(row["title"]), blocks[:80])
        page_id = str(page["id"])
        url = str(page.get("url", ""))
        db.update_report_notion(report_id, "publishing", page_id, url)
        if len(blocks) > 80:
            client.append_blocks(page_id, blocks[80:])
        db.update_report_notion(report_id, "complete", page_id, url)
        return {
            "page_id": page_id,
            "url": url,
            "parent_page_id": parent,
            "blocks": len(blocks),
            "reused": False,
        }
    except Exception:
        db.update_report_notion(report_id, "failed")
        raise
