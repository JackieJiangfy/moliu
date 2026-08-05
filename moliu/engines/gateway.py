"""DeepSeek API 网关 — HTTP 客户端 + 自动重试"""

from __future__ import annotations

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    retry_base,
)

from moliu.config import Config


class DeepSeekAPIError(Exception):
    """DeepSeek API 返回格式异常"""
    pass


class _RetryIfServerError(retry_base):
    """只重试 5xx 和 429；4xx（鉴权/参数错误）不重试"""

    def __call__(self, attempt):
        exc = attempt.exception()
        if exc is None:
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code >= 500 or code == 429
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, (httpx.ConnectError, httpx.ReadError)):
            return True
        return False


class DeepSeekGateway:
    """DeepSeek API 封装 — 复用 httpx 连接"""

    def __init__(self, config: Config):
        self.config = config
        self.usage_tracker = None  # set by caller for token logging
        self._client = httpx.AsyncClient(
            base_url=config.deepseek_base_url,
            headers={
                "Authorization": f"Bearer {config.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.deepseek_timeout,
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        chapter_num: int | None = None,
    ) -> tuple[str, int]:
        temp = temperature if temperature is not None else self.config.default_temperature
        max_tok = max_tokens if max_tokens is not None else self.config.default_max_tokens

        payload = {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temp,
            "max_tokens": max_tok,
        }

        retryer = AsyncRetrying(
            stop=stop_after_attempt(self.config.deepseek_max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=_RetryIfServerError(),
            reraise=True,
        )

        async for attempt in retryer:
            with attempt:
                response = await self._client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    raise DeepSeekAPIError(
                        f"API 返回格式异常: {e}. 原始响应: {str(data)[:500]}"
                    ) from e
                tokens = data.get("usage", {}).get("total_tokens", 0)
                prompt_tok = data.get("usage", {}).get("prompt_tokens", 0)
                completion_tok = data.get("usage", {}).get("completion_tokens", 0)
                if self.usage_tracker:
                    self.usage_tracker.log(
                        command="generate", model=self.config.deepseek_model,
                        tokens=tokens, prompt_tokens=prompt_tok,
                        completion_tokens=completion_tok,
                        chapter_num=chapter_num,
                    )
                return content, tokens

    async def close(self) -> None:
        await self._client.aclose()
