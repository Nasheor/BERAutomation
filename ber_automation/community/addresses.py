"""Read a community's address list from CSV text or a pasted list."""

from __future__ import annotations

import csv
import io

ADDRESS_COLUMNS = ("address", "eircode", "postcode", "postal_code")


def read_addresses(text: str) -> list[dict]:
    """Rows {"id", "address"} from CSV text with a header, or one address per line.

    The address comes from the first of the columns address / eircode / postcode / postal_code
    present (else the first column); ``id`` is used when present, else the row number.
    Blank lines and duplicate addresses are skipped.
    """
    text = text.lstrip("﻿").strip()
    if not text:
        return []
    first = text.splitlines()[0].lower()
    has_header = any(col in [c.strip() for c in first.split(",")] for col in ADDRESS_COLUMNS + ("id",))
    rows: list[dict] = []
    seen: set[str] = set()
    if has_header and "," not in first:
        # One-column list under a header: each line is a whole address, commas and all
        text = "\n".join(text.splitlines()[1:])
        has_header = False
    if has_header:
        reader = csv.DictReader(io.StringIO(text))
        fields = [f.strip().lower() for f in reader.fieldnames or []]
        key = next((c for c in ADDRESS_COLUMNS if c in fields), fields[0] if fields else None)
        for n, raw in enumerate(reader, 1):
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            address = row.get(key, "")
            if address and address.upper() not in seen:
                seen.add(address.upper())
                rows.append({"id": row.get("id") or str(n), "address": address})
    else:
        for line in text.splitlines():
            address = line.strip().strip(",")
            if address and address.upper() not in seen:
                seen.add(address.upper())
                rows.append({"id": str(len(rows) + 1), "address": address})
    return rows
