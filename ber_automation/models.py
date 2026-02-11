"""Shared Pydantic data models for the BER Automation pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class BuildingType(str, Enum):
    """Building type classification matching the Excel tool."""
    DETACHED = "detached"
    SEMI_D_LENGTH = "semi_d_length"   # adjacent on length side
    SEMI_D_WIDTH = "semi_d_width"     # adjacent on width side
    TERRACED_LENGTH = "terraced_length"  # adjacent on both length sides
    TERRACED_WIDTH = "terraced_width"    # adjacent on both width sides


class ConstructionEpoch(str, Enum):
    """Construction era classification — 5 epochs matching the Excel tool."""
    BEFORE_1980 = "before_1980"
    EPOCH_1980_1990 = "1980_1990"
    EPOCH_1990_2000 = "1990_2000"
    EPOCH_2000_2010 = "2000_2010"
    AFTER_2010 = "after_2010"


class HeatingSystem(str, Enum):
    """Heating system types matching the Excel tool dropdowns."""
    OIL_BOILER = "oil_boiler"
    GAS_BOILER = "gas_boiler"
    BIOMASS = "biomass"
    ELECTRIC_DIRECT = "electric_direct"
    HEAT_PUMP_AIR = "heat_pump_air"
    HEAT_PUMP_GROUND = "heat_pump_ground"
    HEAT_PUMP_WATER = "heat_pump_water"
    DISTRICT_HEATING = "district_heating"


class Country(str, Enum):
    """Supported countries/regions for climate data."""
    IRELAND = "ireland"
    FRANCE = "france"
    GERMANY = "germany"
    BELGIUM = "belgium"
    NETHERLANDS = "netherlands"
    AUSTRIA = "austria"


# --- Data Models ---

class Coordinates(BaseModel):
    """GPS coordinates from geocoding."""
    lat: float
    lng: float
    formatted_address: str = ""


class WindowDoorAreas(BaseModel):
    """Window and door areas by orientation in m²."""
    north: float = 0.0
    east: float = 0.0
    south: float = 0.0
    west: float = 0.0
    doors: float = 0.0


class BuildingInput(BaseModel):
    """All inputs needed for the HWB calculation."""
    # Geometry
    length: float = Field(gt=0, description="Building length in meters")
    width: float = Field(gt=0, description="Building width in meters")
    heated_storeys: int = Field(ge=1, default=2, description="Number of heated storeys")
    storey_height: float = Field(gt=0, default=3.0, description="Storey height in meters")

    # Classification
    building_type: BuildingType = BuildingType.DETACHED
    construction_epoch: ConstructionEpoch = ConstructionEpoch.BEFORE_1980
    country: Country = Country.IRELAND

    # Occupancy
    quantity: int = Field(ge=1, default=1, description="Number of identical buildings")
    residents: Optional[float] = Field(default=None, description="Number of residents (auto-calculated if None)")

    # Windows/doors (None = use defaults based on building type)
    window_door_areas: Optional[WindowDoorAreas] = None

    # Heating
    heating_system: HeatingSystem = HeatingSystem.GAS_BOILER
    hot_water_electric_separate: bool = False

    @property
    def floor_area_per_storey(self) -> float:
        return self.length * self.width

    @property
    def total_heated_area(self) -> float:
        return self.floor_area_per_storey * self.heated_storeys

    @property
    def heated_volume(self) -> float:
        return self.total_heated_area * self.storey_height

    @property
    def effective_residents(self) -> float:
        if self.residents is not None:
            return self.residents
        return max(1.0, self.total_heated_area / 52.0)


class RetrofitInput(BaseModel):
    """Retrofit measure inputs."""
    wall_insulation_cm: float = Field(default=12.0, ge=0, description="Additional exterior wall insulation in cm")
    roof_insulation_cm: float = Field(default=20.0, ge=0, description="Additional roof insulation in cm")
    window_u_value: float = Field(default=1.0, gt=0, description="Replacement window U-value W/m²K")
    heating_system_after: Optional[HeatingSystem] = None
    hot_water_electric_separate_after: bool = False


class FootprintResult(BaseModel):
    """Result from building footprint extraction."""
    length_m: float
    width_m: float
    area_m2: float
    confidence: float = Field(ge=0, le=1)
    contour_points: list[list[int]] = Field(default_factory=list)
    source: str = "opencv"  # "opencv", "claude_vision", "fallback"
    building_shape: str = "rectangular"


class StreetViewAnalysis(BaseModel):
    """Result from Claude Vision street view analysis."""
    construction_epoch: ConstructionEpoch = ConstructionEpoch.BEFORE_1980
    building_type: BuildingType = BuildingType.DETACHED
    estimated_storeys: int = 2
    heating_system_guess: HeatingSystem = HeatingSystem.GAS_BOILER
    adjacent_side: str = "length"  # "length" or "width" for semi-d/terraced
    confidence: float = Field(ge=0, le=1, default=0.5)
    reasoning: str = ""


class HWBResult(BaseModel):
    """HWB (Heating demand) calculation result."""
    # Geometry
    floor_area: float
    heated_volume: float
    envelope_area: float

    # Heat loss components
    transmission_heat_loss: float  # W/K
    ventilation_heat_loss: float   # W/K

    # Gains
    solar_gains: float   # kWh/year
    internal_gains: float  # kWh/year

    # Final results
    heating_demand_kwh: float        # kWh/year (useful energy)
    hwb: float                       # kWh/m²/year
    final_energy_kwh: float          # kWh/year (purchased)
    final_energy_kwh_per_m2: float   # kWh/m²/year
    hot_water_kwh: float             # kWh/year
    total_kwh_per_m2: float          # (heating + hot water) kWh/m²/year
    co2_kg: float                    # kg CO2/year
    co2_kg_per_m2: float             # kg CO2/m²/year


class BERResult(BaseModel):
    """Final BER rating result."""
    ber_band: str           # e.g. "B2"
    kwh_per_m2: float       # total primary energy kWh/m²/year
    color_hex: str          # display color
    hwb_result: HWBResult
    building_input: BuildingInput

    # Optional retrofit comparison
    retrofit_ber_band: Optional[str] = None
    retrofit_kwh_per_m2: Optional[float] = None
    retrofit_hwb_result: Optional[HWBResult] = None


class PipelineResult(BaseModel):
    """Complete pipeline output."""
    eircode: str
    coordinates: Optional[Coordinates] = None
    satellite_image_path: Optional[str] = None
    streetview_image_path: Optional[str] = None
    footprint: Optional[FootprintResult] = None
    street_analysis: Optional[StreetViewAnalysis] = None
    ber_result: Optional[BERResult] = None
    errors: list[str] = Field(default_factory=list)
