"""LLM 客户端基类和工厂"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, AsyncIterator
from enum import Enum

import httpx


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: Optional[str] = None
    raw_response: Optional[dict] = None


@dataclass
class LLMStreamResponse:
    """LLM 流式响应"""
    delta: str
    is_final: bool = False


class LLMProvider(Enum):
    """LLM 提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider(self) -> LLMProvider:
        """获取提供商"""
        return LLMProvider.DEEPSEEK  # 默认

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        生成响应

        Args:
            prompt: 用户提示
            system: 系统提示
            **kwargs: 额外参数

        Returns:
            LLMResponse: 响应
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, **kwargs)

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        """
        聊天

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            **kwargs: 额外参数

        Returns:
            LLMResponse: 响应
        """
        pass

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[LLMStreamResponse]:
        """
        流式生成

        Args:
            prompt: 用户提示
            system: 系统提示
            **kwargs: 额外参数

        Yields:
            LLMStreamResponse: 流式响应
        """
        pass

    async def close(self) -> None:
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class DeepSeekClient(LLMClient):
    """DeepSeek 客户端"""

    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.DEEPSEEK

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            model=model,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
        }

        # DeepSeek 特定参数
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0].get("finish_reason"),
            raw_response=data,
        )

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[LLMStreamResponse]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            yield LLMStreamResponse(delta="", is_final=True)
                            break
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        yield LLMStreamResponse(delta=delta)


class OpenAIClient(LLMClient):
    """OpenAI 客户端"""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o-mini"

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OPENAI

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            model=model,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0].get("finish_reason"),
            raw_response=data,
        )

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[LLMStreamResponse]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            yield LLMStreamResponse(delta="", is_final=True)
                            break
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        yield LLMStreamResponse(delta=delta)


class OllamaClient(LLMClient):
    """Ollama 本地模型客户端"""

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3"

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OLLAMA

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "llama3",
        **kwargs,
    ):
        super().__init__(
            api_key=None,  # Ollama 不需要 API Key
            base_url=base_url or self.DEFAULT_BASE_URL,
            model=model,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "stream": False,
        }

        if self.temperature:
            payload["options"] = {"temperature": self.temperature}
        if self.max_tokens:
            payload["options"] = payload.get("options", {})
            payload["options"]["num_predict"] = self.max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("done_reason"),
            raw_response=data,
        )

    async def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[LLMStreamResponse]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        delta = chunk["message"].get("content", "")
                        is_final = chunk.get("done", False)
                        yield LLMStreamResponse(delta=delta, is_final=is_final)


# =============================================================================
# 工厂函数
# =============================================================================

def create_llm_client(
    provider: str = "deepseek",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> LLMClient:
    """
    创建 LLM 客户端

    Args:
        provider: 提供商 (deepseek, openai, ollama)
        api_key: API Key
        base_url: API 基础 URL
        model: 模型名称
        **kwargs: 额外参数

    Returns:
        LLMClient: LLM 客户端实例
    """
    provider = provider.lower()

    if provider == "deepseek":
        return DeepSeekClient(
            api_key=api_key,
            base_url=base_url,
            model=model or DeepSeekClient.DEFAULT_MODEL,
            **kwargs,
        )
    elif provider == "openai":
        return OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            model=model or OpenAIClient.DEFAULT_MODEL,
            **kwargs,
        )
    elif provider == "ollama":
        return OllamaClient(
            base_url=base_url,
            model=model or OllamaClient.DEFAULT_MODEL,
            **kwargs,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")
