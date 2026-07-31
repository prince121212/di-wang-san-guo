"""The only shared business-core package used by desktop and Android hosts."""

from .facade import CoreFacade
from .hashing import compute_core_hash
from .version import CORE_ID, CORE_VERSION

__all__ = [
    "CORE_ID",
    "CORE_VERSION",
    "CoreFacade",
    "compute_core_hash",
]
