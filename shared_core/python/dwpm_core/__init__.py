"""The only shared business-core package used by desktop and Android hosts."""

from .facade import CoreFacade
from .hashing import compute_core_hash
from .host_ports import platform_ports_from_host_bridge
from .version import CORE_ID, CORE_VERSION


def create_hosted_core(
    operation_store_path: str,
    host_bridge=None,
) -> CoreFacade:
    """Construct a facade for an embedded host without exposing repository paths."""

    ports = (
        platform_ports_from_host_bridge(host_bridge)
        if host_bridge is not None
        else None
    )
    facade = CoreFacade(
        operation_store_path=operation_store_path,
        ports=ports,
    )
    if (
        host_bridge is not None
        and hasattr(host_bridge, "executeNetworkOperation")
        and hasattr(host_bridge, "executionOwnerActive")
    ):
        facade.register_host_network_route(
            "GET",
            "/api/military/intel",
            host_bridge,
        )
    return facade

__all__ = [
    "CORE_ID",
    "CORE_VERSION",
    "CoreFacade",
    "compute_core_hash",
    "create_hosted_core",
    "platform_ports_from_host_bridge",
]
