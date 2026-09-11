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
    operation_run_gate = (
        (lambda: bool(host_bridge.executionOwnerActive()))
        if host_bridge is not None
        and hasattr(host_bridge, "executionOwnerActive")
        else None
    )
    facade = CoreFacade(
        operation_store_path=operation_store_path,
        ports=ports,
        operation_run_gate=operation_run_gate,
    )
    shared_login_registered = bool(
        host_bridge is not None
        and hasattr(host_bridge, "executeRawHttp")
        and hasattr(host_bridge, "commitAccountRuntime")
        and hasattr(host_bridge, "startAccountHosting")
        and hasattr(host_bridge, "loadPassword")
        and hasattr(host_bridge, "saveSessionSecrets")
    )
    if shared_login_registered:
        facade.register_account_login_routes()

    shared_raw_game_transport_registered = bool(
        host_bridge is not None
        and hasattr(host_bridge, "executeRawHttp")
        and hasattr(host_bridge, "loadSessionSecrets")
    )
    has_execution_owner = bool(
        host_bridge is not None
        and hasattr(host_bridge, "executionOwnerActive")
    )
    has_account_lane = bool(
        host_bridge is not None
        and hasattr(host_bridge, "tryAcquireNetworkOperation")
        and hasattr(host_bridge, "releaseNetworkOperation")
    )
    has_legacy_network_adapter = bool(
        host_bridge is not None
        and hasattr(host_bridge, "executeNetworkOperation")
        and has_execution_owner
    )

    # Compatibility only for an older embedding host which has not adopted the
    # byte-only HTTP port. Android no longer enters this branch.
    if has_legacy_network_adapter and not shared_raw_game_transport_registered:
        if not shared_login_registered and has_account_lane:
            for path, builder in (
                ("/api/accounts/add", facade.account_add_operation_payload),
                ("/api/accounts/start", facade.account_start_operation_payload),
            ):
                facade.register_host_network_route(
                    "POST",
                    path,
                    host_bridge,
                    persisted_payload_builder=builder,
                    host_response_projector=facade.account_lifecycle_operation_result,
                    coalesce_active=True,
                    require_live_account=False,
                    require_execution_owner=False,
                )
        facade.register_host_network_route(
            "GET", "/api/military/intel", host_bridge
        )
        facade.register_host_network_route(
            "GET",
            "/api/state/refresh",
            host_bridge,
            persisted_payload_builder=facade.state_refresh_operation_payload,
        )
        facade.register_host_network_route(
            "GET",
            "/api/heartbeat",
            host_bridge,
            persisted_payload_builder=facade.heartbeat_operation_payload,
            host_response_projector=facade.heartbeat_operation_result,
        )
        facade.register_host_network_route(
            "POST",
            "/api/raid/fiefs",
            host_bridge,
            persisted_payload_builder=facade.raid_fiefs_operation_payload,
            host_response_projector=facade.raid_fiefs_operation_result,
        )
        facade.register_host_network_route(
            "POST",
            "/api/daily/general-visit/candidates",
            host_bridge,
            persisted_payload_builder=(
                facade.general_visit_candidates_operation_payload
            ),
            host_response_projector=(
                facade.general_visit_candidates_operation_result
            ),
        )
        if has_account_lane:
            facade.register_host_network_route(
                "POST",
                "/api/formations/unassign-all",
                host_bridge,
                persisted_payload_builder=facade.unassign_all_operation_payload,
                host_response_projector=facade.unassign_all_operation_result,
                coalesce_active=True,
            )
            facade.register_host_network_route(
                "POST",
                "/api/formations/apply",
                host_bridge,
                persisted_payload_builder=facade.formation_apply_operation_payload,
                coalesce_active=True,
            )

    # Raw game routes are intentionally independent from executeNetworkOperation.
    # Python builds/parses every packet; the host owns only execution state,
    # account-lane exclusion, Session secret storage and byte HTTP.
    if (
        shared_raw_game_transport_registered
        and has_execution_owner
        and has_account_lane
    ):
        facade.register_automation_recovery_runner(host_bridge)
        facade.register_raid_action_runner(host_bridge)
        facade.register_lossless_action_runner(host_bridge)
        facade.register_dungeon_action_runner(host_bridge)
        raw_routes = (
            (
                "GET",
                "/api/state/refresh",
                facade._run_state_refresh_game_workflow,
                facade.state_refresh_operation_payload,
            ),
            (
                "GET",
                "/api/heartbeat",
                facade._run_heartbeat_game_workflow,
                facade.heartbeat_operation_payload,
            ),
            (
                "GET",
                "/api/military/intel",
                facade._run_military_intel_game_workflow,
                facade.military_intel_operation_payload,
            ),
            (
                "POST", "/api/raid/fiefs",
                facade._run_raid_fiefs_game_workflow,
                facade.raid_fiefs_operation_payload,
            ),
            (
                "POST", "/api/formations/unassign-all",
                facade._run_unassign_all_game_workflow,
                facade.unassign_all_operation_payload,
            ),
            (
                "POST", "/api/formations/apply",
                facade._run_formation_apply_game_workflow,
                facade.formation_apply_operation_payload,
            ),
            (
                "POST", "/api/domestic/query",
                facade._run_domestic_query_game_workflow,
                facade.domestic_query_operation_payload,
            ),
            (
                "POST", "/api/domestic/action",
                facade._run_domestic_action_game_workflow,
                facade.domestic_action_operation_payload,
            ),
            (
                "POST", "/api/daily/general-visit/candidates",
                facade._run_daily_general_visit_candidates_game_workflow,
                facade.general_visit_candidates_operation_payload,
            ),
            (
                "POST", "/api/troops/assign",
                facade._run_troop_assign_game_workflow,
                facade.troop_assign_operation_payload,
            ),
            (
                "POST", "/api/troops/refill",
                facade._run_troop_refill_game_workflow,
                facade.troop_refill_operation_payload,
            ),
            (
                "POST", "/api/troops/heal",
                facade._run_troop_heal_game_workflow,
                facade.troop_heal_operation_payload,
            ),
            (
                "POST", "/api/inventory/open-one",
                facade._run_inventory_open_one_game_workflow,
                facade.inventory_open_one_operation_payload,
            ),
            (
                "POST", "/api/brush/search",
                facade._run_cloud_coordinated_brush_search_game_workflow,
                facade.brush_search_operation_payload,
            ),
            (
                "POST", "/api/mine/search",
                facade._run_cloud_coordinated_mine_search_game_workflow,
                facade.mine_search_operation_payload,
            ),
            (
                "POST", "/api/brush/execute",
                facade._run_cloud_coordinated_brush_execute_game_workflow,
                facade.brush_execute_operation_payload,
            ),
            (
                "POST", "/api/mine/execute",
                facade._run_cloud_coordinated_mine_execute_game_workflow,
                facade.mine_execute_operation_payload,
            ),
            (
                "POST", "/api/liubu/hubu/query",
                facade._run_hubu_status_game_workflow,
                facade.hubu_query_operation_payload,
            ),
            (
                "POST", "/api/liubu/hubu/plant",
                facade._run_hubu_plant_game_workflow,
                facade.hubu_plant_operation_payload,
            ),
            (
                "POST", "/api/daily/sign-in/claim",
                facade.daily_completion_workflow(
                    "autoSignIn", facade._run_daily_sign_in_game_workflow
                ),
                facade.daily_operation_payload,
            ),
            (
                "POST", "/api/daily/arena-coins/claim",
                facade.daily_completion_workflow(
                    "arenaCoins", facade._run_daily_arena_coins_game_workflow
                ),
                facade.daily_operation_payload,
            ),
            (
                "POST", "/api/daily/donate/claim",
                facade.daily_completion_workflow(
                    "autoDonate", facade._run_daily_donate_game_workflow
                ),
                facade.daily_operation_payload,
            ),
            (
                "POST", "/api/daily/donate/custom",
                facade._run_daily_custom_donate_game_workflow,
                facade.daily_custom_donate_operation_payload,
            ),
            (
                "POST", "/api/daily/national-collect/claim",
                facade.daily_completion_workflow(
                    "nationalCollect",
                    facade._run_daily_national_collect_game_workflow,
                ),
                facade.daily_operation_payload,
            ),
            (
                "POST", "/api/daily/city-lord-collect/claim",
                facade.daily_completion_workflow(
                    "cityLordCollect",
                    facade._run_daily_city_lord_collect_game_workflow,
                ),
                facade.daily_operation_payload,
            ),
            (
                "POST", "/api/daily/general-visit/claim",
                facade.daily_completion_workflow(
                    "generalVisit",
                    facade._run_daily_general_visit_game_workflow,
                ),
                facade.daily_general_visit_operation_payload,
            ),
            (
                "POST", "/api/daily/salary/claim",
                facade.daily_completion_workflow(
                    "salary", facade._run_daily_salary_game_workflow
                ),
                facade.daily_operation_payload,
            ),
        )
        for method, path, workflow, payload_builder in raw_routes:
            facade.register_host_game_command_route(
                method,
                path,
                host_bridge,
                workflow,
                persisted_payload_builder=payload_builder,
                coalesce_active=True,
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
