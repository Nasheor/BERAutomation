"""Tests for the Eircode geocoder (unit tests with mocked API)."""

from __future__ import annotations

import pytest

from ber_automation.geospatial.geocoder import validate_eircode


class TestEircodeValidation:
    """Test Eircode format validation."""

    @pytest.mark.parametrize(
        "eircode, expected",
        [
            ("D02 X285", "D02 X285"),
            ("D02X285", "D02 X285"),
            ("d02x285", "D02 X285"),
            ("T12 AB34", "T12 AB34"),
            ("A65 F4E2", "A65 F4E2"),
        ],
    )
    def test_valid_eircodes(self, eircode: str, expected: str):
        assert validate_eircode(eircode) == expected

    @pytest.mark.parametrize(
        "bad_eircode",
        [
            "",
            "12345",
            "ABCDEFG",
            "D02",  # too short
            "D02 X28",  # too short
            "D02 X28567",  # too long
        ],
    )
    def test_invalid_eircodes(self, bad_eircode: str):
        with pytest.raises(ValueError):
            validate_eircode(bad_eircode)
