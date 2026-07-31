"""The only shared business-core package used by desktop and Android hosts."""

from .facade import CoreFacade
from .hashing import compute_core_hash
from .version import CORE_ID, CORE_VERSION


def create_hosted_core(operation_store_path: str) -> CoreFacade:
    """Construct a facade for an embedded host without exposing repository paths."""

    return CoreFacade(operation_store_path=operation_store_path)

__all__ = [
    "CORE_ID",
    "CORE_VERSION",
    "CoreFacade",
    "compute_core_hash",
    "create_hosted_core",
]
