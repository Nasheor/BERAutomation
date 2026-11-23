"""Census housing-stock model: an energy estimate for every home in a Small Area, without images.

The CSO Census 2022 gives, per Small Area (80-120 homes), how many homes were built in each
period, use each central-heating fuel, and have each number of rooms. Each combination of
era x fuel x size is a *typical home*; the calculator rates it, and its weight is the product
of the three shares. Weighted together they give the area's band mix and, scaled by the
number of households, its total heat demand, delivered and primary energy and CO2.

Assumptions (shown with the results):
- Era, fuel and size are independent: the census publishes them separately, not crossed.
- Dwelling type follows the CSO urban flag: semi-detached in towns, detached in rural areas.
- Rooms x 20 m2 = gross floor area (as in ``census.FLOOR_M2_PER_ROOM``); under 70 m2 one storey,
  else two; footprint 1.25 : 1.
- Fuels without an HWB equivalent (coal, peat, LPG, other, none) are left out; the homes that
  use them are assumed to perform like the modelled ones (``modelled_share`` says how many).
- Electric heating in homes built after 2010 is a heat pump (NZEB rules), as in
  ``census.choose_heating``.
"""

from __future__ import annotations

import math

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.ber_engine.rating import get_ber_band
from ber_automation.community.models import SmallAreaStock
from ber_automation.geospatial.census import (
    FLOOR_M2_PER_ROOM,
    ROOMS_8_PLUS,
    choose_epoch,
    choose_heating,
)
from ber_automation.models import (
    BERResult,
    BuildingInput,
    BuildingType,
    CensusArea,
    ConstructionEpoch,
    Country,
    HeatingSystem,
)

# Census fuel -> heating system modelled for it
STOCK_FUELS: dict[str, HeatingSystem] = {
    "gas": HeatingSystem.GAS_BOILER,
    "oil": HeatingSystem.OIL_BOILER,
    "electricity": HeatingSystem.ELECTRIC_DIRECT,
    "wood": HeatingSystem.BIOMASS,
}
ONE_STOREY_BELOW_M2 = 70.0
FOOTPRINT_ASPECT = 1.25
# Used when the census has no usable rooms mix for the area (a typical 3-bed semi)
DEFAULT_ROOMS = "5"

_calc = HWBCalculator()


def rooms_to_floor_m2(rooms: str) -> float:
    return (ROOMS_8_PLUS if rooms == "8+" else float(rooms)) * FLOOR_M2_PER_ROOM


def typical_building(
    floor_m2: float,
    epoch: ConstructionEpoch,
    heating: HeatingSystem,
    urban: bool,
    country: Country = Country.IRELAND,
) -> BuildingInput:
    """A typical home of *floor_m2* gross floor area (see module assumptions)."""
    storeys = 1 if floor_m2 < ONE_STOREY_BELOW_M2 else 2
    per_storey = floor_m2 / storeys
    length = math.sqrt(per_storey * FOOTPRINT_ASPECT)
    return BuildingInput(
        length=round(length, 2),
        width=round(per_storey / length, 2),
        heated_storeys=storeys,
        building_type=BuildingType.SEMI_D_LENGTH if urban else BuildingType.DETACHED,
        construction_epoch=epoch,
        country=country,
        heating_system=heating,
    )


def _system_for(fuel: str, epoch: ConstructionEpoch) -> HeatingSystem:
    system = STOCK_FUELS[fuel]
    if system == HeatingSystem.ELECTRIC_DIRECT and epoch == ConstructionEpoch.AFTER_2010:
        return HeatingSystem.HEAT_PUMP_AIR
    return system


def _normalised(shares: dict[str, float], keep=None) -> dict[str, float]:
    kept = {k: v for k, v in shares.items() if v > 0 and (keep is None or k in keep)}
    total = sum(kept.values())
    return {k: v / total for k, v in kept.items()} if total > 0 else {}


