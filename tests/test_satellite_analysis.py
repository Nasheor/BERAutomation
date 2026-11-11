"""Tests for Claude Vision satellite analysis, footprint reconciliation, and validation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ber_automation.models import (
    BuildingType,
    ConstructionEpoch,
    FootprintResult,
    HeatingSystem,
    PipelineResult,
    StreetViewAnalysis,
)
from ber_automation.pipeline import BERPipeline


def _make_mock_anthropic(response_text: str):
    """Build patched settings + AsyncAnthropic that returns *response_text*."""
    mock_response = MagicMock()
    thinking_block = MagicMock(type="thinking", thinking="")
    text_block = MagicMock(type="text", text=response_text)
    mock_response.content = [thinking_block, text_block]

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "test-key"
    mock_settings.claude_model = "test-model"

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    return mock_settings, mock_anthropic


# ---------------------------------------------------------------------------
# analyze_satellite() tests
# ---------------------------------------------------------------------------

class TestAnalyzeSatellite:
    """Test the Claude Vision satellite analysis function."""

    @pytest.mark.asyncio
    async def test_valid_response_uploaded_image(self, tmp_path):
        """Uploaded image (no zoom): Claude's metre estimates are used directly."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "length_m": 11.5,
            "width_m": 8.2,
            "building_shape": "rectangular",
            "confidence": 0.75,
            "reasoning": "Clear roof visible",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=None)

        assert result.length_m == 11.5
        assert result.width_m == 8.2
        assert result.area_m2 == round(11.5 * 8.2, 1)
        assert result.confidence == 0.75
        assert result.source == "claude_vision"
        assert result.building_shape == "rectangular"

    @pytest.mark.asyncio
    async def test_malformed_json_returns_zero_confidence(self, tmp_path):
        """Malformed JSON response returns zero-confidence result."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic("This is not JSON at all")

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

        assert result.confidence == 0
        assert result.source == "claude_vision"

    @pytest.mark.asyncio
    async def test_out_of_bounds_dimensions_clamped(self, tmp_path):
        """Dimensions outside [4, 25] are clamped."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "length_m": 50.0,
            "width_m": 2.0,
            "building_shape": "rectangular",
            "confidence": 0.8,
            "reasoning": "Test",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=None)

        assert result.length_m == 25.0  # clamped from 50
        assert result.width_m == 4.0    # clamped from 2


    @pytest.mark.asyncio
    async def test_block_split_along_longer_edge(self, tmp_path):
        """GPS path: the block is divided along its longer edge; the slice nearest the centre is drawn."""
        from PIL import Image
        from ber_automation.geospatial.scale import satellite_meters_per_pixel

        img = tmp_path / "satellite.png"
        Image.new("RGB", (640, 640)).save(img)
        # Rotated block 180 px x 300 px, listed starting on the SHORT edge; 3 homes
        block = [[340, 120], [448, 264], [208, 444], [100, 300]]
        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "block_corners_px": block,
            "units_in_block": 3,
            "building_shape": "rectangular",
            "confidence": 0.7,
            "reasoning": "Test",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

        mpp = satellite_meters_per_pixel(53.35, 20)
        assert result.length_m == round(180 * mpp, 1)   # depth
        assert result.width_m == round(100 * mpp, 1)    # 300 px / 3 homes
        # Middle third of the block: the slice containing the image centre
        assert sorted(map(tuple, result.contour_points)) == [(180, 240), (260, 180), (288, 384), (368, 324)]
        prompt = mock_anthropic.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
            "messages"][0]["content"][1]["text"]
        assert "block_corners_px" in prompt
        assert "(320, 320)" in prompt

    @pytest.mark.asyncio
    async def test_missing_corners_returns_zero_confidence(self, tmp_path):
        """GPS path: a response without valid corners is rejected, not guessed."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "length_m": 10.0, "width_m": 8.0, "confidence": 0.9,
            "block_corners_px": [[1, 2], [3, 4]],
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings),              patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

        assert result.confidence == 0


def test_mapbox_scale_is_half_google_scale():
    """Mapbox zoom Z uses 512 px tiles: half the metres per pixel of Google zoom Z."""
    from ber_automation.geospatial.scale import meters_per_pixel, satellite_meters_per_pixel

    assert satellite_meters_per_pixel(51.9, 20) == pytest.approx(meters_per_pixel(51.9, 20) / 2)
    # Cork at zoom 20: a 4.5 m car spans ~98 px
    assert satellite_meters_per_pixel(51.9, 20) == pytest.approx(0.046, abs=0.001)


# ---------------------------------------------------------------------------
# analyze_streetview() tests (multi-image)
# ---------------------------------------------------------------------------

class TestAnalyzeStreetview:
    """Test the multi-image Street View analysis function."""

    @pytest.mark.asyncio
    async def test_single_image_backward_compatible(self, tmp_path):
        """Passing a single path (str) still works."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "construction_epoch": "1990_2000",
            "building_type": "semi_d_length",
            "estimated_storeys": 2,
            "heating_system_guess": "gas_boiler",
            "adjacent_side": "length",
            "confidence": 0.7,
            "reasoning": "PVC windows, cavity block walls",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            result = await analyze_streetview(str(img))

        assert result.construction_epoch.value == "1990_2000"
        assert result.building_type.value == "semi_d_length"
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_multiple_images(self, tmp_path):
        """Passing multiple images sends all to Claude."""
        images = []
        for i in range(4):
            img = tmp_path / f"sv_{i}.jpg"
            img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            images.append(img)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "construction_epoch": "before_1980",
            "building_type": "detached",
            "estimated_storeys": 2,
            "heating_system_guess": "oil_boiler",
            "adjacent_side": "length",
            "confidence": 0.85,
            "reasoning": "Oil tank visible at rear, single-glazed windows",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            result = await analyze_streetview(images)

        assert result.heating_system_guess.value == "oil_boiler"
        assert result.confidence == 0.85

        # Verify all 4 images were included in the API call
        call_args = mock_anthropic.AsyncAnthropic.return_value.messages.create.call_args
        content_blocks = call_args.kwargs["messages"][0]["content"]
        image_blocks = [b for b in content_blocks if b["type"] == "image"]
        assert len(image_blocks) == 4

    @pytest.mark.asyncio
    async def test_malformed_response_returns_defaults(self, tmp_path):
        """Malformed JSON from streetview analysis returns safe defaults."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic("Not JSON")

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            result = await analyze_streetview(str(img))

        # Should return defaults, not crash
        assert result.construction_epoch.value == "before_1980"
        assert result.building_type.value == "detached"

    @pytest.mark.asyncio
    async def test_location_included_in_prompt(self, tmp_path):
        """The geocoded address is passed to Claude for urban/rural heating context."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "construction_epoch": "1980_1990",
            "building_type": "semi_d_length",
            "heating_system_guess": "gas_boiler",
            "confidence": 0.7,
        }))

        address = "Ballinlough, Cork, Co. Cork, T12 TP3C, Ireland"
        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            await analyze_streetview(str(img), location=address)
            create = mock_anthropic.AsyncAnthropic.return_value.messages.create
            with_location = create.call_args.kwargs["messages"][0]["content"][-1]["text"]

            await analyze_streetview(str(img))
            without_location = create.call_args.kwargs["messages"][0]["content"][-1]["text"]

        assert address in with_location
        assert "Property Location" not in without_location.split("## CRITICAL")[0]

    @pytest.mark.asyncio
    async def test_temperature_setting_passed_only_when_set(self, tmp_path):
        """claude_temperature is sent to the API when set and omitted when None."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({"confidence": 0.7}))
        create = mock_anthropic.AsyncAnthropic.return_value.messages.create

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview

            mock_settings.claude_temperature = 0.0
            await analyze_streetview(str(img))
            assert create.call_args.kwargs["temperature"] == 0.0

            mock_settings.claude_temperature = None
            await analyze_streetview(str(img))
            assert "temperature" not in create.call_args.kwargs


# ---------------------------------------------------------------------------
# _reconcile_footprints() tests
# ---------------------------------------------------------------------------

class TestReconcileFootprints:
    """Test footprint reconciliation logic."""

    def test_agreement_boosts_confidence(self):
        """When both methods agree within 30%, confidence is boosted."""
        claude_fp = FootprintResult(
            length_m=10.0, width_m=8.0, area_m2=80.0,
            confidence=0.7, source="claude_vision",
        )
        opencv_fp = FootprintResult(
            length_m=10.5, width_m=7.5, area_m2=78.75,
            confidence=0.5, source="opencv",
        )
        result = BERPipeline._reconcile_footprints(claude_fp, opencv_fp)
        assert result is not None
        assert result.source == "claude_vision"
        assert result.confidence == 0.85  # 0.7 + 0.15

    def test_disagreement_trusts_claude(self):
        """When methods disagree, Claude Vision wins."""
        claude_fp = FootprintResult(
            length_m=10.0, width_m=8.0, area_m2=80.0,
            confidence=0.7, source="claude_vision",
        )
        opencv_fp = FootprintResult(
            length_m=20.0, width_m=15.0, area_m2=300.0,
            confidence=0.5, source="opencv",
        )
        result = BERPipeline._reconcile_footprints(claude_fp, opencv_fp)
        assert result is not None
        assert result.source == "claude_vision"
        assert result.confidence == 0.7  # no boost

    def test_claude_fails_falls_back_to_opencv(self):
        """When Claude fails, OpenCV result is used."""
        opencv_fp = FootprintResult(
            length_m=10.0, width_m=8.0, area_m2=80.0,
            confidence=0.5, source="opencv",
        )
        result = BERPipeline._reconcile_footprints(None, opencv_fp)
        assert result is not None
        assert result.source == "opencv"

    def test_both_fail_returns_none(self):
        """When both fail, returns None."""
        result = BERPipeline._reconcile_footprints(None, None)
        assert result is None

    def test_low_confidence_claude_falls_back_to_opencv(self):
        """Low-confidence Claude result defers to OpenCV."""
        claude_fp = FootprintResult(
            length_m=10.0, width_m=8.0, area_m2=80.0,
            confidence=0.2, source="claude_vision",
        )
        opencv_fp = FootprintResult(
            length_m=11.0, width_m=7.5, area_m2=82.5,
            confidence=0.5, source="opencv",
        )
        result = BERPipeline._reconcile_footprints(claude_fp, opencv_fp)
        assert result is not None
        assert result.source == "opencv"


# ---------------------------------------------------------------------------
# _build_input() validation tests
# ---------------------------------------------------------------------------

class TestBuildInputValidation:
    """Test the improved _build_input validation bounds."""

    def _make_pipeline_result(self, footprint=None, street_analysis=None):
        return PipelineResult(
            address="D02X285",
            footprint=footprint,
            street_analysis=street_analysis,
        )

    def test_high_confidence_uses_footprint(self):
        """High confidence footprint dimensions are used."""
        fp = FootprintResult(
            length_m=12.0, width_m=9.0, area_m2=108.0,
            confidence=0.8, source="claude_vision",
        )
        pr = self._make_pipeline_result(footprint=fp)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        assert building.length == 12.0
        assert building.width == 9.0

    def test_low_confidence_uses_defaults(self):
        """Low confidence footprint triggers default dimensions."""
        fp = FootprintResult(
            length_m=12.0, width_m=9.0, area_m2=108.0,
            confidence=0.3, source="opencv",
        )
        pr = self._make_pipeline_result(footprint=fp)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        assert building.length == 10.0
        assert building.width == 8.0

    def test_unreasonable_area_uses_defaults(self):
        """If area falls outside [20, 500] m2, defaults are used."""
        fp = FootprintResult(
            length_m=3.0, width_m=3.0, area_m2=9.0,
            confidence=0.8, source="claude_vision",
        )
        pr = self._make_pipeline_result(footprint=fp)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        # 3m clamped to 4m → area = 16 < 20 → defaults
        assert building.length == 10.0
        assert building.width == 8.0

    def test_dimensions_clamped_to_bounds(self):
        """Extreme dimensions are clamped to [4, 25] range."""
        fp = FootprintResult(
            length_m=30.0, width_m=2.0, area_m2=60.0,
            confidence=0.8, source="claude_vision",
        )
        pr = self._make_pipeline_result(footprint=fp)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        # 30 → 25, 2 → 4, area = 100 which is in [20,500] range
        assert building.length == 25.0
        assert building.width == 4.0

    def test_no_footprint_uses_defaults(self):
        """No footprint at all uses default 10x8."""
        pr = self._make_pipeline_result()
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        assert building.length == 10.0
        assert building.width == 8.0

    def test_overrides_take_precedence(self):
        """User overrides override footprint dimensions."""
        fp = FootprintResult(
            length_m=12.0, width_m=9.0, area_m2=108.0,
            confidence=0.8, source="claude_vision",
        )
        pr = self._make_pipeline_result(footprint=fp)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr, overrides={"length": 15.0, "width": 10.0})
        assert building.length == 15.0
        assert building.width == 10.0

    def test_high_confidence_street_analysis_used(self):
        """High confidence street analysis parameters are applied."""
        sa = StreetViewAnalysis(
            construction_epoch=ConstructionEpoch("1990_2000"),
            building_type=BuildingType("semi_d_length"),
            estimated_storeys=2,
            heating_system_guess=HeatingSystem("gas_boiler"),
            confidence=0.7,
            reasoning="Clear view of building",
        )
        pr = self._make_pipeline_result(street_analysis=sa)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        assert building.building_type == BuildingType.SEMI_D_LENGTH
        assert building.construction_epoch == ConstructionEpoch.EPOCH_1990_2000
        assert building.heating_system == HeatingSystem.GAS_BOILER

    def test_low_confidence_street_analysis_ignored(self):
        """Low confidence street analysis (e.g. vegetation-blocked view) is ignored."""
        sa = StreetViewAnalysis(
            construction_epoch=ConstructionEpoch("after_2010"),
            building_type=BuildingType("terraced_length"),
            estimated_storeys=3,
            heating_system_guess=HeatingSystem("heat_pump_air"),
            confidence=0.1,
            reasoning="Building not visible, obscured by vegetation",
        )
        pr = self._make_pipeline_result(street_analysis=sa)
        pipeline = BERPipeline()
        building = pipeline._build_input(pr)
        # Should use defaults, not the low-confidence guesses
        assert building.building_type == BuildingType.DETACHED
        assert building.construction_epoch == ConstructionEpoch.BEFORE_1980
        assert building.heating_system == HeatingSystem.GAS_BOILER


# ---------------------------------------------------------------------------
# Terraced / unit-count tests
# ---------------------------------------------------------------------------

class TestTerraceUnitCount:
    """Test estimated_units_in_row parsing from street view."""

    @pytest.mark.asyncio
    async def test_terraced_with_unit_count(self, tmp_path):
        """Verify estimated_units_in_row is parsed from Claude response."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "construction_epoch": "1990_2000",
            "building_type": "terraced_length",
            "estimated_storeys": 2,
            "heating_system_guess": "gas_boiler",
            "adjacent_side": "length",
            "estimated_units_in_row": 5,
            "confidence": 0.7,
            "reasoning": "Row of 5 terraced houses",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            result = await analyze_streetview(str(img))

        assert result.estimated_units_in_row == 5
        assert result.building_type == BuildingType.TERRACED_LENGTH

    @pytest.mark.asyncio
    async def test_missing_unit_count_defaults_to_one(self, tmp_path):
        """Missing estimated_units_in_row defaults to 1."""
        img = tmp_path / "streetview.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "construction_epoch": "before_1980",
            "building_type": "detached",
            "estimated_storeys": 2,
            "heating_system_guess": "oil_boiler",
            "adjacent_side": "length",
            "confidence": 0.8,
            "reasoning": "Detached house",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_streetview
            result = await analyze_streetview(str(img))

        assert result.estimated_units_in_row == 1


