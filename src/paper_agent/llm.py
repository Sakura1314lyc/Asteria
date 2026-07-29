from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from .config import Settings
from .net import NetworkError, request_json


class LLMError(RuntimeError):
    pass


class LanguageModel(Protocol):
    def json(
        self,
        *,
        name: str,
        schema: dict[str, Any],
        instructions: str,
        user_input: str,
    ) -> dict[str, Any]: ...

    def text(self, *, instructions: str, user_input: str) -> str: ...


def _extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if chunks:
        return "".join(chunks)
    error = response.get("error")
    if error:
        raise LLMError(f"Model returned an error: {error}")
    raise LLMError("Model response did not contain output text")


class OpenAIResponsesLLM:
    """OpenAI-compatible adapter for Responses or Chat Completions APIs."""

    def __init__(
        self,
        settings: Settings,
        api_key: str | None = None,
        api_format: str = "responses",
        structured_output: str = "json_schema",
    ):
        self.settings = settings
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_format = api_format
        self.structured_output = structured_output
        if api_format not in {"responses", "chat_completions"}:
            raise LLMError(f"Unsupported API format: {api_format}")
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is missing. Add it to .env or use --demo.")

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = (
            "responses" if self.api_format == "responses" else "chat/completions"
        )
        try:
            return request_json(
                f"{self.settings.base_url}/{endpoint}",
                method="POST",
                headers={"Authorization": f"Bearer {self.api_key}"},
                payload=payload,
                timeout=self.settings.request_timeout,
                retries=self.settings.max_retries,
            )
        except NetworkError as exc:
            message = str(exc)
            if "HTTP 404" in message and self.api_format == "responses":
                message = (
                    "模型服务未提供 Responses API（/responses 返回 404）。"
                    "请把连接的 API 格式改为 Chat Completions。"
                )
            elif "HTTP 401" in message:
                message = "模型服务拒绝了 API Key（HTTP 401），请检查密钥。"
            elif "HTTP 402" in message:
                message = "模型账户余额不足（HTTP 402）。"
            elif "HTTP 429" in message:
                message = "模型服务触发限流（HTTP 429），请稍后重试。"
            raise LLMError(message) from exc

    def _chat_output(self, response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("Chat Completions response did not contain choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        raise LLMError("Chat Completions response did not contain message content")

    def json(
        self,
        *,
        name: str,
        schema: dict[str, Any],
        instructions: str,
        user_input: str,
    ) -> dict[str, Any]:
        if self.api_format == "responses":
            payload = {
                "model": self.settings.model,
                "instructions": instructions,
                "input": user_input,
                "reasoning": {"effort": self.settings.reasoning_effort},
                "text": {
                    "verbosity": "medium",
                    "format": {
                        "type": "json_schema",
                        "name": name,
                        "schema": schema,
                        "strict": True,
                    },
                },
            }
        else:
            if self.structured_output == "json_object":
                instructions = (
                    f"{instructions}\n\nReturn one valid JSON object that matches "
                    "this JSON Schema exactly. Do not add Markdown fences.\n"
                    + json.dumps(schema, ensure_ascii=False)
                )
                response_format: dict[str, Any] = {"type": "json_object"}
            else:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": name,
                        "schema": schema,
                        "strict": True,
                    },
                }
            payload = {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_input},
                ],
                "response_format": response_format,
            }
        response = self._request(payload)
        raw = (
            _extract_output_text(response)
            if self.api_format == "responses"
            else self._chat_output(response)
        )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Model returned invalid structured JSON: {raw[:500]}"
            ) from exc
        if not isinstance(value, dict):
            raise LLMError("Structured model output must be a JSON object")
        return value

    def text(self, *, instructions: str, user_input: str) -> str:
        if self.api_format == "responses":
            payload = {
                "model": self.settings.model,
                "instructions": instructions,
                "input": user_input,
                "reasoning": {"effort": self.settings.reasoning_effort},
                "text": {"verbosity": "high"},
            }
        else:
            payload = {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_input},
                ],
            }
        response = self._request(payload)
        return (
            _extract_output_text(response)
            if self.api_format == "responses"
            else self._chat_output(response)
        ).strip()


