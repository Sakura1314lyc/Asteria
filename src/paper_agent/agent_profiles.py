from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AgentProfile:
    id: str
    name: str
    short_name: str
    description: str
    instructions: str
    capabilities: tuple[str, ...]
    recommended_review_types: tuple[str, ...]
    default_stop_for_screening: bool

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        data["recommended_review_types"] = list(self.recommended_review_types)
        return data


AGENT_PROFILES = (
    AgentProfile(
        id="deep_review",
        name="深度综述 Agent",
        short_name="深度综述",
        description="面向跨论文的脉络、争议、方法演进与研究空白。",
        instructions=(
            "优先构建方法谱系和证据冲突矩阵；区分论文明确报告、跨论文综合与"
            "研究者推断；主动寻找负面结果、边界条件和未解决问题。"
        ),
        capabilities=("多源检索", "证据综合", "争议分析", "研究议程"),
        recommended_review_types=("narrative", "scoping", "thesis"),
        default_stop_for_screening=False,
    ),
    AgentProfile(
        id="systematic_reviewer",
        name="系统综述 Agent",
        short_name="系统综述",
        description="强调协议、纳排可追溯性、覆盖率和保守结论。",
        instructions=(
            "严格遵守综述协议；为检索式记录目的；不得绕过人工纳排；报告中明确"
            "数据库覆盖、时间范围、排除理由、证据质量与缺失数据。"
        ),
        capabilities=("协议执行", "人工筛选", "质量评价", "引用审计"),
        recommended_review_types=("systematic", "scoping"),
        default_stop_for_screening=True,
    ),
    AgentProfile(
        id="benchmark_analyst",
        name="Benchmark 分析 Agent",
        short_name="Benchmark",
        description="比较数据集、基线、指标、消融和计算预算。",
        instructions=(
            "将任务定义、数据集切分、基线版本、评价指标、统计不确定性、消融、"
            "训练与推理计算量作为一等字段；避免比较不可比的数字。"
        ),
        capabilities=("基准归一化", "指标比较", "消融审计", "算力分析"),
        recommended_review_types=("narrative", "scoping", "thesis"),
        default_stop_for_screening=False,
    ),
    AgentProfile(
        id="systems_reproducibility",
        name="系统与复现 Agent",
        short_name="系统复现",
        description="面向系统、网络、数据库与安全研究的复现实证审计。",
        instructions=(
            "优先抽取硬件、软件版本、工作负载、规模、吞吐、尾延迟、资源开销、"
            "故障场景、部署条件、代码与数据可用性；把未报告字段标为未知。"
        ),
        capabilities=("系统证据", "复现评分", "威胁模型", "部署边界"),
        recommended_review_types=("narrative", "scoping", "systematic", "thesis"),
        default_stop_for_screening=False,
    ),
    AgentProfile(
        id="project_qa",
        name="项目证据问答 Agent",
        short_name="证据问答",
        description="只基于项目论文、证据卡、报告和全文片段回答。",
        instructions=(
            "每个可验证主张紧邻来源 ID；无法由项目材料支持时直接说明证据不足；"
            "不得把摘要级信息表述成全文级结论。"
        ),
        capabilities=("项目问答", "来源定位", "差异比较", "证据边界"),
        recommended_review_types=("narrative", "scoping", "systematic", "thesis"),
        default_stop_for_screening=False,
    ),
)

_BY_ID = {profile.id: profile for profile in AGENT_PROFILES}


def get_agent_profile(agent_id: str | None) -> AgentProfile:
    selected = agent_id or "deep_review"
    try:
        return _BY_ID[selected]
    except KeyError as exc:
        raise ValueError(f"Unknown agent profile: {selected}") from exc


def list_agent_profiles() -> list[dict[str, object]]:
    return [profile.to_dict() for profile in AGENT_PROFILES]
