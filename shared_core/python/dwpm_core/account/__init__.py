"""Account login protocol and deterministic area-selection rules."""

from .lifecycle import (
    AccountLifecyclePolicy,
    classify_reconnect_failure,
    is_network_failure_message,
    is_session_invalid_message,
    reconnect_delay_millis,
    reconnect_kind_label,
    requires_relogin,
)
from .protocol import (
    area_catalog_signature,
    find_login_area,
    parse_8003_login,
    parse_passport_area_list,
)
from .store import DurableAccountStore, assert_public_account_record

__all__ = [
    "AccountLifecyclePolicy",
    "area_catalog_signature",
    "classify_reconnect_failure",
    "DurableAccountStore",
    "find_login_area",
    "is_network_failure_message",
    "is_session_invalid_message",
    "parse_8003_login",
    "parse_passport_area_list",
    "reconnect_delay_millis",
    "reconnect_kind_label",
    "requires_relogin",
    "assert_public_account_record",
]
