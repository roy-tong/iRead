from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from typing import Iterable, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "figcaption",
        "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header",
        "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
        "td", "th", "tr", "ul",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text).replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def normalize_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
        ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "scene"}
        query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key not in ignored]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))
    except Exception:
        return value.strip()


def content_fingerprint(title: str, content: str, url: str) -> str:
    sample = "\n".join((title.strip(), content.strip(), normalize_url(url)))
    return hashlib.sha256(sample.encode("utf-8", errors="replace")).hexdigest()


def split_text(value: str, limit: int = 1900) -> Iterable[str]:
    value = value.strip()
    while len(value) > limit:
        cut = max(value.rfind("\n", 0, limit), value.rfind("。", 0, limit), value.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        yield value[:cut].strip()
        value = value[cut:].strip()
    if value:
        yield value
