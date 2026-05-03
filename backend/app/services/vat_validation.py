"""USt-ID validation via the official EU VIES REST API.

Uses the free European Commission endpoint — no API key required.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_VIES_BASE = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms"

_VAT_ID_PATTERN = re.compile(r"^([A-Z]{2})\s*(\d{5,12})$")


def parse_vat_id(vat_id: str) -> tuple[str, str] | None:
    """Extract country code and number from a VAT ID like 'DE123456789'."""
    cleaned = vat_id.strip().upper().replace(" ", "")
    match = _VAT_ID_PATTERN.match(cleaned)
    if not match:
        return None
    return match.group(1), match.group(2)


async def validate_vat_id(vat_id: str) -> dict:
    """Validate a European VAT ID against the VIES database.

    Returns a dict with 'valid' (bool), 'name', 'address', and raw 'details'.
    """
    parsed = parse_vat_id(vat_id)
    if not parsed:
        return {
            "valid": False,
            "vat_id": vat_id,
            "error": f"Ungültiges Format: '{vat_id}'. Erwartet z.B. 'DE123456789'.",
        }

    country_code, vat_number = parsed

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_VIES_BASE}/{country_code}/vat/{vat_number}")
            response.raise_for_status()
            data = response.json()
    except httpx.RequestError as exc:
        logger.error("VIES request failed: %s", exc)
        return {
            "valid": False,
            "vat_id": vat_id,
            "error": f"VIES-Abfrage fehlgeschlagen: {exc}",
        }
    except httpx.HTTPStatusError as exc:
        logger.error("VIES returned %s", exc.response.status_code)
        return {
            "valid": False,
            "vat_id": vat_id,
            "error": f"VIES-Fehler (HTTP {exc.response.status_code})",
        }

    is_valid = data.get("isValid", False)

    return {
        "valid": is_valid,
        "vat_id": f"{country_code}{vat_number}",
        "country_code": country_code,
        "name": data.get("name", "").strip() or None,
        "address": data.get("address", "").strip() or None,
        "request_date": data.get("requestDate"),
        "message": (
            f"USt-ID {country_code}{vat_number} ist gültig."
            if is_valid
            else f"USt-ID {country_code}{vat_number} ist UNGÜLTIG oder nicht registriert."
        ),
    }
