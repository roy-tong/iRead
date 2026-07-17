# iRead subscription manifest

The CLI accepts one JSON object with optional `subscription` and `defaults` objects plus a required non-empty `domains` array.

```json
{
  "subscription": {
    "id": "my-iread",
    "name": "我的 iRead"
  },
  "defaults": {
    "audiences": ["research"],
    "goals": ["material_changes", "trend_detection", "source_verification"],
    "languages": ["zh-CN", "en"],
    "regions": ["global"],
    "max_sources": 20,
    "preset": "standard"
  },
  "domains": [
    {
      "id": "medical-devices",
      "field": "医疗器械监管与临床转化"
    },
    {
      "id": "energy-markets",
      "field": "新能源电力市场",
      "regions": ["中国", "北美", "欧洲"]
    }
  ]
}
```

Supported defaults and per-domain overrides:

- `audiences`: intended readers or decisions.
- `goals`: report goals.
- `languages`: source languages.
- `regions`: geographic scope.
- `max_sources`: 8 to 40 candidates.
- `preset`: `light`, `standard`, or `deep`.
- `history_start`: optional ISO 8601 collection boundary.

Every domain requires `field`. `id` is optional and will be normalized to a path-safe slug. The proposal command writes one `<id>.json` file plus `batch-results.json`; existing proposals are reused unless `--force` is supplied. `apply-subscription` merges all explicitly approved domain ids into one configuration.
