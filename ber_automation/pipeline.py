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
from ber_automation.geospatial.imagery import (
    fetch_satellite_image,
    fetch_streetview_image,
    fetch_streetview_images,
)
from ber_automation.models import (
    BuildingInput,
    BuildingType,
    Coordinates,
    FootprintResult,
    PipelineResult,
    RetrofitInput,
    StreetViewAnalysis,
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

        # Phase 2: Fetch images (parallel) — satellite + 4 Street View angles
        sat_path = self.output_dir / "satellite.jpg"
        sv_dir = self.output_dir / "streetview"

        sat_task = fetch_satellite_image(coords, sat_path)
        sv_task = fetch_streetview_images(coords, sv_dir)

        sv_paths: list[Path] = []
        try:
            sat_result, sv_result = await asyncio.gather(
                sat_task, sv_task, return_exceptions=True
            )
            if isinstance(sat_result, Path):
                result.satellite_image_path = str(sat_result)
            elif isinstance(sat_result, Exception):
                result.errors.append(f"Satellite image failed: {sat_result}")

            if isinstance(sv_result, list):
                sv_paths = sv_result
                if sv_paths:
                    # Store first image as the representative for display
                    result.streetview_image_path = str(sv_paths[0])
                else:
                    result.errors.append("No Street View available at this location")
            elif isinstance(sv_result, Exception):
                result.errors.append(f"Street View failed: {sv_result}")
        except Exception as e:
            result.errors.append(f"Image fetching failed: {e}")

        # Phase 3: Street view analysis (moved before satellite to inform footprint)
        if sv_paths:
            try:
                analysis = await analyze_streetview(sv_paths)
                result.street_analysis = analysis
            except Exception as e:
                result.errors.append(f"Claude analysis failed: {e}")

        # Phase 4: Footprint extraction (Claude Vision primary, OpenCV fallback)
        if result.satellite_image_path:
            claude_fp = None
            opencv_fp = None

            # Build context kwargs from street view when confidence is sufficient
            sat_kwargs: dict = {}
            if result.street_analysis and result.street_analysis.confidence >= 0.4:
                sa = result.street_analysis
                sat_kwargs["building_type"] = sa.building_type.value
                sat_kwargs["adjacent_side"] = sa.adjacent_side
                sat_kwargs["estimated_units_in_row"] = sa.estimated_units_in_row

            # Primary: Claude Vision satellite analysis
            try:
                claude_fp = await analyze_satellite(
                    result.satellite_image_path,
                    lat=coords.lat,
                    zoom=20,
                    **sat_kwargs,
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

            # Apply terrace correction safety net
            if footprint and result.street_analysis:
                footprint = self._correct_terrace_footprint(
                    footprint, result.street_analysis,
                )

            if footprint and footprint.confidence > 0:
                result.footprint = footprint
            else:
                result.errors.append("Footprint extraction found no building contour")

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

    @staticmethod
    def _correct_terrace_footprint(
        footprint: FootprintResult,
        street_analysis: StreetViewAnalysis,
    ) -> FootprintResult:
        """Divide the repeating dimension by unit count for terraced/semi-d buildings.

        Safety net: if Claude measured the entire terrace row instead of one unit,
        this divides the repeating dimension to get a single-unit footprint.
        """
        btype = street_analysis.building_type.value
        units = street_analysis.estimated_units_in_row

        # Only correct for terraced or semi-d with multiple units
        if units <= 1:
            return footprint
        if not btype.startswith(("terraced", "semi_d")):
            return footprint
        # Skip correction when confidence is too low
        if footprint.confidence < 0.4:
            return footprint

        length = footprint.length_m
        width = footprint.width_m

        # Determine which dimension repeats based on party wall orientation
        # Party wall on LENGTH side → units repeat along WIDTH
        # Party wall on WIDTH side → units repeat along LENGTH
        if btype in ("terraced_length", "semi_d_length"):
            per_unit = width / units
            if per_unit < 4.0:
                return footprint  # too small — probably already single-unit
            width = round(per_unit, 1)
        elif btype in ("terraced_width", "semi_d_width"):
            per_unit = length / units
            if per_unit < 4.0:
                return footprint
            length = round(per_unit, 1)
        else:
            return footprint

        area = round(length * width, 1)
        # Apply confidence penalty for the correction
        corrected_confidence = round(max(0.3, footprint.confidence - 0.1), 2)

        return FootprintResult(
            length_m=length,
            width_m=width,
            area_m2=area,
            confidence=corrected_confidence,
            source=footprint.source,
            building_shape=footprint.building_shape,
            contour_points=footprint.contour_points,
        )

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

        # Classification from Claude analysis (require confidence >= 0.4)
        if result.street_analysis and result.street_analysis.confidence >= 0.4:
            sa = result.street_analysis
            params["building_type"] = sa.building_type
            params["construction_epoch"] = sa.construction_epoch
            params["heated_storeys"] = sa.estimated_storeys
            params["heating_system"] = sa.heating_system_guess

        # Apply any user overrides
        if overrides:
            params.update(overrides)

        return BuildingInput(**params)
