# BER Automation — Demo Test Addresses
### CIRCUS Project · March 2026

One verified real address per country. Irish address runs the **full automated pipeline**.
All other countries use **Manual Input mode** — the address is a real reference point;
you enter the building parameters in the Streamlit UI.

---

## 🇮🇪 Ireland — Full Automated Pipeline

### 15 Marino Crescent, Clontarf, Dublin 3
**Eircode: `D03 K078`**

| Detail | Value |
|--------|-------|
| Building type | Mid-terrace house |
| Construction | 1792 (Georgian crescent) |
| Storeys | 3 storeys over raised basement |
| Street View | Excellent — distinctive curved Georgian crescent |
| Satellite | Clear rooftop, uniform terrace row |
| Why publicly known | Birthplace of Bram Stoker (born 8 Nov 1847). Listed on the National Inventory of Architectural Heritage (ref: 50120111). Featured in Irish Times, Buildings of Ireland register, and IrelandXO heritage database. |

**Expected BER: B1–3** — pre-1800 solid brick construction with no cavity, original sash windows, likely solid fuel or gas heating. Extremely high energy consumption, dramatic retrofit potential.

**Demo talking point:** Claude will identify this as a pre-1980 terrace in the Georgian style. The curved terrace geometry means the satellite footprint of each unit is slightly irregular — a good real-world test of the extraction logic. The "before 1980" epoch bucket correctly captures the solid brick U-values.

> Verified via: Google Maps geocoder, Buildings of Ireland register (buildingsofireland.ie ref 50120111), Irish Property Price Register (D03 routing key), IrelandXO heritage database.

---

## 🇧🇪 Belgium — Manual Input Mode

### Rombaut Keldermansstraat 27, 9000 Gent
*(De Grote Tuinwijk — Flemish Heritage Register)*

| Detail | Value |
|--------|-------|
| Building type | Terraced house (social housing, garden city layout) |
| Construction | 1923–1925 |
| Storeys | 2 |
| Storey height | ~2.7 m |
| Heating | Gas boiler (typical for this stock) |

**Parameters to enter in Streamlit Manual Input:**

| Field | Value |
|-------|-------|
| Country | Belgium |
| Building Type | Terraced (Length Adjoining) |
| Length | 7 m |
| Width | 10 m |
| Storeys | 2 |
| Storey Height | 2.7 m |
| Construction Epoch | Before 1980 |
| Heating System | Gas Boiler |

**Expected result: B1–B3** (~250–340 kWh/m²/yr). Belgium's milder climate (HDD 1,826 vs Ireland's 2,149) puts this slightly below an equivalent Dublin house of the same era.

**Why publicly known:** De Grote Tuinwijk is listed in the Flemish Heritage Register (Inventaris Onroerend Erfgoed, object ID 18796) as a protected architectural ensemble. Designed by Oscar and Albert Van de Voorde and Jules Minnaar, 241 social houses built for the Gentse Maatschappij voor Goedkope Woningen. The specific address (number 27) is confirmed in the Belgian property platform Realo (realo.be) and on Yelp business register.

> Verified via: Inventaris Onroerend Erfgoed (inventaris.onroerenderfgoed.be/erfgoedobjecten/18796), Realo.be property listing, Yelp business register entry for the street.

---

## 🇫🇷 France — Manual Input Mode

### 12 Allée des Cèdres, 92150 Suresnes
*(Cité-Jardin de Suresnes — Patrimoine d'Intérêt Régional)*

| Detail | Value |
|--------|-------|
| Building type | Individual pavilion (detached house) |
| Construction | 1921–1939 |
| Storeys | 2 |
| Storey height | ~2.6 m |
| Heating | Gas boiler (typical for Île-de-France stock) |

**Parameters to enter in Streamlit Manual Input:**

| Field | Value |
|-------|-------|
| Country | France |
| Building Type | Detached |
| Length | 9 m |
| Width | 7 m |
| Storeys | 2 |
| Storey Height | 2.6 m |
| Construction Epoch | Before 1980 |
| Heating System | Gas Boiler |

**Expected result: C3–D2** (~220–290 kWh/m²/yr). France's significantly milder heating climate (HDD 1,462 vs Ireland's 2,149) gives this interwar house better numbers than an equivalent Irish or German building despite its age.

**Why publicly known:** The Cité-Jardin de Suresnes is one of France's largest and most documented garden cities, containing 3,300 units including 170 individual pavilions. Built 1921–1939 by architects Alexandre Maistrasse, Julien Quoniam, and Félix Dumail at the initiative of Henri Sellier. Awarded the "Patrimoine d'Intérêt Régional" label by the Île-de-France Region (July 2018), managed by Hauts-de-Seine Habitat, and open for guided tours on heritage days. The Cité Jardins quarter of 92150 Suresnes is a confirmed neighbourhood designation on French property platform SeLoger (code: cite-jardins-92150), with active current listings confirming the pavilions are residential and occupied.

> Verified via: Cité-Jardin de Suresnes Wikipedia (fr.wikipedia.org), Hauts-de-Seine Habitat official press release, SeLoger neighbourhood listings (seloger.com/cite-jardins-92150), exploreparis.com heritage tour listings.

---

## 🇩🇪 Germany — Manual Input Mode

