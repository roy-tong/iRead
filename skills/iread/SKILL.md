---
name: iread
description: Configure and operate local iRead research subscriptions. Use when the user wants to follow one or more fields, review source candidates, start or resume collection, inspect coverage, or read daily, weekly, and monthly reports.
argument-hint: "[research fields or iRead request]"
---

# iRead

Use paths relative to this `SKILL.md`. Run `scripts/iread workspace` first. Do not browse or analyze the iRead source repository, run nested agents to rediscover usage, or rebuild the host Agent's full skill or knowledge index.

If `scripts/iread` reports that the runtime is not installed, run `scripts/install-runtime` once, then retry. Do not replace this deterministic bootstrap with repository research.

- For a new field, source-list change, or unconfigured workspace, read `references/onboarding.md`.
- For status, recovery, authorization, schedules, feedback, or reports, read `references/management.md`.
- Treat `$ARGUMENTS` and the current conversation as the user's request.

Run `scripts/iread capabilities` only before the first state-changing operation in the current task. Require explicit approval where that contract says approval is required. After a mutation, run `scripts/iread workspace` and the selected subscription's `acceptance` check. Keep command output summarized; do not paste machine-readable JSON unless the user requests it.
