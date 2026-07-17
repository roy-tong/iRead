from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


def _strings(values: Iterable[Any]) -> List[str]:
    return [str(value).strip() for value in values if str(value).strip()]


@dataclass(frozen=True)
class ResearchProfile:
    id: str
    name: str
    description: str
    seed_keywords: List[str]
    audiences: List[str]
    goals: List[str]
    languages: List[str]
    regions: List[str]
    exclusions: List[str]
    domains: List[Dict[str, Any]]

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        topics: Dict[str, Any],
    ) -> "ResearchProfile":
        topic_names = _strings(
            item.get("name", "")
            for item in topics.get("topics", [])
            if isinstance(item, dict)
        )
        name = str(config.get("name") or " / ".join(topic_names) or "Research Profile")
        return cls(
            id=str(config.get("id") or "default"),
            name=name,
            description=str(config.get("description") or ""),
            seed_keywords=_strings(config.get("seed_keywords", topic_names)),
            audiences=_strings(config.get("audiences", ["research"])),
            goals=_strings(config.get("goals", ["material_changes", "trend_detection"])),
            languages=_strings(config.get("languages", ["zh-CN"])),
            regions=_strings(config.get("regions", ["global"])),
            exclusions=_strings(config.get("exclusions", [])),
            domains=[
                dict(item)
                for item in config.get("domains", [])
                if isinstance(item, dict)
            ],
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "seed_keywords": self.seed_keywords,
            "audiences": self.audiences,
            "goals": self.goals,
            "languages": self.languages,
            "regions": self.regions,
            "exclusions": self.exclusions,
            "domains": self.domains,
        }
