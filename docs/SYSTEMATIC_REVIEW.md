# 系统综述流程

本项目支持“系统综述准备流程”，但不会声称自动生成的结果天然符合 PRISMA 或任何学科指南。

## 推荐步骤

1. 在运行前冻结研究问题和研究方案。
2. 配置数据库、年份、关键词、语言和研究类型。
3. 保存所有检索式及检索时间。
4. 由至少两名研究者独立完成最终纳入决定；建议标题/摘要阶段也采用双人筛选。
5. 每个决定保存理由和 reviewer，预先规定讨论与第三方仲裁规则。
6. 对标题/摘要候选报告获取全文，记录未取得原因。
7. 由至少两名研究者独立完成全文最终纳排；每个全文排除只记录一个主要原因。
8. 由两名研究者复核关键证据卡。
9. 根据研究设计选择正式风险偏倚工具。
10. 只有在效应量与异质性条件适合时进行统计合并。
11. 逐条核对报告中的引文与原文。

## 自动化与人工职责

| 环节 | 系统可以做 | 人必须负责 |
|---|---|---|
| 计划 | 多视角问题、检索式草案 | 冻结方案、注册方案 |
| 检索 | API 查询、去重、排序 | 数据库覆盖与日期确认 |
| 筛选 | 透明规则建议、获取状态与流程计数 | 两阶段最终纳排与冲突解决 |
| 提取 | 摘要级证据卡 | 全文数据双人复核 |
| 质量 | 可提取性提示 | 正式风险偏倚评价 |
| 写作 | 带稳定 ID 的草稿 | 语义核引、学术判断 |
| 流程图 | 运行计数 | PRISMA 合规表述 |

## 独立双人筛选

Web 或 `paper-agent screen configure` 可以为项目启用两个 reviewer 的盲审。
双方完成前，API 不向一方返回另一方的决定。揭盲后：

- 两人同为 included 或 excluded：自动形成一致结论。
- 一人为 included、一人为 excluded：标记为 conflict。
- 任一人为 maybe：标记为 awaiting_resolution。
- 冲突和待讨论项需要填写仲裁人、最终 included/excluded 与讨论理由。
- reviewer 改判会让已有仲裁失效并重新计算，但旧决定和旧仲裁保留在审计历史中。

## 全文资格评审

标题与摘要阶段完成后，使用 `screen fulltext configure` 或 Web 的“报告全文”阶段
启用最终资格评审：

- 每个标题候选都必须取得全文，或明确记录 `not_retrieved` 及原因。
- 上传并关联 PDF/TXT/MD 后，系统自动记录已取得全文。
- 全文排除必须选择稳定的主要原因代码，并填写具体判断依据。
- 双人模式沿用两位 reviewer，决定继续由服务器端隔离；相同排除决定但原因代码
  不同也需要仲裁。
- 只有全文最终 included 的研究进入后续证据提取；旧项目未启用全文阶段时保持
  原有兼容行为。
- `prisma_flow.json` 和项目归档保存当前流程计数、原因汇总及完整事件轨迹。

系统提供的是可复核的操作记录，不会自动判断检索是否穷尽、报告与研究是否一一
对应，也不会自动声称 PRISMA 合规。

方法学依据：

- [Cochrane Handbook Chapter 4](https://training.cochrane.org/handbook/current/chapter-04)
  建议至少两人独立作出最终纳入决定，并预先规定分歧解决方式。
- [Cochrane Handbook Chapter 5](https://training.cochrane.org/handbook/current/chapter-05)
  建议保留原始提取结果、共识数据及分歧解决记录。
- [Cochrane Handbook Chapter 7](https://training.cochrane.org/handbook/current/chapter-07)
  强调独立评价、透明理由、标准化试评与分歧讨论。
- [PRISMA 2020 flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram)
  区分记录筛选、报告获取、全文资格评估、排除原因和最终纳入研究。
- [PRISMA-S](https://www.equator-network.org/reporting-guidelines/prisma-s/)
  要求完整报告来源、检索策略与检索日期；当前系统保存运行检索信息，但仍需研究者
  检查各数据库报告要求。

## `maybe` 的处理

单人模式为兼容探索性工作流，`maybe` 在继续综合时暂时视为纳入。双人模式中
`maybe` 是待讨论状态，必须仲裁为 included 或 excluded 后才能继续。

## 研究矩阵

`study_matrix.csv` 使用 UTF-8 BOM，可直接用 Excel 打开。建议增加学科特有字段，并锁定字段定义后再进行双人抽取。
