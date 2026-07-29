# Contributing

## 本地检查

```powershell
$env:PYTHONPATH = "src"
python -m compileall -q src tests
python -m unittest discover -s tests -v
python -m pip wheel --no-deps .
```

## 设计原则

- 来源元数据必须来自检索结果，不由模型补写。
- 人工决定与自动建议必须在数据模型中分开。
- 新阶段必须有检查点、专门产物和恢复测试。
- 可选服务不得破坏核心 CLI 的零依赖运行。
- 结构审计不得被描述为语义事实核查。
- 对外部接口使用可替换协议和明确错误。

## Pull Request

说明问题、设计选择、数据迁移、测试和证据边界。涉及数据库 schema 时必须提供向前迁移方案。

