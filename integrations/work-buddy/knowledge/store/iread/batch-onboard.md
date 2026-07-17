---
name: iRead Multi-domain Onboarding
kind: workflow
description: Build resumable domain proposals, review source evidence, and merge explicitly approved fields into one iRead subscription.
workflow_name: iread-multi-domain-onboard
execution: main
allow_override: false
steps:
- id: prepare
  name: Resolve the repository and batch scope
  step_type: reasoning
  depends_on: []
  invokes: []
- id: propose
  name: Generate or resume domain proposals
  step_type: reasoning
  depends_on:
  - prepare
  invokes: []
- id: review
  name: Review source lists and collect explicit approvals
  step_type: reasoning
  depends_on:
  - propose
  requires_individual_consent: true
  invokes: []
- id: apply
  name: Merge approved domains
  step_type: reasoning
  depends_on:
  - review
  invokes: []
- id: verify
  name: Verify the combined subscription
  step_type: reasoning
  depends_on:
  - apply
  invokes: []
- id: activate
  name: Authorize local connectors and start collection
  step_type: reasoning
  depends_on:
  - verify
  requires_individual_consent: true
  invokes: []
- id: readiness
  name: Track initial collection readiness
  step_type: reasoning
  depends_on:
  - activate
  invokes: []
- id: report
  name: Report activation and schedule status
  step_type: reasoning
  depends_on:
  - readiness
  invokes: []
tags:
- iread
- research
- sources
- batch
- onboarding
parents: []
---

## prepare

Resolve the iRead repository, input fields, and an isolated batch directory. Create or validate the batch manifest without starting collection.

## propose

Use WorkBuddy's research tools to create and validate one schema-compliant proposal artifact per domain. A local Codex CLI is optional. Surface failures without discarding completed proposals.

## review

Show source roles, direct URLs, representative works, warnings, conflicts, and report presets. Obtain explicit approved domain ids; silence is not approval.

## apply

Run `apply-subscription` only for the domain ids approved in the review result. Combine them into one subscription and do not use blanket approval unless the user explicitly approved every proposed domain.

## verify

Load the combined subscription through the CLI and verify that its domain map, taxonomy, sources, and report policy resolve.

## activate

After explicit consent, prepare We-MP-RSS, show the local authorization QR when required, match approved sources, and start the one-calendar-month backfill. Offer an explicit RSS/web-only degraded mode when the user has no eligible Official Account access.

## readiness

Persist and report `needs_auth`, `needs_source_review`, `backfilling`, `readiness_review`, `active`, `active_with_gaps`, or `degraded`. Use `active_with_gaps` when required `web_pending` candidates are not connected, and list those source IDs. Install recurring collection and report schedules only after the user approved activation.

## report

Summarize subscribed and skipped domains, authorization status, backfill progress, readiness, schedule installation, and unresolved sources.
