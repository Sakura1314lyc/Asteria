from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, replace
from typing import ClassVar
from urllib.parse import urlparse

from .config import Settings
from .domain import new_id, utc_now


class ConnectionError(RuntimeError):
    pass


@dataclass(slots=True)
class ModelConnection:
    id: str
    name: str
    base_url: str
    model: str
    api_format: str
    provider: str
    structured_output: str
    notice: str
    source: str
    configured: bool
    created_at: str
    api_key: str = ""

    def public_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("api_key", None)
        return data


def validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConnectionError("Base URL 必须是完整的 http(s) 地址")
    if parsed.username or parsed.password:
        raise ConnectionError("Base URL 不能包含用户名或密码")
    if len(normalized) > 500:
        raise ConnectionError("Base URL 过长")
    return normalized


def infer_connection_protocol(
    base_url: str,
    api_format: str,
) -> tuple[str, str, str, str]:
    hostname = (urlparse(base_url).hostname or "").casefold()
    if hostname == "api.deepseek.com" or hostname.endswith(".deepseek.com"):
        notice = ""
        if api_format != "chat_completions":
            notice = "DeepSeek 不提供 /responses，已自动切换到 Chat Completions。"
        return "deepseek", "chat_completions", "json_object", notice
    if hostname == "api.openai.com" or hostname.endswith(".openai.com"):
        return "openai", api_format, "json_schema", ""
    return "openai_compatible", api_format, "json_schema", ""


class ConnectionRegistry:
    """Keeps provider credentials in process memory and exposes redacted metadata."""

    FORMATS: ClassVar[set[str]] = {"responses", "chat_completions"}

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self._connections: dict[str, ModelConnection] = {}

    def _environment_connection(self) -> ModelConnection:
        base_url = validate_base_url(self.settings.base_url)
        provider, api_format, structured_output, notice = (
            infer_connection_protocol(base_url, "responses")
        )
        return ModelConnection(
            id="env-openai",
            name="环境变量",
            base_url=base_url,
            model=self.settings.model,
            api_format=api_format,
            provider=provider,
            structured_output=structured_output,
            notice=notice,
            source="environment",
            configured=bool(os.getenv("OPENAI_API_KEY")),
            created_at="",
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    def list(self) -> list[dict[str, object]]:
        with self._lock:
            session = [
                item.public_dict()
                for item in sorted(
                    self._connections.values(),
                    key=lambda connection: connection.created_at,
                    reverse=True,
                )
            ]
        return [self._environment_connection().public_dict(), *session]

    def create(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_format: str,
        api_key: str,
    ) -> dict[str, object]:
        cleaned_name = name.strip()
        cleaned_model = model.strip()
        cleaned_key = api_key.strip()
        if not cleaned_name or len(cleaned_name) > 100:
            raise ConnectionError("连接名称长度应为 1–100 个字符")
        if not cleaned_model or len(cleaned_model) > 200:
            raise ConnectionError("模型名称长度应为 1–200 个字符")
        if api_format not in self.FORMATS:
            raise ConnectionError("不支持的 API 格式")
        if not cleaned_key:
            raise ConnectionError("API Key 不能为空")
        cleaned_base_url = validate_base_url(base_url)
        provider, effective_format, structured_output, notice = (
            infer_connection_protocol(cleaned_base_url, api_format)
        )
        connection = ModelConnection(
            id=new_id("conn"),
            name=cleaned_name,
            base_url=cleaned_base_url,
            model=cleaned_model,
            api_format=effective_format,
            provider=provider,
            structured_output=structured_output,
            notice=notice,
            source="session",
            configured=True,
            created_at=utc_now(),
            api_key=cleaned_key,
        )
        with self._lock:
            self._connections[connection.id] = connection
        return connection.public_dict()

    def delete(self, connection_id: str) -> None:
        if connection_id == "env-openai":
            raise ConnectionError("环境变量连接不能从 Web 删除")
        with self._lock:
            if self._connections.pop(connection_id, None) is None:
                raise ConnectionError("连接不存在或服务已重启")

    def resolve(self, connection_id: str | None) -> ModelConnection:
        if not connection_id or connection_id == "env-openai":
            connection = self._environment_connection()
        else:
            with self._lock:
                connection = self._connections.get(connection_id)
            if connection is None:
                raise ConnectionError("会话连接不存在；服务重启后需要重新输入密钥")
        if not connection.configured or not connection.api_key:
            raise ConnectionError("所选连接尚未配置 API Key")
        return connection

    def llm_settings(self, connection: ModelConnection) -> Settings:
        return replace(
            self.settings,
            model=connection.model,
            base_url=connection.base_url,
        )
