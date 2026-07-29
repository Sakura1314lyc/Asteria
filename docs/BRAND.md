# Asteria 品牌标志

## 概念

Asteria 的标志由抽象字母 `A` 和三个相连节点组成：

- 字母 `A` 对应产品名称。
- 顶点代表研究问题。
- 两个底部节点代表论文与全文证据。
- 连线与横向连接表示证据图、引用关系和可审计综合。

标志刻意不使用机器人、对话气泡、魔法棒或星芒，避免落入通用 AI
产品图标。

## 资产

- Web 与 favicon 使用 `web/public/asteria-mark.svg`。
- React 侧栏使用 `web/src/components/Logo.tsx` 中的同源 SVG 几何。
- 生产构建输出 `src/paper_agent/web_dist/asteria-mark.svg`，由
  `/asteria-mark.svg` 提供。

## 颜色

| 用途 | 色值 |
|---|---|
| 标志底色 | `#0969DA` |
| 主线与底部节点 | `#F0F6FC` |
| 顶部研究节点 | `#79C0FF` |
| 深色侧栏 | Primer `dark-dimmed` 的 `--bgColor-default` |

颜色来自项目当前采用的 GitHub Primer 体系。单色印刷时，可将底色替换为
100% 黑，线条和节点留白。

## 使用约束

- 推荐尺寸为 32px、48px、64px 或更大；favicon 最小可使用 16px。
- 标志四周至少保留图标宽度四分之一的安全空间。
- 不拉伸、不旋转、不添加发光或渐变。
- 不改变节点位置，也不在方形底座内加入额外文字。
- 深色背景使用当前蓝色版本；浅色背景同样使用完整蓝色底座，不只显示白线。
