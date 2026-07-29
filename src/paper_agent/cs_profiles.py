from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .cs_taxonomy import DomainScore


@dataclass(frozen=True, slots=True)
class CSEvidenceProfile:
    id: str
    primary_questions: tuple[str, ...]
    required_comparisons: tuple[str, ...]
    validity_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROFILES = {
    "algorithm_benchmark": CSEvidenceProfile(
        id="algorithm_benchmark",
        primary_questions=(
            "What task and assumptions are defined?",
            "Which datasets, splits, baselines, metrics, and uncertainty estimates are used?",
            "Which component causes the measured improvement?",
        ),
        required_comparisons=(
            "strong contemporary baselines",
            "ablations and sensitivity",
            "accuracy, robustness, efficiency, and compute",
        ),
        validity_checks=(
            "data leakage and benchmark contamination",
            "hyperparameter and seed sensitivity",
            "out-of-distribution generalization",
        ),
    ),
    "systems_experiment": CSEvidenceProfile(
        id="systems_experiment",
        primary_questions=(
            "What system design and operational assumptions are proposed?",
            "Which hardware, workload, scale, and deployment environment are evaluated?",
            "How do throughput, latency, availability, resource use, and cost change?",
        ),
        required_comparisons=(
            "production-quality or state-of-the-art systems",
            "microbenchmarks and end-to-end workloads",
            "normal operation and failure scenarios",
        ),
        validity_checks=(
            "representativeness of workload and cluster scale",
            "warm-up, caching, and tail-latency methodology",
            "unreported operational complexity",
        ),
    ),
    "security_evaluation": CSEvidenceProfile(
        id="security_evaluation",
        primary_questions=(
            "What threat model, attacker capability, and security goal are defined?",
            "Is the attack or defense evaluated against adaptive adversaries?",
            "What false-positive, false-negative, usability, and performance costs occur?",
        ),
        required_comparisons=(
            "relevant attacks and defenses",
            "adaptive and transfer settings",
            "security benefit versus operational cost",
        ),
        validity_checks=(
            "threat-model mismatch",
            "dataset or lab-only realism",
            "dual-use disclosure and ethical safeguards",
        ),
    ),
    "empirical_software_engineering": CSEvidenceProfile(
        id="empirical_software_engineering",
        primary_questions=(
            "How were projects, repositories, developers, or tasks sampled?",
            "How are constructs operationalized and outcomes measured?",
            "Are confounders, leakage, and temporal effects controlled?",
        ),
        required_comparisons=(
            "multiple projects, languages, and time periods",
            "developer-relevant and automated outcomes",
            "statistical and practical effect sizes",
        ),
        validity_checks=(
            "construct, internal, external, and conclusion validity",
            "repository and benchmark duplication",
            "human evaluation protocol and inter-rater reliability",
        ),
    ),
    "theory": CSEvidenceProfile(
        id="theory",
        primary_questions=(
            "What formal problem, model, and assumptions are stated?",
            "What theorem, bound, reduction, or impossibility result is established?",
            "How tight are the bounds and which cases remain open?",
        ),
        required_comparisons=(
            "previous upper and lower bounds",
            "assumption strength and model generality",
            "constructive algorithm versus existential result",
        ),
        validity_checks=(
            "hidden or incomparable assumptions",
            "proof dependencies and edge cases",
            "gap between asymptotic and practical regimes",
        ),
    ),
    "theory_tool": CSEvidenceProfile(
        id="theory_tool",
        primary_questions=(
            "What semantics, property, or verification obligation is formalized?",
            "What soundness, completeness, or correctness result is provided?",
            "How does the implementation behave on representative programs?",
        ),
        required_comparisons=(
            "formal guarantees and implementation tradeoffs",
            "benchmark suites and real codebases",
            "precision, recall, runtime, and scalability",
        ),
        validity_checks=(
            "unsound approximations or unsupported language features",
            "benchmark representativeness",
            "proof-to-implementation gap",
        ),
    ),
    "user_study": CSEvidenceProfile(
        id="user_study",
        primary_questions=(
            "Who participated and how were they recruited?",
            "What tasks, conditions, measures, and analysis plan were used?",
            "What qualitative and quantitative evidence supports the claim?",
        ),
        required_comparisons=(
            "appropriate control or baseline condition",
            "objective outcomes and participant experience",
            "effect size, uncertainty, and qualitative triangulation",
        ),
        validity_checks=(
            "sample size and population representativeness",
            "novelty, learning, and demand effects",
            "accessibility, privacy, and participant risk",
        ),
    ),
    "robotics_experiment": CSEvidenceProfile(
        id="robotics_experiment",
        primary_questions=(
            "Which robot, sensors, environment, and task assumptions are used?",
            "How many real-world and simulated trials are run?",
            "How are safety, failure recovery, and sim-to-real gaps evaluated?",
        ),
        required_comparisons=(
            "simulation and physical deployment",
            "task success, robustness, sample efficiency, and safety",
            "strong planning, control, or learning baselines",
        ),
        validity_checks=(
            "cherry-picked demonstrations",
            "environment and hardware sensitivity",
            "insufficient failure and safety testing",
        ),
    ),
    "hardware_experiment": CSEvidenceProfile(
        id="hardware_experiment",
        primary_questions=(
            "What architecture, process, memory, and workload assumptions are used?",
            "Are results measured on silicon, FPGA, simulation, or analytical models?",
            "How do performance, area, power, energy, and cost trade off?",
        ),
        required_comparisons=(
            "iso-process or normalized comparisons",
            "representative workloads",
            "performance, power, area, and accuracy",
        ),
        validity_checks=(
            "technology-node normalization",
            "simulator and synthesis accuracy",
            "unreported data movement or system overhead",
        ),
    ),
    "numerical_experiment": CSEvidenceProfile(
        id="numerical_experiment",
        primary_questions=(
            "What equations, discretization, solver, and error criteria are used?",
            "What convergence, stability, and complexity properties are established?",
            "Which reference solutions and hardware configurations are evaluated?",
        ),
        required_comparisons=(
            "accuracy versus runtime and memory",
            "convergence across resolutions",
            "standard solvers and realistic problem sizes",
        ),
        validity_checks=(
            "conditioning and numerical stability",
            "mesh, step-size, and tolerance sensitivity",
            "hardware-dependent speedup claims",
        ),
    ),
    "algorithm_system_hybrid": CSEvidenceProfile(
        id="algorithm_system_hybrid",
        primary_questions=(
            "Which gains come from the algorithm and which from system optimization?",
            "Are quality, latency, throughput, memory, and cost jointly reported?",
            "Can the method be reproduced across datasets and hardware?",
        ),
        required_comparisons=(
            "algorithm-only and system-only ablations",
            "quality-efficiency Pareto frontier",
            "end-to-end and component benchmarks",
        ),
        validity_checks=(
            "hardware or implementation advantage disguised as algorithmic gain",
            "unfair baseline tuning",
            "missing end-to-end cost",
        ),
    ),
    "mixed": CSEvidenceProfile(
        id="mixed",
        primary_questions=(
            "What type of contribution and evidence is actually presented?",
            "Which claims are formal, empirical, observational, or speculative?",
        ),
        required_comparisons=(
            "claim-to-evidence alignment",
            "relevant baselines for each contribution type",
        ),
        validity_checks=(
            "mixing incomparable evidence types",
            "overgeneralizing from a narrow evaluation",
        ),
    ),
}


def protocols_for_domains(domains: list[DomainScore]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    values: list[dict[str, Any]] = []
    for domain in domains:
        profile_id = domain.evidence_profile
        profile = PROFILES.get(profile_id, PROFILES["mixed"])
        if profile.id in seen:
            continue
        seen.add(profile.id)
        values.append(profile.to_dict())
    return values or [PROFILES["mixed"].to_dict()]
