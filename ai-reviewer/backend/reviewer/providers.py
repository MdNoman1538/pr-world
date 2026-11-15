"""Model providers and the role router.

One `RoutedClient` replaces the single Gemini client: every call names a role (specialist:safety, validator,
panel:1, requirement_judge, ...) and the team policy decides which provider and model answers it.

Built in:
- gemini     Google Gemini (google-genai SDK)
- openai     OpenAI chat completions with a JSON schema
- anthropic  Anthropic Messages API, structured output through a forced tool call
- local      any OpenAI-compatible server on your own machine (vLLM, Ollama, LM Studio, llama.cpp)
- mock       offline fixtures (tests and rehearsals)

Locked behaviour (cannot be configured off):
- every prompt and answer goes to the run's llm_log.jsonl
- the budget (calls, cost) is enforced: when it runs out, the remaining checks are reported as NOT CHECKED
- code from a local-only area is never sent to a provider outside your machine
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Dict, List, Optional, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .llm import GeminiClient, LLMError, MockClient, _Logger

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(LLMError):
    pass


class LocalOnlyViolation(LLMError):
    pass


def role_key(role: str) -> str:
    """'specialist:safety' -> 'specialist', 'panel:2' -> 'panel', 'requirement:judge' -> 'requirement_judge'."""
    if role.startswith("specialist"):
        return "specialist"
    if role.startswith("panel"):
        return "panel"
    if role.startswith("requirement:"):
        return {"analyst": "requirement_analyst", "interpreter": "change_interpreter", "judge": "requirement_judge"}[role.split(":", 1)[1]]
    return role.replace("-", "_")


def _schema_for(schema: Type[BaseModel]) -> Dict:
    s = schema.model_json_schema()
    return s


class _HTTPClient:
    """Shared retry/logging for the HTTP providers."""

    def __init__(self, name: str, base_url: str, key: Optional[str], log: _Logger, temperature: float,
                 timeout_s: int, max_retries: int = 4):
        self.name, self.base_url, self.key, self.log = name, base_url.rstrip("/"), key, log
        self.temperature, self.timeout_s, self.max_retries = temperature, timeout_s, max_retries
        self.usage = {"prompt_tokens": 0, "output_tokens": 0}
        self.calls = 0

    def _post(self, url: str, headers: Dict, body: Dict) -> Dict:
        last = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=self.timeout_s)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}")
                if r.status_code >= 400:
                    raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:600]}")
                return r.json()
            except (requests.RequestException, LLMError) as e:
                last = e
                transient = isinstance(e, requests.RequestException) or any(c in str(e) for c in ("429", "500", "502", "503", "504"))
                if attempt == self.max_retries or not transient:
                    break
                time.sleep(min(30, 2 ** attempt + random.random()))
        raise LLMError(f"{self.name} call failed: {last}")


class OpenAICompatClient(_HTTPClient):
    """OpenAI chat completions; also used for local OpenAI-compatible servers."""

    def __init__(self, *a, strict_schema: bool = True, **k):
        super().__init__(*a, **k)
        self.strict_schema = strict_schema

    def generate(self, *, role: str, model: str, system: str, prompt: str, schema: Type[T]) -> T:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        js = _schema_for(schema)
        body = {"model": model, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system + "\n\nAnswer with JSON only, matching this schema:\n" + json.dumps(js)},
                             {"role": "user", "content": prompt}]}
        body["response_format"] = ({"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": js}}
                                   if self.strict_schema else {"type": "json_object"})
        t0 = time.time()
        data = self._post(f"{self.base_url}/chat/completions", headers, body)
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        u = data.get("usage") or {}
        self.usage["prompt_tokens"] += u.get("prompt_tokens", 0)
        self.usage["output_tokens"] += u.get("completion_tokens", 0)
        self.calls += 1
        self.log.write({"role": role, "provider": self.name, "model": model, "seconds": round(time.time() - t0, 2),
                        "system": system, "prompt": prompt, "response": text})
        return schema.model_validate_json(_strip_fences(text))


class AnthropicClient(_HTTPClient):
    """Anthropic Messages API; the answer is forced through one tool whose input schema is the output schema."""

    def generate(self, *, role: str, model: str, system: str, prompt: str, schema: Type[T]) -> T:
        headers = {"Content-Type": "application/json", "x-api-key": self.key or "", "anthropic-version": "2023-06-01"}
        body = {"model": model, "max_tokens": 8000, "temperature": self.temperature, "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{"name": "answer", "description": "Return the answer in this exact structure.",
                           "input_schema": _schema_for(schema)}],
                "tool_choice": {"type": "tool", "name": "answer"}}
        t0 = time.time()
        data = self._post(f"{self.base_url}/messages", headers, body)
        out = next((c.get("input") for c in data.get("content", []) if c.get("type") == "tool_use"), None)
        u = data.get("usage") or {}
        self.usage["prompt_tokens"] += u.get("input_tokens", 0)
        self.usage["output_tokens"] += u.get("output_tokens", 0)
        self.calls += 1
        self.log.write({"role": role, "provider": self.name, "model": model, "seconds": round(time.time() - t0, 2),
                        "system": system, "prompt": prompt, "response": json.dumps(out)})
        if out is None:
            raise LLMError(f"anthropic: no structured answer for {role}")
        return schema.model_validate(out)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


class RoutedClient:
    """Sends each role to the provider/model the policy names; enforces the budget and local-only areas."""

    def __init__(self, cfg, log_path: Optional[str], mock: Optional[str] = None, local_only_active: bool = False):
        self.cfg = cfg
        self.log_path = log_path
        self.log = _Logger(log_path)
        self.mock = MockClient(mock or None, log_path) if mock is not None else None
        self.local_only_active = local_only_active
        self._clients: Dict[str, object] = {}
        self._lock = threading.Lock()
        self.calls = 0
        self.cost_eur = 0.0
        self.usage = {"prompt_tokens": 0, "output_tokens": 0}
        self.by_role: Dict[str, Dict] = {}
        self.refused: List[str] = []
        b = cfg.get("budget", default={}) or {}
        self.max_calls = int(b.get("max_calls", 40))
        self.max_cost = float(b.get("max_cost_eur", 5))
        self.call_timeout = int(b.get("call_timeout_s", 180))

    # ---------------------------------------------------------------- routing
    def route(self, role: str) -> Dict:
        key = role_key(role)
        if key == "panel":
            members = self.cfg.panel_models()
            idx = int(role.split(":")[1]) if ":" in role else 0
            m = dict(members[idx % len(members)])
        else:
            m = dict(self.cfg.model_for(key))
        if self.local_only_active and m["provider"] not in ("local", "mock"):
            local = (self.cfg.get("models", "providers", default={}) or {}).get("local")
            if not local:
                raise LocalOnlyViolation(f"{role}: this PR touches a local-only area and no local model is configured, "
                                         "so its code was not sent anywhere.")
            lm = self.cfg.get("models", "local_model") or {}
            m = {"provider": "local", "model": lm.get("model", m["model"])}
        return m

    def _client(self, provider: str):
        if self.mock is not None:
            return self.mock
        with self._lock:
            if provider in self._clients:
                return self._clients[provider]
            pconf = (self.cfg.get("models", "providers", default={}) or {}).get(provider, {}) or {}
            key = os.environ.get(pconf["key_env"]) if pconf.get("key_env") else None
            temp = float(pconf.get("temperature", 0.1))
            if provider == "gemini":
                c = GeminiClient(api_key=key, temperature=temp, log_path=self.log_path, timeout_s=self.call_timeout)
            elif provider == "openai":
                if not key:
                    raise LLMError(f"openai: set {pconf.get('key_env', 'OPENAI_API_KEY')} in .env")
                c = OpenAICompatClient("openai", pconf.get("base_url", "https://api.openai.com/v1"), key, self.log, temp, self.call_timeout)
            elif provider == "anthropic":
                if not key:
                    raise LLMError(f"anthropic: set {pconf.get('key_env', 'ANTHROPIC_API_KEY')} in .env")
                c = AnthropicClient("anthropic", pconf.get("base_url", "https://api.anthropic.com/v1"), key, self.log, temp, self.call_timeout)
            elif provider == "local":
                c = OpenAICompatClient("local", pconf.get("base_url", "http://127.0.0.1:8000/v1"), key, self.log, temp,
                                       self.call_timeout, strict_schema=False)
            elif provider == "mock":
                c = MockClient(None, self.log_path)
            else:
                raise LLMError(f"unknown provider {provider}")
            self._clients[provider] = c
            return c

    def _price(self, provider: str) -> tuple:
        p = (self.cfg.get("models", "providers", default={}) or {}).get(provider, {}) or {}
        return float(p.get("price_in_per_mtok", 0)), float(p.get("price_out_per_mtok", 0))

    # ---------------------------------------------------------------- the one entry point
    def generate(self, *, role: str, model: str = "", system: str, prompt: str, schema: Type[T]) -> T:
        with self._lock:
            if self.calls >= self.max_calls:
                self.refused.append(role)
                raise BudgetExceeded(f"{role}: budget reached ({self.max_calls} model calls)")
            if self.cost_eur >= self.max_cost > 0:
                self.refused.append(role)
                raise BudgetExceeded(f"{role}: cost cap reached ({self.max_cost} EUR)")
            self.calls += 1
        m = self.route(role)
        c = self._client(m["provider"])
        before = dict(getattr(c, "usage", {}) or {})
        out = c.generate(role=role, model=("mock" if self.mock is not None else m["model"]), system=system, prompt=prompt, schema=schema)
        after = getattr(c, "usage", {}) or {}
        din = after.get("prompt_tokens", 0) - before.get("prompt_tokens", 0)
        dout = after.get("output_tokens", 0) - before.get("output_tokens", 0)
        pin, pout = self._price(m["provider"])
        with self._lock:
            self.usage["prompt_tokens"] += din
            self.usage["output_tokens"] += dout
            cost = din / 1e6 * pin + dout / 1e6 * pout
            self.cost_eur += cost
            r = self.by_role.setdefault(role if role_key(role) == "panel" else role_key(role), {"calls": 0, "provider": m["provider"], "model": m["model"], "cost_eur": 0.0})
            r["calls"] += 1
            r["cost_eur"] = round(r["cost_eur"] + cost, 4)
        return out

    def summary(self) -> Dict:
        return {"calls": self.calls, "cost_eur": round(self.cost_eur, 4), "usage": self.usage, "by_role": self.by_role,
                "budget": {"max_calls": self.max_calls, "max_cost_eur": self.max_cost}, "refused_for_budget": self.refused,
                "local_only_active": self.local_only_active}

    def list_models(self):
        return ["routed"]
