# iRead 本地安装与验收

## 1. 安装到本机 Codex

在仓库根目录运行：

```bash
scripts/install.sh codex
scripts/test.sh
```

安装脚本会登记仓库绝对路径、添加本地 iRead marketplace、安装插件并运行 `doctor`。插件只会在新任务启动时加载，因此安装后需要新建一个 Codex 任务。

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
4. 对于无此类后台权限的用户，只有在用户明确同意后才运行 `activate --skip-wechat --install-schedule`，并输出 `degraded`。
5. `activation` 可随时恢复查看状态；未达到就绪门槛时，`run` 不会过早生成正式报告。
6. 定时任务会生成不含第三方全文的本地 `public/archive`，不会默认推送 GitHub。

如果先选择了 RSS/网页源模式，以后获得公众号后台权限后可以重新启用：

```bash
bin/iread --config-dir <生成目录> activate --enable-wechat
```

## 3. 另一台电脑使用 WorkBuddy

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
