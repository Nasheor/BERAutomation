"""Data models for community assessment (saved as JSON)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ber_automation.models import BERResult, CensusArea, Coordinates, Country

IMAGES = "images"
CENSUS = "census"


class CommunityHome(BaseModel):
    """One listed home: where it is and its estimates."""
    id: str
    address: str
    coordinates: Optional[Coordinates] = None
    small_area: str = ""                         # CSO Small Area code ("" outside Ireland)
    census_estimate: Optional[BERResult] = None  # typical home for its Small Area
    image_estimate: Optional[BERResult] = None   # full pipeline on its images
    image_runs: int = 0                          # pipeline runs behind image_estimate
    errors: list[str] = Field(default_factory=list)

    @property
    def best(self) -> Optional[BERResult]:
        """The estimate to use: the images when analysed, else the census."""
        return self.image_estimate or self.census_estimate

    @property
    def source(self) -> str:
        if self.image_estimate is not None:
            return IMAGES
        return CENSUS if self.census_estimate is not None else ""


class SmallAreaStock(BaseModel):
    """Census housing-stock estimate for a whole Small Area (all its homes, no images)."""
    small_area: str
    urban: bool = False
    urban_area: str = ""
    households: int = 0               # households in the census tables
    modelled_share: float = 0.0       # share of households whose fuel the calculator covers
    typical_homes: int = 0            # era x fuel x size combinations calculated
    floor_area_m2: float = 0.0        # total gross floor area, all households
    heat_demand_mwh: float = 0.0      # space heating demand (HWB x floor area), MWh/yr
    delivered_mwh: float = 0.0        # fuel / electricity bought, heating + hot water
    primary_mwh: float = 0.0
    co2_t: float = 0.0
    mean_primary_kwh_m2: float = 0.0  # total primary energy / total floor area
    band_shares: dict[str, float] = Field(default_factory=dict)  # BER band -> share of homes
    era_shares: dict[str, float] = Field(default_factory=dict)
    fuel_shares: dict[str, float] = Field(default_factory=dict)  # modelled fuels only
    notes: list[str] = Field(default_factory=list)


class CommunityResult(BaseModel):
    """A community: its listed homes and the census stock of the Small Areas they are in."""
    name: str
    country: Country = Country.IRELAND
    created: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    homes: list[CommunityHome] = Field(default_factory=list)
    census: dict[str, CensusArea] = Field(default_factory=dict)      # Small Area code -> census facts
    areas: dict[str, SmallAreaStock] = Field(default_factory=dict)   # Small Area code -> stock

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "CommunityResult":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
