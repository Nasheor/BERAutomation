"""Vision model providers: which one to use, and the Mistral API call.

Claude is called through the anthropic SDK in claude_analyzer.py. Mistral is called over
its REST API with httpx, so no extra dependency is needed. Both receive the same prompts
and the same images in the same order.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx

PROVIDERS: tuple[str, ...] = ("claude", "mistral")
PROVIDER_LABELS: dict[str, str] = {"claude": "Claude", "mistral": "Mistral"}
KEY_ENV_NAMES: dict[str, str] = {"claude": "ANTHROPIC_API_KEY", "mistral": "MISTRAL_API_KEY"}

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_TIMEOUT_S = 300.0
# Same reply limit as the Claude requests (thinking included)
MISTRAL_MAX_TOKENS = 16000
MISTRAL_RETRY_WAIT_S = 2.0

_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def media_type(image_path: Path) -> str:
    """MIME type of an image file, from its extension (JPEG when unknown)."""
    return _MEDIA_TYPES.get(image_path.suffix.lower(), "image/jpeg")


def resolve_provider(provider: str | None, settings) -> str:
    """The provider to use: the one asked for, else the configured default, else Claude."""
    if provider is None:
        provider = getattr(settings, "llm_provider", None)
        if not isinstance(provider, str) or provider.strip().lower() not in PROVIDERS:
            return "claude"
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown vision model provider: {provider!r}. Use one of {PROVIDERS}.")
    return provider


def api_key(provider: str, settings) -> str:
    """The API key configured for *provider* ("" when missing)."""
    key = settings.anthropic_api_key if provider == "claude" else settings.mistral_api_key
    return key if isinstance(key, str) else ""


def model_name(provider: str, settings) -> str:
    """The model ID configured for *provider*."""
    return settings.claude_model if provider == "claude" else settings.mistral_model


def available_providers(settings) -> list[str]:
    """Providers that have an API key, in PROVIDERS order."""
    return [p for p in PROVIDERS if api_key(p, settings)]


async def mistral_complete(settings, parts: list[str | Path]) -> str:
    """Send text and images, in the order given, to Mistral and return the reply text.

    Args:
        settings: Application settings (API key, model, temperature).
        parts: Text strings and image paths, in the order the model should see them.

    Returns:
        The reply text; when it holds a JSON object with text around it, just the object.

    Raises:
        httpx.HTTPStatusError: when Mistral answers with an error (after one retry on
            429 or 5xx).
    """
    content: list[dict] = []
    for part in parts:
        if isinstance(part, Path):
            data = base64.standard_b64encode(part.read_bytes()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": f"data:{media_type(part)};base64,{data}",
            })
        else:
            content.append({"type": "text", "text": part})

    # Streamed, and without JSON mode (response_format json_object). Without streaming,
    # Mistral Large 4 often sent nothing back for over 7 minutes on the Street View and
    # satellite prompts (Nov 2026), and with JSON mode it hung on the satellite prompt;
    # the same requests streamed answered in about 15 s. The prompts ask for JSON
    # already; the object is cut out of the reply below.
    payload: dict = {
        "model": settings.mistral_model,
        "max_tokens": MISTRAL_MAX_TOKENS,
        "stream": True,
        "messages": [{"role": "user", "content": content}],
    }
    temperature = settings.mistral_temperature
    if isinstance(temperature, (int, float)):
        payload["temperature"] = temperature
        # Mistral refuses temperature 0 ("greedy sampling") unless top_p is 1
        payload["top_p"] = 1
    effort = getattr(settings, "mistral_reasoning_effort", None)
    if isinstance(effort, str) and effort:
        payload["reasoning_effort"] = effort

    headers = {"Authorization": f"Bearer {settings.mistral_api_key}"}
    async with httpx.AsyncClient(timeout=MISTRAL_TIMEOUT_S) as client:
        for attempt in (1, 2):
            async with client.stream(
                "POST", MISTRAL_CHAT_URL, json=payload, headers=headers,
            ) as response:
                if response.is_error:
                    await response.aread()
                    if attempt == 1 and (response.status_code == 429 or response.status_code >= 500):
                        await asyncio.sleep(MISTRAL_RETRY_WAIT_S)
                        continue
                    raise httpx.HTTPStatusError(
                        f"Mistral returned {response.status_code}: {_error_message(response)}",
                        request=response.request, response=response,
                    )
                text = await _read_stream(response)
                break
    return json_object_text(text)


async def _read_stream(response: httpx.Response) -> str:
    """Join the text of a streamed Mistral reply (server-sent events), skipping thinking."""
    pieces: list[str] = []
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        event = json.loads(data)
        for choice in event.get("choices") or []:
            delta = (choice.get("delta") or {}).get("content")
            if isinstance(delta, str):
                pieces.append(delta)
            elif isinstance(delta, list):
                pieces.extend(
                    chunk.get("text", "") for chunk in delta
                    if isinstance(chunk, dict) and chunk.get("type") == "text"
                )
    return "".join(pieces).strip()


def json_object_text(text: str) -> str:
    """The JSON object in a reply that may have prose or a code fence around it.

    Returns the text from the first "{" to the last "}" when that part is valid JSON;
    otherwise the text unchanged, so the caller's own parse error handling applies.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return text
    candidate = text[start:end + 1]
    try:
        json.loads(candidate)
    except ValueError:
        return text
    return candidate


def _error_message(response: httpx.Response) -> str:
    """Mistral's own error message, or the start of the response body."""
    try:
        message = response.json().get("message")
    except (ValueError, AttributeError):
        message = None
    return str(message) if message else response.text[:200]
