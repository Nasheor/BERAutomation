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
    """Supported countries/regions for climate data.

    All seven Interreg North-West Europe (CIRCUS) programme countries are supported,
    plus Austria (used in the original HWB Excel tool).
    """
    IRELAND = "ireland"
    FRANCE = "france"
    GERMANY = "germany"
    BELGIUM = "belgium"
    NETHERLANDS = "netherlands"
    LUXEMBOURG = "luxembourg"
    SWITZERLAND = "switzerland"
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
    # Claude roof-corner path: the attached block that was outlined and split into homes
    block_length_m: Optional[float] = None
    block_width_m: Optional[float] = None
    units_in_block: Optional[int] = None   # homes the block was split into
    units_claude: Optional[int] = None     # Claude's own count
    units_visible: bool = False            # Claude could see where the homes end
    units_source: str = ""                 # "claude", or "census" (Small Area room mix)
    block_clipped: bool = False            # outline reaches the image edge: part of a longer row


class StreetViewAnalysis(BaseModel):
    """Result from Claude Vision street view analysis."""
    construction_epoch: ConstructionEpoch = ConstructionEpoch.BEFORE_1980
    building_type: BuildingType = BuildingType.DETACHED
    estimated_storeys: int = 2
    heating_system_guess: HeatingSystem = HeatingSystem.GAS_BOILER
    adjacent_side: str = "length"  # "length" or "width" for semi-d/terraced
    estimated_units_in_row: int = Field(ge=1, default=1, description="Units in terrace row (1=detached, 2=semi-d)")
    heating_observed: bool = False  # True only if a heating clue (tank, flue, meter, heat pump) was seen
    confidence: float = Field(ge=0, le=1, default=0.5)
    reasoning: str = ""


class HouseDescription(BaseModel):
    """Plain description of the target house from Street View (display only).

    Not used by the calculation. See describe_house() in vision/claude_analyzer.py.
    """
    # What the FRONT image shows of the target: "front" (street facade), "side" (gable or
    # side wall), "partial" (facade partly hidden) or "hidden" (blurred or not visible)
    target_view: str = "front"
    # A house of the same design seen more clearly in one of the images, used to fill in
    # details hidden on the target. Heading index of that image (0 = front view) and the
    # x-range of the house's facade in it; None when no such house was found.
    similar_house_view: Optional[int] = None
    similar_house_x1: Optional[int] = None
    similar_house_x2: Optional[int] = None
    inferred_from_similar: list[str] = Field(default_factory=list)  # details taken from it
    description: str = ""

    @property
    def uses_similar_house(self) -> bool:
        """True when a similar house supplied details the front image did not show."""
        return self.similar_house_view is not None and (
            self.target_view != "front" or bool(self.inferred_from_similar)
        )


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
    ber_band: str           # e.g. "B2" (Irish BER scale, common reference)
    kwh_per_m2: float       # total primary energy kWh/m²/year
    color_hex: str          # display color
    hwb_result: HWBResult
    building_input: BuildingInput

    # Native country EPC rating (e.g. "C" on French DPE, "B" on German Energieausweis)
    native_epc_band: Optional[str] = None
    native_epc_scale: Optional[str] = None   # e.g. "DPE", "Energieausweis"
    native_epc_color: Optional[str] = None

    # Optional retrofit comparison
    retrofit_ber_band: Optional[str] = None
    retrofit_kwh_per_m2: Optional[float] = None
    retrofit_hwb_result: Optional[HWBResult] = None
    retrofit_native_epc_band: Optional[str] = None


class CensusEraPrior(BaseModel):
    """Build-period mix of the homes in the property's census Small Area (Ireland)."""
    households: int = 0           # households with a stated year built
    shares: dict[str, float] = Field(default_factory=dict)  # epoch value -> share 0-1
    dominant_epoch: ConstructionEpoch = ConstructionEpoch.BEFORE_1980
    dominant_share: float = 0.0


class CensusArea(BaseModel):
    """CSO Census 2022 facts for the Small Area containing the property (Ireland)."""
    small_area: str = ""          # CSO Small Area code (SA_PUB2022)
    urban: bool = False           # inside a CSO urban area (town, village or city)
    urban_area: str = ""          # e.g. "Cork city and suburbs"; "" when rural
    era: Optional[CensusEraPrior] = None
    heating_households: int = 0   # households with a stated central-heating fuel
    heating_shares: dict[str, float] = Field(default_factory=dict)  # gas/oil/electricity/... -> 0-1
    rooms_households: int = 0     # households with a stated number of rooms
    rooms_shares: dict[str, float] = Field(default_factory=dict)  # "1".."7", "8+" -> 0-1


class PipelineResult(BaseModel):
    """Complete pipeline output."""
    address: str
    coordinates: Optional[Coordinates] = None
    satellite_image_path: Optional[str] = None
    streetview_image_path: Optional[str] = None
    footprint: Optional[FootprintResult] = None
    street_analysis: Optional[StreetViewAnalysis] = None
    census: Optional[CensusArea] = None
    # Where the era / heating used by the calculation came from:
    # "census", "census_urban" (heating only), "streetview", "default" or "override"
    epoch_source: Optional[str] = None
    heating_source: Optional[str] = None
    house_description: Optional[HouseDescription] = None
    # Windows marked on the similar house (see HouseDescription.similar_house_view); 0 if none
    similar_house_windows: int = 0
    # Vision model that read the images: provider ("claude" / "mistral") and model ID
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    ber_result: Optional[BERResult] = None
    errors: list[str] = Field(default_factory=list)
