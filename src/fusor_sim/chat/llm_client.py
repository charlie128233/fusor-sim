"""Client per endpoint LLM OpenAI-compatible (vLLM, llama.cpp, LM Studio...).

Configurazione via ambiente:
- FUSOR_LLM_BASE  (default http://127.0.0.1:8000/v1)
- FUSOR_LLM_MODEL (default: il primo modello esposto da /models)
"""

import os

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000/v1"


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 120.0,
    ):
        self.base = (base_url or os.environ.get("FUSOR_LLM_BASE", DEFAULT_BASE)).rstrip("/")
        self._model = model or os.environ.get("FUSOR_LLM_MODEL")
        self.timeout_s = timeout_s

    def model(self) -> str:
        if not self._model:
            resp = httpx.get(f"{self.base}/models", timeout=10.0)
            resp.raise_for_status()
            self._model = resp.json()["data"][0]["id"]
        return self._model

    def available(self) -> bool:
        try:
            return httpx.get(f"{self.base}/models", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            return False

    def __call__(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> str:
        resp = httpx.post(
            f"{self.base}/chat/completions",
            json={
                "model": self.model(),
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
