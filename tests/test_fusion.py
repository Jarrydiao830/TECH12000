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
