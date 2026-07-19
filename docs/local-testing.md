# iRead 本地安装与验收

## 1. 安装到本机 Codex

在仓库根目录运行：

```bash
scripts/install.sh codex
scripts/test.sh
```

安装脚本会登记仓库绝对路径、添加本地 iRead marketplace、安装插件并运行 `doctor`。插件只会在新任务启动时加载，因此安装后需要新建一个 Codex 任务。

安装后先验证无代码入口：

```text
检查我的 iRead 订阅和下一步。
```

Codex 应自动调用 `iread workspace`；没有用户订阅时进入领域配置，已有订阅时展示名称、领域、状态、文章与报告数、定时任务和下一步，不要让用户自己找配置目录。

## 2. 用任意多个领域测试

在新任务中输入：

```text
用 iRead 建立一个订阅，同时关注医疗器械监管、新能源电力市场和独立游戏发行。
这些只是我本次输入的领域，不要沿用仓库现有 config 的领域或信源。
先给出领域地图、信源角色、评分、风险和每个信源的代表作品；我确认前不要应用配置或启动抓取。
```

验收以下行为：

1. 每个领域产生独立提案，且 `validate-proposal` 通过。
2. Codex 展示候选信源、直接 URL、代表作品、风险和 `light` / `standard` / `deep` 差异。
3. 未经明确批准，不执行 `apply-subscription`。
4. 批准任意两个或三个领域后，只合并已批准领域，共用信源被去重。
5. 最终运行 `bin/iread --config-dir <生成目录> subscription`，输出正确的领域数量和名称。
6. 新目录的 `reporting.json` 只包含 `main` 采集节点，不继承维护者机器的 worker 配置。

确认信源和报告策略后，在同一个任务中说：

```text
批准这些信源，开始本地采集、最近一个自然月回补和定时报告。
```

继续验收：

1. 首次返回 `needs_collector` 时，Agent 自动运行 `scripts/setup_collection.sh` 并重试。
2. 需要微信源时，对话中展示本地 `auth.qr_image`，用拥有某个公众号管理员或运营者权限的微信扫码。
3. 扫码后输出公众号匹配结果、回补进度和 `backfilling` / `readiness_review` / `active` 状态。必抓 `web_pending` 信源尚未连接时，应输出 `active_with_gaps` 和具体信源 ID，不得输出完整 `active`。
4. 对于无此类后台权限的用户，只有在用户明确同意后才运行 `activate --approved --skip-wechat --install-schedule`，并输出 `degraded`。
5. `activation` 可随时恢复查看状态；未达到就绪门槛时，`run` 不会过早生成正式报告。
6. 定时任务会生成不含第三方全文的本地 `public/archive`，不会默认推送 GitHub。

## 3. Codex 跨任务管理验收

完成一个订阅后关闭原任务，新建 Codex 任务并分别输入：

```text
继续我上次未完成的 iRead 配置。
打开并总结我最新的日报。
检查为什么本周没有周报。
```

验收以下行为：

1. Codex 从 `~/.config/iread/subscriptions.json` 和活动定时配置中发现订阅，不要求用户重复提供路径。
2. 多个订阅无法唯一匹配时，先让用户选择，不默认混用数据库。
3. 读取报告时使用 `iread reports`，打开 `exists: true` 的本地 Markdown，不因“打开”而重新生成报告。
4. `active_with_gaps`、`degraded` 和 `active_unverified` 都用人话说明限制，不简化为完全正常。
5. 只有用户明确要求后才安装或切换定时任务、强制重生报告、发布 Notion 或改动信源。

如果先选择了 RSS/网页源模式，以后获得公众号后台权限后可以重新启用：

```bash
bin/iread --config-dir <生成目录> activate --approved --enable-wechat
```

## 4. Agent 控制面验收

选择一个测试订阅，先检查机器契约和结果状态：

```bash
bin/iread capabilities
bin/iread --config-dir <生成目录> acceptance
bin/iread --config-dir <生成目录> operations --limit 20
```

验收以下行为：

1. `capabilities` 输出每项能力的权限、副作用、批准要求和幂等语义，且 Schema 路径存在。
2. 首次执行带稳定 `--request-id` 的反馈命令成功；完全相同的命令重试时返回 `request_already_completed`，只产生一条反馈。
3. 状态变更失败时输出 JSON 错误，其中包含稳定 `error.code`；`operations` 可看到对应的 `started` 和 `failed` 事件。
4. `acceptance` 只有在配置、上下文、激活、采集、定时任务和首份报告等必须项通过时才返回 `accepted: true`；警告不会被隐藏。
5. 新订阅不设置 `--publish` 时只生成本地报告。`feedback add` 写入的编辑偏好会出现在后续报告输入中，但不会被当作事实证据。
6. 在专用测试订阅上，经用户明确批准后运行 `schedule uninstall --approved`，定时任务被删除，文章、配置和报告仍然存在；再次安装必须重新批准。

示例幂等反馈命令：

```bash
bin/iread --config-dir <生成目录> \
  --request-id feedback:test-report:1 \
  feedback add --target report --target-id 1 \
  --rating down --note "重复事件太多，希望更短"
```

## 5. WorkBuddy 实验性适配（暂不作为发版门槛）

iRead 发布到 GitHub 后，在另一台电脑运行：

```bash
git clone https://github.com/<owner>/iread.git
cd iread
scripts/install.sh workbuddy /absolute/path/to/work-buddy
scripts/test.sh
```

然后在 WorkBuddy 中运行 `docs_validate` 和 `agent_docs_rebuild`，新建任务并执行：

```text
/iread 同时订阅城市水务治理、数字人文和消费品供应链
```

WorkBuddy 会使用自己的检索能力生成提案，并调用 iRead CLI 校验和落盘；另一台电脑不需要安装 Codex。GitHub 仓库是跨机器分发代码和安装适配器的必要载体，WorkBuddy 目前不会像 Codex marketplace 一样直接安装尚未克隆的本地仓库。
