# BER Automation — Sample Test Addresses by Country

Use these addresses with the pipeline command or the Full Pipeline tab in the Streamlit app.

```
python main.py pipeline "<address>" --country <country>
```

---

## Luxembourg

| Address | Type | Notes |
|---------|------|-------|
| `9 Rue de Clausen, Luxembourg City` | Terraced urban house | City centre, mixed residential |
| `15 Rue de Beggen, Luxembourg` | Semi-detached suburban | Northern suburb |
| `3 Rue de l'Église, Echternach` | Detached rural | Historic town, Moselle region |
| `7 Rue de Mondorf, Remich` | Detached | Moselle wine village |
| `12 Rue de la Forêt, Wiltz` | Detached | Rural north, Ardennes |
| `Rue des Romains, Diekirch` | Terraced | Small town, northern Luxembourg |
| `5 Rue de la Gare, Ettelbruck` | Semi-detached | Rail town, central Luxembourg |

**Postal code shortcuts (country filter required):**
```
python main.py pipeline "1234 Luxembourg" --country luxembourg
python main.py pipeline "6700 Echternach" --country luxembourg
python main.py pipeline "5600 Mondorf-les-Bains" --country luxembourg
```

---

## Ireland

| Address | Type | Notes | Tested |
|---------|------|-------|--------|
| `D02 X285` | Eircode — Dublin city | Government buildings area | — |
| `V92 K254` | Eircode — Kerry (Ballyferriter) | Rural, oil-heated housing common | OK |
| `V93 CX58` | Eircode — Kerry (Ranalough) | Rural Kerry | OK |
| `T12 YE28` | Eircode — Cork city | Urban semi-detached | — |
| `H91 Y3X4` | Eircode — Galway city | Urban residential | — |
| `1 Pembroke Road, Ballsbridge, Dublin 4` | Detached/large semi-D | Victorian era housing | OK |
| `5 The Green, Castlebar, Co. Mayo` | Semi-detached | Rural town estate | — |
| `3 Mallow Street, Limerick` | Terraced | Georgian/Victorian terraced | — |

> **Note:** `V93 H2RH` is NOT in Google's geocoding database — it resolves to the
> centre of Ireland with no Street View. Use `V92 K254` or `V93 CX58` instead for Kerry.
> Always verify an Eircode geocodes to a specific address (not just "Ireland") before testing.

```
python main.py pipeline "D02 X285" --country ireland
python main.py pipeline "V92 K254" --country ireland
```

---

## France (North-West — CIRCUS region)

| Address | Type | Notes |
|---------|------|-------|
| `5 Rue du Faubourg Saint-Martin, Rennes` | Terraced town house | Capital of Brittany, NW France |
| `12 Rue de la Paix, Nantes` | Terraced/semi-D | Major city, Loire-Atlantique |
| `3 Rue de l'Église, Vitré` | Stone farmhouse | Rural Brittany, pre-1980 stock |
| `8 Allée des Chênes, Laval` | Detached | Suburban Mayenne |
| `20 Rue de la Forêt, Le Mans` | Semi-detached | Climate reference station city |
| `2 Place du Marché, Vannes` | Terraced | Morbihan coastal town |
| `44000 Nantes` | Postal code | Works with country=france |

```
python main.py pipeline "5 Rue du Faubourg Saint-Martin, Rennes" --country france
python main.py pipeline "44000 Nantes" --country france
```

---

## Germany (North-West — CIRCUS region)

| Address | Type | Notes |
|---------|------|-------|
| `Marienplatz 1, Paderborn` | Town centre | Climate reference city for NW Germany |
| `Prinzipalmarkt 5, Münster` | Historic terraced | Westphalia, NW Germany |
| `Hauptstraße 10, Aachen` | Semi-detached | Border city (BE/NL/DE) |
| `Freiherr-vom-Stein-Straße 3, Bielefeld` | Detached suburban | East Westphalia |
| `Schloßstraße 2, Bonn` | Terraced | Rhine valley, pre-1980 stock |
| `Bahnhofstraße 5, Osnabrück` | Semi-detached | Lower Saxony, NW Germany |
| `33098 Paderborn` | Postal code | Works with country=germany |

```
python main.py pipeline "Marienplatz 1, Paderborn" --country germany
python main.py pipeline "33098 Paderborn" --country germany
```

---

## Belgium

