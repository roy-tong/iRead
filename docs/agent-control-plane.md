# iRead Agent 控制面

## 结论

iRead 的正式产品形态不是传统 CLI 工具，也不是把全部流程塞进 GUI。目标架构分为三层：

1. Headless execution：本地抓取、分析、报告、调度和归档能力，不依赖图形界面。
2. Agent control：Codex 读取上下文、规划步骤、调用结构化命令、处理异常并检查结果。
3. Human supervision：用户负责目标、授权、例外决策、结果验收和反馈。

当前 Codex-first 版本先交付前两层和对话式人工监督。未来 GUI 只需要读取同一套状态和能力契约，不应重新实现业务逻辑。

## 为什么不能只提供一组命令

普通用户表达的是结果，例如“持续跟踪这个领域”“减少重复内容”“为什么没有周报”，而不是 `sync`、`enrich` 或 `launchctl`。如果 iRead 只暴露命令，用户仍然需要自己理解配置目录、执行顺序、失败恢复和发布权限。

因此，正式版必须同时具备五类能力：

| 层 | iRead 中的实现 | 解决的问题 |
| --- | --- | --- |
| Context | 订阅注册表、`workspace`、激活状态、报告索引 | Agent 在新任务中知道用户已有订阅和当前进度 |
| Execution | 结构化 CLI、能力契约、配置 Schema | Agent 可以稳定调用，而不是操作某个易变界面 |
| Evaluation | 提案校验、覆盖审计、`acceptance` | 系统判断是否真的完成，而不是只判断命令是否退出 |
| Governance | 权限分类、显式批准、请求 ID、操作日志、本地优先发布策略 | 用户保持控制权，重复调用不会造成不透明副作用 |
| Learning | 本地反馈记录并注入后续报告上下文 | 用户对长度、重复度、主题和信源价值的反馈能够生效 |

## Agent 执行协议

每个 Codex 任务应遵循同一条控制链：

```mermaid
flowchart LR
    A["用户目标"] --> B["capabilities 能力与权限"]
    B --> C["workspace 当前上下文"]
    C --> D["Agent 规划"]
    D --> E["用户批准高影响动作"]
    E --> F["带 request-id 的执行"]
    F --> G["operations 操作审计"]
    G --> H["acceptance 结果验收"]
    H --> I["本地报告或显式发布"]
    I --> J["feedback 反馈"]
    J --> C
```

### 1. 发现能力

```bash
bin/iread capabilities
```

输出包含权限类别、副作用、批准要求和幂等语义。契约 Schema 位于 `schemas/agent_capabilities.schema.json`。

### 2. 恢复上下文

```bash
bin/iread workspace
bin/iread --config-dir <subscription> reports --limit 5
```

新订阅会登记到 `~/.config/iread/subscriptions.json`。Codex 新任务不依赖旧对话，也不应要求用户重新寻找配置路径。

### 3. 执行变更

Agent 为一次不变的操作意图生成稳定请求 ID，并把全局参数放在子命令之前：

```bash
bin/iread --config-dir <subscription> \
  --request-id activate:<subscription-id>:<approval-version> \
  activate --approved --install-schedule
```

同一意图重试时复用请求 ID；目标、参数或批准范围改变时必须使用新 ID。成功操作不会重复执行，并发重复请求会在本地串行化。

### 4. 观察与恢复

```bash
bin/iread --config-dir <subscription> operations --limit 20
bin/iread --config-dir <subscription> workspace
```

所有状态变更都写入本地 JSONL 操作日志，记录开始、完成或失败、稳定错误码和请求 ID。可恢复流程使用激活状态机、固定配置目录和唯一报告窗口继续执行。

### 5. 验收结果

```bash
bin/iread --config-dir <subscription> acceptance
```

验收检查配置、跨任务可发现性、激活、文章采集、分析健康、定时任务、报告交付和信源覆盖。`accepted` 代表必须项通过；`accepted_with_warnings` 仍需向用户披露限制。

### 6. 记录反馈

```bash
bin/iread --config-dir <subscription> \
  --request-id feedback:<report-id>:<revision> \
  feedback add --target report --target-id <report-id> \
  --rating down --note "重复事件太多，希望日报更短"
```

反馈只作为编辑偏好，不作为事实证据。后续报告会读取最近反馈，调整篇幅、重复控制、主题权重和信源价值判断。

## 权限边界

以下动作必须由用户当前请求明确授权：

- 首次开始采集、安装或替换定时任务；
- 新增、删除或改变领域和信源；
- 微信公众号本地授权；
- 强制重新生成报告；
- 发布到 Notion 或其他外部服务；
- 导出第三方全文；
- 停止定时任务。

生成订阅默认只创建本地报告，`notion.auto_publish` 为 `false`。对外发布必须使用明确的 `--publish` 或独立 `publish` 命令。第三方全文还必须单独提供权利确认。

用户可以停止自动执行而保留本地数据：

```bash
bin/iread --config-dir <subscription> \
  --request-id schedule:remove:<subscription-id> \
  schedule uninstall --approved
```

该操作会卸载 launchd 或 cron 任务、撤销已保存的调度批准，但不删除文章、报告、配置或反馈。

## Codex Skill 的职责

Skill 不是一段提示词，而是 iRead 的 Agent 适配层。它必须：

- 先读 `capabilities` 和 `workspace`，再决定动作；
- 选择并固定唯一 `config_dir`；
- 解释批准范围，不把沉默当作同意；
- 为状态变更分配和复用请求 ID；
- 读取结构化错误码和 `next_actions` 恢复；
- 在完成后运行 `acceptance`；
- 展示警告和覆盖缺口，不把降级状态描述为完全正常；
- 把用户对报告和信源的评价写入 `feedback`。

## 正式版边界

`v0.2.0` 的目标是 Codex 中的完整结果交付，而不是 GUI 或通用云服务。正式版需要满足：

- 从 GitHub 干净安装后，新 Codex 任务能够直接发现 iRead；
- 任意一个或多个用户领域可以完成提案、检查、批准和合并；
- RSS/网页模式和真实微信扫码模式至少各完成一次端到端验收；
- 最近一个自然月回补、覆盖审计和首份本地报告通过 `acceptance`；
- 新任务可以恢复进度、找到最新报告、解释未出报告原因；
- 失败、重试、重复请求、停止调度和外部发布边界均可审计；
- GitHub Actions、插件校验、源码安装和密钥扫描通过。

WorkBuddy 和 GUI 可以复用这套控制面，但不阻塞首个 Codex 正式版。
