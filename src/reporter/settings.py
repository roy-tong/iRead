from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .profiles import ResearchProfile


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Account:
    name: str
    wechat_id: str
    priority: str
    weight: float
    influence: float
    reliability: float
    originality: float
    clickbait_risk: float
    source_type: str
    profile_status: str
    aliases: List[str]
    feed_id: Optional[str] = None
    feed_url: Optional[str] = None
    homepage_url: Optional[str] = None
    capture_method: str = "wechat"
    content_mode: str = "full_text"
    conflict_note: str = ""
    collection_status: str = "active"
    inactive_reason: str = ""

    @property
    def match_names(self) -> List[str]:
        return [self.name] + self.aliases

    def matches(self, candidate: str) -> bool:
        normalized = normalize_name(candidate)
        return any(normalize_name(name) == normalized for name in self.match_names)


@dataclass(frozen=True)
class WeRSSNode:
    name: str
    base_url: str
    db_path: Path


@dataclass
class Settings:
    root: Path
    data_dir: Path
    logs_dir: Path
    config_dir: Path
    schema_dir: Path
    prompt_dir: Path
    profile_config: Dict[str, Any]
    source_policy: Dict[str, Any]
    accounts_config: Dict[str, Any]
    external_sources_config: Dict[str, Any]
    topics: Dict[str, Any]
    reporting: Dict[str, Any]
    entities: Dict[str, Any]

    @classmethod
    def load(cls, root: Path, config_dir: Optional[Path] = None) -> "Settings":
        root = root.resolve()
        load_env(root / ".env")
        default_config_dir = root / "config"
        configured_config_dir = config_dir or (
            Path(value)
            if (
                value := os.environ.get("IREAD_CONFIG_DIR")
                or os.environ.get("REPORTER_CONFIG_DIR")
            )
            else None
        )
        active_config_dir = (
            _resolve_path(root, str(configured_config_dir))
            if configured_config_dir
            else default_config_dir
        ).resolve()

        def config_json(name: str, optional_default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            path = active_config_dir / name
            if path.exists():
                return read_json(path)
            fallback = default_config_dir / name
            if fallback.exists():
                return read_json(fallback)
            if optional_default is not None:
                return optional_default
            raise FileNotFoundError(f"Missing configuration file: {path}")

        accounts_config = config_json("accounts.json")
        default_accounts_path = default_config_dir / "accounts.json"
        if active_config_dir != default_config_dir and default_accounts_path.exists():
            default_accounts = read_json(default_accounts_path)
            merged_priorities = {
                **default_accounts.get("priorities", {}),
                **accounts_config.get("priorities", {}),
            }
            accounts_config = {
                **default_accounts,
                **accounts_config,
                "priorities": merged_priorities,
            }

        topics = config_json("topics.json")
        runtime_path = active_config_dir / "runtime.json"
        runtime = read_json(runtime_path) if runtime_path.exists() else {}
        settings = cls(
            root=root,
            data_dir=_resolve_path(
                root,
                os.environ.get("IREAD_DATA_DIR")
                or os.environ.get(
                    "REPORTER_DATA_DIR", str(runtime.get("data_dir", "data"))
                ),
            ),
            logs_dir=_resolve_path(
                root,
                os.environ.get("IREAD_LOGS_DIR")
                or os.environ.get(
                    "REPORTER_LOGS_DIR", str(runtime.get("logs_dir", "logs"))
                ),
            ),
            config_dir=active_config_dir,
            schema_dir=root / "schemas",
            prompt_dir=root / "prompts",
            profile_config=config_json("profile.json", {}),
            source_policy=config_json("source_policy.json", {}),
            accounts_config=accounts_config,
            external_sources_config=config_json("external_sources.json", {"sources": []}),
            topics=topics,
            reporting=config_json("reporting.json"),
            entities=config_json("entities.bootstrap.json"),
        )
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "reports").mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "state").mkdir(parents=True, exist_ok=True)
        return settings

    @property
    def db_path(self) -> Path:
        return self.data_dir / "research.db"

    @property
    def history_start(self) -> datetime:
        value = self.reporting.get("history_start") or self.accounts_config["history_start"]
        return parse_datetime(value)

    @property
    def profile(self) -> ResearchProfile:
        return ResearchProfile.from_config(self.profile_config, self.topics)

    def priority_defaults(self, priority: str) -> Dict[str, Any]:
        configured = self.accounts_config.get("priorities", {})
        if priority in configured:
            return configured[priority]
        fallback_path = self.root / "config" / "accounts.json"
        if fallback_path.resolve() != (self.config_dir / "accounts.json").resolve():
            fallback = read_json(fallback_path).get("priorities", {})
            if priority in fallback:
                return fallback[priority]
        raise KeyError(f"Missing priority configuration: {priority}")

    @property
    def accounts(self) -> List[Account]:
        result: List[Account] = []
        for item in self.accounts_config["accounts"]:
            defaults = self.priority_defaults(str(item["priority"]))
            result.append(
                Account(
                    name=item["name"],
                    wechat_id=item["wechat_id"],
                    priority=item["priority"],
                    weight=float(defaults["weight"]),
                    influence=float(item.get("influence", defaults["influence"])),
                    reliability=float(item.get("reliability", defaults["reliability"])),
                    originality=float(item.get("originality", defaults["originality"])),
                    clickbait_risk=float(item.get("clickbait_risk", defaults["clickbait_risk"])),
                    source_type=str(item.get("source_type", defaults.get("source_type", "wechat"))),
                    profile_status=str(item.get("profile_status", "provisional")),
                    aliases=list(item.get("aliases", [])),
                    feed_id=item.get("feed_id"),
                    capture_method="wechat",
                    content_mode="full_text",
                    conflict_note=str(item.get("conflict_note", "")),
                    collection_status=str(item.get("collection_status", "active")),
                    inactive_reason=str(item.get("inactive_reason", "")),
                )
            )
        return result

    @property
    def external_sources(self) -> List[Account]:
        result: List[Account] = []
        for item in self.external_sources_config.get("sources", []):
            defaults = self.priority_defaults(str(item["priority"]))
            source_id = str(item["id"])
            result.append(
                Account(
                    name=str(item["name"]),
                    wechat_id=f"external:{source_id}",
                    priority=str(item["priority"]),
                    weight=float(defaults["weight"]),
                    influence=float(item.get("influence", defaults["influence"])),
                    reliability=float(item.get("reliability", defaults["reliability"])),
                    originality=float(item.get("originality", defaults["originality"])),
                    clickbait_risk=float(item.get("clickbait_risk", defaults["clickbait_risk"])),
                    source_type=str(item.get("source_type", "external")),
                    profile_status=str(item.get("profile_status", "provisional")),
                    aliases=list(item.get("aliases", [])),
                    feed_url=item.get("feed_url"),
                    homepage_url=item.get("homepage_url"),
                    capture_method=str(item.get("capture_method", "web_pending")),
                    content_mode=str(item.get("content_mode", "full_text")),
                    conflict_note=str(item.get("conflict_note", "")),
                    collection_status=str(item.get("collection_status", "active")),
                    inactive_reason=str(item.get("inactive_reason", "")),
                )
            )
        return result

    @property
    def all_sources(self) -> List[Account]:
        return self.accounts + self.external_sources

    def env(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(name, default)

    def resolve_path(self, value: str) -> Path:
        return _resolve_path(self.root, value)

    @property
    def werss_db_path(self) -> Path:
        raw = self.env(
            "WERSS_DB_PATH",
            self.reporting["collection"].get("werss_db_path", "data/we-mp-rss/we_mp_rss.db"),
        )
        assert raw is not None
        return self.resolve_path(raw)

    @property
    def werss_base_url(self) -> str:
        default = self.reporting["collection"].get("werss_base_url", "http://127.0.0.1:8001")
        return str(self.env("WERSS_BASE_URL", default)).rstrip("/")

    @property
    def werss_nodes(self) -> List[WeRSSNode]:
        nodes = [
            WeRSSNode(
                name="main",
                base_url=self.werss_base_url,
                db_path=self.werss_db_path,
            )
        ]
        for item in self.reporting["collection"].get("werss_workers", []):
            nodes.append(
                WeRSSNode(
                    name=str(item["name"]),
                    base_url=str(item["base_url"]).rstrip("/"),
                    db_path=self.resolve_path(str(item["db_path"])),
                )
            )
        return nodes

    def topic_names(self) -> Iterable[str]:
        for topic in self.topics.get("topics", []):
            yield topic["name"]
