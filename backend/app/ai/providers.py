"""Free LLM provider layer: Gemini free tier -> Groq free tier -> local Ollama.

Messages use one neutral, OpenAI-like shape inside the app:
  {"role": "system" | "user" | "assistant" | "tool", "content": str,
   "tool_calls": [{"id", "name", "arguments": dict}],   # assistant only
   "tool_call_id": str, "name": str}                     # tool only
Each provider converts to its own wire format.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


class NoLLMAvailable(Exception):
    pass


@dataclass
class LLMResult:
    text: str | None
    tool_calls: list[dict] = field(default_factory=list)
    provider: str = ""


class OpenAICompatProvider:
    """Groq and Ollama both speak the OpenAI chat-completions format."""

    def __init__(self, name: str, base_url: str, model: str, api_key: str | None, timeout: float):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        wire = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                wire.append({
                    "role": "assistant", "content": m.get("content") or "",
                    "tool_calls": [{"id": c["id"], "type": "function",
                                    "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                                   for c in m["tool_calls"]],
                })
            elif m["role"] == "tool":
                wire.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                wire.append({"role": m["role"], "content": m["content"]})
        body = {"model": self.model, "messages": wire, "temperature": 0.2}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name}: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"{self.name}: HTTP {r.status_code} {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": c.get("id") or uuid.uuid4().hex[:12], "name": c["function"]["name"], "arguments": args})
        return LLMResult(text=msg.get("content"), tool_calls=calls, provider=self.name)


class GeminiProvider:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.name = "gemini"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _post(self, body: dict) -> dict:
        try:
            r = httpx.post(self.URL.format(model=self.model), json=body,
                           headers={"x-goog-api-key": self.api_key}, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"gemini: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})
            elif m["role"] == "assistant":
                parts = [{"text": m["content"]}] if m.get("content") else []
                for c in m.get("tool_calls", []):
                    part = {"functionCall": {"name": c["name"], "args": c["arguments"]}}
                    if c.get("thought_signature"):  # newer Gemini models require it echoed back
                        part["thoughtSignature"] = c["thought_signature"]
                    parts.append(part)
                contents.append({"role": "model", "parts": parts})
            elif m["role"] == "tool":
                try:
                    payload = json.loads(m["content"])
                except json.JSONDecodeError:
                    payload = m["content"]
                part = {"functionResponse": {"name": m["name"], "response": {"result": payload}}}
                # Consecutive tool results go back in one user turn.
                if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part]})
        body: dict = {"contents": contents, "generationConfig": {"temperature": 0.2}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            decls = []
            for t in tools:
                d = {"name": t["name"], "description": t["description"]}
                if t.get("parameters", {}).get("properties"):
                    d["parameters"] = t["parameters"]
                decls.append(d)
            body["tools"] = [{"functionDeclarations": decls}]
        data = self._post(body)
        try:
            parts = data["candidates"][0]["content"].get("parts", [])
        except (KeyError, IndexError) as e:
            raise ProviderError(f"gemini: unexpected response {str(data)[:200]}") from e
        text = "".join(p.get("text", "") for p in parts) or None
        calls = [{"id": uuid.uuid4().hex[:12], "name": p["functionCall"]["name"],
                  "arguments": p["functionCall"].get("args") or {},
                  "thought_signature": p.get("thoughtSignature")}
                 for p in parts if "functionCall" in p]
        return LLMResult(text=text, tool_calls=calls, provider=self.name)

    def read_image(self, prompt: str, image_b64: str, mime: str) -> str:
        body = {"contents": [{"role": "user", "parts": [
            {"text": prompt}, {"inline_data": {"mime_type": mime, "data": image_b64}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        data = self._post(body)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise ProviderError("gemini: no image result") from e


def build_providers() -> list:
    s = get_settings()
    out = []
    for name in s.provider_order:
        if name == "gemini" and s.gemini_api_key:
            out.append(GeminiProvider(s.gemini_api_key, s.gemini_model, s.llm_timeout_seconds))
        elif name == "groq" and s.groq_api_key:
            out.append(OpenAICompatProvider("groq", "https://api.groq.com/openai/v1", s.groq_model,
                                            s.groq_api_key, s.llm_timeout_seconds))
        elif name == "ollama" and s.ollama_enabled:
            out.append(OpenAICompatProvider("ollama", f"{s.ollama_url}/v1", s.ollama_model, None,
                                            max(s.llm_timeout_seconds, 120)))
    return out


def chat(messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
    """Try each configured provider in order; fall through on rate limits or errors."""
    providers = build_providers()
    if not providers:
        raise NoLLMAvailable("No free LLM provider is configured")
    errors = []
    for p in providers:
        try:
            return p.chat(messages, tools)
        except ProviderError as e:
            log.warning("LLM provider failed, trying next: %s", e)
            errors.append(str(e))
    raise NoLLMAvailable("; ".join(errors))


def any_configured() -> bool:
    return bool(build_providers())


def gemini_for_vision() -> GeminiProvider | None:
    for p in build_providers():
        if isinstance(p, GeminiProvider):
            return p
    return None