def small_area_stock(area: CensusArea, country: Country = Country.IRELAND) -> SmallAreaStock:
    """Estimate the energy use of every home in the Small Area from its census mix."""
    stock = SmallAreaStock(small_area=area.small_area, urban=area.urban, urban_area=area.urban_area)
    era = _normalised(area.era.shares) if area.era else {}
    fuels = _normalised(area.heating_shares, keep=STOCK_FUELS)
    rooms = _normalised(area.rooms_shares)
    households = max(
        area.era.households if area.era else 0, area.heating_households, area.rooms_households,
    )
    stock.households = households
    stock.era_shares, stock.fuel_shares = era, fuels
    stock.modelled_share = round(
        sum(v for k, v in area.heating_shares.items() if k in STOCK_FUELS), 3
    ) if area.heating_shares else 0.0

    if not era:
        stock.notes.append("No usable build-period mix in the census for this area.")
        return stock
    if not fuels:
        fallback = "gas" if area.urban else "oil"
        fuels = {fallback: 1.0}
        stock.notes.append(f"No usable fuel mix: all homes taken as {fallback}-heated (urban flag).")
    if not rooms:
        rooms = {DEFAULT_ROOMS: 1.0}
        stock.notes.append("No usable rooms mix: all homes taken as 5 rooms (about 100 m²).")

    # Per average home: floor area and yearly energy, weighted over all combinations
    floor = heat = delivered = primary = co2 = 0.0
    bands: dict[str, float] = {}
    for epoch_value, w_era in era.items():
        epoch = ConstructionEpoch(epoch_value)
        for fuel, w_fuel in fuels.items():
            for room_key, w_rooms in rooms.items():
                w = w_era * w_fuel * w_rooms
                area_m2 = rooms_to_floor_m2(room_key)
                ber = _calc.calculate_ber(
                    typical_building(area_m2, epoch, _system_for(fuel, epoch), area.urban, country)
                )
                hw = ber.hwb_result
                floor += w * hw.floor_area
                heat += w * hw.heating_demand_kwh
                delivered += w * hw.total_kwh_per_m2 * hw.floor_area
                primary += w * ber.kwh_per_m2 * hw.floor_area
                co2 += w * hw.co2_kg
                bands[ber.ber_band] = bands.get(ber.ber_band, 0.0) + w
                stock.typical_homes += 1

    stock.floor_area_m2 = round(floor * households, 1)
    stock.heat_demand_mwh = round(heat * households / 1000, 2)
    stock.delivered_mwh = round(delivered * households / 1000, 2)
    stock.primary_mwh = round(primary * households / 1000, 2)
    stock.co2_t = round(co2 * households / 1000, 2)
    stock.mean_primary_kwh_m2 = round(primary / floor, 1) if floor > 0 else 0.0
    stock.band_shares = {b: round(s, 4) for b, s in sorted(bands.items(), key=lambda kv: _band_order(kv[0]))}
    if stock.modelled_share and stock.modelled_share < 0.999:
        stock.notes.append(
            f"{1 - stock.modelled_share:.0%} of households use a fuel the calculator does not "
            "cover (coal, peat, LPG, other, none); they are assumed to perform like the rest."
        )
    return stock


_BAND_NAMES = [b for b, _, _ in BER_BANDS]


def _band_order(band: str) -> int:
    return _BAND_NAMES.index(band) if band in _BAND_NAMES else len(_BAND_NAMES)


def census_home_estimate(area: CensusArea, country: Country = Country.IRELAND) -> BERResult | None:
    """Estimate for one home known only by its Small Area: the area's most likely home.

    Era and heating are chosen exactly as the image pipeline does without images
    (``choose_epoch`` / ``choose_heating``); the size is the area's commonest room count.
    """
    epoch, _ = choose_epoch(area.era, None)
    if epoch is None:
        return None
    heating, _ = choose_heating(area, None, epoch)
    rooms = max(area.rooms_shares, key=area.rooms_shares.get) if area.rooms_shares else DEFAULT_ROOMS
    building = typical_building(
        rooms_to_floor_m2(rooms), epoch, heating or HeatingSystem.GAS_BOILER, area.urban, country,
    )
    return _calc.calculate_ber(building)


def band_from_kwh(kwh_m2: float) -> str:
    return get_ber_band(kwh_m2)[0]
