# iRead WorkBuddy adapter

This adapter adds a WorkBuddy knowledge-store workflow and `/iread` command for multi-domain onboarding. It calls the local iRead CLI through the user's terminal; it does not vendor or import WorkBuddy code.

In WorkBuddy, ask the agent:

```text
请从 https://github.com/roy-tong/iRead 安装 iRead，然后用它订阅我关注的多个研究领域。
```

Or paste the same one-line installer into a terminal opened in the WorkBuddy project:

```bash
curl -fsSL https://raw.githubusercontent.com/roy-tong/iRead/main/install-workbuddy.sh | bash
```

The installer downloads or updates iRead, detects the WorkBuddy project, installs the workflow, and runs the iRead environment check. It is safe to rerun for upgrades. If WorkBuddy cannot be detected automatically, pass its project directory once:

```bash
curl -fsSL https://raw.githubusercontent.com/roy-tong/iRead/main/install-workbuddy.sh | bash -s -- "/absolute/path/to/work-buddy"
```

The WorkBuddy agent should follow the installer's final instruction and run `docs_validate` plus `agent_docs_rebuild`; the user does not need to invoke those internal capabilities manually. Start the workflow with `/iread`. The installer records the absolute iRead repository path in WorkBuddy's knowledge store, so `IREAD_ROOT` is only needed as a developer override.

WorkBuddy uses its own browsing and reasoning tools to produce source proposals, then calls `bin/iread validate-proposal` and `apply-subscription` for deterministic validation and configuration. A Codex installation is not required on the WorkBuddy computer.

The adapter files are MIT-licensed as part of iRead. WorkBuddy itself is distributed under GPL-3.0; see WorkBuddy's own repository and license for its terms.

## Smoke test

In WorkBuddy, start with a new set of fields that is not copied from the repository examples:

```text
/iread 同时订阅城市地下管网韧性、宠物医疗服务和电池回收。
先为每个领域生成主题地图、信源角色、评分、风险和代表作品；我确认前不要创建订阅、启动抓取或安装定时任务。
```

Confirm that WorkBuddy shows progress per field, proposes at least eight evidence-backed sources per field, and waits for explicit approval. Approve only a subset and the `standard` preset first; verify that unapproved fields are not written. Approve collection separately, then verify QR or RSS/web-only handling, one-calendar-month backfill, schedule installation, and a final `acceptance` result. See the repository's `docs/ux-acceptance.md` for release criteria.
