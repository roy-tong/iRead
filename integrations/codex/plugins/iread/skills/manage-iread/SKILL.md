---
name: manage-iread
description: Inspect, read, resume, or troubleshoot existing local iRead subscriptions and reports.
---

# Manage iRead

Use `../../scripts/iread` relative to this file. Run only `workspace` first. Do not run Doctor, inspect the repository, or rebuild indexes.

Select the subscription explicitly named by the user, otherwise the active schedule, otherwise `recommended_config_dir`. If multiple choices remain, show name, domains, and status, then ask. Use the selected absolute `--config-dir` for every command.

- For status, coverage, or reading an existing daily/weekly/monthly report, read `references/status-and-reports.md`.
- For recovery, authorization, collection, schedules, feedback, source changes, report generation, or publication, read `references/recovery-and-mutations.md`.

Run `capabilities` once immediately before the first mutation, never for a read-only request. Use a stable request ID for unchanged intent and inspect `operations --limit 20` before retrying uncertain work. Respect explicit approval boundaries.

After a mutation, rerun `workspace` and `acceptance`. Report persisted status, warnings, required gaps, and the next user decision. Never summarize `active_with_gaps`, `degraded`, `active_unverified`, or failed acceptance as fully complete.
