"""Live providers over plain HTTP.

No vendor SDK. Two reasons: the project carries zero runtime dependencies, and a firm
that may mandate a different model next quarter should not have a client review pipeline
coupled to one vendor's package. Each provider differs only in endpoint, headers, request
shaping and where the text sits in the response.

Credentials come from the environment and are never written to the ledger, the cache key
or the cassette.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from ..base import AdapterError

FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


def _salvage_elements(text: str) -> list[dict[str, Any]] | None:
    """Recover whole element objects from a response that stopped mid-array.

    A truncated response is not a wrong one. The objects that did arrive are complete and
    verifiable, and an element that never arrived simply reads as unsupported - which is
    the same conservative default as a missing claim. Discarding the whole control instead
    throws away work that was already paid for and already correct.
    """
    objects: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    parsed = json.loads(text[start: index + 1])
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    objects.append(parsed)
                start = -1
    usable = [o for o in objects if "supported" in o]
    return usable or None


def _coerce_payload(value: Any) -> dict[str, Any]:
    """Normalize whatever shape the provider chose into the payload contract.

    Asked for "one entry per element id", a model will sometimes return the array on its
    own rather than wrapped in an object. The content is right and the wrapper is missing,
    so wrapping it is the correct repair - not an error. Guessing any further is not: an
    unrecognised shape raises with the observed keys, so the failure names itself instead
    of surfacing as an AttributeError three frames downstream.
    """
    if isinstance(value, list):
        return {"elements": value}
    if not isinstance(value, dict):
        raise AdapterError(
            f"provider returned a {type(value).__name__}, expected an object or an array of "
            "element results"
        )
    if "elements" in value:
        return value
    # A single wrapper key around the array, e.g. {"results": [...]}.
    if len(value) == 1:
        wrapper, only = next(iter(value.items()))
        if isinstance(only, list):
            return {"elements": only, "_wrapper_key": wrapper}
    # Element results keyed by id rather than listed, e.g. {"e1": {"supported": true}}.
    if all(isinstance(v, dict) for v in value.values()) and value:
        rebuilt = []
        for key, entry in value.items():
            if "supported" not in entry:
                break
            rebuilt.append({"id": key, **entry})
        else:
            return {"elements": rebuilt}
    raise AdapterError(
        "provider returned an object without an 'elements' array; keys were "
        f"{sorted(value)[:8]}"
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    """Extract the payload from a provider response.

    Candidates are tried whole first, then as the outermost bracketed span of each kind.
    Both a decode failure and an unusable shape move on to the next candidate, because a
    response that opens with prose can contain an inner object that parses but means
    nothing - taking the first thing that happens to be valid JSON is how a wrong shape
    gets three frames downstream before it fails.
    """
    cleaned = FENCE.sub("", text).strip()
    candidates = [cleaned]
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            candidates.append(cleaned[start: end + 1])

    last: Exception | None = None
    for candidate in candidates:
        try:
            return _coerce_payload(json.loads(candidate))
        except (json.JSONDecodeError, AdapterError) as exc:
            last = exc
            continue
    salvaged = _salvage_elements(cleaned)
    if salvaged:
        return {"elements": salvaged, "_truncated": True}
    raise AdapterError(
        f"provider returned no usable payload ({last}); response began {cleaned[:160]!r}"
    )


MAX_TOKENS = int(os.environ.get("PFIA_MAX_TOKENS", "8192"))
CONDITION_ID = re.compile(r"^[A-Z]{2,4}-\d{2}$")


def _coerce_conditions(value: Any) -> dict[str, Any]:
    """Schedule B v2 contract: {"conditions": {id: fact}, "activation": {key: answer}}."""
    if isinstance(value, dict) and isinstance(value.get("conditions"), dict):
        return {"conditions": value["conditions"], "activation": value.get("activation") or {}}
    if isinstance(value, dict) and value and all(CONDITION_ID.match(k) for k in value):
        return {"conditions": value, "activation": {}}
    keys = sorted(value)[:8] if isinstance(value, dict) else type(value).__name__
    raise AdapterError(f"provider returned no 'conditions' object; got {keys}")


def _parse_conditions(text: str) -> dict[str, Any]:
    cleaned = FENCE.sub("", text).strip()
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start: end + 1])
    last: Exception | None = None
    for candidate in candidates:
        try:
            return _coerce_conditions(json.loads(candidate))
        except (json.JSONDecodeError, AdapterError) as exc:
            last = exc
    # No salvage: a partial conditions object is indistinguishable from a complete one
    # that omitted answers, and omitted answers already read as UNKNOWN.
    raise AdapterError(f"provider returned no usable conditions payload ({last}); began {cleaned[:160]!r}")


RETRYABLE = {429, 500, 502, 503, 504, 529}
RETRIES = int(os.environ.get("PFIA_HTTP_RETRIES", "4"))


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Merge extra request settings into a body without dropping nested defaults.

    A shallow merge let PFIA_GEMINI_EXTRA_BODY='{"generationConfig": {...}}' replace the
    whole generationConfig, silently losing responseMimeType and the output ceiling.
    """
    out = dict(base)
    for key, value in extra.items():
        out[key] = _deep_merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def _http_detail(exc: urllib.error.HTTPError) -> str:
    """The provider's error message, so a failure says why. Never echoes request headers."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        err = parsed.get("error", parsed)
        message = err.get("message") if isinstance(err, dict) else str(err)
        kind = err.get("type") or err.get("status") if isinstance(err, dict) else None
        return f"{kind}: {message}" if kind else str(message)
    except Exception:  # noqa: BLE001 - diagnostics only
        return ""


def _extra_body(env_key: str) -> dict[str, Any]:
    """Provider-specific request settings (thinking, effort, safety) from the environment.

    Kept out of code so a setting the provider renames does not need a release; the run
    manifest records the value used.
    """
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"{env_key} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError(f"{env_key} must be a JSON object")
    return value


class _HttpAdapter:
    url = ""
    name = "http"
    env_key = ""
    timeout = 120
    truncated = False

    def __init__(self, model: str, api_key: str | None = None, timeout: int | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get(self.env_key, "")
        if not self.api_key:
            raise AdapterError(f"{self.env_key} is not set")
        if timeout:
            self.timeout = timeout
        self.name = f"{self.name}:{model}"

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    def _text(self, payload: dict[str, Any]) -> str:
        raise NotImplementedError

    def _endpoint(self) -> str:
        return self.url

    extra_env = ""
    last_meta: dict[str, Any] = {}

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        """One HTTP POST. Separate so tests can substitute a transport."""
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _meta(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {}

    @staticmethod
    def _sleep(seconds: float) -> None:
        import time
        time.sleep(seconds)

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        body = _deep_merge(self._body(prompt), _extra_body(self.extra_env)) if self.extra_env else self._body(prompt)
        payload = None
        for attempt in range(RETRIES + 1):
            try:
                payload = self._post(self._endpoint(), body, self._headers())
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE and attempt < RETRIES:
                    retry_after = exc.headers.get("retry-after") if exc.headers else None
                    delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
                    self._sleep(min(delay, 60.0))
                    continue
                detail = _http_detail(exc)
                raise AdapterError(f"{self.name} HTTP {exc.code} on {control_id}" + (f": {detail}" if detail else "")) from exc
            except urllib.error.URLError as exc:
                if attempt < RETRIES:
                    self._sleep(min(2 ** attempt, 60.0))
                    continue
                raise AdapterError(f"{self.name} transport error on {control_id}: {exc.reason}") from exc
        self.truncated = False
        # Which model actually answered, and what it cost. Recorded in the cassette so a
        # replay can prove its provenance; never the key.
        self.last_meta = {"requested_model": self.model, **self._meta(payload)}
        text = self._text(payload)
        if "conditions" in response_schema.get("properties", {}):
            if self.truncated:
                raise AdapterError(f"{self.name} response hit the {MAX_TOKENS}-token ceiling on {control_id}")
            return _parse_conditions(text)
        try:
            parsed = _parse_json_object(text)
        except AdapterError as exc:
            if self.truncated:
                raise AdapterError(
                    f"{self.name} response hit the {MAX_TOKENS}-token ceiling on "
                    f"{control_id} and could not be salvaged; the control asks for "
                    f"{len(response_schema.get('properties', {}).get('elements', {}).get('items', {}).get('properties', {}).get('id', {}).get('enum', []))} "
                    "element quotes"
                ) from exc
            raise
        if self.truncated:
            parsed["_truncated"] = True
        return parsed


class AnthropicAdapter(_HttpAdapter):
    url = "https://api.anthropic.com/v1/messages"
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    extra_env = "PFIA_ANTHROPIC_EXTRA_BODY"

    def _meta(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage = payload.get("usage") or {}
        return {"served_model": payload.get("model"), "stop_reason": payload.get("stop_reason"),
                "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    def _body(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }

    def _text(self, payload: dict[str, Any]) -> str:
        blocks = [b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"]
        if not blocks:
            raise AdapterError("anthropic response contained no text block")
        if payload.get("stop_reason") == "max_tokens":
            # Named explicitly, because the downstream symptom is a JSON decode error that
            # looks like a malformed response rather than a budget that ran out.
            self.truncated = True
        return "\n".join(blocks)


class GeminiAdapter(_HttpAdapter):
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    name = "gemini"
    env_key = "GEMINI_API_KEY"
    extra_env = "PFIA_GEMINI_EXTRA_BODY"

    def _meta(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage = payload.get("usageMetadata") or {}
        return {"served_model": payload.get("modelVersion"),
                "input_tokens": usage.get("promptTokenCount"),
                "output_tokens": (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)}

    def _endpoint(self) -> str:
        return f"{self.url}/{self.model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key}

    def _body(self, prompt: str) -> dict[str, Any]:
        config: dict[str, Any] = {
            "responseMimeType": "application/json",
            # The ceiling includes thinking tokens on Gemini 3.x; 8k truncates at medium.
            "maxOutputTokens": int(os.environ.get("PFIA_GEMINI_MAX_OUTPUT_TOKENS", "32768")),
        }
        if self.model.startswith("gemini-3"):
            # Google's guidance for Gemini 3.x: leave temperature, top_p and top_k at their
            # defaults; lowering temperature can cause looping or degraded output.
            # Reasoning effort is set with thinkingLevel (3.8 Flash: low, medium, high).
            level = os.environ.get("PFIA_GEMINI_THINKING_LEVEL", "").strip()
            if level:
                config["thinkingConfig"] = {"thinkingLevel": level}
        else:
            config["temperature"] = 0
        return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}

    def _text(self, payload: dict[str, Any]) -> str:
        feedback = payload.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise AdapterError(f"gemini blocked the prompt: {feedback['blockReason']}")
        try:
            candidate = payload["candidates"][0]
        except (KeyError, IndexError) as exc:
            raise AdapterError("gemini response contained no candidate") from exc
        reason = candidate.get("finishReason")
        if reason == "MAX_TOKENS":
            self.truncated = True
        elif reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
            raise AdapterError(f"gemini stopped the response: {reason}")
        parts = (candidate.get("content") or {}).get("parts") or []
        # Thought summaries, if requested, arrive as parts flagged "thought"; never parse them.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise AdapterError(f"gemini response contained no text (finishReason {reason})")
        return text
