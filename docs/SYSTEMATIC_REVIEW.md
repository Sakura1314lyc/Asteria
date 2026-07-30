# 系统综述流程

本项目支持“系统综述准备流程”，但不会声称自动生成的结果天然符合 PRISMA 或任何学科指南。

## 推荐步骤

1. 在运行前冻结研究问题和研究方案。
2. 配置数据库、年份、关键词、语言和研究类型。
3. 保存所有检索式及检索时间。
4. 由至少两名研究者独立完成最终纳入决定；建议标题/摘要阶段也采用双人筛选。
5. 每个决定保存理由和 reviewer，预先规定讨论与第三方仲裁规则。
6. 对纳入论文导入全文。
7. 由两名研究者复核关键证据卡。
8. 根据研究设计选择正式风险偏倚工具。
9. 只有在效应量与异质性条件适合时进行统计合并。
10. 逐条核对报告中的引文与原文。

## 自动化与人工职责

| 环节 | 系统可以做 | 人必须负责 |
|---|---|---|
| 计划 | 多视角问题、检索式草案 | 冻结方案、注册方案 |
| 检索 | API 查询、去重、排序 | 数据库覆盖与日期确认 |
| 筛选 | 透明规则建议 | 最终纳排与冲突解决 |
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

方法学依据：

- [Cochrane Handbook Chapter 4](https://training.cochrane.org/handbook/current/chapter-04)
  建议至少两人独立作出最终纳入决定，并预先规定分歧解决方式。
- [Cochrane Handbook Chapter 5](https://training.cochrane.org/handbook/current/chapter-05)
  建议保留原始提取结果、共识数据及分歧解决记录。
- [Cochrane Handbook Chapter 7](https://training.cochrane.org/handbook/current/chapter-07)
  强调独立评价、透明理由、标准化试评与分歧讨论。

## `maybe` 的处理

单人模式为兼容探索性工作流，`maybe` 在继续综合时暂时视为纳入。双人模式中
`maybe` 是待讨论状态，必须仲裁为 included 或 excluded 后才能继续。

## 研究矩阵

`study_matrix.csv` 使用 UTF-8 BOM，可直接用 Excel 打开。建议增加学科特有字段，并锁定字段定义后再进行双人抽取。
