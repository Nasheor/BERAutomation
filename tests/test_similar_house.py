"""Tests for the similar-house evidence: a house of the same design in one of the Street
View images fills in what is hidden or side-on on the property."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
import pytest
from PIL import Image

from ber_automation.models import HouseDescription, StreetViewAnalysis
from ber_automation.pipeline import BERPipeline
from ber_automation.vision.footprint import SIMILAR_WINDOW_COLOR, draw_window_boxes

BASE_REPLY = {"target_view": "partial", "description": "Two-storey pebble-dashed house."}


def _mock_anthropic(reply: str):
    response = MagicMock()
    response.content = [MagicMock(type="text", text=reply)]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    mod = MagicMock()
    mod.AsyncAnthropic.return_value = client
    settings = MagicMock(anthropic_api_key="k", claude_model="m", claude_temperature=None)
    return settings, mod


def _images(tmp_path: Path, indices=(0, 1, 2, 3)) -> list[Path]:
    paths = []
    for i in indices:
        p = tmp_path / f"streetview_{i}.jpg"
        Image.new("RGB", (640, 640)).save(p)
        paths.append(p)
    return paths


async def _analyse(paths, extra: dict, analysis: StreetViewAnalysis | None = None):
    settings, mod = _mock_anthropic(json.dumps({**BASE_REPLY, **extra}))
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=settings), \
         patch("ber_automation.vision.claude_analyzer.anthropic", mod):
        from ber_automation.vision.claude_analyzer import describe_house
        result = await describe_house(paths, analysis=analysis)
    prompt = mod.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
        "messages"][0]["content"][-1]["text"]
    return result, prompt


@pytest.mark.asyncio
async def test_similar_house_is_parsed_and_described(tmp_path):
    result, prompt = await _analyse(_images(tmp_path), {
        "target_view": "partial",
        "similar_house": {"image": 3, "x1": 470, "x2": 215},
        "inferred_from_similar": ["front door and porch"],
        "description": "Two-storey pebble-dashed house; door assumed from the house opposite.",
    })
    assert result.target_view == "partial"
    # Image 3 in the request is streetview_2; the x-range is put in order
    assert (result.similar_house_view, result.similar_house_x1, result.similar_house_x2) == (2, 215, 470)
    assert result.inferred_from_similar == ["front door and porch"]
    assert result.description.startswith("Two-storey")
    assert result.uses_similar_house
    assert '"similar_house"' in prompt
    assert "ONE camera position" in prompt
    assert "Earlier classification" not in prompt


@pytest.mark.asyncio
async def test_classification_is_passed_as_context_and_its_prompt_is_untouched(tmp_path):
    _, prompt = await _analyse(_images(tmp_path), {}, analysis=StreetViewAnalysis())
    assert "classified the target as detached, 2 storey(s), built before_1980" in prompt
    # The classification prompt decides the rating inputs: the description task stays out of it
    from ber_automation.vision.claude_analyzer import _build_streetview_prompt
    assert "similar_house" not in _build_streetview_prompt("Irish", multi=True)


@pytest.mark.asyncio
async def test_unreadable_reply_gives_no_description(tmp_path):
    settings, mod = _mock_anthropic("I cannot see a house.")
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=settings), \
         patch("ber_automation.vision.claude_analyzer.anthropic", mod):
        from ber_automation.vision.claude_analyzer import describe_house
        assert await describe_house(_images(tmp_path)) is None


@pytest.mark.asyncio
async def test_image_number_maps_to_heading_index_when_a_view_was_dropped(tmp_path):
    """Duplicate views are removed before analysis, so image numbers and headings differ."""
    result, _ = await _analyse(_images(tmp_path, indices=(0, 2, 3)), {
        "target_view": "side",
        "similar_house": {"image": 2, "x1": 100, "x2": 300},
    })
    assert result.similar_house_view == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("similar", [
    None,
    "image 3",
    {"image": 9, "x1": 100, "x2": 300},     # no such image
    {"image": 2, "x1": 100},                # no right edge
    {"image": 2, "x1": 300, "x2": 310},     # too narrow to be a facade
])
async def test_missing_or_invalid_similar_house_is_ignored(tmp_path, similar):
    result, _ = await _analyse(_images(tmp_path), {
        "target_view": "partial",
        "similar_house": similar,
        "inferred_from_similar": ["front door"],
    })
    assert result.similar_house_view is None
    assert result.inferred_from_similar == []
    assert not result.uses_similar_house


@pytest.mark.asyncio
async def test_reply_without_the_new_fields_keeps_defaults(tmp_path):
    result, _ = await _analyse(_images(tmp_path), {"target_view": "sideways", "description": None})
    assert result.target_view == "front"
    assert result.similar_house_view is None
    assert result.description == ""


def test_similar_house_only_counts_when_it_supplied_something():
    seen = HouseDescription(target_view="front", similar_house_view=2,
                            similar_house_x1=10, similar_house_x2=200)
    assert not seen.uses_similar_house
    filled = seen.model_copy(update={"inferred_from_similar": ["front door"]})
    assert filled.uses_similar_house
    side_on = seen.model_copy(update={"target_view": "side"})
    assert side_on.uses_similar_house


def test_pipeline_finds_the_similar_house_image(tmp_path):
    paths = _images(tmp_path, indices=(0, 2, 3))
    described = HouseDescription(target_view="partial", similar_house_view=2,
                                 similar_house_x1=215, similar_house_x2=470)
    assert BERPipeline._similar_house_view(described, paths) == (paths[1], (215, 470))
    # The image was dropped as a duplicate, or the front view showed everything
    assert BERPipeline._similar_house_view(
        described.model_copy(update={"similar_house_view": 1}), paths) is None
    assert BERPipeline._similar_house_view(
        described.model_copy(update={"target_view": "front"}), paths) is None
    assert BERPipeline._similar_house_view(None, paths) is None


@pytest.mark.asyncio
async def test_detect_windows_marks_the_house_in_the_given_range(tmp_path):
    img = _images(tmp_path, indices=(2,))[0]
    settings, mod = _mock_anthropic(json.dumps({
        "target_visible": True, "facade_x1": 215, "facade_x2": 470,
        "windows": [
            {"x1": 290, "y1": 310, "x2": 350, "y2": 335},   # the similar house
            {"x1": 60, "y1": 300, "x2": 110, "y2": 340},    # its neighbour
        ],
    }))
    with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=settings), \
         patch("ber_automation.vision.claude_analyzer.anthropic", mod):
        from ber_automation.vision.claude_analyzer import detect_windows
        wins = await detect_windows(img, facade_hint=(215, 470))
    prompt = mod.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
        "messages"][0]["content"][1]["text"]
    assert wins == [{"x1": 290, "y1": 310, "x2": 350, "y2": 335}]
    assert "between about x = 215 and x = 470" in prompt
    assert "horizontal centre" not in prompt


def test_similar_house_boxes_are_drawn_over_the_property_boxes(tmp_path):
    src = tmp_path / "streetview_0.jpg"
    cv2.imwrite(str(src), np.full((640, 640, 3), 128, dtype=np.uint8))
    out = tmp_path / "streetview_0_annotated.jpg"
    draw_window_boxes(src, [{"x1": 300, "y1": 300, "x2": 360, "y2": 340}], out)
    draw_window_boxes(out, [{"x1": 100, "y1": 300, "x2": 160, "y2": 340}], out,
                      color=SIMILAR_WINDOW_COLOR, title="Similar house")
    img = cv2.imread(str(out)).astype(int)
    # Border pixels: orange on the similar house (red high, blue low), cyan on the property
    blue, _, red = img[320, 100]
    assert red > 200 and blue < 80
    blue, _, red = img[320, 300]
    assert blue > 200 and red < 80
