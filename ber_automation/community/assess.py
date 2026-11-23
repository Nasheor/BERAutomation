"""Assess a community from a list of addresses.

Every home gets a census estimate (instant: geocode + Small Area lookup + stock model).
Image analysis (the full pipeline, about a minute and some API credit per home) runs on all
homes, a sample spread over the Small Areas, or chosen ids. Everything is saved to
``<base_dir>/<name>/community.json`` after each home, and a rerun reuses what is there, so an
interrupted run resumes without paying twice.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional, Union

from ber_automation.community.models import CommunityHome, CommunityResult
from ber_automation.community.stock import census_home_estimate, small_area_stock
from ber_automation.geospatial.census import lookup_census_area
from ber_automation.geospatial.geocoder import geocode_address
from ber_automation.models import Country

log = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path("output") / "communities"
IMAGE_CONCURRENCY = 3
LOOKUP_CONCURRENCY = 5

Analyse = Union[str, int, Iterable[str], None]  # "none" | "all" | N | ids
Progress = Callable[[int, int, str], None]


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_") or "community"


def community_dir(name: str, base_dir: Path = DEFAULT_BASE_DIR) -> Path:
    return Path(base_dir) / slug(name)


def pick_sample(homes: list[CommunityHome], n: int) -> list[str]:
    """Ids of *n* homes spread over the Small Areas (round robin, in list order)."""
    by_area: dict[str, list[str]] = {}
    for h in homes:
        if h.coordinates is not None:
            by_area.setdefault(h.small_area, []).append(h.id)
    picked: list[str] = []
    queues = list(by_area.values())
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop(0))
    return picked


def _image_ids(homes: list[CommunityHome], analyse: Analyse) -> list[str]:
    if analyse in (None, "none", 0):
        return []
    if analyse == "all":
        return [h.id for h in homes if h.coordinates is not None]
    if isinstance(analyse, int):
        return pick_sample(homes, analyse)
    wanted = {str(i) for i in analyse}
    return [h.id for h in homes if h.id in wanted]


async def assess_community(
    entries: list[dict],
    name: str,
    country: Country = Country.IRELAND,
    analyse: Analyse = "none",
    provider: Optional[str] = None,
    base_dir: Path = DEFAULT_BASE_DIR,
    progress: Optional[Progress] = None,
    geocode: Callable[..., Awaitable] = geocode_address,
    census_lookup: Callable[..., Awaitable] = lookup_census_area,
    pipeline_factory: Optional[Callable[..., object]] = None,
) -> CommunityResult:
    """Census estimate for every entry ({"id", "address"}), image analysis as *analyse* says."""
    folder = community_dir(name, base_dir)
    path = folder / "community.json"
    result = CommunityResult.load(path) if path.exists() else CommunityResult(name=name, country=country)
    result.country = country
    known = {(h.id, h.address): h for h in result.homes}
    result.homes = [
        known.get((str(e["id"]), e["address"])) or CommunityHome(id=str(e["id"]), address=e["address"])
        for e in entries
    ]
    note = progress or (lambda done, total, msg: None)
    lock = asyncio.Lock()

    async def save():
        async with lock:
            result.save(path)

    # --- 1. Locate every home and give it a census estimate ---
    todo = [h for h in result.homes if h.coordinates is None or (not h.census_estimate and not h.errors)]
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    done = 0

    async def locate(home: CommunityHome):
        nonlocal done
        async with sem:
            home.errors = []
            try:
                home.coordinates = await geocode(home.address, country)
            except Exception as e:
                home.errors.append(f"Address not found: {e}")
            if home.coordinates is not None:
                area = await census_lookup(home.coordinates, country)
                if area is None:
                    if country == Country.IRELAND:
                        home.errors.append("No census Small Area found for this location.")
                else:
                    home.small_area = area.small_area
                    result.census[area.small_area] = area
                    home.census_estimate = census_home_estimate(area, country)
            done += 1
            note(done, len(todo), f"Located {home.address}")

    await asyncio.gather(*(locate(h) for h in todo))
    for code, area in result.census.items():
        if code not in result.areas:
            result.areas[code] = small_area_stock(area, country)
    await save()

    # --- 2. Image analysis for the chosen homes (skipping those already analysed) ---
    ids = set(_image_ids(result.homes, analyse))
    to_run = [h for h in result.homes if h.id in ids and h.image_estimate is None]
    if to_run:
        if pipeline_factory is None:
            from ber_automation.pipeline import BERPipeline
            pipeline_factory = BERPipeline
        img_sem = asyncio.Semaphore(IMAGE_CONCURRENCY)
        finished = 0

        async def analyse_home(home: CommunityHome):
            nonlocal finished
            async with img_sem:
                note(finished, len(to_run), f"Analysing images of {home.address}")
                try:
                    pipeline = pipeline_factory(output_dir=folder / slug(home.id), provider=provider)
                    run = await pipeline.run(home.address, country)
                    if run.ber_result is not None:
                        home.image_estimate = run.ber_result
                        home.image_runs = 1
                    home.errors.extend(f"Images: {e}" for e in run.errors)
                except Exception as e:  # one home failing must not stop the community
                    log.exception("Image analysis failed for %s", home.address)
                    home.errors.append(f"Images: {e}")
                finished += 1
                note(finished, len(to_run), f"Analysed {home.address}")
                await save()

        await asyncio.gather(*(analyse_home(h) for h in to_run))
    return result