| Address | Type | Notes |
|---------|------|-------|
| `Grote Markt 1, Gent` | Terraced urban | Flanders — very common brick terraced |
| `Meir 1, Antwerpen` | Terraced | Antwerp city centre |
| `Rue de la Loi 1, Bruxelles` | Urban | Brussels — bilingual, uses Flanders EPC |
| `Vrijthof 3, Hasselt` | Semi-detached | Flemish Brabant |
| `Grand-Place 5, Liège` | Terraced | Wallonia (note: EPC system differs) |
| `Dorp 4, Mechelen` | Terraced | Suburb between Brussels and Antwerp |
| `1000 Bruxelles` | Postal code | Works with country=belgium |

```
python main.py pipeline "Grote Markt 1, Gent" --country belgium
python main.py pipeline "1000 Bruxelles" --country belgium
```

---

## Netherlands

| Address | Type | Notes |
|---------|------|-------|
| `Herengracht 1, Amsterdam` | Canal terraced house | Classic Dutch row house |
| `Vredenburg 1, Utrecht` | Semi-detached | Central NL, reference station city |
| `Grote Markt 1, Haarlem` | Terraced | Old town North Holland |
| `Binnenhof 1, Den Haag` | Institutional/large | The Hague |
| `Coolsingel 1, Rotterdam` | Modern urban | Rotterdam |
| `Dorpsstraat 5, Lochem` | Detached rural | LochemEnergie CIRCUS partner area |
| `7241 BL Lochem` | Full postal code | LochemEnergie project area | OK |
| `7241 GA Lochem` | Full postal code | Lochem area | OK |

> **Note:** Dutch postal codes require the 2-letter sector suffix (e.g. `7241 BL`).
> `7241 Lochem` without the letters geocodes to a rural centroid without Street View coverage.

```
python main.py pipeline "Dorpsstraat 5, Lochem" --country netherlands
python main.py pipeline "7241 BL Lochem" --country netherlands
```

---

## Switzerland (Basel region — most relevant for NWE)

| Address | Type | Notes |
|---------|------|-------|
| `Aeschenplatz 1, Basel` | Urban | NW Switzerland, NWE programme boundary |
| `Marktplatz 1, Basel` | Terraced city centre | Historic Basel |
| `Hauptstraße 5, Liestal` | Semi-detached | Baselland canton suburb |
| `Dorfstrasse 3, Binningen` | Detached | Climate reference station suburb |
| `Rheinsprung 4, Basel` | Old town terraced | Pre-1900 stock |
| `4001 Basel` | Postal code | Works with country=switzerland |

```
python main.py pipeline "Marktplatz 1, Basel" --country switzerland
python main.py pipeline "4001 Basel" --country switzerland
```

---

## Austria (supplementary — not a CIRCUS partner)

| Address | Type | Notes |
|---------|------|-------|
| `Stephansplatz 1, Wien` | Historic urban | Vienna city centre |
| `Mariahilfer Straße 1, Wien` | Mixed terraced | Vienna residential |
| `Mozartplatz 1, Salzburg` | Terraced | Historic Salzburg |
| `Hauptplatz 1, Graz` | Urban | Styria |
| `1010 Wien` | Postal code | Works with country=austria |

```
python main.py pipeline "Stephansplatz 1, Wien" --country austria
python main.py pipeline "1010 Wien" --country austria
```

---

## Notes on Address Input

- **Eircodes** (Ireland only): always work best without street name — e.g. `D02 X285`, `V93 H2RH`
- **Postal codes**: work for all continental countries when combined with `--country` flag
- **Rural addresses**: Street View coverage may be limited; the pipeline will warn and fall back to satellite-only footprint analysis
- **Multi-unit blocks / apartments**: the tool is designed for single-family residential; results for apartments will be less accurate
- **Language**: Google Geocoding accepts addresses in the local language (French for Luxembourg/France, German for Germany/Switzerland)

---

## Quick Batch Test (Streamlit)

For a quick demo covering all 8 countries, run the Streamlit app and try these in order:

| Input | Country |
|-------|---------|
| `V92 K254` | ireland |
| `44000 Nantes` | france |
| `33098 Paderborn` | germany |
| `1000 Bruxelles` | belgium |
| `7241 BL Lochem` | netherlands |
| `1234 Luxembourg` | luxembourg |
| `4001 Basel` | switzerland |
| `1010 Wien` | austria |
