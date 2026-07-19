---
name: manage-iread
description: Inspect, resume, troubleshoot, and operate existing local iRead subscriptions in Codex. Use when a user asks what iRead is doing, wants to continue an incomplete setup, check collection or schedule health, understand coverage gaps, find or read a daily/weekly/monthly report, generate a due report, or recover a local iRead workflow.
---

# Manage iRead

Use the plugin wrapper at `../../scripts/iread`. Resolve all returned paths to absolute paths before invoking commands or linking files.

## Start With State

1. Run `../../scripts/iread capabilities` and honor its permission, approval, side-effect, and idempotency contract.
2. Run `../../scripts/iread doctor --surface codex`.
3. Run `../../scripts/iread workspace` before inspecting files or choosing a subscription.
4. Select a subscription using an explicit user choice first, then `active_schedule`, then `recommended_config_dir`. If multiple subscriptions remain plausible, show their names, domains, status, and config paths and ask which one to use.
5. If the user gives an unregistered configuration directory, run:

   ```bash
   ../../scripts/iread --config-dir <absolute-config-dir> workspace --register
   ```

6. Use the selected absolute `config_dir` in every subsequent command. Never silently fall back to repository `config/` after selecting a subscription.

## Execute Mutations

For every state-changing command, create one stable request ID for the unchanged user intent. Put the global option before the subcommand:

```bash
../../scripts/iread --config-dir <config-dir> \
  --request-id <stable-request-id> \
  <mutation> <arguments>
```

Reuse that request ID for retries after timeouts or task interruption. Use a new ID if the target, arguments, approval scope, or intended outcome changes. If a mutation fails or returns an uncertain result, inspect `operations --limit 20` before retrying. Do not use `--force` as generic recovery.

## Read And Explain

- For current state, report subscription name, domains, source counts, status, article count, pending analysis count, report count, schedule state, and required coverage gaps. Translate statuses into plain language without hiding warnings.
- For reports, run:

  ```bash
  ../../scripts/iread --config-dir <config-dir> reports --kind <kind> --limit 5
  ```

  Omit `--kind` when the user asks for the latest report of any type. Prefer the newest record whose `exists` value is true. Read the Markdown file, return a clickable absolute file link, and answer from its contents. Do not regenerate a report merely because the user asks to read it.
- If no report exists, explain whether collection is not ready, analysis remains pending, or the report is not due. Only offer generation after identifying the actual gate.
- Run `activation` for full recovery details and `audit` for complete source warnings when the compact workspace result is insufficient.

## Resume And Recover

Use `next_actions` as diagnostics, not blanket permission. Execute an action without another question only when the user's current request already authorizes that class of action and `requires_confirmation` is false.

- `configured` or `not_started`: summarize approved sources and report policy, then ask before starting collection.
- `needs_collector`: after collection was already approved, run `<repo>/scripts/setup_collection.sh` and retry activation.
- `needs_auth` or `auth_timeout`: render the absolute local QR image, wait for the user to scan, then run `activate --wait-for-auth --install-schedule` with the activation request ID. If prior state does not contain schedule approval, ask and add `--approved`. Never request cookies, tokens, `wx.lic`, or QR screenshots.
- `needs_source_review`: show unresolved or ambiguous sources. Never choose an uncertain account automatically.
- `backfilling` or `readiness_review`: run one resumable `collect` step when the user asked to continue, then show updated workspace state.
- `active_with_gaps`: reports can run, but list every required pending external source ID and use `audit` before describing coverage as complete.
- `degraded`: state that WeChat collection was explicitly skipped. Use `activate --approved --enable-wechat` only when the user asks to add it later.
- `active_unverified`: this is an older scheduled configuration without persisted activation state. Run `audit`; do not repeat initial activation automatically.
- `pipeline_busy`: explain that another scheduled or interactive run holds the lock. Do not start duplicate work.

## Approval Boundaries

Require explicit approval before:

- starting first collection or installing/replacing a schedule;
- switching the active scheduled subscription;
- adding, removing, or changing sources or domains;
- forcing report regeneration;
- publishing to Notion or any public destination;
- exporting third-party full text.
- removing recurring tasks.

Reading status, audits, existing local reports, and logs is safe. A request such as "continue the backfill" or "fix the collector" is sufficient approval for that named recovery step, but not for unrelated schedule, source, or publication changes.

When the user asks to stop automatic execution, run `schedule status`, confirm the selected subscription, then use `schedule uninstall --approved` with a request ID. Explain that local data and reports are preserved.

## Learn From Feedback

When the user evaluates a report, source, or subscription, record the actionable preference instead of only acknowledging it. Use `feedback add` with a request ID, a target, rating, optional target ID, and a concise note. Use `feedback list` when checking whether a preference was already captured. Never treat feedback as factual evidence.

## Completion

After any state-changing command, rerun `workspace` and `acceptance`. Report persisted status, whether required acceptance checks passed, concrete remaining gaps, and the next user decision. Never summarize `active_with_gaps`, `degraded`, `active_unverified`, or `accepted_with_warnings` as fully complete.
