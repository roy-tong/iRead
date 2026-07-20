# Status And Reports

Use `workspace` for the compact state. Report subscription name, domains, source count, activation status, article count, pending analysis, reports, schedule, required gaps, and the first useful next action. Use `activation` or `audit` only when compact state is insufficient.

If the user gives an unregistered config directory, register it explicitly:

```bash
../../scripts/iread --config-dir <absolute-config-dir> workspace --register
```

For reports:

```bash
../../scripts/iread --config-dir <config-dir> reports --kind <kind> --limit 5
```

Omit `--kind` for the latest report of any type. Read the newest record with `exists: true`, link its absolute Markdown path, and answer from its contents. Do not regenerate a report merely because the user asks to read it.

If no report exists, explain the real gate: initial collection readiness, eligible analysis still pending, schedule not due, or generation failure. Do not hide `web_pending` coverage gaps or call propagation frequency independent evidence.
