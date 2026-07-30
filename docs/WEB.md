# Web 工作台

## 产品定位

Web 端是研究工作台，不是聊天机器人的包装层。信息架构围绕项目、论文、人工决定、运行、证据和报告组织：

- 工作台：项目组合、后台任务和待筛选提示。
- 文献入口：跨项目搜索论文记录。
- 项目概览：研究问题、协议、统计和运行历史。
- 文献库：RIS/BibTeX/CSL JSON 导入、密集列表、状态过滤和右侧论文详情。
- 筛选台：逐篇阅读摘要；可选独立双人盲审、揭盲、决定对照与冲突仲裁。
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

界面刻意避免把所有内容放进相同卡片，也不使用渐变、网格背景、巨幅宣传文案、虚构实时思维链或单一聊天窗口。视觉采用中性灰工作区、白色内容面、细边框和紧凑列表，强调“研究工具”而不是“AI 展示页”。

### 视觉约束

- 正文基准字号为 15px；输入框最小高度 42px、字号 14px；小于 11px 的文字仅用于短 ID 或时间戳。
- 中文采用系统 UI 字体，等宽字体只用于代码、论文 ID 和运行 ID。
- 页面标题不使用全大写英文眉题；说明文字只在帮助决策时保留。
- 常规圆角统一为 5–7px；胶囊只用于状态或标签；阴影只用于模态框和移动导航。
- 工作台是项目与待办入口，不承担营销落地页功能。
- 文献库和对话采用稳定分栏，资料、正文与来源各自保持清晰边界。
- 移动端隐藏辅助检查器，保留核心阅读、筛选和运行操作。

### 颜色层级

界面直接加载 Primer Primitives 11.9.0 的 `light` 和 `dark-dimmed`
主题 CSS。应用主体使用 light 语义令牌，侧栏单独使用 dark-dimmed
作用域，不在业务组件中复制一套暗色值。

视觉表面分为四层：

1. 深色侧栏：导航、品牌和本地运行状态。
2. 冷灰蓝画布：页面背景和大范围工作区域。
3. 浅色内容面：列表、统计、设置面板和检查器。
4. 白色抬升面：输入框、对话消息与需要模拟纸张的报告。

这种分层减少整屏纯白带来的眩光，同时不依赖渐变、玻璃拟态或装饰阴影。

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
