"""Tests for aegis_core.hooks — pluggy hook specs and call ordering."""

from __future__ import annotations

from aegis_core.hooks import get_plugin_manager, hookimpl

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _RecordingPlugin:
    """Records every hook call with its arguments."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls: list[tuple[str, dict[str, object]]] = []

    @hookimpl
    def on_run_start(self, run_id: str, route: str, principal: str | None) -> None:
        self.calls.append(("on_run_start", {"run_id": run_id, "route": route, "principal": principal}))

    @hookimpl
    def on_node_end(self, run_id: str, node_name: str, duration_ms: float) -> None:
        self.calls.append(("on_node_end", {"run_id": run_id, "node_name": node_name, "duration_ms": duration_ms}))

    @hookimpl
    def on_verdict(self, run_id: str, node_name: str, verdict: str) -> None:
        self.calls.append(("on_verdict", {"run_id": run_id, "node_name": node_name, "verdict": verdict}))

    @hookimpl
    def on_run_end(self, run_id: str, status: str, usage: dict[str, object]) -> None:
        self.calls.append(("on_run_end", {"run_id": run_id, "status": status, "usage": usage}))


# ---------------------------------------------------------------------------
# Plugin manager bootstrap
# ---------------------------------------------------------------------------


def test_get_plugin_manager_returns_manager() -> None:
    import pluggy
    pm = get_plugin_manager()
    assert isinstance(pm, pluggy.PluginManager)


def test_plugin_manager_has_aegis_project() -> None:
    pm = get_plugin_manager()
    assert pm.project_name == "aegis"


def test_hookspecs_registered() -> None:
    """AegisSpec hookspecs must be registered — verified by hook attributes on pm.hook."""
    pm = get_plugin_manager()
    assert hasattr(pm.hook, "on_run_start")
    assert hasattr(pm.hook, "on_node_end")
    assert hasattr(pm.hook, "on_verdict")
    assert hasattr(pm.hook, "on_run_end")


# ---------------------------------------------------------------------------
# Individual hook calls
# ---------------------------------------------------------------------------


def test_on_run_start_called_with_correct_args() -> None:
    pm = get_plugin_manager()
    plugin = _RecordingPlugin("p1")
    pm.register(plugin)

    pm.hook.on_run_start(run_id="r-1", route="default", principal="user-42")

    assert len(plugin.calls) == 1
    name, kwargs = plugin.calls[0]
    assert name == "on_run_start"
    assert kwargs["run_id"] == "r-1"
    assert kwargs["route"] == "default"
    assert kwargs["principal"] == "user-42"


def test_on_run_start_principal_none() -> None:
    pm = get_plugin_manager()
    plugin = _RecordingPlugin("p1")
    pm.register(plugin)

    pm.hook.on_run_start(run_id="r-2", route="drafts", principal=None)

    _, kwargs = plugin.calls[0]
    assert kwargs["principal"] is None


def test_on_node_end_records_duration() -> None:
    pm = get_plugin_manager()
    plugin = _RecordingPlugin("p1")
    pm.register(plugin)

    pm.hook.on_node_end(run_id="r-3", node_name="ingress", duration_ms=12.5)

    _, kwargs = plugin.calls[0]
    assert kwargs["node_name"] == "ingress"
    assert kwargs["duration_ms"] == 12.5


def test_on_verdict_records_verdict() -> None:
    pm = get_plugin_manager()
    plugin = _RecordingPlugin("p1")
    pm.register(plugin)

    pm.hook.on_verdict(run_id="r-4", node_name="pii-guard", verdict="sanitize")

    _, kwargs = plugin.calls[0]
    assert kwargs["verdict"] == "sanitize"


def test_on_run_end_records_usage() -> None:
    pm = get_plugin_manager()
    plugin = _RecordingPlugin("p1")
    pm.register(plugin)

    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_cost": 0.001}
    pm.hook.on_run_end(run_id="r-5", status="ok", usage=usage)

    _, kwargs = plugin.calls[0]
    assert kwargs["status"] == "ok"
    usage_result = kwargs["usage"]
    assert isinstance(usage_result, dict)
    assert usage_result["prompt_tokens"] == 10


# ---------------------------------------------------------------------------
# Hook call ordering (pluggy LIFO — last registered, first called)
# ---------------------------------------------------------------------------


def test_hook_call_ordering_multiple_plugins() -> None:
    """pluggy calls implementations in LIFO order (last registered = first called)."""
    pm = get_plugin_manager()
    p1 = _RecordingPlugin("p1")
    p2 = _RecordingPlugin("p2")
    pm.register(p1)
    pm.register(p2)

    call_order: list[str] = []

    class _OrderPlugin:
        def __init__(self, tag: str) -> None:
            self._tag = tag

        @hookimpl
        def on_run_start(self, run_id: str, route: str, principal: str | None) -> None:
            call_order.append(self._tag)

    op1 = _OrderPlugin("first")
    op2 = _OrderPlugin("second")
    pm.register(op1)
    pm.register(op2)

    pm.hook.on_run_start(run_id="r-order", route="default", principal=None)

    # pluggy LIFO: op2 (last registered) called before op1
    assert call_order.index("second") < call_order.index("first")


def test_multiple_plugins_all_receive_the_same_call() -> None:
    """All registered plugins must receive each hook call."""
    pm = get_plugin_manager()
    plugins = [_RecordingPlugin(f"p{i}") for i in range(3)]
    for p in plugins:
        pm.register(p)

    pm.hook.on_run_end(run_id="r-multi", status="ok", usage={})

    for p in plugins:
        assert len(p.calls) == 1
        assert p.calls[0][0] == "on_run_end"


def test_no_plugins_registered_hook_call_is_noop() -> None:
    """Calling a hook with no registered implementations does not raise."""
    pm = get_plugin_manager()
    # No plugins registered; this must be a no-op, not an error.
    pm.hook.on_run_start(run_id="r-noop", route="default", principal=None)


# ---------------------------------------------------------------------------
# hookimpl marker is re-exported
# ---------------------------------------------------------------------------


def test_hookimpl_marker_exported() -> None:
    from aegis_core.hooks import hookimpl as imported_hookimpl
    assert callable(imported_hookimpl)
