# iRead

iRead 会根据你关心的行业或研究领域，找出值得长期跟踪的官方机构、专业媒体、研究者和从业者，持续采集公开信息，并整理成日报、周报和月报。它优先为不会写代码的 Codex 用户设计。

你只需要做三件事：

1. 说出你关心的一个或多个领域。
2. 检查 iRead 推荐的信源及代表作，删掉不合适的。
3. 选择轻量、标准或深度报告，确认后开始采集。

iRead **没有内置或限定任何订阅领域**。一个订阅可以同时包含任意多个行业、学科和研究主题。仓库中的 `config/` 只是维护者公开的示例，新用户不会自动订阅其中的领域或信源。

## 快速开始

当前 Beta 版优先支持 macOS 上的 Codex，需要本机已安装 Codex 和 Python 3.9 或更高版本。打开终端并运行一行命令：

```bash
git clone https://github.com/roy-tong/iRead.git ~/iRead && cd ~/iRead && scripts/install.sh codex
```

安装结果显示 `iRead is ready` 后，**新建一个 Codex 任务**，直接输入一个或多个关注领域，例如：

```text
帮我订阅医疗器械监管、新能源电力市场和独立游戏发行。
```

Codex 会完成领域展开、信源提案和代表作品检查；只有在你明确批准后，才会创建订阅、回补数据并安装定时任务。完整本地验收步骤见 [`docs/local-testing.md`](docs/local-testing.md)。

你不需要自己准备 RSS 地址、公众号清单或配置文件。如果推荐源包含微信公众号，iRead 会在启动采集时解释扫码要求；没有公众号后台权限也可以明确选择 RSS/网页源模式。

安装后也可以直接用自然语言继续和管理已有订阅：

```text
检查我的 iRead 订阅，告诉我现在卡在哪一步。
继续上次未完成的回补。
打开并总结我最新的日报。
检查为什么这周没有生成周报。
```

WorkBuddy 用户需要先克隆本仓库，再把本机 WorkBuddy 源码目录传给安装脚本：

```bash
cd ~/iRead && scripts/install.sh workbuddy /absolute/path/to/work-buddy
```

## 第一阶段产品形态

本项目以“完整代码仓 + 稳定 CLI”为核心，不做配置 GUI。普通用户不需要自己编写配置文件，而是通过 Codex 插件或 WorkBuddy 工作流用自然语言批量接入：

```text
提供一个或多个行业、研究领域
  -> 自动扩展并确认一级、二级主题
  -> 检索候选信源
  -> 用户检查信源、角色、风险和代表作品
  -> 用户批准后生成独立订阅配置
  -> 如包含微信源，展示本地二维码并等待用户扫码授权
  -> 匹配信源并回补最近一个自然月数据
  -> 完整性达标后生成基线报告
  -> 按 light / standard / deep 节奏生成日报、周报和月报
```

GUI 延后不会造成返工：CLI、JSON Schema、配置目录和审批边界是后续任何桌面或 Web 界面的稳定后端。现有 `research-library` 网页只用于阅读已采集文章，不承担配置职责。完整产品方案见 `docs/product-plan.md`，第一阶段实现边界见 `docs/cli-first-product.md`。

CLI 在 iRead 中是 Agent 的结构化执行层，不是要求普通用户学习的交互界面。Codex 负责恢复上下文、规划和调用能力；用户保留目标、授权、例外决策和结果验收。能力契约、请求幂等、操作审计、验收与反馈闭环见 [`docs/agent-control-plane.md`](docs/agent-control-plane.md)。

日报、周报和月报的信息准入、阅读路由、论点账本和质量指标见 `docs/report-editorial-framework.md`。

当前代码支持为任意多个领域分别生成信源提案，把用户批准的领域合并成一个 iRead 订阅，并在明确同意后完成本地微信扫码、信源匹配、最近一个自然月回补、就绪验收和定时任务安装。没有公众号后台权限的用户可以明确选择 RSS/网页源模式；系统会标记为 `degraded`，不会把微信源误报为已采集。

