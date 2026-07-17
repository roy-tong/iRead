# 数据入口与新增信源候选清单

更新日期：2026-07-16

状态说明：第一轮中除 Bloomberg、Financial Times、The Information 之外的候选，以及第二轮全部 KOL/KOC 候选，已于 2026-07-16 在 Notion 确认并进入配置。用户已授权后续高质量原创访谈源经核验后直接收录，无需逐个确认。

## 当前数据在哪里

- 原始文章浏览入口：[本机 WeRSS](http://127.0.0.1:8001)。这里可以按公众号查看已抓取文章、正文和订阅状态，页面随后台采集持续更新。
- 原始抓取数据库：默认在 `$HOME/Library/Application Support/ResearchReporter/data/we-mp-rss/we_mp_rss.db`，或 `.env` 中的 `WERSS_DB_PATH`。
- 研究数据库：默认在兼容目录 `$HOME/Library/Application Support/ResearchReporter/data/research.db`，或 `IREAD_DATA_DIR/research.db`。这里保存去重后的正文、主题、实体、证据质量、可信度、原创性、标题党风险和事件评分。
- 研究报告：继续发布到当前 Notion 父页面。Notion 不复制每篇完整原文，避免数千个页面造成检索和 API 同步负担；原始全文统一在本机 WeRSS 查看，报告引用原文链接。

## 收录原则

- 已勾选来源均已进入正式配置；后续只自动加入具名深访、原创研究、产品实测或一手工程实践源。
- 影响力、可信度、原创性和标题党风险分开计分；账号影响力不是事实真伪判决。
- 高频内容按事件合并。多次转载不等于多家独立验证。
- 小型来源的独家材料只有在具备原始文件、实测、具名采访或可复核数据时，才进入“独家候选”。
- 证据不足或标题正文错位的内容标为“待核验”，不直接指控造假。

## 中文公众号候选

### 第一优先：补齐明显缺口

- [x] **量子位**：AI 产品、模型、创业融资和技术进展覆盖广，适合做高频事件发现；逐篇评估标题党与商业稿风险。[官网](https://www.qbitai.com/)
- [x] **智东西**：覆盖 AI、机器人、AIoT、AI PC/Phone 和产业链，能补足具身与 AI 硬件交叉信息。[官网](https://zhidx.com/)
- [x] **甲子光年**：偏产业研究、企业访谈和白皮书，适合周报/月报的结构性材料。[官网](https://www.jazzyear.com/)
- [x] **投资界**：补充融资、投资机构和一级市场事件；融资金额仍需公司公告或投资方交叉确认。[官网](https://www.pedaily.cn/)
- [x] **高工机器人**：补机器人产业链、出货、零部件、集成商和制造场景信息。[官网](https://www.gg-robot.com/)
- [x] **机器人大讲堂**：补机器人垂直报道、行业访谈和大会材料。[行业页](https://mp.agentren.cn/leaderobot)
- [x] **Founder Park**：补创始人访谈、AI 原生产品和创业方法，重点提取一手产品与组织信息。

### 第二优先：技术、硬件与独家产品体验

- [x] **AI科技评论**：补论文、研究者和技术路线，适合核验技术突破是否成立。
- [x] **芯东西**：补 AI 芯片、端侧算力、RISC-V、Chiplet 和供应链。
- [x] **电子工程专辑**：补器件、传感器、SoC、制造和硬件工程信息。
- [x] **新战略机器人**：当前公众号名称为“移动机器人产业联盟”，补工业机器人、移动机器人与产业应用。
- [x] **智源社区**：补论文、研究机构和技术活动，优先保留原始论文链接。
- [x] **中国信通院 CAICT**：补标准、政策、产业白皮书和统计口径，作为高可信一手研究源。
- [x] **归藏的AI工具箱**：补 AI 应用实测和新工具发现；产品体验与商业推广分开标注。
- [x] **宝玉**：补海外 AI 一手材料的翻译、整理和技术讨论；最终事实回链英文原始来源。

## 海外媒体候选

### 建议首批接入

- [x] **Reuters Technology / AI**：重大公司、交易和政策事实核验；网页栏目采集。[栏目](https://www.reuters.com/technology/artificial-intelligence/)
- [x] **MIT Technology Review AI**：技术趋势、研究与社会影响的深度解释。[栏目](https://www.technologyreview.com/topic/artificial-intelligence/)
- [x] **IEEE Spectrum Robotics**：机器人、传感器、执行器和工程进展，技术证据密度高。[栏目](https://spectrum.ieee.org/topic/robotics/)
- [x] **The Robot Report**：机器人公司、产品、部署和融资的垂直行业媒体。[官网](https://www.therobotreport.com/)
- [x] **TechCrunch AI**：AI 产品、创业公司与融资事件发现；融资数字需二次核验。[栏目](https://techcrunch.com/category/artificial-intelligence/)
- [x] **Crunchbase News AI / Robotics**：融资趋势、公司和投资方数据，适合月度聚合。[官网](https://news.crunchbase.com/)
- [x] **Rest of World**：补非美国市场、跨境扩张和中国科技出海的独家报道。[官网](https://restofworld.org/)

### 建议第二批接入

- [x] **VentureBeat AI**：企业 AI、infra、Agent 和商业化。[栏目](https://venturebeat.com/category/ai/)
- [x] **Semafor Technology**：科技公司、政策和行业观点，事实与作者观点结构较清楚。[官网](https://www.semafor.com/technology)
- [x] **Sifted**：欧洲 AI 创业与融资，补足美国之外的公司池。[官网](https://sifted.eu/)
- [x] **Ars Technica AI**：技术产品、平台和基础设施报道。[栏目](https://arstechnica.com/ai/)
- [x] **WIRED AI**：AI 产品、人物和社会影响，深度稿优先，快讯降权。[栏目](https://www.wired.com/tag/artificial-intelligence/)

### 付费源，可选

- [ ] **Bloomberg Technology**：公司、资本市场与供应链。需要合法订阅。[栏目](https://www.bloomberg.com/technology)
- [ ] **Financial Times AI**：公司战略、资本和政策。需要合法订阅。[栏目](https://www.ft.com/artificial-intelligence)
- [ ] **The Information**：科技公司独家与组织变化。需要合法订阅。[官网](https://www.theinformation.com/)

## 海外一手发布候选

媒体报道之外，建议把下列官方发布作为事实核验层。它们只对自身产品、组织和合作事实具有一手价值，不能替代外部评价。

- [x] [OpenAI News](https://openai.com/news/)
- [x] [Anthropic News](https://www.anthropic.com/news)
- [x] [Google DeepMind Blog](https://deepmind.google/discover/blog/)
- [x] [NVIDIA Blog](https://blogs.nvidia.com/)
- [x] [Meta AI Blog](https://ai.meta.com/blog/)
- [x] [Hugging Face Blog](https://huggingface.co/blog)
- [x] 机器人公司动态池：Figure、1X、Physical Intelligence、Agility Robotics、Apptronik、Boston Dynamics；由文章实体高频和融资事件自动调整跟踪优先级。

## 第二轮：海外 KOL/KOC 候选

以下候选用于弥补机构媒体趋同。默认只把作者亲历、实测、代码、原始访谈或明确论证计为高价值；转载、赞助和投资组合相关内容自动降低独立性权重。

### 工程实践与产品实测

- [x] [Simon Willison](https://simonwillison.net/)：长期独立开发者，持续实测模型、Agent、代码工具和开源生态；优先接入其长文 Atom feed。
- [x] [Latent Space](https://www.latent.space/)：AI Engineer 社区的技术访谈与工程实践，适合 infra、Agent、模型工具链。
- [x] [Ahead of AI / Sebastian Raschka](https://magazine.sebastianraschka.com/)：偏模型实现、训练方法和论文复现，技术细节密度高。
- [x] [Chip Huyen](https://huyenchip.com/blog/)：AI 工程、生产部署和系统设计；低频但原创度高。
- [x] [Eugene Yan](https://eugeneyan.com/)：推荐系统、LLM 应用和生产实践；优先保留代码与实验依据。
- [x] [Ben's Bites](https://www.bensbites.com/)：产品发现、工具试用与创业案例；作者有投资业务，相关公司内容需标注利益关系并降独立性权重。

### 模型、产业与资本判断

- [x] [Interconnects / Nathan Lambert](https://www.interconnects.ai/)：开源模型、后训练、模型评测和研究者访谈；兼具研究与一线训练经验。
- [x] [SemiAnalysis](https://newsletter.semianalysis.com/)：AI 算力、半导体、数据中心和供应链；影响力高，但付费研究和咨询利益需显式标注。
- [x] [Import AI / Jack Clark](https://jack-clark.net/)：AI 研究、政策和长期趋势；作者与 Anthropic 有直接关系，涉及该公司时不视为独立信源。
- [x] [No Priors](https://www.nopriorspodcast.com/)：AI 创始人、研究者和投资人长访谈；主持人有 VC 身份，项目相关内容标注投资偏差。
- [x] [Dwarkesh Podcast](https://www.dwarkesh.com/)：研究者、创业者与政策人物长访谈，适合提取一手观点，嘉宾自述仍需外部核验。

### 应用观察与反共识

- [x] [One Useful Thing / Ethan Mollick](https://www.oneusefulthing.org/)：持续亲测 AI 在工作、教育和组织中的应用，兼具实验与研究背景。
- [x] [AI as Normal Technology](https://www.normaltech.ai/)：识别能力夸大、评测缺陷和政策误区，作为反炒作校准源。
- [x] [Rodney Brooks Essays](https://rodneybrooks.com/category/essays/)：机器人落地、时间尺度与技术炒作的长期反思，适合具身智能反共识核验。

## 第二轮：中文 KOL/KOC 候选

原有 61 个公众号已经覆盖主流综合媒体、融资、研究、芯片和机器人产业。国内不再横向增加同质综合媒体，本轮只补充以下个人与深访源。

- [x] **张小珺Jùn**：文字版公众号为“语言即世界language is world”，科技创业者长访谈和组织变化，一手口述价值高；嘉宾自述与事实分开记录。
- [x] **赛博禅心**：AI 产品、公司与产业链分析，作为个人判断源，不直接承担事实确认。
- [x] **夕小瑶科技说**：论文、模型与工程知识解释，优先回链论文和代码。
- [x] **乱翻书**：互联网与 AI 产品从业者长对谈，适合产品判断与组织经验。
- [x] **暗涌Waves**：创投与创业者深度报道，补机构关系和公司组织变化。
- [x] **42章经**：创业、融资与投资人观点；涉及投资组合时降低独立性权重。

## 第三轮：原创访谈与观点源（自动确认）

### 中文

- [x] **硅谷101**：中美科技、AI、芯片和创业者长访谈。
- [x] **晚点对话**：企业家与科技公司关键人物的具名深访。
- [x] **OnBoard Podcast**：创业者、投资人和产品负责人的长对谈。
- [x] **屠龙之术**：创投、组织和产业判断，涉及利益关系时单独标注。
- [x] **捕蛇者說**：工程师与技术从业者访谈，优先保留一线实践经验。

### 海外

- [x] [The Cognitive Revolution](https://www.cognitiverevolution.ai/)：AI 创业者、研究者和一线建设者访谈，官方页面可获取逐字稿。
- [x] [ChinaTalk](https://www.chinatalk.media/)：中国科技、AI、芯片和政策的原创访谈与分析。
- [x] [The Gradient Podcast](https://thegradient.pub/)：研究者深访与技术路线讨论。
- [x] [Machine Learning Street Talk](https://www.mlst.ai/)：偏技术与反共识的长访谈。
- [x] [How I AI](https://www.youtube.com/@howiaipodcast)：产品与工作流实践访谈。
- [x] [Lex Fridman Podcast](https://lexfridman.com/podcast/)：只保留 AI、机器人和关键技术人物相关节目，优先使用官方逐字稿。
- [x] [Lenny's Podcast](https://www.lennyspodcast.com/)：AI 产品、增长、组织与创始人访谈，按主题相关度过滤。

### 获取与分析状态

- 11 个新增中文公众号已精确匹配并订阅到 WeRSS，历史文章由微信侧后台分批回溯。
- 21 个新增海外源全部接入正式配置；RSS 首轮已完成，当前累计取得 80 期官方完整逐字稿。
- 系统单独保存说话者、身份、机构、观点、论据/亲历、语境、利益关系、预测和验证目标。只有节目简介时不生成受访者观点。

## GitHub 清单评估

- [RSSHub](https://github.com/DIYgod/RSSHub) 是采集路由基础设施，适合解决站点没有原生 RSS 的问题，不是信源质量榜单。
- [Awesome RSSHub Routes](https://github.com/JackyST0/awesome-rsshub-routes) 提供官方 feed、RSSHub route、OPML 和健康检查，是本系统最适合持续发现可采信源的机器可读入口。
- [Open Source AI News](https://github.com/aitools-coffee/Open-Source-AI-News) 有活跃度、原创策展、免费入口和反垃圾标准，适合发现 newsletter 候选，仍需逐个核验作者背景。
- [Awesome AI Newsletters](https://github.com/alternbits/awesome-ai-newsletters) 和 [Finxter Curated AI Newsletters](https://github.com/finxter/curated-list-of-ai-newsletters/) 覆盖面广，但商业与自荐内容较多，只作候选发现，不直接批量订阅。

## 后续新增机制

系统可直接加入经核验的原创访谈、独立研究和一手实践源，并同步写入 Notion 信源页。纯聚合号、同质媒体、停更源和缺乏原始材料的营销源不自动扩充。
