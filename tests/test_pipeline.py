"""Tests for the pipeline orchestrator (integration-level, mocked APIs)."""

from __future__ import annotations

import pytest

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.models import (
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
)


class TestPipelineManualInput:
    """Test the calculator path that the pipeline uses."""

    def test_end_to_end_manual(self):
        """Simulate what the pipeline does with manual inputs."""
        building = BuildingInput(
            length=10.0,
            width=8.0,
            heated_storeys=2,
            storey_height=3.0,
            building_type=BuildingType.DETACHED,
            construction_epoch=ConstructionEpoch.EPOCH_1990_2000,
            country=Country.IRELAND,
            heating_system=HeatingSystem.GAS_BOILER,
        )

        calc = HWBCalculator()
        ber = calc.calculate_ber(building)

        assert ber.ber_band is not None
        assert ber.kwh_per_m2 > 0
        assert ber.hwb_result.floor_area == 160.0
        assert ber.hwb_result.co2_kg > 0

    def test_all_epochs_produce_results(self):
        """Every construction epoch should produce a valid result."""
        calc = HWBCalculator()
        for epoch in ConstructionEpoch:
            building = BuildingInput(
                length=10.0,
                width=8.0,
                heated_storeys=2,
                building_type=BuildingType.DETACHED,
                construction_epoch=epoch,
                country=Country.IRELAND,
                heating_system=HeatingSystem.GAS_BOILER,
            )
            ber = calc.calculate_ber(building)
            assert ber.kwh_per_m2 > 0, f"Failed for epoch {epoch}"

    def test_all_countries_produce_results(self):
        """Every supported country should produce a valid result."""
        calc = HWBCalculator()
        for country in Country:
            building = BuildingInput(
                length=10.0,
                width=8.0,
                heated_storeys=2,
                building_type=BuildingType.DETACHED,
                construction_epoch=ConstructionEpoch.BEFORE_1980,
                country=country,
                heating_system=HeatingSystem.GAS_BOILER,
            )
            ber = calc.calculate_ber(building)
            assert ber.kwh_per_m2 > 0, f"Failed for country {country}"

    def test_all_heating_systems_produce_results(self):
        """Every heating system should produce a valid result."""
        calc = HWBCalculator()
        for hs in HeatingSystem:
            building = BuildingInput(
                length=10.0,
                width=8.0,
                heated_storeys=2,
                building_type=BuildingType.DETACHED,
                construction_epoch=ConstructionEpoch.BEFORE_1980,
                country=Country.IRELAND,
                heating_system=hs,
            )
            ber = calc.calculate_ber(building)
            assert ber.kwh_per_m2 > 0, f"Failed for heating system {hs}"
