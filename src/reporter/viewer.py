from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from .settings import Settings


LOGGER = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Asia/Shanghai")


def _json_value(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _published(value: int) -> str:
    return datetime.fromtimestamp(value, tz=TIMEZONE).isoformat()


def _bounded_int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


class LibraryStore:
    def __init__(self, db_path: Path, settings: Optional[Settings] = None) -> None:
        self.db_path = db_path
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro", uri=True, timeout=10, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def ui_config(self) -> Dict[str, Any]:
        if self.settings is None:
            return {"profile_name": "Research Library", "topic_labels": {}}
        return {
            "profile_name": self.settings.profile.name,
            "topic_labels": {
                str(item.get("id")): str(item.get("name"))
                for item in self.settings.topics.get("topics", [])
                if isinstance(item, dict) and item.get("id") and item.get("name")
            },
        }

    @staticmethod
    def _where(params: Mapping[str, str]) -> Tuple[str, List[Any]]:
        clauses = ["1=1"]
        values: List[Any] = []
        source_kind = params.get("type", "all")
        if source_kind == "external":
            clauses.append("a.source_wechat_id LIKE 'external:%'")
        elif source_kind == "wechat":
            clauses.append("a.source_wechat_id NOT LIKE 'external:%'")
        source = params.get("source", "")
        if source:
            clauses.append("a.source_wechat_id=?")
            values.append(source)
        topic = params.get("topic", "")
        if topic:
            clauses.append("COALESCE(a.primary_topic, 'unclassified')=?")
            values.append(topic)
        query = params.get("q", "").strip()
        if query:
            token = f"%{query}%"
            clauses.append(
                "(a.title LIKE ? OR a.source_name LIKE ? OR a.content_text LIKE ? OR a.ai_summary LIKE ?)"
            )
            values.extend([token, token, token, token])
        return " AND ".join(clauses), values

    def stats(self) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN source_wechat_id LIKE 'external:%' THEN 1 ELSE 0 END) AS external,
                       SUM(CASE WHEN source_wechat_id NOT LIKE 'external:%' THEN 1 ELSE 0 END) AS wechat,
                       SUM(CASE WHEN transcript_status='complete' THEN 1 ELSE 0 END) AS transcripts,
                       SUM(CASE WHEN viewpoints_json IS NOT NULL AND viewpoints_json NOT IN ('', '[]') THEN 1 ELSE 0 END) AS viewpoints
                FROM articles
                """
            ).fetchone()
        assert row is not None
        return {key: int(row[key] or 0) for key in row.keys()}

    def sources(self, source_kind: str) -> List[Dict[str, Any]]:
        clauses = []
        if source_kind == "external":
            clauses.append("ac.wechat_id LIKE 'external:%'")
        elif source_kind == "wechat":
            clauses.append("ac.wechat_id NOT LIKE 'external:%'")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ac.wechat_id AS id, ac.expected_name AS name, ac.source_type,
                       COUNT(a.id) AS article_count
                FROM accounts ac LEFT JOIN articles a ON a.source_wechat_id=ac.wechat_id
                {where}
                GROUP BY ac.wechat_id
                HAVING COUNT(a.id) > 0
                ORDER BY article_count DESC, name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_articles(self, params: Mapping[str, str]) -> Dict[str, Any]:
        where, values = self._where(params)
        limit = _bounded_int(params.get("limit", "30"), 30, 1, 100)
        offset = _bounded_int(params.get("offset", "0"), 0, 0, 1_000_000)
        sort = params.get("sort", "newest")
        order = {
            "relevance": "COALESCE(a.relevance, 0) DESC, a.published_at DESC",
            "originality": "COALESCE(a.originality_score, 0) DESC, a.published_at DESC",
            "newest": "a.published_at DESC",
        }.get(sort, "a.published_at DESC")
        with self.connect() as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM articles a WHERE {where}", values).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT a.id, a.source_wechat_id, a.source_name, a.title, a.url,
                       a.published_at, a.description, a.ai_summary, a.primary_topic,
                       a.relevance, a.source_role, a.originality_score, a.credibility,
                       a.transcript_status, LENGTH(COALESCE(a.content_text, '')) AS content_chars
                FROM articles a
                WHERE {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?
                """,
                values + [limit, offset],
            ).fetchall()
        items = []
        for row in rows:
            summary = row["ai_summary"] or row["description"] or ""
            items.append(
                {
                    **dict(row),
                    "published_at": _published(int(row["published_at"])),
                    "summary": str(summary)[:320],
                }
            )
        return {"total": total, "offset": offset, "limit": limit, "items": items}

    def article(self, article_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT a.*, ac.source_type, ac.influence, ac.reliability,
                       ac.originality AS source_originality, ac.conflict_note
                FROM articles a JOIN accounts ac ON ac.wechat_id=a.source_wechat_id
                WHERE a.id=?
                """,
                (article_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "source_name": row["source_name"],
            "source_wechat_id": row["source_wechat_id"],
            "source_type": row["source_type"],
            "published_at": _published(int(row["published_at"])),
            "url": row["url"] or "",
            "transcript_url": row["transcript_url"] or "",
            "transcript_status": row["transcript_status"] or "",
            "primary_topic": row["primary_topic"] or "unclassified",
            "secondary_topics": _json_value(row["secondary_topics_json"], []),
            "relevance": row["relevance"],
            "source_role": row["source_role"] or "unknown",
            "credibility": row["credibility"],
            "originality_score": row["originality_score"],
            "summary": row["ai_summary"] or row["description"] or "",
            "content": row["content_text"] or row["description"] or "",
            "viewpoints": _json_value(row["viewpoints_json"], []),
            "facts": _json_value(row["facts_json"], []),
            "opinions": _json_value(row["opinions_json"], []),
            "companies": _json_value(row["companies_json"], []),
            "people": _json_value(row["people_json"], []),
            "verification_flags": _json_value(row["verification_flags_json"], []),
            "source_profile": {
                "influence": row["influence"],
                "reliability": row["reliability"],
                "originality": row["source_originality"],
                "conflict_note": row["conflict_note"] or "",
            },
        }


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Research Library</title>
  <style>
    :root { color-scheme: light; --ink:#17201f; --muted:#687371; --line:#d9dfdd; --paper:#f7f9f8; --white:#fff; --teal:#0b6b61; --teal-soft:#e2f0ed; --orange:#b95720; --yellow:#f3c94d; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--paper); font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; letter-spacing:0; }
    button,input,select { font:inherit; letter-spacing:0; }
    button { cursor:pointer; }
    .topbar { height:58px; display:flex; align-items:center; gap:18px; padding:0 22px; background:var(--ink); color:#fff; border-bottom:3px solid var(--yellow); }
    .brand { font-size:17px; font-weight:700; white-space:nowrap; }
    .stats { display:flex; gap:17px; color:#c8d1cf; font-size:12px; overflow:hidden; white-space:nowrap; }
    .stats strong { color:#fff; font-size:14px; margin-right:4px; }
    .toolbar { display:grid; grid-template-columns:minmax(240px,1fr) 180px 150px; gap:9px; padding:12px 18px; border-bottom:1px solid var(--line); background:var(--white); }
    .search,.select { width:100%; height:36px; border:1px solid #bdc7c4; border-radius:5px; background:#fff; color:var(--ink); padding:0 11px; outline:none; }
    .search:focus,.select:focus { border-color:var(--teal); box-shadow:0 0 0 2px var(--teal-soft); }
    .modes { display:flex; padding:0 18px 12px; gap:0; background:#fff; border-bottom:1px solid var(--line); }
    .mode { height:34px; min-width:88px; border:1px solid #b8c2c0; background:#fff; color:#36423f; padding:0 14px; }
    .mode:first-child { border-radius:5px 0 0 5px; }
    .mode:last-child { border-radius:0 5px 5px 0; }
    .mode + .mode { border-left:0; }
    .mode.active { background:var(--teal); color:#fff; border-color:var(--teal); }
    .workspace { height:calc(100vh - 153px); min-height:520px; display:grid; grid-template-columns:minmax(360px,42%) minmax(0,58%); }
    .list-pane { overflow:auto; border-right:1px solid var(--line); background:#fff; }
    .result-head { position:sticky; top:0; z-index:2; display:flex; justify-content:space-between; align-items:center; height:40px; padding:0 17px; background:#edf1f0; border-bottom:1px solid var(--line); color:var(--muted); font-size:12px; }
    .article-row { width:100%; min-height:116px; display:block; text-align:left; padding:14px 17px; border:0; border-bottom:1px solid #e4e8e7; background:#fff; color:inherit; }
    .article-row:hover { background:#f2f7f5; }
    .article-row.active { background:var(--teal-soft); box-shadow:inset 4px 0 0 var(--teal); }
    .row-title { font-size:15px; font-weight:650; line-height:1.42; margin-bottom:6px; }
    .meta { display:flex; flex-wrap:wrap; gap:5px 10px; color:var(--muted); font-size:12px; }
    .source { color:var(--teal); font-weight:650; }
    .summary { margin-top:7px; color:#515d5a; font-size:13px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .badge { display:inline-flex; align-items:center; min-height:20px; border:1px solid #c9d1cf; border-radius:4px; padding:0 6px; color:#4f5d5a; background:#fff; font-size:11px; }
    .badge.transcript { border-color:#d99b76; color:#8a3f18; background:#fff2e9; }
    .pager { display:flex; align-items:center; justify-content:center; gap:12px; padding:16px; }
    .pager button,.command { min-height:34px; border:1px solid #aebbb8; border-radius:5px; background:#fff; color:#273330; padding:0 12px; }
    .pager button:disabled { cursor:default; opacity:.4; }
    .detail-pane { overflow:auto; background:var(--paper); }
    .empty { height:100%; display:grid; place-items:center; color:var(--muted); }
    .detail { max-width:900px; margin:0 auto; padding:28px 34px 70px; }
    .detail h1 { margin:0 0 10px; font-size:26px; line-height:1.3; letter-spacing:0; }
    .detail-actions { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 24px; }
    .command.primary { color:#fff; background:var(--teal); border-color:var(--teal); text-decoration:none; display:inline-flex; align-items:center; }
    .section { padding:20px 0; border-top:1px solid var(--line); }
    .section h2 { margin:0 0 12px; font-size:15px; letter-spacing:0; }
    .lead { font-size:16px; line-height:1.75; color:#31403c; }
    .viewpoint { padding:12px 0 12px 14px; border-left:3px solid var(--orange); }
    .viewpoint + .viewpoint { margin-top:13px; }
    .speaker { font-weight:700; }
    .basis { margin-top:5px; color:var(--muted); }
    .content { white-space:pre-wrap; word-break:break-word; font-size:15px; line-height:1.8; color:#293532; }
    .flags { color:#8a3f18; }
    .loading { padding:24px; color:var(--muted); }
    @media (max-width:860px) {
      .topbar { height:auto; min-height:58px; align-items:flex-start; flex-direction:column; gap:3px; padding:10px 14px; }
      .stats { width:100%; overflow:auto; }
      .toolbar { grid-template-columns:1fr 1fr; padding:10px 12px; }
      .toolbar .search { grid-column:1 / -1; }
      .modes { padding:0 12px 10px; }
      .mode { min-width:0; flex:1; }
      .workspace { height:auto; min-height:0; display:block; }
      .list-pane { height:auto; max-height:none; border-right:0; }
      .detail-pane { min-height:70vh; border-top:3px solid var(--ink); }
      .detail { padding:22px 17px 60px; }
      .detail h1 { font-size:22px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand" id="brand">研究资料库</div>
    <div class="stats" id="stats"></div>
  </header>
  <section class="toolbar">
    <input class="search" id="search" type="search" placeholder="搜索标题、来源或正文">
    <select class="select" id="source"><option value="">全部来源</option></select>
    <select class="select" id="sort">
      <option value="newest">最新发布</option>
      <option value="relevance">研究相关度</option>
      <option value="originality">原创性</option>
    </select>
  </section>
  <nav class="modes" aria-label="来源类型">
    <button class="mode" data-type="all">全部</button>
    <button class="mode" data-type="wechat">公众号</button>
    <button class="mode" data-type="external">海外</button>
  </nav>
  <main class="workspace">
    <section class="list-pane">
      <div class="result-head"><span id="resultCount">加载中</span><span id="pageInfo"></span></div>
      <div id="articleList"></div>
      <div class="pager">
        <button id="prev">上一页</button><span id="pagerText"></span><button id="next">下一页</button>
      </div>
    </section>
    <article class="detail-pane" id="detail"><div class="empty">从左侧选择一篇文章</div></article>
  </main>
  <script>
    const state = { type: new URLSearchParams(location.search).get('type') || 'all', source:'', q:'', sort:'newest', offset:0, limit:30, total:0, selected:'', topicLabels:{} };
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const topicLabel = (value) => state.topicLabels[value] || ({other:'其他',unclassified:'未分类'}[value]) || value || '未分类';
    const fmtDate = (value) => new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
    const api = async (path) => { const response = await fetch(path); if (!response.ok) throw new Error(await response.text()); return response.json(); };

    async function loadConfig() {
      const config = await api('/api/config');
      state.topicLabels = config.topic_labels || {};
      $('brand').textContent = `${config.profile_name || '研究'} · 资料库`;
      document.title = `${config.profile_name || '研究'} · 资料库`;
    }

    async function loadStats() {
      const s = await api('/api/stats');
      $('stats').innerHTML = `<span><strong>${s.total.toLocaleString()}</strong>总文章</span><span><strong>${s.wechat.toLocaleString()}</strong>公众号</span><span><strong>${s.external.toLocaleString()}</strong>海外</span><span><strong>${s.transcripts.toLocaleString()}</strong>完整逐字稿</span><span><strong>${s.viewpoints.toLocaleString()}</strong>观点文章</span>`;
    }
    async function loadSources() {
      const data = await api(`/api/sources?type=${encodeURIComponent(state.type)}`);
      $('source').innerHTML = '<option value="">全部来源</option>' + data.items.map(s => `<option value="${esc(s.id)}">${esc(s.name)} (${s.article_count})</option>`).join('');
      $('source').value = state.source;
    }
    function updateModes() { document.querySelectorAll('.mode').forEach(b => b.classList.toggle('active', b.dataset.type === state.type)); }
    async function loadArticles(selectFirst=true) {
      $('articleList').innerHTML = '<div class="loading">正在读取文章...</div>';
      const params = new URLSearchParams({type:state.type,source:state.source,q:state.q,sort:state.sort,offset:state.offset,limit:state.limit});
      const data = await api('/api/articles?' + params);
      state.total = data.total;
      $('resultCount').textContent = `共 ${data.total.toLocaleString()} 篇`;
      const page = Math.floor(state.offset/state.limit)+1, pages = Math.max(1,Math.ceil(data.total/state.limit));
      $('pageInfo').textContent = `${page} / ${pages}`;
      $('pagerText').textContent = `第 ${page} 页`;
      $('prev').disabled = state.offset === 0;
      $('next').disabled = state.offset + state.limit >= data.total;
      $('articleList').innerHTML = data.items.map(a => `<button class="article-row ${a.id===state.selected?'active':''}" data-id="${esc(a.id)}"><div class="row-title">${esc(a.title)}</div><div class="meta"><span class="source">${esc(a.source_name)}</span><span>${fmtDate(a.published_at)}</span><span class="badge">${esc(topicLabel(a.primary_topic))}</span>${a.transcript_status==='complete'?'<span class="badge transcript">完整逐字稿</span>':''}</div><div class="summary">${esc(a.summary)}</div></button>`).join('') || '<div class="loading">没有符合条件的文章</div>';
      document.querySelectorAll('.article-row').forEach(row => row.addEventListener('click', () => openArticle(row.dataset.id, true)));
      if (selectFirst && data.items.length) openArticle(data.items[0].id);
    }
    async function openArticle(id, shouldScroll=false) {
      state.selected = id;
      document.querySelectorAll('.article-row').forEach(row => row.classList.toggle('active', row.dataset.id===id));
      $('detail').innerHTML = '<div class="loading">正在读取正文...</div>';
      const a = await api('/api/articles/' + encodeURIComponent(id));
      const viewpoints = (a.viewpoints || []).map(v => `<div class="viewpoint"><div><span class="speaker">${esc(v.speaker || '未具名')}</span>${v.speaker_role?` · ${esc(v.speaker_role)}`:''}${v.organization?` · ${esc(v.organization)}`:''}</div><div>${esc(v.viewpoint)}</div>${v.basis?`<div class="basis">依据：${esc(v.basis)}</div>`:''}${v.verification_target?`<div class="basis">验证：${esc(v.verification_target)}</div>`:''}</div>`).join('');
      const facts = (a.facts || []).map(x => `<li>${esc(x)}</li>`).join('');
      const flags = (a.verification_flags || []).map(x => `<li>${esc(x)}</li>`).join('');
      $('detail').innerHTML = `<div class="detail"><h1>${esc(a.title)}</h1><div class="meta"><span class="source">${esc(a.source_name)}</span><span>${fmtDate(a.published_at)}</span><span class="badge">${esc(topicLabel(a.primary_topic))}</span>${a.transcript_status==='complete'?'<span class="badge transcript">完整逐字稿</span>':''}</div><div class="detail-actions">${a.url?`<a class="command primary" href="${esc(a.url)}" target="_blank" rel="noopener">打开原文</a>`:''}${a.transcript_url && a.transcript_url!==a.url?`<a class="command" href="${esc(a.transcript_url)}" target="_blank" rel="noopener">打开逐字稿</a>`:''}</div>${a.summary?`<section class="section"><h2>摘要</h2><div class="lead">${esc(a.summary)}</div></section>`:''}${viewpoints?`<section class="section"><h2>原创观点</h2>${viewpoints}</section>`:''}${facts?`<section class="section"><h2>事实摘录</h2><ul>${facts}</ul></section>`:''}${flags?`<section class="section flags"><h2>待核验</h2><ul>${flags}</ul></section>`:''}<section class="section"><h2>正文</h2><div class="content">${esc(a.content)}</div></section></div>`;
      if (shouldScroll && matchMedia('(max-width: 860px)').matches) $('detail').scrollIntoView({block:'start'});
    }
    function refreshFilters() { state.offset=0; state.selected=''; loadArticles(); }
    document.querySelectorAll('.mode').forEach(b => b.addEventListener('click', async () => { state.type=b.dataset.type; state.source=''; updateModes(); history.replaceState(null,'',state.type==='all'?'/' : `/?type=${state.type}`); await loadSources(); refreshFilters(); }));
    $('source').addEventListener('change', e => { state.source=e.target.value; refreshFilters(); });
    $('sort').addEventListener('change', e => { state.sort=e.target.value; refreshFilters(); });
    let timer; $('search').addEventListener('input', e => { clearTimeout(timer); timer=setTimeout(()=>{state.q=e.target.value.trim();refreshFilters();},250); });
    $('prev').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-state.limit);loadArticles();});
    $('next').addEventListener('click',()=>{state.offset+=state.limit;loadArticles();});
    updateModes(); Promise.all([loadConfig(),loadStats(),loadSources()]).then(()=>loadArticles()).catch(err => {$('articleList').innerHTML=`<div class="loading">加载失败：${esc(err.message)}</div>`;});
  </script>
</body>
</html>"""


class LibraryHandler(BaseHTTPRequestHandler):
    store: LibraryStore

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format % args)

    def _send(self, payload: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/" or parsed.path == "/index.html":
                self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/stats":
                self._json(self.store.stats())
                return
            if parsed.path == "/api/config":
                self._json(self.store.ui_config())
                return
            if parsed.path == "/api/sources":
                query = parse_qs(parsed.query)
                source_kind = query.get("type", ["all"])[0]
                self._json({"items": self.store.sources(source_kind)})
                return
            if parsed.path == "/api/articles":
                query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                self._json(self.store.list_articles(query))
                return
            prefix = "/api/articles/"
            if parsed.path.startswith(prefix):
                article = self.store.article(unquote(parsed.path[len(prefix):]))
                if article is None:
                    self._json({"error": "article not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self._json(article)
                return
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            LOGGER.exception("Library request failed")
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def serve(settings: Settings, host: str, port: int) -> None:
    if not settings.db_path.exists():
        raise RuntimeError(f"Research database does not exist: {settings.db_path}")
    handler = type(
        "ConfiguredLibraryHandler",
        (LibraryHandler,),
        {"store": LibraryStore(settings.db_path, settings)},
    )
    server = ThreadingHTTPServer((host, port), handler)
    LOGGER.info("Research library listening on http://%s:%s", host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Local unified research article library")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    serve(Settings.load(Path(args.project_root)), args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
