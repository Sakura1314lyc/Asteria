# 检索器插件开发

插件必须实现：

```python
class MyRetriever:
    name = "my_index"

    def __init__(self, settings):
        self.settings = settings

    def search(self, query: str, limit: int) -> list[Paper]:
        ...
```

在插件包的 `pyproject.toml` 注册：

```toml
[project.entry-points."paper_agent.retrievers"]
my_index = "my_package.retriever:MyRetriever"
```

安装插件后：

```powershell
paper-agent plugins
```

## 插件约束

- 返回真实来源元数据，不得让模型生成 DOI、作者或年份。
- 网络错误应抛出异常，由工作流记录单个来源告警。
- 不应把 API key 写入日志、论文对象或运行产物。
- `search()` 应是只读、幂等操作。
- 对许可或服务条款受限的数据库，必须使用合规接口。