class TestBuildingContextInSatellitePrompt:
    """Test that building context is injected into satellite prompt."""

    @pytest.mark.asyncio
    async def test_terraced_context_appended(self, tmp_path):
        """Terraced building context is appended to satellite prompt."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "length_m": 10.0,
            "width_m": 7.0,
            "building_shape": "rectangular",
            "confidence": 0.7,
            "reasoning": "Single unit",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            # Uploaded image (no zoom): Claude measures metres, so it is told to measure one unit
            await analyze_satellite(
                str(img), lat=53.35, zoom=None,
                building_type="terraced_length",
                adjacent_side="length",
                estimated_units_in_row=4,
            )
            uploaded_prompt = mock_anthropic.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
                "messages"][0]["content"][1]["text"]

            # GPS path: Claude outlines the whole block; street view is only a home-count hint
            await analyze_satellite(
                str(img), lat=53.35, zoom=20,
                building_type="terraced_length",
                adjacent_side="length",
                estimated_units_in_row=4,
            )
            gps_prompt = mock_anthropic.AsyncAnthropic.return_value.messages.create.call_args.kwargs[
                "messages"][0]["content"][1]["text"]

        assert "ONE unit" in uploaded_prompt
        assert "terraced row" in uploaded_prompt
        assert "4" in uploaded_prompt
        assert "Hint from Street View" in gps_prompt
        assert "one home in a terrace, in a building of about 4 homes" in gps_prompt
        assert "ONE unit" not in gps_prompt

    @pytest.mark.asyncio
    async def test_no_context_when_none(self, tmp_path):
        """Prompt is unchanged when no building type is provided."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_settings, mock_anthropic = _make_mock_anthropic(json.dumps({
            "length_m": 10.0,
            "width_m": 7.0,
            "building_shape": "rectangular",
            "confidence": 0.7,
            "reasoning": "Clear roof",
        }))

        with patch("ber_automation.vision.claude_analyzer.get_settings", return_value=mock_settings), \
             patch("ber_automation.vision.claude_analyzer.anthropic", mock_anthropic):
            from ber_automation.vision.claude_analyzer import analyze_satellite
            await analyze_satellite(str(img), lat=53.35, zoom=20)

        call_args = mock_anthropic.AsyncAnthropic.return_value.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "CRITICAL: Building Context" not in prompt_text


