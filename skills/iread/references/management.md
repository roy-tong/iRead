# Manage iRead

Use the subscription selected by the user, otherwise the workspace's active schedule or recommended configuration. Always pass its absolute `--config-dir`; never silently fall back to the repository example.

## Read Operations

- Use `workspace` for compact status and `activation` or `audit` only when more detail is needed.
- Use `reports --kind <daily|weekly|monthly> --limit 5` to find existing reports. Read the newest existing Markdown file; do not regenerate it merely because the user asks to open it.
- Explain missing reports by the actual gate: collection readiness, pending analysis, schedule, or coverage gaps.

## Recovery And Mutations

Read `capabilities` before the first mutation. Use a stable `--request-id` before the subcommand and reuse it for retries of unchanged intent. Inspect `operations --limit 20` before retrying an uncertain result.

Require explicit approval before first collection, schedule changes, source or field changes, forced report generation, external publication, third-party full-text export, or schedule removal.

- `needs_collector`: run the repository's `scripts/setup_collection.sh` only after collection approval.
- `needs_auth`: show the local QR and resume with `activate --wait-for-auth --install-schedule`.
- `backfilling` or `readiness_review`: continue one resumable collection step when requested.
- `active_with_gaps`: list every required pending source; do not call coverage complete.
- `degraded`: state that WeChat was explicitly skipped.
- `pipeline_busy`: do not start a duplicate run.

Record actionable user evaluation with `feedback add`. After mutations, rerun `workspace` and `acceptance`; report persisted status, warnings, gaps, and the next user decision.
