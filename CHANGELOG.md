# Changelog

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
