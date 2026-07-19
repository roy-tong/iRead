---
name: onboard-research-domains
description: Configure one iRead subscription from one or more industry or research-field keywords. Use when a user wants Codex to discover and verify source candidates, show representative works for review, configure daily/weekly/monthly report policies, or combine multiple approved research domains through the local iRead CLI.
---

# Configure iRead Domains

Use the plugin wrapper at `../../scripts/iread`. Resolve paths to absolute paths before invoking it. Source approval is also consent to start local collection and install the selected report schedule only when the user explicitly says so.

## Workflow

1. Locate and check iRead. Run `../../scripts/iread capabilities`, `../../scripts/iread doctor --surface codex`, and `../../scripts/iread workspace` from this skill directory. Honor the returned approval and idempotency contract. The installer records the repository root; if the wrapper still cannot find it, set `IREAD_ROOT` to its absolute path. If an existing subscription has the requested domains or an incomplete activation, show it and ask whether to resume it before creating a duplicate.
2. Collect one or more research fields. Accept a pasted list, CSV/JSON file, or fields already stated in the conversation. Ask only for missing distinctions that would materially change the sources, such as geography or audience.
3. Tell the user what will happen next in plain language: iRead will expand each field, research candidate sources and representative works, then stop for review. Give a short progress update before researching each domain.
4. Create a JSON batch manifest. Read [references/batch-manifest.md](references/batch-manifest.md) for the schema and defaults. Store working artifacts under `data/onboarding/<batch-id>/` unless the user names another location.
5. Author each proposal in the current Codex task instead of invoking another Codex process. Read [references/proposal-authoring.md](references/proposal-authoring.md), `<repository_root>/prompts/propose.md`, and the JSON Schema path returned by `capabilities`. Use current web-search tools to verify direct source pages, feeds, identities, and representative works. Write one proposal to `<batch-dir>/proposals/<domain-id>.json`, then run:

   ```bash
   ../../scripts/iread validate-proposal <proposal.json>
   ```

   Fix validation errors before continuing. This current-task path is required because starting nested `iread batch-propose` Codex jobs is slow, consumes a second quota, and cannot provide useful progress. Use `batch-propose` only as an explicitly disclosed fallback when the current surface has no web research capability.
6. Review every generated proposal before applying it. Start with a compact domain-level summary, then show the source table. For each domain, report:
   - field and generated domain name;
   - topic coverage and known gaps;
   - source counts by role;
   - source name, homepage, capture method, conflict note, warnings, and preliminary score;
   - two or three representative works with direct URLs.
   Run `../../scripts/iread validate-proposal <proposal.json>` first and fix validation errors before review.
7. End the review with exact reply examples so a non-technical user knows what to do, such as `批准全部领域，使用标准报告，开始采集` or `删除 <信源名>，其余批准，先不启动采集`. Ask the user to approve domain IDs, one shared `light`, `standard`, or `deep` policy, and whether approval should start local collection plus recurring reports. Explain that WeChat sources require one local QR scan and that metadata-only public archives are generated without third-party full text. Never infer approval from silence and never use `--approve-all` unless the user explicitly approves all domains.
8. Merge only approved domains into one subscription:

   ```bash
   ../../scripts/iread --request-id <apply-request-id> \
     apply-subscription <manifest.json> \
     --proposals-dir <batch-dir>/proposals \
     --output-dir subscriptions/<subscription-id> \
     --approved <domain-id>
   ```

   Repeat `--approved` for multiple IDs.
9. Verify the combined subscription with:

   ```bash
   ../../scripts/iread --config-dir subscriptions/<subscription-id> subscription
   ```

   `apply-subscription` registers the configuration for discovery in future Codex tasks. Confirm it appears in `../../scripts/iread workspace` before continuing.

10. If the user approved activation, run:

   ```bash
   ../../scripts/iread --config-dir subscriptions/<subscription-id> \
     --request-id <activation-request-id> activate \
     --approved --install-schedule
   ```

   - On `needs_collector`, run `<repo>/scripts/setup_collection.sh` and retry.
   - On `needs_auth`, render the absolute `auth.qr_image` path in the conversation, explain that the scan must use a WeChat account authorized as an administrator or operator of a WeChat Official Account, and wait for the user to scan. Then run `activate --wait-for-auth --install-schedule`; the initial approved command has already persisted collection and schedule consent.
   - If the user has no eligible Official Account access, offer RSS/web-only mode. Use `activate --approved --skip-wechat --install-schedule` only after explicit confirmation and label the result `degraded`.
   - If a user in degraded mode later gains eligible access, use `activate --approved --enable-wechat` to restart the QR authorization flow.
   - On `needs_source_review`, show unresolved matches and edit or remove only those sources before retrying. Never choose an ambiguous account automatically.
11. Verify resumable progress with `../../scripts/iread --config-dir <config-dir> activation`. After every long step, state the completed stage, elapsed result when available, and the next gate. Inspect `operations --limit 20` before retrying an uncertain mutation, and reuse the same request ID only for the unchanged intent. Reports remain gated until the initial one-calendar-month collection passes readiness review. `web_pending` sources remain candidates rather than active feeds. If any required candidate is still pending, report `active_with_gaps` and list its ID; never summarize that state as fully `active`.
12. Run `../../scripts/iread --config-dir <config-dir> acceptance` before declaring setup complete. `accepted_with_warnings` must be explained with its remaining warnings.

## Guardrails

- Treat proposal scores as cold-start priors, not observed quality.
- Preserve warnings and conflict notes when applying configurations.
- Prefer first-party sources for facts, independent reporting for verification, specialist analysis for interpretation, expert voices for practice, and discovery sources only for leads.
- Do not claim that representative works, RSS endpoints, licensing, or full-text rights are verified when the proposal marks them uncertain.
- Do not export or publish third-party full text without confirmed rights.
- Never ask users to send WeChat cookies, `wx.lic`, tokens, passwords, or QR screenshots. Authorization remains on their machine.
- Do not advise maintainers to add unrelated users as operators of a shared Official Account. Use local authorization or explicit RSS/web-only mode.
- Keep the generated `runtime.json` isolation. All approved domains in one subscription intentionally share one database and one report stream; separate subscriptions must still use separate runtime paths.
- Do not overwrite or replace a registered subscription with `--force` unless the user explicitly approves that exact configuration path.
