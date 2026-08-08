# Web 工作台

## 产品定位

Web 端是研究工作台，不是聊天机器人的包装层。信息架构围绕项目、论文、人工决定、运行、证据和报告组织：

- 今日工作：项目组合、后台任务、待筛选提示和可直接继续的研究入口。
- 文献入口：跨项目搜索论文记录。
- 项目概览：研究问题、协议、统计、运行历史、方案—检索—筛选—证据—报告证据脊柱，以及项目/方案修订账本。
- 文献库：RIS/BibTeX/CSL JSON 导入、密集列表、状态过滤和右侧论文详情。
- 筛选台：标题/摘要与报告全文两阶段工作区；支持获取状态、文档关联、
  结构化排除原因、独立双人盲审、揭盲、决定对照、冲突仲裁和 PRISMA 计数。
- 运行台：八阶段进度、事件、人工门和产物下载。
- 证据台：证据卡、复现报告、benchmark 目录与研究缺口。
- 图谱：文献节点、相似关系和详情联动。
- 报告：Markdown 阅读、结构引用审计和词汇对齐诊断。
- 全文：上传、页码级 FTS5 检索和源文件访问。
- 对话：绑定项目、Agent 和模型连接，回答回链论文与全文页码。
- 运行环境：创建、测试和删除当前服务进程内的模型连接。

## 启动

安装 API 依赖并启动：

```powershell
python -m pip install -e ".[all]"
paper-agent serve
```

浏览器打开 `http://127.0.0.1:8765/app`。生产构建随 Python wheel 一起分发，不需要单独启动 Node。

## 前端开发

Node 24+ 与 pnpm：

```powershell
cd web
pnpm install
pnpm dev
```

开发服务器位于 `http://127.0.0.1:5173/app`，Vite 会把 API 请求代理到 `127.0.0.1:8765`。

构建并把静态资源写入 Python 包：

```powershell
pnpm typecheck
pnpm test
pnpm build
```

构建目录是 `src/paper_agent/web_dist`，并由 `pyproject.toml` 的 package-data 打进 wheel。

### 公共观测站

