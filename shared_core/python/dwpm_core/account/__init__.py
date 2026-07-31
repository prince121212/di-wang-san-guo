"""Account login protocol and deterministic area-selection rules."""

from .protocol import (
    area_catalog_signature,
    find_login_area,
    parse_8003_login,
    parse_passport_area_list,
)

__all__ = [
    "area_catalog_signature",
    "find_login_area",
    "parse_8003_login",
    "parse_passport_area_list",
]
