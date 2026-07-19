# Changelog

## 0.2.0-beta.4 - 2026-07-19

- Reworked first-run guidance around the three user decisions: research fields, source approval, and report depth.
- Prevented a clean installation from presenting the maintainer's repository configuration as the user's active subscription.
- Made the Codex onboarding skill research and author proposals in the current task instead of launching a slow, quota-consuming nested Codex process.
- Added concise installation progress, missing `CODEX_HOME` preparation, and actionable partial-failure recovery messages.
- Required strict proposals to cover first-party evidence, expert voices, independent reporting, specialist analysis, and discovery signals.
- Removed default Python tracebacks from expected CLI failures while preserving structured errors and opt-in verbose diagnostics.

## 0.2.0-beta.3 - 2026-07-19

- Added `iread workspace` to discover local subscriptions and expose compact activation, schedule, article, analysis, report, and next-action state for Codex.
- Added `iread reports` for stable daily, weekly, and monthly report discovery.
- Added the `manage-iread` Codex skill for recovery, diagnostics, coverage gaps, and local report reading.
- Registered newly applied subscriptions under `~/.config/iread/subscriptions.json` so new Codex tasks can resume them without path prompts.
- Added legacy scheduled-configuration detection to avoid repeating activation when older installations already contain articles or reports.
- Added a machine-readable Agent capability and permission contract plus schema-backed outcome acceptance.
- Added request-ID idempotency, per-subscription operation journals, stable error codes, and structured recovery state for mutations.
- Added explicit activation and scheduling approval enforcement, local-only default report delivery for generated subscriptions, and reversible schedule removal that preserves local data.
- Added report, source, and subscription feedback that is included as editorial preference context in later reports.
- Documented the Headless execution, Agent control, and human supervision architecture for the Codex-first formal release path.

## 0.2.0-beta.2 - 2026-07-17

- Added post-approval activation with local WeChat QR authorization and resumable state.
- Added one-calendar-month backfill, source matching, readiness gates, and recurring schedules.
- Added explicit RSS/web-only degraded mode and a path to re-enable WeChat later.
- Added daily metadata-only public archive generation without automatic GitHub pushes.
- Hardened local runtime credential preparation and macOS/Linux collector setup.
- Added `active_with_gaps` and audit warnings for required web candidates that are not yet collected.
- Made overlapping scheduled pipeline runs exit as an explicit non-failing skip after the lock timeout.

## 0.2.0-beta.1 - 2026-07-16

- Renamed the product to iRead and added a domain-agnostic multi-domain subscription model.
- Added Codex marketplace installation, repository discovery, and natural-language onboarding.
- Added a WorkBuddy adapter that can research proposals without a local Codex dependency.
- Added strict proposal validation, explicit approval gates, source deduplication, and isolated generated configurations.
- Added generic daily, weekly, and monthly strategy presets plus source-quality and representative-work review.
- Added `doctor`, one-command installers, local acceptance tests, disclosure documents, and public-export safeguards.