生产演示部署在 [Asteria Observatory](https://asteria-observatory.vercel.app/app)。它不是把无认证的本地服务直接暴露到公网，而是单独的只读入口：

- Vercel Function 冷启动时使用合成语料生成完整项目，项目与运行 ID 为确定值，跨实例深链接稳定。
- 中间件拒绝所有非 `GET`/`HEAD`/`OPTIONS` 请求；前端同时禁用新建研究并显示公开观测站状态条。
- 不接受模型连接或 API Key，不承诺保存浏览器操作。
- Vercel `/tmp` 仅承担单个实例的临时演示文件；真实研究仍使用本地 SQLite，团队部署需要外部持久数据库、认证与项目授权。

Vercel 构建会重新生成 `src/paper_agent/web_dist`，而不是上传开发机中的历史哈希资源。生产回归可通过 `QA_PROJECT_URL` 和 `QA_RUN_URL` 注入确定性深链接，避免 Node 网络环境影响前置 API 探测。

### 项目生命周期管理

本地工作台支持编辑项目名称、主题、研究问题、工作流类型和输出语言；也可修订年份、关键词、语言、研究类型、PICO 式范围与方案备注。实际方案变更必须填写原因，所有变化都会写入 `project_events`，在项目页的“研究修订记录”中保留字段级 before/after。模型连接也可修改，API Key 留空时继续使用原密钥。

API 边界采用显式公开视图：浏览器只能看到运行状态、阶段、公开 Agent/连接元数据与“产物是否可用”，不会收到 SQLite 路径、数据根目录、运行目录或后台作业内部结果。文件访问始终通过受约束的产物与全文端点完成。

删除不是只隐藏界面记录，而是针对对象执行可验证清理：

- 项目删除会级联处理运行、报告、对话、筛选、全文门禁、证据与质量记录，并清理 FTS5 索引和受管磁盘目录。
- 单次运行、全文文档、对话和项目内论文可以独立删除；删除最后一份关联全文时会重置对应论文的全文获取状态。
- 每种危险操作都要求输入项目名称、文件名或稳定 ID；排队中或运行中的项目/运行拒绝删除。
- 删除项目内论文不会绕过全文约束：如果仍有关联文档，必须先处理全文文档。

公共观测站保持只读，因此这些控件在线上样例中可见但不可执行。完整生命周期操作只在本地持久工作台开放。

### 真实页面验收

先启动含 Web 的本地 API，再严格按探索、排练、录制三阶段执行：

```powershell
$env:QA_BASE_URL = "http://127.0.0.1:8765"
pnpm ui:explore
pnpm ui:rehearse
pnpm ui:record
```

- `ui:explore` 遍历工作台、首个项目与运行页，保存截图并输出可见交互控件。
- `ui:rehearse` 默认只验证演示所需的真实选择器，不移动鼠标、不修改数据。
- `ui:record` 在排练通过后才加入可见光标、自然节奏和字幕，输出到 `web/artifacts/ui-demo/`。

验收数据库必须使用合成或已脱敏数据。默认脚本只浏览页面，不启动运行、提交筛选决定或写入密钥。维护者可以在一次性隔离数据目录中设置 `QA_LIFECYCLE_MUTATE=1`，执行编辑与全部细粒度删除的真实 mutation 回归；该模式会永久删除隔离项目，禁止指向真实研究库。

## 设计依据

- [GitHub Primer Primitives](https://github.com/primer/primitives)：项目直接使用其 light 与 dark-dimmed 主题令牌，统一画布、前景、边框、控件和状态颜色。
- [Zotero Web Library](https://github.com/zotero/web-library)：收藏/列表/详情的高密度工作区。
- [Outline](https://github.com/outline/outline)：安静的层级导航、紧凑工具栏和以内容为中心的留白。
- [Plane](https://github.com/makeplane/plane)：开发者工具中的状态、筛选和操作密度。
- [AppFlowy](https://github.com/AppFlowy-IO/AppFlowy)：本地优先工作区与克制的文档编辑外壳。
- [ASReview LAB](https://github.com/asreview/asreview)：以人类筛选决定为中心。
- [Open Knowledge Maps](https://openknowledgemaps.org/about)：图谱与来源列表联动。
- [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)：文档管理、搜索与本地部署边界。
- [Open WebUI](https://github.com/open-webui/open-webui)：基础模型与 Agent 配置分层。
- [LibreChat](https://github.com/danny-avila/LibreChat)：连接/Agent 选择和会话切换。
- [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)：workspace 绑定文档与对话。
- [OpenScience](https://github.com/synthetic-sciences/openscience)：科学工作台把文件、会话、实验与来源保留在可操作 workspace，而非营销式首页。
- [React Router View Transitions](https://reactrouter.com/how-to/view-transitions)：使用现有路由器的原生页面过渡，不再引入一套并行动画状态。
- [MDN View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)：过渡用于保持导航上下文、降低感知等待，不承担装饰任务。
- [MDN prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion)：系统减少动态偏好是验收要求，不是可选优化。

界面刻意避免把所有内容放进相同卡片，也不使用满屏霓虹、玻璃拟态、装饰粒子、虚构实时思维链或单一聊天窗口。视觉采用深蓝墨色观测台、少量光谱蓝/青/琥珀状态色，以及项目内的浅色研究纸面；首页证据星图、研究账本与项目页证据脊柱是整套界面的识别元素。

### 视觉约束

- 正文基准字号为 15px；输入框最小高度 42px、字号 14px；小于 11px 的文字仅用于短 ID 或时间戳。
- 中文标题与正文采用 Segoe UI Variable Display、微软雅黑 UI 等系统字体；Bahnschrift 与等宽字体只用于数字、代码、论文 ID、运行 ID 和短仪器标签。
- 英文眉题只作短小的栏目索引，不承担主标题；说明文字只在帮助决策时保留。
- 常规圆角统一为 5–7px；胶囊只用于状态或标签；阴影只用于模态框和移动导航。
- 工作台是项目与待办入口，不承担营销落地页功能。
- 文献库和对话采用稳定分栏，资料、正文与来源各自保持清晰边界。
- 移动端隐藏辅助检查器，保留核心阅读、筛选和运行操作。

### 颜色层级

界面加载 Primer Primitives 11.9.0 的 `light` 和 `dark-dimmed` 主题 CSS，
再在应用根部定义 Asteria 的少量语义色与排版令牌。业务组件消费语义类名，
不自行散落页面专属颜色。

视觉表面分为四层：

1. 深色侧栏：导航、品牌和运行状态。
2. 深蓝观测台：首页任务、阶段信号和研究账本。
3. 冷灰蓝研究纸面：项目工作区与长时间阅读区域。
4. 白色抬升面：输入框、对话消息与需要模拟纸张的报告。

这种分层减少整屏纯白带来的眩光；渐变只用于证据信号和状态线，不用作整页装饰，也不依赖玻璃拟态或大面积阴影。

### 动态语法

- 证据信号谱的五个通道完全由项目当前阶段计算；它是状态摘要，不是装饰波形。
- 信号线在首次进入时绘制一次，扫描器只经过一次；只有 `queued` 或 `running` 的真实阶段持续呼吸。
- 页面导航使用 React Router 的 `viewTransition`，工作区轻微淡入位移，固定侧栏不参与动画。
- 悬停只改变 1–3px 位移、状态线和箭头，不使用大幅缩放、弹跳或鼠标跟随特效。
- `prefers-reduced-motion: reduce` 会把 CSS 动画、过渡与 View Transition 压缩为近零时长；Playwright 排练读取计算样式验证该规则。
- 动画主要使用 `transform` 和 `opacity`；SVG 描边与扫描只在载入时短暂运行，避免长期占用绘制资源。

## 安全

- 默认只绑定 `127.0.0.1`。
- Web 可以提交 API 密钥，但密钥只驻留服务进程内存，响应、数据库和导出均不包含密钥。
- 文档上传分块写入，默认上限 50 MB。
- 文献库上传使用同一体积上限，并额外限制最多解析 10,000 条记录。
- API 不向浏览器返回 `source_path` 或 `text_path`。
- 下载运行产物时只允许已知扩展名和运行目录的直接子文件。
- CORS 默认只允许本地 Vite 开发地址，可通过 `PAPER_AGENT_CORS_ORIGINS` 修改。

当前没有账号系统；共享网络部署必须增加 TLS、认证、项目级授权、限速和配额。
筛选页中的 reviewer 是工作流身份和审计标签，不是安全主体。盲审响应由后端裁剪，
但能读取本地 SQLite 或项目导出包的操作者仍可访问完整审计记录。

### DeepSeek

选择 `DeepSeek` 快捷配置会填写 `https://api.deepseek.com`、
`deepseek-v4-pro` 和 `Chat Completions`。DeepSeek 当前不提供
`/responses`；后端也会对手动填写的 DeepSeek 地址自动修正协议。
其结构化输出使用 `json_object`，与 OpenAI Responses 的 JSON Schema
传输格式不同。
