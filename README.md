# iRead: AI Research Radar & Source Discovery

**Local-first AI research assistant for source discovery, RSS and WeChat collection, and daily, weekly, and monthly research digests.**

[简体中文](#iread-是什么) | [English](README.en.md) | [Quick Start](#两分钟开始) | [Documentation](#文档) | [Contributing](CONTRIBUTING.md)

![Version](https://img.shields.io/badge/version-0.2.0--beta.6-orange)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Interface](https://img.shields.io/badge/interface-Agent%20Skills-111111)
![License](https://img.shields.io/badge/license-MIT-blue)

## iRead 是什么

iRead 是一个开源、本地优先的 **AI 研究助手 / 个人信息雷达**。你只需要说出关心的行业或研究领域，iRead 会：

1. 展开领域与子主题。
2. 找出官方机构、专业媒体、研究者、从业者和弱信号来源。
3. 展示每个信源的代表作、评分、风险和采集方式，等你确认。
4. 采集 RSS、公开网页和已授权的微信公众号。
5. 去重、评估证据质量，生成日报、周报和月报。

**适合：** 需要长期跟踪专业领域，但不想自己整理 RSS、公众号和信源评分的研究者、投资人、产品经理、行业从业者和学生。

## 它和普通 RSS / AI 摘要工具有什么不同

| 普通工具 | iRead |
| --- | --- |
| 需要用户自己找 RSS 和作者 | 只输入研究领域，自动生成待审核信源清单 |
| 通常对单篇文章做摘要 | 按事件去重，追踪跨源共识、分歧和趋势变化 |
| 媒体、官方和个人观点混在一起 | 区分一手证据、独立核验、专业分析、专家经验和发现线索 |
| 关注“今天发了什么” | 日报看新增，周报看演化，月报看结构性变化和预测回看 |
| 默认上传到云端 | 配置、文章和报告默认保存在本机 |

## 两分钟开始

### 1. 准备环境

- macOS
- Codex、Claude Code、豆包专业版办公任务模式或 WorkBuddy 之一
- Python 3.9+
- Git

### 2. 一行安装

```bash
set -o pipefail; curl -fsSL https://cdn.jsdelivr.net/gh/roy-tong/iRead@main/install | bash -s -- codex
```

上面是 Codex 命令。Claude Code 将末尾的 `codex` 换成 `claude-code`，豆包专业版换成 `doubao`，WorkBuddy 换成 `workbuddy`。安装只执行确定性脚本，不需要 Agent 分析仓库或重建全量索引。不希望使用 `curl | bash` 时，见 [Agent 安装指南](docs/agent-installation.md) 中的 Git 备用命令。

### 3. 用一句话建立订阅

```text
用 iRead 同时订阅医疗器械监管、新能源电力市场和独立游戏发行。
先推荐信源和代表作，我确认前不要启动采集。
```

Codex 会先显示领域地图、候选信源、代表作和报告方案。只有在你明确批准后，iRead 才会创建订阅、回补最近一个自然月的数据并安装定时任务。

### WorkBuddy 一行安装（实验性）

在 WorkBuddy 中发送一句话：

```text
只执行这条命令安装 iRead，不要分析仓库：set -o pipefail; curl -fsSL https://cdn.jsdelivr.net/gh/roy-tong/iRead@main/install | bash -s -- workbuddy
```

WorkBuddy 只需执行一次确定性脚本，不需要读取仓库内容。终端备用命令为：

```bash
set -o pipefail; curl -fsSL https://cdn.jsdelivr.net/gh/roy-tong/iRead@main/install | bash -s -- workbuddy
```

安装器会自动更新 iRead、定位 WorkBuddy、安装工作流并自检。完成后新建一个 WorkBuddy 任务，直接输入 `/iread`。不再执行全量知识库检测或重建。

## 用户只需要做的三个决策

```mermaid
flowchart LR
    A["输入一个或多个领域"] --> B["检查信源和代表作"]
    B --> C["选择轻量 / 标准 / 深度报告"]
    C --> D["批准后采集、回补和定时生成"]
```

你不需要自己准备 RSS 地址、公众号清单、JSON 或定时任务。

## 信源是怎么选的

每个领域的严格提案必须覆盖五种角色：

- **一手来源**：政府、监管机构、标准组织、公司原始发布。
- **独立报道**：用于交叉核验事实。
- **专业分析**：用于理解行业机制和影响。
- **专家与从业者**：用于获取实践经验和非公式知识。
- **发现信号**：用于发现新话题，不直接当作事实证据。

冷启动评分只是候选排序，iRead 会保留利益冲突、抓取限制和不确定性，不会把“官方”等同于“所有主张都可信”。详见 [信源质量方法](docs/source-quality.md)。

## 报告策略

| 模式 | 适合 | 阅读负担 |
| --- | --- | --- |
| `light` 轻量 | 只想知道关键变化 | 最短，只保留高优先级项 |
| `standard` 标准 | 长期专业跟踪 | 默认选择，平衡覆盖和时间 |
| `deep` 深度 | 研究、投资或战略分析 | 更多证据、分歧和跨期回看 |

所有新订阅默认只生成本地 Markdown；Notion 和公开发布都需要额外明确批准。

## 支持的能力

- 任意多领域合并成一个订阅。
- RSS / Atom、公开网页候选源和已授权微信公众号。
- 近一个自然月的历史回补。
- 本地 SQLite 归档、去重、完整性审计和可恢复任务。
- 日报、周报、月报和本地文章阅读库。
- Codex 自然语言配置、状态检查、故障恢复和报告阅读。
- 明确审批边界、幂等请求和本地操作日志。

## Beta 状态与限制

`0.2.0-beta.6` 用于公开测试，**还不是稳定版**。

- 当前运行时优先支持 macOS。Codex 和 Claude Code 有确定性本地安装；豆包专业版和 WorkBuddy 适配仍属实验性。
- 只有 RSS 和已完成授权的微信源会自动采集；`web_pending` 会被持续披露为覆盖缺口。
- 微信公众号采集需要用户自己拥有某个公众号的管理员或运营者权限；否则可选择 RSS/网页源模式。
- 本机需要在定时任务运行时开机并联网。

当前验收结果和稳定版门槛见 [发版就绪状态](docs/release-readiness.md) 和 [用户体验验收](docs/ux-acceptance.md)。

## 数据、隐私与版权

- 配置、凭据、文章和报告默认留在本机。
- 公开归档默认只包含链接、元数据和结构化分析，不上传第三方全文。
- 只有确认拥有转载权或兼容许可证时，才能导出第三方全文。

代码使用 [MIT License](LICENSE)。第三方组件、信源和内容权利边界见 [NOTICE.md](NOTICE.md) 和 [开源发布说明](docs/open-source-release.md)。

## 文档

| 我想要…… | 阅读 |
| --- | --- |
| 安装并走完一次测试 | [本地安装与验收](docs/local-testing.md) |
| 在 Codex、Claude Code、豆包或 WorkBuddy 安装 | [Agent 安装指南](docs/agent-installation.md) |
| 查看第三方体验、性能和发版判断 | [Beta 6 体验基准](docs/ux-benchmark-beta6.md) |
| 了解产品逻辑和用户流程 | [产品方案](docs/product-plan.md) |
| 理解信源评级 | [信源质量策略](docs/source-quality.md) |
| 理解日报、周报和月报 | [报告编辑框架](docs/report-editorial-framework.md) |
| 配置微信授权 | [微信授权说明](docs/wechat-authorization.md) |
| 手工配置或使用 CLI | [高级定制](docs/customization.md) |
| 了解 Agent 权限和审批边界 | [Agent 控制面](docs/agent-control-plane.md) |
| 查看一套真实运行的 AI 与具身研究案例 | [AI 与具身研究标杆案例](examples/ai-embodied-research/README.md) |
| 贡献代码、信源或订阅领域 | [贡献指南](CONTRIBUTING.md) |

## 开发与验证

```bash
scripts/test.sh
```

开发者和 Agent 可以使用 `bin/iread --help`、`bin/iread capabilities` 和 `bin/iread workspace` 查看结构化能力与本地状态。

## 参与项目

- 发现问题：提交 [GitHub Issue](https://github.com/roy-tong/iRead/issues)。
- 想订阅新领域：Issue 中只需要写下领域名称和关注范围。
- 想贡献信源或代码：阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

If iRead is useful to you, starring the repository helps other researchers discover it.