激活状态会区分完整运行的 `active`、可出报告但仍有必抓 `web_pending` 信源未连接的 `active_with_gaps`，以及用户明确跳过微信源的 `degraded`。定时报告可在后两种状态运行，但必须持续披露未覆盖信源。

### 本地 Codex 验收

```bash
scripts/install.sh codex
scripts/test.sh
```

安装后新建一个 Codex 任务，用从未出现在维护者配置中的任意多个领域进行测试。完整步骤和预期结果见 `docs/local-testing.md`。

### 批量配置研究领域

复制并编辑示例清单，也可以直接让 Codex 或 WorkBuddy 根据对话生成：

```bash
cp config/batch.example.json data/onboarding.json
bin/iread batch-propose data/onboarding.json \
  --output-dir data/onboarding/proposals
```

检查每个提案中的信源 URL、角色、风险、评分和代表作品后，只把明确批准的领域合并进一个订阅：

```bash
bin/iread apply-subscription data/onboarding.json \
  --proposals-dir data/onboarding/proposals \
  --output-dir subscriptions/my-iread \
  --approved medical-devices \
  --approved energy-markets \
  --approved indie-games

bin/iread --config-dir subscriptions/my-iread subscription
```

`batch-propose` 默认断点续跑；`apply-subscription` 强制要求 `--approved` 或明确的 `--approve-all`。多个领域合并后只有一个运行目录和一套报告策略；生成提案本身不会触发订阅或抓取。

### 通过 Codex 使用

仓库内提供可安装的 Codex marketplace 和插件：

```bash
scripts/install.sh codex
```

安装后新建 Codex 任务，直接提供一个或多个行业名称。插件会完成批量提案和复核，得到明确批准后才调用 CLI 落盘。

插件包含两个能力：`onboard-research-domains` 负责新建多领域订阅，`manage-iread` 负责恢复流程、检查采集与定时任务、定位覆盖缺口和读取本地报告。订阅配置会登记在本机 `~/.config/iread/subscriptions.json`，新任务不需要用户重新提供目录。

Codex 在执行前可以读取 `iread capabilities` 的机器契约，状态变更使用稳定 `--request-id` 防止重复执行，完成后通过 `iread acceptance` 验收。`iread operations` 提供本地操作审计；用户对报告或信源的反馈由 `iread feedback` 保存并用于后续报告。

批准采集后，插件会自动准备本地 We-MP-RSS。需要微信源时，它会在对话中显示二维码；扫码必须使用已绑定某个公众号管理员或运营者权限的微信号。账号边界和无公众号权限方案见 `docs/wechat-authorization.md`。

### 通过 WorkBuddy 使用

仓库内提供 WorkBuddy 原生 Markdown 工作流适配器：

```bash
scripts/install.sh workbuddy /absolute/path/to/work-buddy
```

在 WorkBuddy 中运行 `docs_validate` 和 `agent_docs_rebuild` 后使用 `/iread`。详细说明见 `integrations/work-buddy/README.md`。

## 维护者运行配置（非产品默认）

- 72 个公众号，包含必抓、可抓、观察三级权重；另有 40 个已确认海外源，其中 32 个已通过 RSS 激活。
- 历史范围从 `2026-01-01 00:00:00 Asia/Shanghai` 开始。
- 当前维护者实例包含三个公开研究领域；新订阅不会继承这些领域或信源。
- 每天 18:00 生成过去 24 小时简报。
- 每周五 18:00 额外生成滚动 7 天深度周报。
- 每月最后一天 18:00 额外生成月度研究，并引用此前月份的聚合与报告。
- 每天 19:00 更新不含第三方全文的本地公开归档。
- 分析模型为 `gpt-5.6-terra`；报告发布到 Notion。

## 数据流