class DemoLLM:
    """Deterministic offline model for smoke tests and product demonstrations."""

    def __init__(self, topic: str = ""):
        self.topic = topic

    def json(
        self,
        *,
        name: str,
        schema: dict[str, Any],
        instructions: str,
        user_input: str,
    ) -> dict[str, Any]:
        if name == "research_plan":
            topic_match = re.search(r"Topic:\s*(.+)", user_input)
            topic = topic_match.group(1).strip() if topic_match else self.topic
            return {
                "refined_question": f"{topic} 的主要研究进展、证据边界与未来方向是什么？",
                "perspectives": ["概念与理论", "方法与数据", "实证结果", "局限与争议"],
                "queries": [
                    {"query": topic, "purpose": "核心研究"},
                    {"query": f"{topic} systematic review", "purpose": "综述证据"},
                    {"query": f"{topic} methods limitations", "purpose": "方法与局限"},
                ],
                "inclusion_criteria": ["与研究问题直接相关", "包含可核验摘要或元数据"],
                "exclusion_criteria": ["主题仅弱相关", "重复记录"],
                "sections": [
                    "研究背景",
                    "主要方法",
                    "证据综合",
                    "局限与争议",
                    "研究空白",
                ],
            }
        if name == "evidence_cards":
            records_text = user_input.split("Retrieved records:\n", 1)[-1]
            records = json.loads(records_text)
            cards = []
            for record in records:
                abstract = str(record.get("abstract") or "")
                first_sentence = re.split(r"(?<=[.!?。！？])\s+", abstract.strip())[0]
                cards.append(
                    {
                        "paper_id": record["paper_id"],
                        "relevance": "该文献被检索与研究问题相关，需结合原文复核。",
                        "objective": record.get("title") or "摘要未报告",
                        "methods": "摘要信息有限，未做超出摘要的推断。",
                        "data_or_sample": "摘要未明确报告或离线演示未抽取。",
                        "findings": [first_sentence or "摘要未提供可抽取结论。"],
                        "limitations": ["当前证据卡仅基于题录与摘要。"],
                        "confidence": "medium" if abstract else "low",
                        "cs_evidence": {
                            "contribution_type": "unclear",
                            "problem": "离线演示未抽取",
                            "core_contribution": first_sentence or "摘要未提供",
                            "approach": "离线演示未抽取",
                            "datasets": [],
                            "tasks": [],
                            "baselines": [],
                            "metrics": [],
                            "headline_results": [first_sentence]
                            if first_sentence
                            else [],
                            "ablations": [],
                            "compute": "未报告",
                            "implementation_details": "未报告",
                            "code_availability": "unclear",
                            "code_urls": list(record.get("code_urls") or []),
                            "dataset_urls": list(record.get("dataset_urls") or []),
                            "threats_to_validity": ["仅基于摘要"],
                            "security_ethics": [],
                            "evidence_level": "unclear",
                        },
                    }
                )
            return {"cards": cards}
        raise LLMError(f"DemoLLM does not support structured task {name!r}")

    def text(self, *, instructions: str, user_input: str) -> str:
        metadata_match = re.search(
            r"Paper metadata:\n(\[.*?\])\n\nEvidence cards:",
            user_input,
            flags=re.DOTALL,
        )
        papers = json.loads(metadata_match.group(1)) if metadata_match else []
        citations = " ".join(f"[{paper['paper_id']}]" for paper in papers[:4])
        references = []
        for paper in papers:
            authors = ", ".join(paper.get("authors") or ["作者未知"])
            locator = paper.get("doi") or paper.get("url") or "无链接"
            references.append(
                f"- [{paper['paper_id']}] {authors}. "
                f"({paper.get('year') or '年份未知'}). {paper.get('title')}. "
                f"{paper.get('venue') or ''}. {locator}"
            )
        return f"""# {self.topic or "论文科研"}：证据导向研究简报

## 执行摘要

本报告演示了从学术检索、证据卡到引用审计的完整流程。当前内容由离线演示模型生成，结论仅用于验证软件工作流，不应直接用于论文投稿。{citations}

## 研究范围与方法

系统依据多视角检索计划汇总题录和摘要，去重后建立逐篇证据卡。由于没有阅读全文，所有判断均应视为初步证据，后续需回到原文核验。{citations}

## 证据综合

已检索文献从不同角度覆盖研究主题。离线模式不会补写摘要之外的方法、样本或效应量，因此这里保留证据边界，并把来源 ID 紧邻相关陈述。{citations}

## 局限、争议与研究空白

摘要级分析可能遗漏实验设置、负面结果与附录信息；检索数据库的覆盖范围也会影响结论。正式研究应增加全文筛选、质量评价和可复现的数据提取。{citations}

## 结论

该演示说明工作流已能生成可追踪产物，但学术结论必须在真实模型模式下结合原文复核。

## 参考文献

{chr(10).join(references)}
"""
