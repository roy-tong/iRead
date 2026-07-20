# iRead：说出领域，得到可信的研究日报

**开源、本地优先的 AI 研究助手。自动发现高质量信源，采集 RSS 与已授权公众号，并生成日报、周报和月报。**

[English](README.en.md) | [真实案例](examples/ai-embodied-research/README.md) | [安装说明](docs/agent-installation.md) | [提需求](https://github.com/roy-tong/iRead/issues/new?template=research-profile.yml)

![Version](https://img.shields.io/badge/version-0.2.0--beta.6-orange)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Interface](https://img.shields.io/badge/interface-Codex%20%7C%20Claude%20Code-111111)
![License](https://img.shields.io/badge/license-MIT-blue)

你不需要先整理 RSS、作者或公众号。只要告诉 iRead 你关注什么，它会先给出**信源、代表作、评分和风险**供你检查；得到批准后才开始采集。

## 60 秒开始

要求：macOS、Python 3.9+，以及 Codex 或 Claude Code。安装器实测约 5 秒完成全新安装。

### 1. 一行安装

Codex：

```bash
set -o pipefail; curl -fsSL https://cdn.jsdelivr.net/gh/roy-tong/iRead@main/install | bash -s -- codex
```

Claude Code 只需把最后的 `codex` 换成 `claude-code`。豆包专业版和 WorkBuddy 适配仍处于实验阶段。

### 2. 新建 Agent 任务，说出领域

```text
用 iRead 同时订阅医疗器械监管、新能源电力市场和独立游戏发行。
先推荐信源和代表作，我确认前不要启动采集。
```

### 3. 检查并批准

iRead 会按领域展示候选信源及代表作。你可以删除、替换或补充信源，再选择 `light`、`standard` 或 `deep` 报告。批准后，iRead 会回补最近一个自然月并安装本地定时任务。

```mermaid
flowchart LR
    A["说出一个或多个领域"] --> B["检查信源与代表作"]
    B --> C["选择报告深度"]
    C --> D["批准采集、回补和定时任务"]
```

不希望运行 `curl | bash`，或要安装到其他 Agent？查看 [完整安装说明](docs/agent-installation.md)。

## iRead 解决什么问题

信息检索真正困难的部分通常不是“总结文章”，而是判断**该长期听谁的、哪些内容互相重复、结论由什么证据支撑**。

| 常见 RSS / AI 摘要工具 | iRead |
| --- | --- |
| 用户自己提供订阅源 | 用户提供领域，iRead 生成待审核信源组合 |
| 逐篇摘要，重复事件反复出现 | 事件级去重，追踪共识、分歧和变化 |
| 官方、媒体、KOL 混为一谈 | 区分一手证据、独立核验、专业分析、专家经验和发现线索 |
| 只回答“今天发了什么” | 日报看新增，周报看演化，月报看结构性变化 |
| 数据通常进入云端 | 配置、凭据、文章和报告默认保留在本机 |

适合需要长期跟踪专业领域的研究者、投资人、产品经理、行业从业者和学生。

## 信源如何选择

严格提案必须覆盖五种角色：

- **一手来源**：政府、监管机构、标准组织、公司原始发布。
- **独立报道**：交叉核验事实。
- **专业分析**：解释机制与影响。
- **专家与从业者**：补充实践经验和非公式知识。
- **发现信号**：发现新话题，不能单独支撑事实结论。

冷启动评分只是候选排序，不是对信源的永久判决。iRead 会保留利益冲突、抓取限制和不确定性。详见 [信源质量方法](docs/source-quality.md)。

## 报告策略

| 模式 | 适合 | 输出特点 |
| --- | --- | --- |
| `light` | 只想知道关键变化 | 最短，只保留高优先级项 |
| `standard` | 长期专业跟踪 | 默认，平衡覆盖与阅读时间 |
| `deep` | 研究、投资或战略分析 | 更多证据、分歧和跨期回看 |

日报负责发现新增事实和异常信号；周报合并重复事件、分析演化；月报维护趋势账本并回看此前判断。所有新订阅默认只生成本地 Markdown。

## 已验证的效果

Beta 6 的公开验收不是模拟数字：

- 全新 Claude Code 安装约 **5 秒**，Doctor 无警告。
- 15 个 RSS 源并发回补最近一个自然月，约 **11 秒**返回；14 个成功，导入 318 篇。
- 一份真实 AI / 具身日报质量规则得分 **94/100**；分析覆盖率仍是明确短板。
- Codex 插件已实测识别；Claude Code 已验证 Skill 加载。豆包专业版和 WorkBuddy 仍需更多真实客户端验证。

完整方法、失败项和边界见 [Beta 6 第三方体验基准](docs/ux-benchmark-beta6.md)。公开的 AI 与具身研究运行案例包含 112 个信源及脱敏元数据快照，见 [参考案例](examples/ai-embodied-research/README.md)。

## 当前能力与边界

- 支持任意多个领域合并为一个订阅，不内置或限制特定行业。
- 支持 RSS / Atom、公开网页候选源和已授权微信公众号。
- 微信采集需要用户拥有某个公众号的管理员或运营者权限；没有权限时可使用 RSS / 网页模式。
- `web_pending` 会明确显示为覆盖缺口，不伪装成已经采集。
- 当前运行时优先支持 macOS，定时任务运行时机器需要开机并联网。
- `0.2.0-beta.6` 是公开 Beta，不是稳定版。

## 隐私、版权与开源边界

- 配置、凭据、文章和报告默认留在本机。
- 公开归档默认只包含链接、元数据和结构化分析，不上传第三方全文。
- 只有确认拥有转载权或兼容许可证时，才能导出第三方全文。

代码使用 [MIT License](LICENSE)。第三方组件、信源和内容权利边界见 [NOTICE.md](NOTICE.md) 和 [开源发布说明](docs/open-source-release.md)。

## 需要帮助或参与项目

| 你想做什么 | 入口 |
| --- | --- |
| 只写领域，让社区协助设计订阅 | [提交订阅需求](https://github.com/roy-tong/iRead/issues/new?template=research-profile.yml) |
| 安装失败或结果异常 | [报告问题](https://github.com/roy-tong/iRead/issues/new?template=bug-report.yml) |
| 纠错或推荐高质量信源 | [贡献信源](https://github.com/roy-tong/iRead/issues/new?template=source-contribution.yml) |
| 参与开发 | [贡献指南](CONTRIBUTING.md) |
| 查看全部技术文档 | [文档导航](docs/README.md) |

开发者可运行 `scripts/test.sh`，并使用 `bin/iread --help`、`bin/iread capabilities` 和 `bin/iread workspace` 检查结构化能力与本地状态。

如果 iRead 对你有用，给仓库点一个 Star，会帮助更多需要高质量信息源的人找到它。