```text
微信扫码授权
  -> We-MP-RSS 抓取与本地 SQLite
海外 RSS / 官方发布
  -> 外部源增量采集
  -> 本项目增量导入、去重和覆盖率审计
  -> Codex 分批提取主题、事实、结构化原创观点、推断、公司、人物、融资与证据质量
  -> 事件级去重，计算跨源共振、独家价值、原创性和标题党风险
  -> 日报 / 周报 / 月报
  -> Notion 页面
```

系统优先直接读取 We-MP-RSS 的本地 SQLite，以保留完整正文和超过 RSS 单页上限的历史记录；SQLite 不可用时可退回 We-MP-RSS 的 RSS 分页接口。

`patches/we-mp-rss-macos-qr.patch` 是唯一的上游兼容补丁，用于修复 macOS WebKit 对登录二维码元素截图超时的问题；补丁改为优先在同一浏览器会话中下载二维码字节。

## 开源与内容边界

本仓库代码使用 MIT License。第三方运行组件和信源披露见 `NOTICE.md`、`docs/disclosure.md`，当前信源配置见 `config/accounts.json`、`config/external_sources.json` 和 `docs/source-candidates.md`。

其他用户可以通过 GitHub 的 iRead subscription request 只提交一个或多个研究领域，维护者再生成信源候选和代表作品；代码、信源与订阅贡献规则见 `CONTRIBUTING.md`。

采集到的文章正文、站点 HTML、图片、付费内容和逐字稿不属于本仓库许可证。公开发布数据时默认导出链接、元数据和结构化分析结果；只有在确认拥有转载授权或兼容许可证时，才应启用全文导出。完整说明见 `docs/open-source-release.md`。

## 首次安装

1. Codex 或 WorkBuddy 安装命令会自动生成仅保存在本机 `.env` 中的 We-MP-RSS 管理凭据。Notion 是可选输出；需要同步时再填写：

   ```bash
   scripts/install.sh codex
   ```

2. 在 Notion 创建一个内部 Integration，把目标父页面分享给它，然后设置：

   ```text
   NOTION_TOKEN=...
   NOTION_PARENT_PAGE_ID=...
   ```

3. 信源批准后，Agent 会自动运行以下命令准备采集服务。也可以手工执行：

   ```bash
   scripts/setup_collection.sh
   ```

   已安装 Docker 的机器也可直接使用：

   ```bash
   docker compose up -d
   ```

4. 对已生成的订阅启动激活：

   ```bash
   bin/iread --config-dir subscriptions/my-iread activate \
     --approved --install-schedule
   ```

   返回 `needs_auth` 时展示 `auth.qr_image` 并扫码，然后运行：

   ```bash
   bin/iread --config-dir subscriptions/my-iread activate \
     --wait-for-auth --install-schedule
   ```

   没有公众号管理员或运营者权限时，可以明确选择：

   ```bash
   bin/iread --config-dir subscriptions/my-iread activate \
     --approved --skip-wechat --install-schedule
   ```

   以后获得权限后，可以用 `activate --approved --enable-wechat` 恢复微信授权和采集。

5. 激活流程会自动进行公众号高置信匹配。也可以先手工预演：

   ```bash
   bin/iread subscribe --dry-run
   bin/iread subscribe
   ```

   自动匹配只接受精确名称或高置信别名；有歧义的公众号会进入 `unresolved`，不会冒险订错。

6. 查看可恢复的激活和回补进度：

   ```bash
   bin/iread --config-dir subscriptions/my-iread activation
   bin/iread --config-dir subscriptions/my-iread audit
   ```

   安装脚本当前沿用兼容目录 `~/Library/Application Support/ResearchReporter`，以避开 macOS 对 `Documents` 目录的后台访问限制；当前项目中的 `data`、`.runtime` 和 `logs` 会成为指向该目录的软链接。新配置使用 `IREAD_SERVICE_ROOT` 覆盖这个位置，旧的 `REPORTER_SERVICE_ROOT` 仍可用。

## 常用命令