class TestCorrectTerraceFootprint:
    """Test _correct_terrace_footprint safety net."""

    def _make_fp(self, length=12.0, width=24.0, confidence=0.7):
        return FootprintResult(
            length_m=length, width_m=width,
            area_m2=round(length * width, 1),
            confidence=confidence, source="claude_vision",
        )

    def _make_sa(self, btype="terraced_length", units=4, adjacent_side="length", confidence=0.7):
        return StreetViewAnalysis(
            building_type=BuildingType(btype),
            estimated_units_in_row=units,
            adjacent_side=adjacent_side,
            confidence=confidence,
        )

    def test_terraced_length_corrects_width(self):
        """Terraced with party wall on length -> divide width by units."""
        fp = self._make_fp(length=12.0, width=24.0)
        sa = self._make_sa(btype="terraced_length", units=4)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        assert result.width_m == 6.0  # 24 / 4
        assert result.length_m == 12.0  # unchanged
        assert result.area_m2 == 72.0
        assert result.confidence == 0.6  # 0.7 - 0.1

    def test_terraced_width_corrects_length(self):
        """Terraced with party wall on width -> divide length by units."""
        fp = self._make_fp(length=24.0, width=8.0)
        sa = self._make_sa(btype="terraced_width", units=4)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        assert result.length_m == 6.0  # 24 / 4
        assert result.width_m == 8.0  # unchanged
        assert result.area_m2 == 48.0

    def test_detached_unchanged(self):
        """Detached building is not corrected."""
        fp = self._make_fp(length=12.0, width=10.0)
        sa = self._make_sa(btype="detached", units=1)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        assert result.length_m == 12.0
        assert result.width_m == 10.0

    def test_semi_d_length_halves_width(self):
        """Semi-d with party wall on length -> divide width by 2."""
        fp = self._make_fp(length=10.0, width=16.0)
        sa = self._make_sa(btype="semi_d_length", units=2)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        assert result.width_m == 8.0  # 16 / 2
        assert result.length_m == 10.0

    def test_low_confidence_skips_correction(self):
        """Low confidence footprint is not corrected."""
        fp = self._make_fp(length=12.0, width=24.0, confidence=0.3)
        sa = self._make_sa(btype="terraced_length", units=4)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        assert result.width_m == 24.0  # unchanged
        assert result.confidence == 0.3

    def test_too_small_per_unit_skips_correction(self):
        """If per-unit dimension would be < 4m, skip correction."""
        fp = self._make_fp(length=12.0, width=12.0)
        sa = self._make_sa(btype="terraced_length", units=4)
        result = BERPipeline._correct_terrace_footprint(fp, sa)
        # 12 / 4 = 3.0 < 4.0 -> skip
        assert result.width_m == 12.0  # unchanged
