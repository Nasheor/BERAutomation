"""Tests for the census construction-era prior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ber_automation.geospatial import census
from ber_automation.geospatial.census import choose_epoch, lookup_era_prior, prior_from_counts
from ber_automation.models import (
    ConstructionEpoch as E,
    Coordinates,
    Country,
    PipelineResult,
    StreetViewAnalysis,
)
from ber_automation.pipeline import BERPipeline


def _counts(**kw):
    keys = {"pre80": "before_1980", "e80": "1980_1990", "e90": "1990_2000",
            "e00": "2000_2010", "post10": "after_2010"}
    return {keys[k]: v for k, v in kw.items()}


def _sv(epoch, conf=0.6):
    return StreetViewAnalysis(construction_epoch=epoch, confidence=conf)


# Shares of the validation houses' Small Areas (households, Census 2022)
HYW6 = prior_from_counts(_counts(pre80=29, e80=46, e90=3, e00=2))
RK10 = prior_from_counts(_counts(pre80=7, e80=36, e90=34, e00=2))
K7AC = prior_from_counts(_counts(e90=7, e00=102, post10=2))


def test_prior_shares_and_dominant():
    assert HYW6.dominant_epoch == E.EPOCH_1980_1990
    assert HYW6.households == 80
    assert HYW6.dominant_share == pytest.approx(46 / 80)
    assert sum(HYW6.shares.values()) == pytest.approx(1.0)


def test_too_few_households_gives_no_prior():
    assert prior_from_counts(_counts(e80=10, e90=5)) is None


def test_adjacent_band_defers_to_census():
    # Claude reads the 1980s estate as 1990s: census wins
    assert choose_epoch(HYW6, _sv(E.EPOCH_1990_2000)) == (E.EPOCH_1980_1990, "census")
    assert choose_epoch(RK10, _sv(E.EPOCH_1990_2000, 0.6)) == (E.EPOCH_1980_1990, "census")


def test_adjacent_band_kept_when_common_and_confident():
    assert choose_epoch(RK10, _sv(E.EPOCH_1990_2000, 0.85)) == (E.EPOCH_1990_2000, "streetview")


def test_distant_band_kept_when_present_in_area():
    # 36 % of HYW6's area is pre-1980: a confident distant reading stands
    assert choose_epoch(HYW6, _sv(E.BEFORE_1980)) == (E.EPOCH_1980_1990, "census")  # adjacent
    mixed = prior_from_counts(_counts(pre80=20, e80=10, e90=60, e00=10))
    assert choose_epoch(mixed, _sv(E.BEFORE_1980)) == (E.BEFORE_1980, "streetview")


def test_distant_band_absent_from_area_rejected():
    assert choose_epoch(K7AC, _sv(E.BEFORE_1980)) == (E.EPOCH_2000_2010, "census")


def test_matching_and_missing_readings():
    assert choose_epoch(K7AC, _sv(E.EPOCH_2000_2010)) == (E.EPOCH_2000_2010, "census")
    assert choose_epoch(K7AC, None) == (E.EPOCH_2000_2010, "census")
    # Low-confidence (e.g. privacy-blurred) reading is ignored
    assert choose_epoch(K7AC, _sv(E.EPOCH_1990_2000, 0.2)) == (E.EPOCH_2000_2010, "census")
    assert choose_epoch(None, _sv(E.EPOCH_1990_2000)) == (E.EPOCH_1990_2000, "streetview")
    assert choose_epoch(None, None) == (None, "default")


def _client(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_lookup_reads_small_area(monkeypatch):
    monkeypatch.setattr(census, "_year_built_table",
                        lambda: {"guid-1": _counts(pre80=29, e80=46, e90=3, e00=2, post10=0)})
    client = _client({"features": [{"attributes": {
        "SA_GUID_2022": "guid-1", "SA_PUB2022": "048051004",
        "SA_URBAN_AREA_NAME": "Cork city and suburbs"}}]})
    prior = await lookup_era_prior(Coordinates(lat=51.9, lng=-8.5), client=client)
    assert prior.small_area == "048051004"
    assert prior.urban_area == "Cork city and suburbs"
    assert prior.dominant_epoch == E.EPOCH_1980_1990
    assert client.get.call_args.kwargs["params"]["geometry"] == "-8.5,51.9"


@pytest.mark.asyncio
async def test_lookup_outside_ireland_or_failing_returns_none():
    assert await lookup_era_prior(Coordinates(lat=49.6, lng=6.1), Country.LUXEMBOURG) is None
    assert await lookup_era_prior(Coordinates(lat=0, lng=0), client=_client({"features": []})) is None
    broken = MagicMock()
    broken.get = AsyncMock(side_effect=RuntimeError("offline"))
    assert await lookup_era_prior(Coordinates(lat=51.9, lng=-8.5), client=broken) is None


def test_data_file_covers_all_small_areas():
    table = census._year_built_table()
    assert len(table) > 18_000
    assert table["4c07d11e-2517-851d-e053-ca3ca8c0ca7f"] == _counts(
        pre80=29, e80=46, e90=3, e00=2, post10=0)


def test_build_input_uses_prior_and_respects_override():
    result = PipelineResult(address="x", era_prior=HYW6,
                            street_analysis=_sv(E.EPOCH_1990_2000))
    pipe = BERPipeline.__new__(BERPipeline)
    assert pipe._build_input(result).construction_epoch == E.EPOCH_1980_1990
    assert result.epoch_source == "census"
    bi = pipe._build_input(result, overrides={"construction_epoch": E.AFTER_2010})
    assert bi.construction_epoch == E.AFTER_2010
    assert result.epoch_source == "override"
