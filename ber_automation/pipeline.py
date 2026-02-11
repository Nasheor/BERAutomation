"""Pipeline orchestrator — ties all phases together.

Flow: Eircode → geocode → fetch images (parallel) → footprint → Claude analysis
     → HWB calculation → BER rating
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.geospatial.geocoder import geocode_eircode
from ber_automation.geospatial.imagery import fetch_satellite_image, fetch_streetview_image
from ber_automation.models import (
    BuildingInput,
    BuildingType,
    Coordinates,
    FootprintResult,
    PipelineResult,
    RetrofitInput,
)
from ber_automation.vision.claude_analyzer import analyze_satellite, analyze_streetview
from ber_automation.vision.footprint import extract_footprint


class BERPipeline:
    """End-to-end BER estimation pipeline."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.calculator = HWBCalculator()

    async def run(
        self,
        eircode: str,
        retrofit: RetrofitInput | None = None,
        overrides: dict | None = None,
    ) -> PipelineResult:
        """Run the full pipeline for an Eircode.

        Args:
            eircode: Irish Eircode (e.g. "D02 X285").
            retrofit: Optional retrofit parameters for comparison.
            overrides: Optional dict of BuildingInput field overrides
                       (e.g. {"heating_system": "gas_boiler"}).

        Returns:
            PipelineResult with all intermediate and final results.
        """
        result = PipelineResult(eircode=eircode)

        # Phase 1: Geocode
        try:
            coords = await geocode_eircode(eircode)
            result.coordinates = coords
        except Exception as e:
            result.errors.append(f"Geocoding failed: {e}")
            return result

        # Phase 2: Fetch images (parallel)
        sat_path = self.output_dir / "satellite.png"
        sv_path = self.output_dir / "streetview.jpg"

        sat_task = fetch_satellite_image(coords, sat_path)
        sv_task = fetch_streetview_image(coords, sv_path)

        try:
            sat_result, sv_result = await asyncio.gather(
                sat_task, sv_task, return_exceptions=True
            )
            if isinstance(sat_result, Path):
                result.satellite_image_path = str(sat_result)
            elif isinstance(sat_result, Exception):
                result.errors.append(f"Satellite image failed: {sat_result}")

            if isinstance(sv_result, Path):
                result.streetview_image_path = str(sv_result)
            elif sv_result is None:
                result.errors.append("No Street View available at this location")
            elif isinstance(sv_result, Exception):
                result.errors.append(f"Street View failed: {sv_result}")
        except Exception as e:
            result.errors.append(f"Image fetching failed: {e}")

        # Phase 3: Footprint extraction (Claude Vision primary, OpenCV fallback)
        if result.satellite_image_path:
            claude_fp = None
            opencv_fp = None

            # Primary: Claude Vision satellite analysis
            try:
                claude_fp = await analyze_satellite(
                    result.satellite_image_path,
                    lat=coords.lat,
                    zoom=20,
                )
            except Exception as e:
                result.errors.append(f"Claude satellite analysis failed: {e}")

            # Secondary: OpenCV for cross-validation
            try:
                opencv_fp = extract_footprint(
                    result.satellite_image_path,
                    lat=coords.lat,
                    zoom=20,
                )
            except Exception as e:
                result.errors.append(f"OpenCV footprint extraction failed: {e}")

            # Reconcile results
            footprint = self._reconcile_footprints(claude_fp, opencv_fp)
            if footprint and footprint.confidence > 0:
                result.footprint = footprint
            else:
                result.errors.append("Footprint extraction found no building contour")

        # Phase 4: Claude analysis (from street view)
        if result.streetview_image_path:
            try:
                analysis = await analyze_streetview(result.streetview_image_path)
                result.street_analysis = analysis
            except Exception as e:
                result.errors.append(f"Claude analysis failed: {e}")

        # Phase 5: Build inputs and calculate BER
        try:
            building_input = self._build_input(result, overrides)
            ber_result = self.calculator.calculate_ber(building_input, retrofit)
            result.ber_result = ber_result
        except Exception as e:
            result.errors.append(f"BER calculation failed: {e}")

        return result

    @staticmethod
    def _reconcile_footprints(
        claude_fp: FootprintResult | None,
        opencv_fp: FootprintResult | None,
    ) -> FootprintResult | None:
        """Reconcile Claude Vision and OpenCV footprint results.

        Strategy:
        - If both succeed and agree within 30%, boost confidence by 0.15
        - If they disagree, trust Claude Vision
        - If Claude fails, fall back to OpenCV
        """
        claude_ok = claude_fp is not None and claude_fp.confidence >= 0.4
        opencv_ok = opencv_fp is not None and opencv_fp.confidence >= 0.15

        if claude_ok and opencv_ok:
            # Check agreement: both areas within 30%
            avg_area = (claude_fp.area_m2 + opencv_fp.area_m2) / 2
            diff = abs(claude_fp.area_m2 - opencv_fp.area_m2)
            agreement = diff / avg_area < 0.30 if avg_area > 0 else False

            if agreement:
                # Boost confidence when both methods agree
                boosted = min(1.0, claude_fp.confidence + 0.15)
                return FootprintResult(
                    length_m=claude_fp.length_m,
                    width_m=claude_fp.width_m,
                    area_m2=claude_fp.area_m2,
                    confidence=round(boosted, 2),
                    source="claude_vision",
                    building_shape=claude_fp.building_shape,
                )
            else:
                # Disagreement: trust Claude
                return claude_fp

        if claude_ok:
            return claude_fp

        if opencv_ok:
            return opencv_fp

        # Both failed — return whichever has higher confidence, or None
        candidates = [fp for fp in (claude_fp, opencv_fp) if fp is not None and fp.confidence > 0]
        if candidates:
            return max(candidates, key=lambda fp: fp.confidence)
        return None

    def _build_input(
        self,
        result: PipelineResult,
        overrides: dict | None = None,
    ) -> BuildingInput:
        """Assemble BuildingInput from pipeline results and overrides."""
        params: dict = {}

        # Dimensions from footprint (raised threshold from 0.2 to 0.4)
        if result.footprint and result.footprint.confidence >= 0.4:
            length = max(4.0, min(25.0, result.footprint.length_m))
            width = max(4.0, min(25.0, result.footprint.width_m))
            area = length * width

            # Area sanity check: reject unreasonable values
            if 20 <= area <= 500:
                params["length"] = length
                params["width"] = width
            else:
                params["length"] = 10.0
                params["width"] = 8.0
        else:
            # Fallback defaults for a typical Irish house
            params["length"] = 10.0
            params["width"] = 8.0

        # Classification from Claude analysis
        if result.street_analysis:
            sa = result.street_analysis
            params["building_type"] = sa.building_type
            params["construction_epoch"] = sa.construction_epoch
            params["heated_storeys"] = sa.estimated_storeys
            params["heating_system"] = sa.heating_system_guess

        # Apply any user overrides
        if overrides:
            params.update(overrides)

        return BuildingInput(**params)
