# Apply And Activate

Read this only after the user has reviewed the generated `.review.md` artifacts and explicitly named the approved fields and report preset.

## Apply

Run `capabilities` once before the first mutation. Never use blanket approval unless every field was explicitly approved.

```bash
../../scripts/iread --request-id <apply-id> \
  apply-subscription <manifest.json> \
  --proposals-dir <batch-dir>/proposals \
  --output-dir subscriptions/<subscription-id> \
  --approved <domain-id> --preset <light|standard|deep>
```

Repeat `--approved` for multiple fields. Verify with the selected absolute config directory:

```bash
../../scripts/iread --config-dir <config-dir> subscription
../../scripts/iread workspace
```

Do not overwrite an existing subscription with `--force` without approval for that exact path.

## Start Collection

Collection and recurring reports require separate explicit consent:

```bash
../../scripts/iread --config-dir <config-dir> --request-id <activation-id> \
  activate --approved --install-schedule
```

- `needs_collector`: run `<repository-root>/scripts/setup_collection.sh`, then retry.
- `needs_auth`: show the absolute local QR path. The scan needs a WeChat Official Account administrator/operator. Never request cookies, tokens, licenses, passwords, or QR screenshots.
- After scanning, resume with `activate --wait-for-auth --install-schedule` using the same unchanged request ID.
- No eligible Official Account: offer RSS/web-only mode. Use `--skip-wechat` only after explicit consent and label it `degraded`.
- `needs_source_review`: show unresolved matches; never choose an ambiguous account automatically.
- `backfilling` or `readiness_review`: preserve progress and continue resumably.
- `active_with_gaps`: reports may run, but list every required `web_pending` source.

Inspect `operations --limit 20` before retrying an uncertain mutation. Reports remain gated until the initial one-calendar-month collection passes readiness review.

Finish with `workspace` and `acceptance`. Do not call the setup complete when required checks fail, or describe warning states as fully active. Public archives remain metadata-only unless third-party republication rights are separately confirmed.
