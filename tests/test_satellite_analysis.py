"""Tests for Claude Vision satellite analysis, footprint reconciliation, and validation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ber_automation.models import (
    FootprintResult,
    PipelineResult,
    StreetViewAnalysis,
)
from ber_automation.pipeline import BERPipeline


# ---------------------------------------------------------------------------
# analyze_satellite() tests
# ---------------------------------------------------------------------------

class TestAnalyzeSatellite:
    """Test the Claude Vision satellite analysis function."""

    @pytest.mark.asyncio
    async def test_valid_response(self, tmp_path):
        """Valid Claude response produces correct FootprintResult."""
        # Create a dummy image file
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "length_m": 11.5,
            "width_m": 8.2,
            "building_shape": "rectangular",
            "confidence": 0.75,
            "reasoning": "Clear roof visible",
        })

        with patch("ber_automation.vision.claude_analyzer.get_settings") as mock_settings, \
             patch("ber_automation.vision.claude_analyzer.anthropic") as mock_anthropic:
            mock_settings.return_value.anthropic_api_key = "test-key"
            mock_settings.return_value.claude_model = "test-model"
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

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

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "This is not JSON at all"

        with patch("ber_automation.vision.claude_analyzer.get_settings") as mock_settings, \
             patch("ber_automation.vision.claude_analyzer.anthropic") as mock_anthropic:
            mock_settings.return_value.anthropic_api_key = "test-key"
            mock_settings.return_value.claude_model = "test-model"
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

        assert result.confidence == 0
        assert result.source == "claude_vision"

    @pytest.mark.asyncio
    async def test_out_of_bounds_dimensions_clamped(self, tmp_path):
        """Dimensions outside [4, 25] are clamped."""
        img = tmp_path / "satellite.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "length_m": 50.0,
            "width_m": 2.0,
            "building_shape": "rectangular",
            "confidence": 0.8,
            "reasoning": "Test",
        })

        with patch("ber_automation.vision.claude_analyzer.get_settings") as mock_settings, \
             patch("ber_automation.vision.claude_analyzer.anthropic") as mock_anthropic:
            mock_settings.return_value.anthropic_api_key = "test-key"
            mock_settings.return_value.claude_model = "test-model"
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.Anthropic.return_value = mock_client

            from ber_automation.vision.claude_analyzer import analyze_satellite
            result = await analyze_satellite(str(img), lat=53.35, zoom=20)

        assert result.length_m == 25.0  # clamped from 50
        assert result.width_m == 4.0    # clamped from 2


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
            eircode="D02X285",
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
