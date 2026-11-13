"""Tests for reading and checking the official-BER sample CSV."""

from __future__ import annotations

from pathlib import Path

from ber_automation.evaluation.official_sample import (
    COLUMNS,
    epoch_from_year,
    load_official_sample,
    normalise_eircode,
    summarise,
)
from ber_automation.models import ConstructionEpoch, HeatingSystem

GOOD = {
    "id": "1", "eircode": "t12k7ac", "county": "cork", "settlement": "Urban",
    "listing_source": "daft.ie", "date_recorded": "2026-11-20", "ber_number": "108 123 456",
    "ber_band": "a3", "ber_kwh_m2_yr": "62.2", "dwelling_type": "Semi-Detached",
    "year_built": "2004", "floor_area_m2": "116", "storeys": "2", "heating": "gas_boiler",
    "register_checked": "yes",
}


def _write(tmp_path: Path, rows: list[dict], columns=COLUMNS) -> Path:
    path = tmp_path / "sample.csv"
    lines = [",".join(columns)]
    lines += [",".join(str(row.get(c, "")) for c in columns) for row in rows]
    # Excel saves CSV with a byte-order mark
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def test_good_row_is_read_and_normalised(tmp_path):
    homes, problems = load_official_sample(_write(tmp_path, [GOOD]))
    assert problems == []
    home = homes[0]
    assert home.eircode == "T12 K7AC"
    assert home.county == "Cork"
    assert home.settlement == "urban"
    assert home.ber_number == "108123456"
    assert (home.ber_band, home.ber_kwh_m2_yr) == ("A3", 62.2)
    assert home.dwelling_type == "semi_detached"
    assert home.heating is HeatingSystem.GAS_BOILER
    assert home.epoch is ConstructionEpoch.EPOCH_2000_2010
    assert home.register_checked


def test_optional_columns_may_be_empty_or_absent(tmp_path):
    required_only = [c for c in COLUMNS if c in GOOD and c not in (
        "dwelling_type", "year_built", "floor_area_m2", "storeys", "heating", "register_checked")]
    homes, problems = load_official_sample(_write(tmp_path, [GOOD], columns=required_only))
    assert problems == []
    assert homes[0].dwelling_type is None and homes[0].epoch is None
    assert not homes[0].register_checked


def test_band_that_does_not_match_the_energy_value_is_reported(tmp_path):
    homes, problems = load_official_sample(_write(tmp_path, [{**GOOD, "ber_band": "B2"}]))
    assert len(homes) == 1          # kept: either value could be the typing mistake
    assert "ber_band B2 does not match 62.2 kWh/m2/yr (that value is band A3)" in problems[0]


def test_unusable_required_values_drop_the_row(tmp_path):
    rows = [
        {**GOOD, "id": "1", "eircode": "T12 K7A"},
        {**GOOD, "id": "2", "ber_number": "12345"},
        {**GOOD, "id": "3", "ber_band": "H"},
        {**GOOD, "id": "4", "ber_kwh_m2_yr": "n/a"},
        {**GOOD, "id": "5", "settlement": "suburb"},
        {**GOOD, "id": "6", "date_recorded": "20/11/2026"},
        {**GOOD, "id": "7", "county": ""},
    ]
    homes, problems = load_official_sample(_write(tmp_path, rows))
    assert homes == []
    assert len(problems) == 7
    assert "line 2 (id 1): eircode 'T12 K7A' is not a valid Eircode" in problems
    assert "line 8 (id 7): county is empty" in problems


def test_bad_optional_values_are_reported_and_left_out(tmp_path):
    row = {**GOOD, "dwelling_type": "apartment", "year_built": "204", "floor_area_m2": "5",
           "storeys": "2.5", "heating": "gas", "register_checked": "maybe"}
    homes, problems = load_official_sample(_write(tmp_path, [row]))
    assert len(problems) == 6
    home = homes[0]
    assert (home.dwelling_type, home.year_built, home.floor_area_m2, home.storeys,
            home.heating) == (None, None, None, None, None)


def test_duplicates_are_reported(tmp_path):
    rows = [GOOD, {**GOOD, "id": "2"}]
    _, problems = load_official_sample(_write(tmp_path, rows))
    assert "eircode T12 K7AC appears 2 times" in problems
    assert "ber_number 108123456 appears 2 times" in problems


def test_missing_required_column_stops_the_read(tmp_path):
    columns = [c for c in COLUMNS if c != "ber_number"]
    homes, problems = load_official_sample(_write(tmp_path, [GOOD], columns=columns))
    assert homes == []
    assert problems == ["missing column(s): ber_number"]


def test_empty_template_gives_no_homes_and_no_problems(tmp_path):
    assert load_official_sample(_write(tmp_path, [])) == ([], [])


def test_the_template_in_the_repo_has_the_expected_columns():
    template = Path(__file__).resolve().parent.parent / "data" / "validation" / "official" / "sample.csv"
    header = template.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(",") == list(COLUMNS)
    assert load_official_sample(template)[1] == []


def test_eircode_and_era_helpers():
    assert normalise_eircode(" d6w xy12 ") == "D6W XY12"
    assert normalise_eircode("B12 K7AC") is None      # B is not a routing-key letter
    assert epoch_from_year(1979) is ConstructionEpoch.BEFORE_1980
    assert epoch_from_year(1980) is ConstructionEpoch.EPOCH_1980_1990
    assert epoch_from_year(1999) is ConstructionEpoch.EPOCH_1990_2000
    assert epoch_from_year(2010) is ConstructionEpoch.AFTER_2010


def test_summary_counts_and_orders_bands(tmp_path):
    rows = [
        GOOD,
        {**GOOD, "id": "2", "eircode": "T23 HYW6", "ber_number": "108123457",
         "ber_band": "G", "ber_kwh_m2_yr": "500", "settlement": "rural", "year_built": ""},
        {**GOOD, "id": "3", "eircode": "V92 K254", "ber_number": "108123458",
         "county": "Kerry", "ber_band": "B2", "ber_kwh_m2_yr": "103.3"},
    ]
    homes, problems = load_official_sample(_write(tmp_path, rows))
    assert problems == []
    summary = summarise(homes)
    assert summary["county"] == {"Cork": 2, "Kerry": 1}
    assert summary["settlement"] == {"rural": 1, "urban": 2}
    assert summary["era"] == {"(not recorded)": 1, "2000_2010": 2}
    assert list(summary["ber_band"]) == ["A3", "B2", "G"]
