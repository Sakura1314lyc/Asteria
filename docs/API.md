# REST API

安装并启动：

```powershell
python -m pip install -e ".[api]"
paper-agent serve
```

交互式文档位于 `http://127.0.0.1:8765/docs`。
集成 Web 工作台位于 `http://127.0.0.1:8765/app`。

## 主要端点

| Method | Path | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/capabilities` | 不含密钥的运行能力摘要 |
| GET | `/agents` | 可选择的科研 Agent 配置 |
| GET/POST | `/connections` | 列出或创建进程级模型连接 |
| DELETE | `/connections/{id}` | 删除进程级模型连接 |
| POST | `/connections/{id}/test` | 显式调用模型测试连接 |
| GET | `/taxonomy` | CS 方向与 arXiv 类别 |
| POST | `/taxonomy/classify` | 主题多标签分类 |
| POST | `/projects` | 创建项目 |
| GET | `/projects` | 项目列表与统计 |
| GET | `/projects/{id}` | 项目、运行、报告和文档 |
| PUT | `/projects/{id}/protocol` | 更新研究方案 |
| POST | `/projects/{id}/runs` | 后台启动研究 |
| GET | `/runs/{id}` | 运行状态 |
| GET | `/runs/{id}/cs-analysis` | CS landscape、benchmark 与复现分析 |
| GET | `/runs/{id}/research` | 计划、论文、证据、质量和审计 |
| GET | `/runs/{id}/report` | Markdown 报告与引用审计 |
| GET | `/runs/{id}/graph` | 文献图谱 |
| GET | `/runs/{id}/artifacts` | 可下载运行产物 |
| GET | `/runs/{id}/artifacts/{name}` | 下载单项产物 |
| GET | `/runs/{id}/events?after=0` | 增量事件 |
| GET | `/projects/{id}/papers` | 论文与筛选状态 |
| POST | `/projects/{id}/bibliography` | 导入 RIS、BibTeX 或 CSL JSON 文献库 |
| POST | `/projects/{id}/screening` | 批量保存人工决定 |
| POST | `/runs/{id}/continue` | 通过人工门后继续 |
| GET/POST | `/projects/{id}/conversations` | 列出或创建项目对话 |
| GET | `/conversations/{id}` | 对话与消息历史 |
| POST | `/conversations/{id}/messages` | 基于项目证据回答并返回来源 |
| POST | `/projects/{id}/documents` | 上传全文 |
| GET | `/projects/{id}/documents` | 全文列表，不暴露内部路径 |
| GET | `/projects/{id}/documents/{doc_id}/file` | 下载原始全文 |
| GET | `/projects/{id}/documents/{doc_id}/text` | 读取提取文本 |
| GET | `/projects/{id}/documents/search?q=...` | 全文检索 |
| GET | `/projects/{id}/export` | 下载带校验清单的项目 ZIP |
| GET | `/jobs` | 进程内后台作业 |
| DELETE | `/jobs/{id}` | 取消尚未开始的任务 |

## 后台运行

创建运行返回 `run_id` 和 `job_id`：

- `job_id` 描述当前进程内任务；
- `run_id` 是持久化研究运行，服务重启后仍可查询。

当前 JobManager 不支持强行终止已经执行的模型 HTTP 调用。生产队列应实现租约、心跳、幂等和可见性超时。

Web 的 `demo=true` 会同时使用 DemoLLM 和安装包内置合成论文，确保无密钥、无网络环境也能完成演示。合成论文不能用于真实研究结论。

## 文献库导入

`POST /projects/{id}/bibliography` 使用 `multipart/form-data` 的 `file` 字段，
接受 `.ris`、`.bib` 和 `.json`。JSON 必须是 CSL JSON 对象、数组或包含
`items` 数组的对象。上传受 `PAPER_AGENT_MAX_UPLOAD_MB` 限制；解析记录上限为
10,000 条。

返回值区分新增记录、项目中已存在记录、被补全元数据的记录、文件内重复与损坏
记录。导入在单个 SQLite 事务中完成，不修改已有筛选状态，也不会以空字段覆盖
既有摘要、作者或标识符。当前是文件导入，不是 Zotero Web API 同步。

`POST /projects/{id}/runs` 接受 `agent_id`、`connection_id`、`demo` 和
`stop_for_screening`。运行只持久化连接名称、模型和 ID，不保存 API Key。
进程级连接在服务重启后失效；环境变量连接 ID 固定为 `env-openai`。

## 部署边界

API 没有内置账号系统，默认只适用于本机。不要把 `--host 0.0.0.0` 直接暴露到公网。
