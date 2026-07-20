# Recovery And Mutations

Read `capabilities` before the first mutation. Put a stable request ID before the subcommand and reuse it only for unchanged intent:

```bash
../../scripts/iread --config-dir <config-dir> --request-id <stable-id> <command>
```

Require explicit approval before first collection, schedules, source/domain changes, forced report generation, external publication, full-text export, or schedule removal. A request to continue one named recovery step authorizes that step, not unrelated changes.

- `configured`: summarize sources and policy, then ask before activation.
- `needs_collector`: after collection approval, run `<repo>/scripts/setup_collection.sh`.
- `needs_auth`: show the local QR, wait for scan, then resume activation. Never request credentials or QR screenshots.
- `backfilling` / `readiness_review`: run one resumable `collect` step when requested.
- `active_with_gaps`: reports can run; list all required pending external sources.
- `degraded`: state that WeChat was explicitly skipped.
- `active_unverified`: run `audit`; do not repeat activation automatically.
- `pipeline_busy`: do not start duplicate work.

Use `schedule status` before `schedule uninstall --approved`. Local data remains. Record actionable user evaluations with `feedback add`; feedback guides editing but is not factual evidence.

After every mutation, run `workspace` and `acceptance`. Explain every failed or warning check.
