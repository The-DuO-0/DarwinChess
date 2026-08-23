from dogmatist_v2 import live_parallel_population
from dogmatist_v2.live_parallel_league import LiveLeagueProcessPool
from dogmatist_v2.live_signal_safety import (
    SigintSafeLeagueProcessPool,
    _ignore_parent_sigint,
    install_parallel_league_signal_safety,
)
import dogmatist_v2.live_signal_safety as safety


def test_worker_signal_guard_ignores_sigint(monkeypatch):
    calls = []

    def fake_signal(sig, handler):
        calls.append((sig, handler))

    monkeypatch.setattr(safety.signal, "signal", fake_signal)
    _ignore_parent_sigint()
    assert calls == [(safety.signal.SIGINT, safety.signal.SIG_IGN)]


def test_live_entrypoint_can_swap_population_pool_to_sigint_safe_subclass(monkeypatch):
    monkeypatch.setattr(live_parallel_population, "LiveLeagueProcessPool", LiveLeagueProcessPool)
    install_parallel_league_signal_safety()
    assert live_parallel_population.LiveLeagueProcessPool is SigintSafeLeagueProcessPool
    assert issubclass(SigintSafeLeagueProcessPool, LiveLeagueProcessPool)
