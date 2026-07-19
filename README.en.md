# iRead: AI Research Radar & Source Discovery

iRead is an open-source, local-first AI research assistant that discovers high-quality sources for any field, collects RSS and authorized WeChat content, and produces daily, weekly, and monthly research digests.

[Simplified Chinese](README.md) | [Quick Start](#quick-start) | [Documentation](#documentation) | [Contributing](CONTRIBUTING.md)

![Version](https://img.shields.io/badge/version-0.2.0--beta.5-orange)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Interface](https://img.shields.io/badge/interface-Agent%20Skills-111111)
![License](https://img.shields.io/badge/license-MIT-blue)

## Why iRead

Most AI RSS readers assume that you already know which feeds to follow. iRead starts one step earlier: give it one or more research fields, and it builds a reviewable source map before collecting anything.

iRead helps you:

- expand a field into durable topics and event types;
- discover first-party sources, independent reporting, specialist analysis, expert voices, and discovery signals;
- review direct source pages, representative works, risks, and preliminary quality scores;
- collect RSS, public web candidates, and locally authorized WeChat Official Accounts;
- deduplicate events and separate facts, opinions, inference, and evidence quality;
- generate daily updates, weekly trend analysis, and monthly structural reviews.

It is designed for researchers, investors, product managers, students, and industry professionals who need long-term information tracking without manually building a feed list.

## How it differs from a typical AI RSS reader

| Typical RSS or summarization tool | iRead |
| --- | --- |
| You provide the feeds | You provide research fields; iRead proposes sources for review |
| Summarizes individual articles | Deduplicates events and tracks agreement, disagreement, and change over time |
| Mixes source types together | Separates first-party evidence, verification, analysis, expert practice, and discovery leads |
| Focuses on today's links | Uses daily, weekly, and monthly editorial strategies |
| Often cloud-first | Keeps configuration, articles, and reports local by default |

## Quick Start

Requirements: macOS, Python 3.9+, Git, and Codex, Claude Code, Doubao Professional office-task mode, or WorkBuddy.

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/scripts/install.sh codex
```

This is the Codex command. Replace the final `codex` with `claude-code` or `doubao` for those surfaces. See the [Agent installation guide](docs/agent-installation.md) for WorkBuddy and Doubao ZIP import. Installation is deterministic and does not ask the Agent to analyze the repository or rebuild a full index.

After installation, start a new task and say:

```text
Use iRead to follow battery recycling, urban climate adaptation, and pet healthcare.
Show me the proposed sources and representative works before starting collection.
```

The Agent will stop for review before creating a subscription, collecting articles, or installing recurring tasks.

### WorkBuddy one-line install (experimental)

Send one sentence in WorkBuddy:

```text
Only run this command to install iRead; do not browse or analyze the repository: git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/install-workbuddy.sh
```

WorkBuddy only needs one deterministic shell action. The terminal fallback is:

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/install-workbuddy.sh
```

Open a new WorkBuddy task after installation and run `/iread`. Normal installation does not analyze the repository or rebuild the full WorkBuddy knowledge index.

## The three user decisions

```mermaid
flowchart LR
    A["Choose one or more fields"] --> B["Review sources and representative works"]
    B --> C["Choose light / standard / deep reports"]
    C --> D["Approve collection, backfill, and scheduling"]
```

Users do not need to prepare RSS URLs, WeChat account lists, JSON files, or cron jobs.

## Source quality

A strict proposal must cover five roles:

- **Primary sources** for original facts and records.
- **Independent reporting** for verification.
- **Specialist analysis** for mechanisms and implications.
- **Expert voices** for practical knowledge.
- **Discovery signals** for finding emerging topics, never as sole evidence.

Scores are conservative cold-start priors, not observed truth. iRead preserves conflicts of interest, collection limitations, and uncertainty. See the [source-quality strategy](docs/source-quality.md).

## Report modes

| Mode | Best for |
| --- | --- |
| `light` | Short, high-priority change detection |
| `standard` | Balanced professional monitoring; the default |
| `deep` | Research, investment, or strategy work with more evidence and longitudinal review |

New subscriptions generate local Markdown by default. Notion or public publishing requires separate explicit approval.

## Current status

`0.2.0-beta.5` is a public beta, not a stable release.

- The runtime currently targets macOS. Codex and Claude Code have deterministic local installers; Doubao Professional and WorkBuddy remain experimental adapters.
- RSS feeds can be collected automatically. Public web candidates remain disclosed as coverage gaps until a connector is available.
- WeChat collection requires local access to a WeChat Official Account administrator or operator identity. RSS/web-only mode is available without it.
- The machine must be awake and online when scheduled jobs run.

See [release readiness](docs/release-readiness.md) and [UX acceptance](docs/ux-acceptance.md) for current gates.

## Privacy and copyright

- Configuration, credentials, articles, and reports stay local by default.
- Public archives contain links, metadata, and structured analysis, not third-party full text.
- Full-text export requires confirmed republication rights or a compatible license.

The code is available under the [MIT License](LICENSE). See [NOTICE.md](NOTICE.md) and the [open-source publishing policy](docs/open-source-release.md) for third-party components and content boundaries.

## Documentation

- [Local installation and acceptance](docs/local-testing.md)
- [Product plan and user journey](docs/product-plan.md)
- [Source-quality strategy](docs/source-quality.md)
- [Daily, weekly, and monthly editorial framework](docs/report-editorial-framework.md)
- [WeChat authorization](docs/wechat-authorization.md)
- [Advanced customization](docs/customization.md)
- [Agent permissions and approval boundaries](docs/agent-control-plane.md)

## Development

```bash
scripts/test.sh
```

Use `bin/iread --help`, `bin/iread capabilities`, and `bin/iread workspace` to inspect the structured CLI and local state.

Open an [issue](https://github.com/roy-tong/iRead/issues) to report a problem or request a source map for a new research field. If iRead is useful to you, starring the repository helps other researchers discover it.
