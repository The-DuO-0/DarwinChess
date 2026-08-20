from dogmatist_v2.live_compute import HeartbeatComputeClock


class FakeTime:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_long_suspend_gap_does_not_consume_compute_budget():
    now = FakeTime()
    clock = HeartbeatComputeClock(
        100.0,
        now=now,
        heartbeat_interval_seconds=1.0,
        suspension_threshold_seconds=10.0,
    )
    now.advance(5)
    clock.pulse()
    assert clock.elapsed_seconds == 5.0

    # Simulate lid-close/process suspension: no heartbeat can run for an hour.
    now.advance(3600)
    detected = clock.pulse()
    assert detected == 3599.0
    assert clock.elapsed_seconds == 6.0
    snap = clock.snapshot()
    assert snap["excluded_sleep_seconds"] == 3599.0
    assert snap["wall_sleep_counts"] is False


def test_normal_active_heartbeat_time_counts_even_if_work_is_slow():
    now = FakeTime()
    clock = HeartbeatComputeClock(
        30.0,
        now=now,
        heartbeat_interval_seconds=1.0,
        suspension_threshold_seconds=10.0,
    )
    for _ in range(12):
        now.advance(1)
        assert clock.pulse() == 0.0
    assert clock.elapsed_seconds == 12.0
    assert not clock.expired

    # As long as the heartbeat continues, all remaining runnable time counts.
    for _ in range(18):
        now.advance(1)
        assert clock.pulse() == 0.0
    assert clock.elapsed_seconds == 30.0
    assert clock.expired


def test_explicit_pause_is_excluded_independently_of_sleep_detection():
    now = FakeTime()
    clock = HeartbeatComputeClock(
        20.0,
        now=now,
        heartbeat_interval_seconds=1.0,
        suspension_threshold_seconds=10.0,
    )
    now.advance(4)
    clock.pause()
    now.advance(100)
    clock.resume()
    now.advance(6)
    clock.pulse()
    snap = clock.snapshot()
    assert snap["elapsed_seconds"] == 10.0
    assert snap["paused_seconds"] == 100.0
    assert snap["excluded_sleep_seconds"] == 0.0
    assert snap["remaining_seconds"] == 10.0