```bash
bin/iread sync                         # 从 We-MP-RSS 增量导入
bin/iread enrich --max-batches 2       # 用 Codex 分批标注文章
bin/iread audit                        # 检查必抓源、历史边界和正文缺失
bin/iread subscription                 # 查看当前订阅、领域、信源和报告策略
bin/iread activation                   # 查看授权、回补、就绪和定时任务状态
bin/iread capabilities                 # 查看 Agent 能力、权限、副作用和幂等契约
bin/iread workspace                    # 跨 Codex 任务发现订阅和下一步
bin/iread acceptance                   # 验收采集、覆盖、定时任务和报告交付
bin/iread operations --limit 20        # 查看本地状态变更审计记录
bin/iread wechat-auth status           # 只检查本地微信授权状态，不输出凭据
bin/iread sources-review --output data/source-review.json  # 评级信源并选取代表作
bin/iread report daily --no-publish    # 只生成本地日报
bin/iread report weekly                # 按本订阅策略生成周报；新订阅默认只保存在本地
bin/iread report weekly --publish      # 明确发布周报到已配置的 Notion
bin/iread feedback add --target report --target-id 1 --rating down --note "重复内容太多"
bin/iread schedule uninstall --approved # 停止定时任务并保留本地数据
bin/iread backfill --max-accounts 1    # 请求下一批历史分页
bin/iread export --output-dir public/archive  # 导出可公开归档，默认不含全文
bin/iread run                          # 执行当天应有的完整流程
```

本地报告保存在 `data/reports/`，运行日志在 `logs/`，研究数据库为 `data/research.db`。

微信公众号原始库可在 [http://127.0.0.1:8001](http://127.0.0.1:8001) 浏览。公众号与海外 RSS 的统一文章库位于 [http://127.0.0.1:8002](http://127.0.0.1:8002)，支持来源、关键词、相关度和原创性筛选。中外信源、获取方式和收录状态见 `docs/source-candidates.md`。

## 单领域高级配置

常规多领域配置应使用前面的 `batch-propose` 和 `apply-subscription`。只需要一套独立单领域研究库时，也可以直接生成并应用单个提案：

```bash
bin/iread propose \
  --field "医疗器械监管与临床转化" \
  --region 中国 --region 美国 --region 欧洲 \
  --output data/medical-devices-proposal.json

bin/iread apply-proposal data/medical-devices-proposal.json \
  --output-dir profiles/medical-devices \
  --preset standard
```

需要完全手工控制时，也可以通过单独配置目录运行另一套研究 profile：

```bash
mkdir -p profiles/my-field
cp config/profile.json profiles/my-field/profile.json
cp config/topics.json profiles/my-field/topics.json
cp config/accounts.json profiles/my-field/accounts.json
cp config/external_sources.json profiles/my-field/external_sources.json
cp config/source_policy.json profiles/my-field/source_policy.json
cp config/reporting.json profiles/my-field/reporting.json

bin/iread --config-dir profiles/my-field init
bin/iread --config-dir profiles/my-field sync
```

缺失的配置文件会回退到默认 `config/`。`profile.json` 定义研究目标和受众，`topics.json` 定义主题体系，目标作者和 RSS 源分别位于 `accounts.json`、`external_sources.json`，`reporting.json` 定义日报、周报和月报策略。详细字段说明见 `docs/customization.md`，信源评级方法见 `docs/source-quality.md`。

## 完整性边界

非官方微信公众号采集无法从技术上承诺绝对零漏抓，尤其是登录失效、平台限频、文章删除、仅粉丝可见和历史分页受限时。本系统把“尽可能完整”落实为可审计机制：必抓源必须全部匹配；历史文章分批回溯；缺正文自动重试；按来源检测异常发布空档；每天在报告中附上完整性状态。只有最早文章覆盖到指定历史边界附近时，系统才会标记该来源的回溯范围已被证实。

本机需要保持开机并联网。macOS 睡眠时错过的任务通常会在唤醒后补跑，但报告时间会相应延后。