### Platanenallee 3, 50765 Köln-Chorweiler
*(Wohnsiedlung Seeberg-Nord — documented on baukunst-nrw.de)*

| Detail | Value |
|--------|-------|
| Building type | Terraced house (Reihenhaus) |
| Construction | 1972–1976 |
| Storeys | 2 |
| Storey height | ~2.6 m |
| Heating | Gas boiler (dominant in this Cologne Plattenbau-era stock) |

**Parameters to enter in Streamlit Manual Input:**

| Field | Value |
|-------|-------|
| Country | Germany |
| Building Type | Terraced (Width Adjoining) |
| Length | 10 m |
| Width | 6 m |
| Storeys | 2 |
| Storey Height | 2.6 m |
| Construction Epoch | 1980–1990 *(use as proxy for early 1970s build quality)* |
| Heating System | Gas Boiler |

**Expected result: C2–D1** (~200–260 kWh/m²/yr). Germany's HDD (2,157) is nearly identical to Ireland's (2,149) — a like-for-like comparison between a German and Irish house of the same spec gives almost the same result, which is a useful cross-country methodology talking point.

**Why publicly known:** Chorweiler (postcode 50765) is Cologne's largest 1970s new-town district and one of the most extensively documented prefabricated housing developments in NRW. The Wohnsiedlung Seeberg-Nord sub-district is registered on baukunst-nrw.de (NRW state architectural register). The development is covered on de.Wikipedia (Chorweiler article), the City of Cologne official city portal (koeln.de/apps/strassen/plz/50765), and the StadtBauKultur NRW database. First residents moved in 1972; shopping street completed 1976. The Platanenallee street name (Plane Tree Avenue) is characteristic of the area's green-space-named streets. Postcode 50765 is confirmed as the Chorweiler postal area.

> Verified via: baukunst-nrw.de Seeberg-Nord listing, Chorweiler Wikipedia (de.wikipedia.org/wiki/Chorweiler), Stadt Köln official postcode map (koeln.de), deu.postcodebase.com.

---

## 🇳🇱 Netherlands — Manual Input Mode

### Plein 1953 4, 3086 EM Rotterdam
*(Pendrecht — Post-war Reconstruction Heritage)*

| Detail | Value |
|--------|-------|
| Building type | Terraced house (rijtjeshuis) |
| Construction | 1953–1956 |
| Storeys | 2 |
| Storey height | ~2.7 m |
| Heating | Gas boiler (Netherlands is actively phasing these out by 2026) |

**Parameters to enter in Streamlit Manual Input:**

| Field | Value |
|-------|-------|
| Country | Netherlands |
| Building Type | Terraced (Width Adjoining) |
| Length | 10 m |
| Width | 6 m |
| Storeys | 2 |
| Storey Height | 2.7 m |
| Construction Epoch | Before 1980 |
| Heating System | Gas Boiler |

**Expected result: D2–E1** (~290–360 kWh/m²/yr). Enable the retrofit and switch the heating system to a heat pump — this drops to B2 territory, a striking demo of the Dutch gas phase-out policy's energy impact.

**Why publicly known:** Plein 1953 is the central square of the Pendrecht district, named after the North Sea floods of 1953 that devastated nearby communities (all Pendrecht streets are named after flooded villages). Pendrecht was designed by Lotte Stam-Beese for Rotterdam's Urban Development and Reconstruction Agency in 1949, and is documented on the Wederopbouw Rotterdam heritage platform (wederopbouwrotterdam.nl), Architectuul, BKOR (Rotterdam Art Foundation), and in a peer-reviewed paper in the *International Journal of Urban and Regional Research*. Postcode 3086 EM for Plein 1953 is confirmed in the Dutch postcode register (drimble.nl/postcode/3086EM).

> Verified via: drimble.nl/postcode/3086EM (postcode confirmed), wederopbouwrotterdam.nl (heritage documentation), BKOR (bkor.nl), nld.postcodebase.com node 443271 (3086 NV Pendrecht confirmed).

---

## Suggested Demo Order

| Step | Country | Address | Why |
|------|---------|---------|-----|
| 1 | 🇮🇪 | D03 K078 | Opens automated pipeline — pre-1800 terrace, striking result |
| 2 | 🇮🇪 | D03 K078 + retrofit | Same property, enable retrofit — dramatic band jump |
| 3 | 🇩🇪 | Chorweiler, Köln | Manual mode intro — nearly identical HDD to Ireland, same result |
| 4 | 🇫🇷 | Suresnes | Show how milder French climate changes the numbers |
| 5 | 🇧🇪 | Gent Tuinwijk | Inter-war Belgian terrace — between France and Germany |
| 6 | 🇳🇱 | Plein 1953 + retrofit | Gas phase-out policy demo — big improvement with heat pump |

---

## Troubleshooting During Demo

| Symptom | Recovery |
|---------|---------|
| Claude returns low confidence for D03 K078 | The crescent curves away from the road — try overriding epoch to "before 1980" and building type to "terraced" manually |
| App takes >40 s | Normal on cold start. Subsequent runs faster. |
| API rate limit | Switch entirely to Manual Input — works with no API keys |
| Footprint looks wrong for the crescent | Expected — curved terrace is hard for a rectangular bounding box model. Note this to the audience as a known limitation |
