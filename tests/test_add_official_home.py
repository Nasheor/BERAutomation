"""Tests for the manual-lookup checklist (scripts/add_official_home.py)."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from ber_automation.evaluation.official_sample import (
    COLUMNS,
    dwelling_from_register,
    first_number,
    load_official_sample,
    parse_rating,
)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "add_official_home.py"
spec = importlib.util.spec_from_file_location("add_official_home", SCRIPT)
add_official_home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add_official_home)

TULLAMORE = [
    "https://www.daft.ie/for-sale/13-harbour-drive-tullamore-co-offaly/6707192",
    "r35hh93", "offaly", "urban", "113 779 219", "", "",
    "C2  177.03 (kWh/m2/yr)", "Semi-detached house", "2001", "137.17 (m2)",
    "21-04-2021", "",
]


def _reader(answers):
    answers = iter(answers)
    return lambda prompt: next(answers)


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_bytes(("﻿" + ",".join(COLUMNS) + "\r\n").encode("utf-8"))
    return path


@pytest.mark.parametrize("text, expected", [
    ("C2  177.03 (kWh/m2/yr)", ("C2", 177.03)),
    ("a1 22", ("A1", 22.0)),
    ("G 512.4", ("G", 512.4)),
    ("C2", None),
    ("H1 100", None),
    ("177.03", None),
])
def test_parse_rating(text, expected):
    assert parse_rating(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Semi-detached house", "semi_detached"),
    ("Detached house", "detached"),
    ("Mid-terrace house", "terraced"),
    ("End of terrace house", "semi_detached"),
    ("End-of-terrace house", "semi_detached"),
    ("semi_detached", "semi_detached"),
    ("Top-floor apartment", None),
    ("Maisonette", None),
])
def test_dwelling_from_register(text, expected):
    assert dwelling_from_register(text) == expected


def test_first_number():
    assert first_number("137.17 (m2)") == "137.17"
    assert first_number("1,485 sq ft") == "1485"
    assert first_number("none") == ""


def test_adds_a_home_that_passes_the_checker(sample):
    added = add_official_home.run(sample, read=_reader(TULLAMORE + ["y", "quit"]),
                                  today=date(2026, 11, 13))
    assert added == 1
    homes, problems = load_official_sample(sample)
    assert problems == []
    (home,) = homes
    assert home.id == "1"
    assert home.eircode == "R35 HH93"
    assert home.county == "Offaly"
    assert home.listing_source == "daft.ie"
    assert home.ber_number == "113779219"
    assert (home.ber_band, home.ber_kwh_m2_yr) == ("C2", 177.03)
    assert (home.dwelling_type, home.year_built, home.floor_area_m2) == ("semi_detached", 2001, 137.17)
    assert home.register_checked
    assert home.notes == "Register: issued 21-04-2021"
    assert sample.read_bytes().endswith(b"\r\n")


def test_reasks_after_a_bad_answer(sample):
    answers = list(TULLAMORE)
    answers[8:9] = ["Ground-floor apartment", "Semi-detached house"]  # dwelling retyped
    answers[1:2] = ["not an eircode", "R35HH93"]       # Eircode retyped
    add_official_home.run(sample, read=_reader(answers + ["y", "quit"]))
    homes, _ = load_official_sample(sample)
    assert homes[0].eircode == "R35 HH93"


def test_duplicate_eircode_is_refused(sample):
    add_official_home.run(sample, read=_reader(TULLAMORE + ["y", "quit"]))
    second = [TULLAMORE[0], "R35 HH93", "skip", "quit"]
    assert add_official_home.run(sample, read=_reader(second)) == 0
    homes, _ = load_official_sample(sample)
    assert len(homes) == 1


def test_band_that_does_not_match_the_value_is_not_saved(sample):
    answers = list(TULLAMORE)
    answers[7] = "B2 177.03"   # 177.03 is C2
    assert add_official_home.run(sample, read=_reader(answers + ["quit"])) == 0
    homes, _ = load_official_sample(sample)
    assert homes == []


def test_answer_no_saves_nothing(sample):
    assert add_official_home.run(sample, read=_reader(TULLAMORE + ["n", "quit"])) == 0
    assert load_official_sample(sample)[0] == []


def test_ids_continue_from_the_sample(sample):
    add_official_home.run(sample, read=_reader(TULLAMORE + ["y", "quit"]))
    other = ["https://www.daft.ie/x/1", "T12 K7AC", "Cork", "urban", "100000001", "2",
             "gas_boiler", "B3 140", "Detached house", "1998", "160", "", "", "y", "quit"]
    add_official_home.run(sample, read=_reader(other))
    homes, problems = load_official_sample(sample)
    assert problems == []
    assert [h.id for h in homes] == ["1", "2"]
    assert homes[1].storeys == 2 and homes[1].heating.value == "gas_boiler"
