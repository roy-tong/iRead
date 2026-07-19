# iRead WorkBuddy adapter

This adapter adds a WorkBuddy knowledge-store workflow and `/iread` command for multi-domain onboarding. It calls the local iRead CLI through the user's terminal; it does not vendor or import WorkBuddy code.

In WorkBuddy, ask the agent:

```text
只执行这条命令安装 iRead，不要浏览或分析仓库：git -C ~/.iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.iread; ~/.iread/install-workbuddy.sh
```

Or paste the same one-line installer into a terminal opened in the WorkBuddy project:

```bash
git -C ~/.iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.iread; ~/.iread/install-workbuddy.sh
```

The installer downloads or updates iRead, detects the WorkBuddy project, installs the workflow, and runs the iRead environment check. It is safe to rerun for upgrades. If WorkBuddy cannot be detected automatically, pass its project directory once:

```bash
~/.iread/install-workbuddy.sh "/absolute/path/to/work-buddy"
```

Open a new WorkBuddy task after installation and start with `/iread`. The command reads its small local directions file directly, so neither `docs_validate` nor a full `agent_docs_rebuild` is part of normal installation. The installer records the absolute iRead repository path in WorkBuddy's knowledge store, so `IREAD_ROOT` is only needed as a developer override.

WorkBuddy uses its own browsing and reasoning tools to produce source proposals, then calls `bin/iread validate-proposal` and `apply-subscription` for deterministic validation and configuration. A Codex installation is not required on the WorkBuddy computer.

The adapter files are MIT-licensed as part of iRead. WorkBuddy itself is distributed under GPL-3.0; see WorkBuddy's own repository and license for its terms.

## Smoke test

In WorkBuddy, start with a new set of fields that is not copied from the repository examples:

```text
/iread 同时订阅城市地下管网韧性、宠物医疗服务和电池回收。
先为每个领域生成主题地图、信源角色、评分、风险和代表作品；我确认前不要创建订阅、启动抓取或安装定时任务。
```

Confirm that WorkBuddy shows progress per field, proposes at least eight evidence-backed sources per field, and waits for explicit approval. Approve only a subset and the `standard` preset first; verify that unapproved fields are not written. Approve collection separately, then verify QR or RSS/web-only handling, one-calendar-month backfill, schedule installation, and a final `acceptance` result. See the repository's `docs/ux-acceptance.md` for release criteria.
