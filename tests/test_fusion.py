import pytest

from tech12000.sources.sim import LABELS
from tech12000.models import DeployStatus, Mode, SystemState as S


def test_starts_initializing_then_ready(rig):
    assert rig.eng.fsm.state is S.INITIALIZING
    rig.run(2.0)
    assert rig.eng.fsm.state is S.READY
    assert rig.eng.mode is Mode.MONITOR


def test_fall_triggers_and_latches(rig):
    rig.run(2.0)
    rig.inject("fall")
    rig.run(2.0)
    assert rig.eng.fsm.state is S.TRIGGERED
    assert rig.states.count("triggered") == 1
    rig.run(5.0)                       # 之后无论数据如何都保持锁定
    assert rig.eng.fsm.state is S.TRIGGERED
    assert len(rig.store.list_events()) == 1


def test_wrist_only_never_triggers(rig):
    rig.run(2.0)
    rig.inject("wave")
    rig.run(1.0)
    assert rig.eng.fsm.state is S.SUSPECTED_FALL
    rig.run(8.0)
    assert rig.eng.fsm.state is S.READY
    assert "triggered" not in rig.states
    assert rig.store.list_events() == []


def test_slow_squat_does_not_trigger(rig):
    rig.run(2.0)
    rig.inject("squat")
    rig.run(6.0)
    assert "triggered" not in rig.states


def test_stale_source_faults_and_recovers(rig):
    rig.run(2.0)
    rig.run(1.5, wrist=False)          # 手环断联
    assert rig.eng.fsm.state is S.FAULT
    assert "wristband" in rig.eng.fsm.reason
    rig.run(0.5)                       # 刚恢复，还没稳定够久
    assert rig.eng.fsm.state is S.FAULT
    rig.run(1.0)
    assert rig.eng.fsm.state is S.READY


def test_stale_data_cannot_trigger(rig):
    """雷达断了以后，即使手环出现跌倒波形也不能用旧雷达数据触发。"""
    rig.run(2.0)
    rig.inject("fall")
    rig.run(3.0, radar=False)
    assert "triggered" not in rig.states
    assert rig.eng.fsm.state is S.FAULT


def test_never_ready_without_data(rig):
    for _ in range(700):
        rig.t += 0.01
        rig.eng.tick(rig.t, rig.t)
    assert rig.eng.fsm.state is S.FAULT


def test_duplicate_and_lost_packets_counted(rig):
    rig.run(1.0)
    s = rig.wrist.make(rig.t + 0.01, wall=rig.t)
    rig.eng.on_imu(s)
    rig.eng.on_imu(s)                  # 重复
    rig.wrist.seq += 3                 # 丢3包
    rig.eng.on_imu(rig.wrist.make(rig.t + 0.02, wall=rig.t))
    m = rig.eng.monitors["wristband"]
    assert m.duplicates == 1 and m.lost == 3


def test_reset_disarms(rig):
    rig.configure_servo()
    rig.run(2.0)
    assert rig.eng.set_mode(Mode.ARMED, "ARM") == (True, "")
    rig.inject("fall")
    rig.run(2.0)
    assert rig.eng.last_event.deploy_status is DeployStatus.COMMAND_SENT
    assert rig.eng.set_mode(Mode.DEMO)[0] is False      # 锁定期间不能改模式
    rig.eng.reset()
    rig.scn.reset()
    assert rig.eng.mode is Mode.MONITOR
    rig.run(2.0)
    assert rig.eng.fsm.state is S.READY and rig.eng.mode is Mode.MONITOR


def test_fall_snapshot_captures_imu_radar_and_point_cloud(rig):
    rig.run(2.0)
    assert rig.eng.fall_snapshot is None
    rig.inject("fall")
    rig.run(3.0)
    snap = rig.eng.fall_snapshot
    assert snap is not None and snap["complete"]
    assert snap["event_id"] == rig.eng.last_event.event_id
    te = snap["t_event"]
    assert snap["imu"][0][0] < te < snap["imu"][-1][0]
    assert max(t for t, *_ in snap["imu"]) >= te + snap["post_s"]
    assert len(snap["imu"][0]) == 7                      # t + 3 accel + 3 gyro
    assert snap["cloud_before"] and snap["cloud_after"]
    top = lambda pts: max(p[2] for p in pts if p[4] >= 10)   # ignore low-SNR clutter
    assert top(snap["cloud_before"]) > top(snap["cloud_after"]) + 0.5   # standing vs on the floor
    head = lambda js: next(z for n, x, y, z in js if n == "head")
    assert len(snap["joints_before"]) == 15
    assert head(snap["joints_before"]) > 1.4 and head(snap["joints_after"]) < 0.5   # skeleton lies down too


@pytest.mark.parametrize("kind", ["fall_forward", "fall_backward", "fall_side", "slip", "faint"])
def test_each_simulated_fall_type_triggers_and_ends_lying(rig, kind):
    rig.run(2.0)
    rig.inject(kind)
    rig.run(4.0)
    assert rig.eng.fsm.state is S.TRIGGERED
    snap = rig.eng.fall_snapshot
    assert snap["complete"] and snap["scenario"] == LABELS[kind]
    head = lambda js: next(z for n, x, y, z in js if n == "head")
    assert head(snap["joints_after"]) < 0.4
