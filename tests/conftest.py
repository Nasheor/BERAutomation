"""Shared fixtures for tests."""

from __future__ import annotations

import pytest

from ber_automation.models import (
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
)


@pytest.fixture
def typical_irish_house() -> BuildingInput:
    """A typical pre-1980 Irish detached house."""
    return BuildingInput(
        length=10.0,
        width=8.0,
        heated_storeys=2,
        storey_height=3.0,
        building_type=BuildingType.DETACHED,
        construction_epoch=ConstructionEpoch.BEFORE_1980,
        country=Country.IRELAND,
        heating_system=HeatingSystem.OIL_BOILER,
    )


@pytest.fixture
def modern_semi_d() -> BuildingInput:
    """A modern (post-2010) semi-detached house."""
    return BuildingInput(
        length=9.0,
        width=7.0,
        heated_storeys=2,
        storey_height=2.7,
        building_type=BuildingType.SEMI_D_LENGTH,
        construction_epoch=ConstructionEpoch.AFTER_2010,
        country=Country.IRELAND,
        heating_system=HeatingSystem.HEAT_PUMP_AIR,
    )
