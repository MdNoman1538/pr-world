"""LLM access: Gemini (real) and a Mock (offline tests and demos).

Trust practices built in:
- structured JSON output validated against a Pydantic schema (no free text parsing)
- low temperature and pinned model names (configurable) for repeatable runs
- every prompt and response is appended to the run's llm_log.jsonl (audit trail)
- retries with backoff on rate limits / transient errors
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class _Logger:
    def __init__(self, path: Optional[str]):
        self.path = path
        self.lock = threading.Lock()

    def write(self, record: Dict) -> None:
        if not self.path:
            return
        with self.lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class GeminiClient:
    """Thin wrapper over the google-genai SDK (pip install google-genai)."""

    def __init__(self, api_key: Optional[str] = None, temperature: float = 0.1,
                 log_path: Optional[str] = None, max_retries: int = 5, timeout_s: int = 180):
        try:
            from google import genai  # noqa: F401
            from google.genai import types  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise LLMError("google-genai is not installed. Run: pip install -r requirements.txt") from e
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise LLMError("No API key. Set GEMINI_API_KEY in your environment (never commit it).")
        from google import genai
        self._genai = genai
        self.client = genai.Client(api_key=key)
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.log = _Logger(log_path)
        self.calls = 0
        self.usage = {"prompt_tokens": 0, "output_tokens": 0}

    def list_models(self):
        return [m.name for m in self.client.models.list()]

    def generate(self, *, role: str, model: str, system: str, prompt: str, schema: Type[T]) -> T:
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                resp = self.client.models.generate_content(model=model, contents=prompt, config=config)
                text = resp.text or ""
                try:
                    obj = schema.model_validate_json(text)
                except ValidationError:
                    parsed = getattr(resp, "parsed", None)
                    if isinstance(parsed, schema):
                        obj = parsed
                    elif isinstance(parsed, dict):
                        obj = schema.model_validate(parsed)
                    else:
                        raise
                meta = getattr(resp, "usage_metadata", None)
                if meta is not None:
                    self.usage["prompt_tokens"] += getattr(meta, "prompt_token_count", 0) or 0
                    self.usage["output_tokens"] += getattr(meta, "candidates_token_count", 0) or 0
                self.calls += 1
                self.log.write({"role": role, "model": model, "attempt": attempt, "seconds": round(time.time() - t0, 2),
                                "system": system, "prompt": prompt, "response": text})
                return obj
            except Exception as e:  # SDK raises various error types; retry on all, log each
                last_err = e
                msg = str(e)
                self.log.write({"role": role, "model": model, "attempt": attempt, "error": msg[:2000]})
                transient = any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE",
                                                   "DEADLINE", "timeout", "Timeout")) or isinstance(e, ValidationError)
                if attempt == self.max_retries or not transient:
                    break
                time.sleep(min(60, (2 ** attempt) + random.random() * 2))
        raise LLMError(f"{role}: Gemini call failed after retries: {last_err}")


class MockClient:
    """Offline stand-in. Returns fixture JSON per role, or a neutral default.

    Fixture file format: {"<role>": <json object matching the schema>, ...}
    Roles: specialist:<dimension> (correctness, architecture, safety, tests, maintainability, performance),
           validator, radar, fixer, draft-policy
    """

    def __init__(self, fixture_path: Optional[str] = None, log_path: Optional[str] = None):
        self.fixtures: Dict = {}
        if fixture_path:
            with open(fixture_path, encoding="utf-8") as fh:
                self.fixtures = json.load(fh)
        self.log = _Logger(log_path)
        self.calls = 0
        self.usage = {"prompt_tokens": 0, "output_tokens": 0}

    def list_models(self):
        return ["mock"]

    def generate(self, *, role: str, model: str, system: str, prompt: str, schema: Type[T]) -> T:
        self.calls += 1
        data = self.fixtures.get(role)
        if data is None:
            data = self._default(role, prompt)
        obj = schema.model_validate(data)
        self.log.write({"role": role, "model": "mock", "system": system, "prompt": prompt,
                        "response": obj.model_dump_json()})
        return obj

    @staticmethod
    def _default(role: str, prompt: str) -> Dict:
        if role.startswith("specialist:"):
            return {"orientation": "Mock run: no model was called.", "requirement_alignment": "unknown",
                    "alignment_reason": "Mock mode cannot judge the requirement.", "findings": [],
                    "refusals": [{"topic": "Model judgment", "reason": "Mock mode: no LLM review was performed."}],
                    "checked": []}
        if role == "validator":
            import re
            pairs = re.findall(r"\[id=([A-Z]\d+)\] \[severity=(\w+)\]", prompt)
            return {"verdicts": [{"finding_id": i, "q1_nitpick": sev == "Nit", "q2_hallucination": False,
                                  "q3_severity": sev, "duplicate_of": "",
                                  "reason": "mock: kept as proposed"} for i, sev in pairs]}
        if role == "radar":
            import re
            hunks = re.findall(r"^\[(H\d+)\]", prompt, re.M)
            return {"items": [], "hunks": [{"hunk_id": h, "classification": "unclear", "item_ids": [],
                                            "reason": "mock mode"} for h in hunks]}
        if role == "fixer":
            return {"fixes": []}
        if role == "requirement:analyst":
            import re
            lines = [l.strip(" -*\t") for l in prompt.splitlines() if re.match(r"^\s*[-*] ", l)]
            if not lines:   # no bullet list: one item per sentence of the requirement body
                body = prompt.split("REQUIREMENT", 1)[-1]
                lines = [x.strip() for x in re.split(r"(?<=[.!?])\s+", body) if len(x.strip()) > 20 and not x.strip().startswith("#")]
            return {"items": [{"id": f"R{i}", "text": t[:200], "kind": "behaviour", "testable": True, "unclear": ""}
                              for i, t in enumerate(lines[:12], start=1)]}
        if role == "requirement:interpreter":
            return {"behaviours": []}
        if role == "requirement:judge":
            import re
            ids = re.findall(r"^\[(R\d+)\]", prompt, re.M)
            return {"results": [{"item_id": i, "status": "missing", "behaviour_ids": [],
                                 "reason": "mock: no behaviours were described"} for i in ids], "extra_behaviours": []}
        if role.startswith("panel"):
            return {"real": True, "nitpick": False, "severity": "Blocker", "reason": "mock: kept"}
        if role == "investigator":
            return {"action": "conclude", "argument": "", "verdict": "unsure", "evidence": "", "reason": "mock mode"}
        if role == "writer":
            return {"items": []}
        if role == "draft-policy":
            return {"areas": [], "notes": "mock"}
        return {}


def make_client(mock: Optional[str], log_path: Optional[str], temperature: float):
    if mock is not None:
        return MockClient(mock or None, log_path)
    return GeminiClient(temperature=temperature, log_path=log_path)
