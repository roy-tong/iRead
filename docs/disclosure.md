# Disclosure

This repository discloses both runtime components and collection sources.

## Runtime components

- We-MP-RSS: local WeChat public-account collector, MIT license, cloned at
  install time.
- uv: optional Python runtime installer helper, Apache-2.0 OR MIT license.
- Playwright: browser automation used indirectly by We-MP-RSS, Apache-2.0
  license.
- RSSHub: optional RSS route infrastructure referenced for future source
  discovery, AGPL-3.0 license.
- WorkBuddy: optional GPL-3.0 agent runtime. The repository includes only a
  separate Markdown workflow adapter and does not copy WorkBuddy code.

Codex and WorkBuddy adapters are optional entry points over the same local CLI;
neither changes the source-selection or explicit-approval rules.

See `NOTICE.md` for the authoritative component notice.

## Source lists

The maintainer's example subscription discloses:

- 72 WeChat public accounts in `config/accounts.json`.
- 40 external sources in `config/external_sources.json`.
- 32 active RSS, Atom, or podcast feed URLs in `config/external_sources.json`.
- Rationale and candidate notes in `docs/source-candidates.md`.

The public archive exporter also writes a consolidated machine-readable source
list:

```bash
bin/iread export --output-dir public/archive
```

The resulting `public/archive/sources.json` includes source names, homepage
URLs, feed URLs, capture methods, content modes, source types, and scoring
subscriptions.

## Collected content

The repository license does not transfer rights to upstream articles. The
default public archive excludes `content_text` and `content_html`; enabling
full-text export requires `--include-content --rights-confirmed`.
