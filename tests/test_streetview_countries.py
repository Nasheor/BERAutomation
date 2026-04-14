"""Diagnostic: test geocoding + Street View metadata availability for all test addresses."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow running as a script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
STREETVIEW_META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"

TEST_CASES = [
    # (address, country_iso, country_label)
    ("V93 H2RH",                                     "IE", "Ireland"),
    ("1 Pembroke Road, Ballsbridge, Dublin 4",        "IE", "Ireland"),
    ("44000 Nantes",                                  "FR", "France"),
    ("5 Rue du Faubourg Saint-Martin, Rennes",        "FR", "France"),
    ("3 Rue de l'Église, Vitré",                      "FR", "France"),
    ("33098 Paderborn",                               "DE", "Germany"),
    ("Marienplatz 1, Paderborn",                      "DE", "Germany"),
    ("Prinzipalmarkt 5, Münster",                     "DE", "Germany"),
    ("1000 Bruxelles",                                "BE", "Belgium"),
    ("Grote Markt 1, Gent",                           "BE", "Belgium"),
    ("7241 Lochem",                                   "NL", "Netherlands"),
    ("Dorpsstraat 5, Lochem",                         "NL", "Netherlands"),
    ("1234 Luxembourg",                               "LU", "Luxembourg"),
    ("9 Rue de Clausen, Luxembourg City",             "LU", "Luxembourg"),
    ("Rue des Romains, Diekirch",                     "LU", "Luxembourg"),
    ("4001 Basel",                                    "CH", "Switzerland"),
    ("Marktplatz 1, Basel",                           "CH", "Switzerland"),
    ("1010 Wien",                                     "AT", "Austria"),
    ("Stephansplatz 1, Wien",                         "AT", "Austria"),
]


async def check_address(client: httpx.AsyncClient, address: str, iso: str, label: str, api_key: str) -> dict:
    result = {
        "address": address,
        "country": label,
        "geocode_ok": False,
        "geocoded_address": "",
        "lat": None,
        "lng": None,
        "sv_status": "NOT_CHECKED",
        "sv_pano_id": None,
        "sv_cam_lat": None,
        "sv_cam_lng": None,
        "error": None,
    }

    # 1. Geocode
    try:
        geo_resp = await client.get(GEOCODING_URL, params={
            "address": address,
            "components": f"country:{iso}",
            "key": api_key,
        })
        geo_resp.raise_for_status()
        geo = geo_resp.json()

        if geo["status"] != "OK" or not geo.get("results"):
            result["error"] = f"Geocoding: {geo.get('status')}"
            return result

        loc = geo["results"][0]["geometry"]["location"]
        result["geocode_ok"] = True
        result["geocoded_address"] = geo["results"][0].get("formatted_address", "")
        result["lat"] = loc["lat"]
        result["lng"] = loc["lng"]
    except Exception as e:
        result["error"] = f"Geocoding exception: {e}"
        return result

    # 2. Street View metadata
    try:
        sv_resp = await client.get(STREETVIEW_META_URL, params={
            "location": f"{result['lat']},{result['lng']}",
            "key": api_key,
            "radius": 50,   # default production radius
        })
        sv_resp.raise_for_status()
        sv = sv_resp.json()

        result["sv_status"] = sv.get("status", "UNKNOWN")
        result["sv_pano_id"] = sv.get("pano_id")
        cam = sv.get("location")
        if cam:
            result["sv_cam_lat"] = cam.get("lat")
            result["sv_cam_lng"] = cam.get("lng")
    except Exception as e:
        result["sv_status"] = "ERROR"
        result["error"] = f"SV metadata exception: {e}"

    return result


async def run_all():
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY not set in environment or .env file")
        sys.exit(1)

    print(f"Testing {len(TEST_CASES)} addresses...\n")
    print(f"{'Country':<14} {'Address':<46} {'Geocode':<8} {'SV Status':<14} {'Pano ID'}")
    print("-" * 110)

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [check_address(client, addr, iso, label, api_key)
                 for addr, iso, label in TEST_CASES]
        results = await asyncio.gather(*tasks)

    # Group by country for summary
    countries_ok: dict[str, list[bool]] = {}
    for r in results:
        c = r["country"]
        countries_ok.setdefault(c, [])

        geo = "OK" if r["geocode_ok"] else f"FAIL({r.get('error', '')})"
        sv = r["sv_status"]
        pano = r["sv_pano_id"][:12] + "…" if r["sv_pano_id"] else "-"
        addr_short = r["address"][:44]

        sv_ok = sv == "OK"
        countries_ok[c].append(sv_ok)

        sv_display = f"[OK]  {sv}" if sv_ok else f"[!!] {sv}"
        print(f"{c:<14} {addr_short:<46} {geo:<8} {sv_display:<18} {pano}")

        if r["geocode_ok"]:
            print(f"{'':14}   Geocoded: {r['geocoded_address']}")
            if r["sv_cam_lat"]:
                # Compute rough distance between geocoded point and SV camera
                import math
                dlat = (r["sv_cam_lat"] - r["lat"]) * 111000
                dlng = (r["sv_cam_lng"] - r["lng"]) * 111000 * math.cos(math.radians(r["lat"]))
                dist = math.sqrt(dlat**2 + dlng**2)
                print(f"{'':14}   SV camera is {dist:.0f}m from geocoded point")
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY BY COUNTRY")
    print("=" * 70)
    for country, sv_results in countries_ok.items():
        ok_count = sum(sv_results)
        total = len(sv_results)
        status = "ALL OK" if ok_count == total else f"PARTIAL ({ok_count}/{total})" if ok_count > 0 else "NONE"
        print(f"  {country:<16} Street View: {status}")

    print()
    all_sv = [r["sv_status"] for r in results]
    ok = all_sv.count("OK")
    zero = all_sv.count("ZERO_RESULTS")
    err = len(all_sv) - ok - zero
    print(f"Overall: {ok}/{len(results)} addresses have Street View (ZERO_RESULTS: {zero}, errors: {err})")


if __name__ == "__main__":
    asyncio.run(run_all())
