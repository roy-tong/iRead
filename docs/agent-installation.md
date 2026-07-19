# iRead Agent 安装指南

## 统一原则

安装是确定性系统操作，不是研究任务。Agent 安装 iRead 时必须：

- 只执行指定 Shell 命令，不浏览、摘要或分析仓库；
- 不启动子 Agent，不重建全量知识库或向量索引；
- 安装 Doctor 只输出一行摘要，失败时才列出失败项；
- 安装后正常使用只先调用一次 `workspace`，发生写操作前才读取 `capabilities`。

## Codex

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/scripts/install.sh codex
```

新建 Codex 任务后直接说“用 iRead 订阅……”。插件通过本地 marketplace 注册，不需要 Agent 读取仓库安装说明。

## Claude Code

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/scripts/install.sh claude-code
```

Skill 安装到 `~/.claude/skills/iread`。如果当前会话启动时 `~/.claude/skills` 尚不存在，重启一次 Claude Code；否则可直接输入 `/iread`。

## 豆包专业版

办公任务模式允许操作本地电脑时，可执行：

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/scripts/install.sh doubao
```

安装器将开放 Skill 写入 `~/.agents/skills/iread`。如果当前豆包版本未自动发现该通用目录，在“自定义 Skill”中导入仓库 [`dist/`](../dist/) 目录的 `iread-agent-skill-<version>.zip`。由于豆包尚未公开稳定 CLI 安装规范，这一入口在 Beta 5 中保持实验性。

## WorkBuddy

```bash
git -C ~/.local/share/iread pull --ff-only 2>/dev/null || git clone --depth 1 https://github.com/roy-tong/iRead.git ~/.local/share/iread; ~/.local/share/iread/install-workbuddy.sh
```

安装后新建任务并输入 `/iread`。正常安装不运行 `docs_validate` 或 `agent_docs_rebuild`。

## 性能验收

不含 GitHub 首次下载时间，本地安装目标为 10 秒以内；安装标准输出小于 1 KB。安装阶段不应产生仓库分析、多 Agent 调用或全量索引的 Token 消耗。
