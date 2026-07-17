---
name: iRead Multi-domain Onboarding Directions
kind: directions
description: How to turn several research-field keywords into one reviewed iRead subscription while preserving an explicit approval boundary.
summary: Generate resumable domain proposals, review source roles and representative works, then merge only approved domains into one subscription.
trigger: user asks WorkBuddy to configure one or more research fields, industries, authors, source lists, or report strategies in iRead
command: iread
workflow: iread/multi-domain-onboard
tags:
- iread
- research
- sources
- approval
- directions
aliases:
- configure research sources
- batch research onboarding
- build industry source lists
parents: []
---

Follow the `iread-multi-domain-onboard` workflow. Use the user's terminal tool for iRead commands; these steps are intentionally agent-mediated because they involve web research, file changes, and user consent.

## Repository resolution

Read `iread/repository-root.txt` from the WorkBuddy knowledge store first. Use `IREAD_ROOT` when set as an explicit override. Otherwise locate a repository containing executable `bin/iread` and `schemas/research_proposal.schema.json`. Refuse to guess between multiple repositories.

Use this command form:

```bash
"$IREAD_ROOT/bin/iread" <arguments>
```

If the environment variable is absent, substitute the resolved absolute root directly.

## Manifest

Accept research fields from the conversation, a pasted list, or a JSON file. Create this shape under an isolated `data/onboarding/<batch-id>/` directory:

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
    {"id": "example-field", "field": "Example field"}
  ]
}
```

Ask only about missing distinctions that materially alter source selection. Do not force a user to enumerate sources or authors.

## Build proposals with WorkBuddy

Use WorkBuddy's own research and browsing tools to build one proposal for every manifest domain. The product supports arbitrary domains; do not reuse the repository's maintainer profile, topic taxonomy, or source list unless they are independently relevant to the user's request.

Write each result to `<batch-dir>/proposals/<domain-id>.json`. Follow `schemas/research_proposal.schema.json` and add `batch_profile_id` at the top level with the exact manifest domain id. Every strict proposal needs at least three topics, eight sources, two direct representative-work URLs per source, all five cold-start score dimensions, and exactly the `light`, `standard`, and `deep` report presets.

Prefer primary sources for facts, independent reporting for verification, specialist analysis for interpretation, expert voices for practice, and discovery sources only for leads. Verify URLs with browsing. Preserve uncertainty in `warnings`, `known_gaps`, `score_confidence`, and `conflict_note` rather than inventing certainty.

Validate every proposal before showing it to the user:

```bash
bin/iread validate-proposal <batch-dir>/proposals/<domain-id>.json
```

Fix validation failures before review. Preserve successful proposal artifacts if one domain fails and report the failed id. `bin/iread batch-propose` is an optional Codex-backed shortcut when a working Codex CLI is available; it is not required for WorkBuddy operation.

## Review gate

Before applying anything, summarize each proposal with:

- domain id, field, generated name, topic count, and known gaps;
- source count by `primary_source`, `expert_voice`, `independent_reporting`, `specialist_analysis`, and `discovery_signal`;
- source name, role, homepage, feed or capture method, conflict note, warnings, and cold-start composite score;
- two or three representative works with direct URLs;
- `light`, `standard`, and `deep` report-policy differences.

Call out missing role coverage, unverified feeds, `web_pending` candidates, and weak representative-work evidence. Treat preliminary scores as priors rather than observed quality.

Ask the user for the exact domain ids to approve, one shared `light`, `standard`, or `deep` preset, and whether approval should start local collection plus recurring reports. Explain that WeChat sources require a local QR scan. Treat existing manifest presets as proposed defaults, not consent; update the manifest with the confirmed choice before apply. Do not infer approval from a general positive response. Do not use `--approve-all` unless the user explicitly approves every domain.

## Apply and verify

Merge approved ids into one subscription:

```bash
bin/iread apply-subscription <manifest.json> \
  --proposals-dir <batch-dir>/proposals \
  --output-dir subscriptions/<subscription-id> \
  --approved <domain-id>
```

Repeat `--approved` for multiple ids. Then verify the combined configuration:

```bash
bin/iread --config-dir subscriptions/<subscription-id> subscription
```

## Activate approved collection

When the user approved collection, run `bin/iread --config-dir <config-dir> activate`.

- On `needs_collector`, run `scripts/setup_collection.sh`, then retry.
- On `needs_auth`, show the local `auth.qr_image` to the user. The scan must use a WeChat account authorized as an administrator or operator of an Official Account. After scanning, run `activate --wait-for-auth --install-schedule`.
- If the user has no eligible Official Account access, offer RSS/web-only mode and run `activate --skip-wechat --install-schedule` only after explicit confirmation. Mark the subscription degraded and list skipped WeChat sources.
- If the user later gains eligible access, run `activate --enable-wechat` to restart QR authorization.
- On `needs_source_review`, show unresolved matches and correct or remove those sources before retrying.

Use `bin/iread --config-dir <config-dir> activation` for resumable status. Reports remain gated until the initial one-calendar-month collection passes readiness review. Required `web_pending` candidates must produce `active_with_gaps` with their IDs rather than a fully active claim. Metadata-only public archives may be scheduled; never export third-party full text without separately confirmed rights. Never request or transfer WeChat cookies, tokens, passwords, `wx.lic`, or QR screenshots.
