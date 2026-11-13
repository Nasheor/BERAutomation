"""Tests for the vision model providers: choosing one, and the Mistral request."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from PIL import Image

from ber_automation.models import PipelineResult
from ber_automation.pipeline import BERPipeline
from ber_automation.vision import providers
from ber_automation.vision.providers import (
    MISTRAL_CHAT_URL,
    available_providers,
    mistral_complete,
    model_name,
    resolve_provider,
)


def _settings(**overrides) -> SimpleNamespace:
    values = dict(
        llm_provider="claude",
        anthropic_api_key="a-key", claude_model="claude-x", claude_temperature=None,
        mistral_api_key="m-key", mistral_model="mistral-x", mistral_temperature=0.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _image(tmp_path: Path, name: str = "streetview_0.jpg") -> Path:
    path = tmp_path / name
    Image.new("RGB", (640, 640)).save(path)
    return path


def _reply(content) -> httpx.Response:
    """A streamed Mistral reply (server-sent events) carrying *content*.

    A string is sent in two pieces; a list is sent one chunk per event, as Mistral
    streams thinking and text chunks.
    """
    if isinstance(content, str):
        deltas = [content[: len(content) // 2], content[len(content) // 2:]]
    else:
        deltas = [[chunk] for chunk in content]
    events = [
        {"choices": [{"index": 0, "delta": {"content": d}, "finish_reason": None}]}
        for d in deltas
    ]
    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


# ---------------------------------------------------------------- choosing a provider

def test_provider_asked_for_wins_over_the_setting():
    assert resolve_provider(" Mistral ", _settings()) == "mistral"
    assert resolve_provider("claude", _settings(llm_provider="mistral")) == "claude"


def test_default_provider_comes_from_settings_and_falls_back_to_claude():
    assert resolve_provider(None, _settings(llm_provider="mistral")) == "mistral"
    assert resolve_provider(None, _settings(llm_provider="gpt")) == "claude"
    # Settings mocked in older tests have no usable llm_provider
    assert resolve_provider(None, MagicMock()) == "claude"


def test_unknown_provider_is_refused():
    with pytest.raises(ValueError, match="Unknown vision model provider"):
        resolve_provider("gpt", _settings())


def test_available_providers_are_those_with_a_key():
    assert available_providers(_settings()) == ["claude", "mistral"]
    assert available_providers(_settings(mistral_api_key="")) == ["claude"]
    assert available_providers(_settings(anthropic_api_key="", mistral_api_key="")) == []
    assert model_name("mistral", _settings()) == "mistral-x"
    assert model_name("claude", _settings()) == "claude-x"


# ---------------------------------------------------------------- the Mistral request

@pytest.mark.asyncio
@respx.mock
async def test_mistral_request_keeps_part_order_and_sends_images_as_data_uris(tmp_path):
    route = respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply('{"ok": true}'))
    jpg, png = _image(tmp_path), _image(tmp_path, "satellite.png")

    text = await mistral_complete(_settings(), ["Image 1 - FRONT VIEW", jpg, png, "The prompt"])

    assert text == '{"ok": true}'
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer m-key"
    body = json.loads(request.content)
    assert body["model"] == "mistral-x"
    # Mistral refuses temperature 0 unless top_p is 1
    assert (body["temperature"], body["top_p"]) == (0.0, 1)
    assert body["max_tokens"] == 16000
    # Without streaming Mistral often sent nothing back for minutes
    assert body["stream"] is True
    # JSON mode made Mistral hang on the satellite prompt; it stays off
    assert "response_format" not in body
    content = body["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "image_url", "image_url", "text"]
    assert content[0]["text"] == "Image 1 - FRONT VIEW"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert content[2]["image_url"].startswith("data:image/png;base64,")
    assert content[3]["text"] == "The prompt"


@pytest.mark.asyncio
@respx.mock
async def test_mistral_temperature_is_left_out_when_unset(tmp_path):
    route = respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply("{}"))
    await mistral_complete(_settings(mistral_temperature=None), ["prompt"])
    body = json.loads(route.calls.last.request.content)
    assert "temperature" not in body and "top_p" not in body


@pytest.mark.asyncio
@respx.mock
async def test_mistral_reply_given_as_chunks_is_joined(tmp_path):
    respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply([
        {"type": "thinking", "thinking": [{"type": "text", "text": "hmm"}]},
        {"type": "text", "text": '{"a": '},
        {"type": "text", "text": "1}"},
    ]))
    assert await mistral_complete(_settings(), ["prompt"]) == '{"a": 1}'


@pytest.mark.asyncio
@respx.mock
async def test_mistral_retries_once_when_rate_limited(monkeypatch):
    monkeypatch.setattr(providers, "MISTRAL_RETRY_WAIT_S", 0)
    route = respx.post(MISTRAL_CHAT_URL).mock(side_effect=[httpx.Response(429), _reply("{}")])
    assert await mistral_complete(_settings(), ["prompt"]) == "{}"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_mistral_error_is_raised_after_the_retry(monkeypatch):
    monkeypatch.setattr(providers, "MISTRAL_RETRY_WAIT_S", 0)
    route = respx.post(MISTRAL_CHAT_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await mistral_complete(_settings(), ["prompt"])
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("reply, expected", [
    ('{"a": 1}', '{"a": 1}'),
    ('Here is the result:\n{"a": {"b": 2}}\nHope this helps.', '{"a": {"b": 2}}'),
    ('```json\n{"a": 1}\n```', '{"a": 1}'),
    ("I cannot see a house.", "I cannot see a house."),
    ("Width {about 5 m} and more", "Width {about 5 m} and more"),   # not JSON: unchanged
])
async def test_json_object_is_cut_out_of_the_reply(reply, expected):
    respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply(reply))
    assert await mistral_complete(_settings(), ["prompt"]) == expected


@pytest.mark.asyncio
@respx.mock
async def test_reasoning_effort_is_sent_only_when_set():
    route = respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply("{}"))
    await mistral_complete(_settings(mistral_reasoning_effort="low"), ["prompt"])
    assert json.loads(route.calls.last.request.content)["reasoning_effort"] == "low"
    await mistral_complete(_settings(), ["prompt"])
    assert "reasoning_effort" not in json.loads(route.calls.last.request.content)


@pytest.mark.asyncio
async def test_pipeline_names_an_error_without_a_message(tmp_path):
    from ber_automation.models import Coordinates

    with patch("ber_automation.pipeline.get_settings", return_value=_settings()), \
         patch("ber_automation.pipeline.analyze_streetview",
               AsyncMock(side_effect=httpx.ReadTimeout(""))), \
         patch("ber_automation.pipeline.describe_house", AsyncMock(return_value=None)), \
         patch("ber_automation.pipeline.detect_windows", AsyncMock(return_value=[])):
        result = await BERPipeline(output_dir=tmp_path, provider="mistral")._run_vision_and_calc(
            PipelineResult(address="x"), Coordinates(lat=51.9, lng=-8.5), [_image(tmp_path)],
            country=None, retrofit=None, overrides=None,
        )
    assert "AI analysis failed (Mistral): ReadTimeout" in result.errors


@pytest.mark.asyncio
@respx.mock
async def test_mistral_error_shows_mistrals_message():
    respx.post(MISTRAL_CHAT_URL).mock(return_value=httpx.Response(
        400, json={"object": "error", "message": "top_p must be 1 when using greedy sampling."}))
    with pytest.raises(httpx.HTTPStatusError,
                       match="Mistral returned 400: top_p must be 1 when using greedy sampling"):
        await mistral_complete(_settings(), ["prompt"])


# ---------------------------------------------------------------- through the analyser

@pytest.mark.asyncio
@respx.mock
async def test_streetview_analysis_with_mistral_parses_the_same_json(tmp_path):
    reply = json.dumps({
        "construction_epoch": "2000_2010", "building_type": "semi_d_length",
        "estimated_storeys": 2, "heating_system_guess": "gas_boiler",
        "adjacent_side": "length", "estimated_units_in_row": 2,
        "confidence": 0.8, "reasoning": "Pair of houses.",
    })
    # Mistral wraps the JSON in a code fence here; it is stripped like Claude's
    route = respx.post(MISTRAL_CHAT_URL).mock(return_value=_reply(f"```json\n{reply}\n```"))
    paths = [_image(tmp_path, f"streetview_{i}.jpg") for i in range(2)]
    anthropic_mod = MagicMock()
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=_settings()), \
         patch("ber_automation.vision.claude_analyzer.anthropic", anthropic_mod):
        from ber_automation.vision.claude_analyzer import (
            _build_streetview_prompt,
            analyze_streetview,
        )
        result = await analyze_streetview(paths, provider="mistral")

    assert result.building_type.value == "semi_d_length"
    assert result.confidence == 0.8
    anthropic_mod.AsyncAnthropic.assert_not_called()
    content = json.loads(route.calls.last.request.content)["messages"][0]["content"]
    # Same labels, images and prompt as the Claude request, in the same order
    assert [c["type"] for c in content] == ["text", "image_url", "text", "image_url", "text"]
    assert content[-1]["text"] == _build_streetview_prompt("Irish", multi=True)


@pytest.mark.asyncio
async def test_missing_mistral_key_is_named(tmp_path):
    settings = _settings(mistral_api_key="")
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=settings):
        from ber_automation.vision.claude_analyzer import (
            analyze_satellite,
            analyze_streetview,
            detect_windows,
        )
        with pytest.raises(ValueError, match="MISTRAL_API_KEY not configured"):
            await analyze_streetview(_image(tmp_path), provider="mistral")
        with pytest.raises(ValueError, match="MISTRAL_API_KEY not configured"):
            await analyze_satellite(_image(tmp_path), lat=51.9, provider="mistral")
        assert await detect_windows(_image(tmp_path), provider="mistral") == []


# ---------------------------------------------------------------- through the pipeline

@pytest.mark.asyncio
async def test_pipeline_passes_the_provider_on_and_records_the_model(tmp_path):
    sv = _image(tmp_path)
    seen: dict[str, str | None] = {}

    def _record(name, value):
        async def _fn(*args, provider=None, **kwargs):
            seen[name] = provider
            return value
        return _fn

    from ber_automation.models import Coordinates, StreetViewAnalysis

    with patch("ber_automation.pipeline.get_settings", return_value=_settings()), \
         patch("ber_automation.pipeline.analyze_streetview",
               _record("streetview", StreetViewAnalysis())), \
         patch("ber_automation.pipeline.describe_house", _record("describe", None)), \
         patch("ber_automation.pipeline.detect_windows", _record("windows", [])):
        result = await BERPipeline(output_dir=tmp_path, provider="mistral")._run_vision_and_calc(
            PipelineResult(address="x"), Coordinates(lat=51.9, lng=-8.5), [sv],
            country=None, retrofit=None, overrides=None,
        )

    assert seen == {"streetview": "mistral", "describe": "mistral", "windows": "mistral"}
    assert (result.llm_provider, result.llm_model) == ("mistral", "mistral-x")


@pytest.mark.asyncio
async def test_pipeline_error_names_the_provider(tmp_path):
    from ber_automation.models import Coordinates

    with patch("ber_automation.pipeline.get_settings", return_value=_settings()), \
         patch("ber_automation.pipeline.analyze_streetview",
               AsyncMock(side_effect=ValueError("MISTRAL_API_KEY not configured"))), \
         patch("ber_automation.pipeline.describe_house", AsyncMock(return_value=None)), \
         patch("ber_automation.pipeline.detect_windows", AsyncMock(return_value=[])):
        result = await BERPipeline(output_dir=tmp_path, provider="mistral")._run_vision_and_calc(
            PipelineResult(address="x"), Coordinates(lat=51.9, lng=-8.5), [_image(tmp_path)],
            country=None, retrofit=None, overrides=None,
        )
    assert "AI analysis failed (Mistral): MISTRAL_API_KEY not configured" in result.errors


def test_settings_without_mistral_fields_do_not_crash():
    """Settings loaded before the Mistral fields existed (Streamlit Cloud hot reload)."""
    from types import SimpleNamespace

    from ber_automation.vision.providers import api_key, available_providers, model_name

    old = SimpleNamespace(anthropic_api_key="key", claude_model="claude-sonnet-5-5")
    assert available_providers(old) == ["claude"]
    assert api_key("mistral", old) == ""
    assert model_name("mistral", old) == ""
    assert model_name("claude", old) == "claude-sonnet-5-5"
