# 计算机科学专精

## 分类依据

本项目用两层分类：

1. [arXiv Category Taxonomy](https://arxiv.org/category_taxonomy) 提供 `cs.AI`、`cs.LG`、`cs.OS`、`cs.SE` 等细粒度标签。
2. [ACM Computing Classification System](https://www.acm.org/publications/class-2012) 的上层思想用于把细标签组织为可操作研究方向。

映射保存在 `src/paper_agent/data/cs_taxonomy.json`，具有版本号和来源地址，不依赖模型记忆。

## 覆盖方向

| 工作台方向 | 典型 arXiv 类别 |
|---|---|
| AI 与机器学习 | cs.AI, cs.LG, cs.CL, cs.CV, cs.MA, cs.NE |
| 计算机系统 | cs.OS, cs.DC, cs.PF, cs.AR |
| 网络 | cs.NI |
| 安全、隐私、密码学 | cs.CR |
| 数据管理与检索 | cs.DB, cs.IR, cs.DL |
| 软件工程 | cs.SE |
| PL 与形式化方法 | cs.PL, cs.LO, cs.FL |
| 理论与算法 | cs.CC, cs.DS, cs.DM, cs.CG, cs.GT, cs.IT |
| HCI 与计算社会 | cs.HC, cs.CY, cs.SI |
| 图形学与多媒体 | cs.GR, cs.MM, cs.SD |
| 机器人与自主系统 | cs.RO, cs.SY |
| 硬件与体系结构 | cs.AR, cs.ET |
| 科学计算 | cs.CE, cs.MS, cs.NA, cs.SC |

一个课题可以是多标签，例如向量数据库可同时属于数据管理、信息检索和系统。

## 方向化证据协议

### 算法与机器学习

- 数据集、划分、任务定义
- 强基线与调参公平性
- 指标、方差、置信区间和显著性
- 消融、敏感性与分布外测试
- 训练/推理硬件、时间、能耗和成本
- 数据泄漏、benchmark contamination

### 系统与网络

- 软硬件环境、工作负载和规模
- throughput、median/tail latency、availability
- CPU、内存、网络、存储、能耗和成本
- microbenchmark 与 end-to-end workload
- 失败场景、恢复和运维复杂度

### 安全

- 威胁模型、攻击者能力和安全目标
- 自适应攻击、迁移攻击与现实性
- false positive / false negative
- 安全收益与性能、可用性成本
- dual-use、披露和伦理边界

### 软件工程

- 仓库、项目、开发者和时间窗口采样
- construct operationalization
- 数据泄漏、重复仓库和时间穿越
- effect size、实际意义和开发者研究
- 内部、外部、构念与结论效度

### 理论、PL 与形式化

- 形式问题、计算模型和假设
- 定理、界、规约、soundness/completeness
- 证明依赖、边界情况与假设强度
- 理论保证与工具实现之间的差距

### HCI

- 参与者招募、任务与条件
- 客观指标、主观体验与定性材料
- 样本代表性、学习/新奇效应
- accessibility、privacy 与 participant risk

### 机器人与硬件

- 仿真与真实部署
- 机器人/传感器/芯片/工艺/内存/工作负载
- safety、failure recovery、sim-to-real
- performance、power、area、energy、accuracy
- simulator、synthesis 与 silicon measurement 的证据区别

## 检索源角色

| 来源 | 主要作用 | 证据边界 |
|---|---|---|
| DBLP | 计算机会议/期刊题录与 venue | 官方说明不提供摘要 |
| arXiv | 预印本摘要与 CS 类别 | 未必经过同行评审 |
| OpenAlex | 跨来源元数据、摘要、引用和开放链接 | 覆盖与元数据质量不均 |
| Semantic Scholar | 摘要、领域和引用 | 默认仅在配置 API key 后启用 |
| 本地全文 | 页码级可检索文本 | PDF 抽取质量依赖源文件 |

[DBLP publication API](https://dblp.org/faq/13501473.html) 最多返回 1000 个结果。项目遵循 DBLP 的限速建议，每个请求至少间隔一秒；大规模分析应使用 DBLP 数据集而不是高频抓取 API。

## 复现评分

`reproducibility.json` 对以下十项各给 0–2 分：

- 问题与任务
- 数据集
- 基线
- 指标
- 实现细节
- 算力
- 消融
- 代码
- 效度威胁
- 可解析标识符

这是“报告完整性”而不是独立复现实验结果。高分不代表代码一定可运行，低分也不直接说明论文结论错误。

## 输出

- `cs_classification.json`
- `cs_landscape.json`
- `cs_evidence_matrix.csv`
- `benchmark_catalog.json`
- `reproducibility.json`
- `research_agenda.json`

`research_agenda.json` 只根据缺失或薄弱的证据字段提出候选方向，不声称这些方向具有学术新颖性。

