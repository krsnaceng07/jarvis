"""Projects an MMDB city record into coarse shape callers display.

OpenClaw parity: mirrors extensions/geolocation/src/lookup.ts.
"""

from __future__ import annotations

from typing import Any, TypedDict


class GeolocationResult(TypedDict, total=False):
    city: str
    region: str
    country: str
    countryCode: str


def english_name(names: dict[str, Any] | None) -> str | None:
    if not isinstance(names, dict):
        return None
    en = names.get("en")
    if isinstance(en, str) and en.strip():
        return en.strip()
    return None


def project_geolocation_record(record: dict[str, Any] | None) -> GeolocationResult | None:
    """Returns None when the database has no usable placement for the address,
    so callers can distinguish 'not found' from an empty-but-present answer.
    """
    if not record or not isinstance(record, dict):
        return None

    city_name = english_name(
        record.get("city", {}).get("names") if isinstance(record.get("city"), dict) else None
    )

    subdivs = record.get("subdivisions")
    first_subdiv = (
        subdivs[0]
        if isinstance(subdivs, list) and len(subdivs) > 0 and isinstance(subdivs[0], dict)
        else None
    )
    region_name = english_name(first_subdiv.get("names") if first_subdiv else None)

    country_dict = record.get("country") if isinstance(record.get("country"), dict) else None
    country_name = english_name(country_dict.get("names") if country_dict else None)
    country_code = (
        country_dict.get("iso_code")
        if country_dict and isinstance(country_dict.get("iso_code"), str)
        else None
    )

    result: GeolocationResult = {}
    if city_name:
        result["city"] = city_name
    if region_name:
        result["region"] = region_name
    if country_name:
        result["country"] = country_name
    if country_code:
        result["countryCode"] = country_code

    return result if result else None
