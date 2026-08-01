# Contributing

## 本地检查

```powershell
python -m ruff check src tests
python -m pytest -q

pnpm --dir web typecheck
pnpm --dir web test
pnpm --dir web build
```

## 发布包检查

前端哈希资源变化后，旧 `build/lib` 可能让 setuptools 把已经删除的资源带入
wheel。发布前应在干净工作树或归档旧构建缓存后重新打包，并比较 wheel 与源码：

```powershell
python -m pip wheel . --no-deps --no-cache-dir --wheel-dir build\release
$wheel = Get-ChildItem build\release\paper_research_agent-*.whl |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
python scripts\verify_wheel.py $wheel.FullName
```

验证器要求 wheel 中的 `paper_agent/web_dist` 与当前源码文件集合完全一致，缺失和
陈旧哈希资源都会使检查失败。

## 设计原则

- 来源元数据必须来自检索结果，不由模型补写。
- 人工决定与自动建议必须在数据模型中分开。
- 新阶段必须有检查点、专门产物和恢复测试。
- 可选服务不得破坏核心 CLI 的零依赖运行。
- 结构审计不得被描述为语义事实核查。
- 对外部接口使用可替换协议和明确错误。

## Pull Request

说明问题、设计选择、数据迁移、测试和证据边界。涉及数据库 schema 时必须提供向前迁移方案。
