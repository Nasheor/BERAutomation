"""Tests for detect_windows(): target-facade filtering and blurred/hidden targets."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image


def _mock_anthropic(reply: str):
    response = MagicMock()
    response.content = [MagicMock(type="text", text=reply)]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    mod = MagicMock()
    mod.AsyncAnthropic.return_value = client
    settings = MagicMock(anthropic_api_key="k", claude_model="m", claude_temperature=None)
    return settings, mod


async def _run(tmp_path, reply):
    img = tmp_path / "streetview_0.jpg"
    Image.new("RGB", (640, 640)).save(img)
    settings, mod = _mock_anthropic(json.dumps(reply))
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=settings), \
         patch("ber_automation.vision.claude_analyzer.anthropic", mod):
        from ber_automation.vision.claude_analyzer import detect_windows
        wins = await detect_windows(img)
    prompt = mod.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
        "messages"][0]["content"][1]["text"]
    return wins, prompt


@pytest.mark.asyncio
async def test_neighbour_windows_outside_facade_dropped(tmp_path):
    wins, prompt = await _run(tmp_path, {
        "target_visible": True, "facade_x1": 200, "facade_x2": 450,
        "windows": [
            {"x1": 0, "y1": 260, "x2": 40, "y2": 300},      # neighbour on the left
            {"x1": 250, "y1": 280, "x2": 290, "y2": 320},   # target
            {"x1": 380, "y1": 360, "x2": 420, "y2": 400},   # target
            {"x1": 470, "y1": 360, "x2": 520, "y2": 400},   # neighbour on the right
        ],
    })
    assert wins == [
        {"x1": 250, "y1": 280, "x2": 290, "y2": 320},
        {"x1": 380, "y1": 360, "x2": 420, "y2": 400},
    ]
    assert "x = 320" in prompt


@pytest.mark.asyncio
async def test_blurred_target_returns_no_windows(tmp_path):
    wins, _ = await _run(tmp_path, {
        "target_visible": False, "facade_x1": 280, "facade_x2": 460,
        "windows": [{"x1": 300, "y1": 280, "x2": 340, "y2": 320}],
    })
    assert wins == []


@pytest.mark.asyncio
async def test_legacy_list_reply_still_parsed(tmp_path):
    wins, _ = await _run(tmp_path, [{"x1": 100, "y1": 100, "x2": 150, "y2": 160}])
    assert wins == [{"x1": 100, "y1": 100, "x2": 150, "y2": 160}]
