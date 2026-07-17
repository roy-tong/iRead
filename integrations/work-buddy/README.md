# iRead WorkBuddy adapter

This adapter adds a WorkBuddy knowledge-store workflow and `/iread` command for multi-domain onboarding. It calls the local iRead CLI through the user's terminal; it does not vendor or import WorkBuddy code.

Install into a WorkBuddy source tree:

```bash
scripts/install.sh workbuddy /absolute/path/to/work-buddy
```

Then run WorkBuddy's `docs_validate` and `agent_docs_rebuild` capabilities and start the workflow with `/iread`. The installer records the absolute iRead repository path in WorkBuddy's knowledge store, so `IREAD_ROOT` is only needed as an override.

WorkBuddy uses its own browsing and reasoning tools to produce source proposals, then calls `bin/iread validate-proposal` and `apply-subscription` for deterministic validation and configuration. A Codex installation is not required on the WorkBuddy computer.

The adapter files are MIT-licensed as part of iRead. WorkBuddy itself is distributed under GPL-3.0; see WorkBuddy's own repository and license for its terms.
