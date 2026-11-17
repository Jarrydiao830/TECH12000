from tech12000.actuators.base import NoServo, SimServo
from tech12000.config import Config
from tech12000.executor import Executor
from tech12000.models import DeployStatus, FallEvent, Mode, event_message
from tech12000.store import Store

from conftest import Rig


def test_monitor_mode_sends_nothing(rig):
    rig.configure_servo()
    rig.run(2.0)
    rig.inject("fall")
    rig.run(2.0)
    assert rig.servo.moves == []
    assert rig.eng.last_event.deploy_status is DeployStatus.NOT_SENT_MONITOR


def test_demo_uses_demo_position_and_is_marked_test(rig):
    rig.configure_servo()
    rig.run(2.0)
    assert rig.eng.set_mode(Mode.DEMO)[0]
    rig.inject("fall")
    rig.run(2.0)
    assert [m[2] for m in rig.servo.moves] == [1550]
    ev = rig.eng.last_event
    assert ev.deploy_status is DeployStatus.DEMO_SENT and ev.is_test
    assert "Simulated test" in event_message(ev)


def test_arm_requires_confirm_ready_and_config(rig):
    assert rig.eng.set_mode(Mode.ARMED, "ARM")[0] is False     # 还没 Ready
    rig.run(2.0)
    assert rig.eng.set_mode(Mode.ARMED, "")[0] is False        # 没确认
    assert rig.eng.set_mode(Mode.ARMED, "ARM")[0] is False     # 释放位置未配置
    rig.configure_servo()
    assert rig.eng.set_mode(Mode.ARMED, "ARM")[0] is True


def test_cannot_arm_without_servo():
    cfg = Config()
    ex = Executor(NoServo(), Store(":memory:"), cfg.actuators.servo)
    assert ex.can_arm()[0] is False


def test_same_event_executes_once_even_across_restart(tmp_path):
    db = tmp_path / "t.sqlite3"
    cfg = Config()
    s = cfg.actuators.servo
    s.channel, s.release_pulse_us, s.move_time_ms = 1, 1900, 300
    ev = FallEvent(event_id="e1", t_wall=1.0, mode=Mode.ARMED, simulated_input=True)

    servo1, store1 = SimServo(), Store(db)
    ex1 = Executor(servo1, store1, s)
    assert ex1.execute(ev) is DeployStatus.COMMAND_SENT
    assert ex1.execute(ev) is DeployStatus.SKIPPED_DUPLICATE
    store1.close()

    servo2 = SimServo()                       # 模拟程序重启
    ex2 = Executor(servo2, Store(db), s)
    assert ex2.execute(ev) is DeployStatus.SKIPPED_DUPLICATE
    assert len(servo1.moves) == 1 and servo2.moves == []


def test_failed_send_is_not_retried(tmp_path):
    cfg = Config()
    s = cfg.actuators.servo
    s.channel, s.release_pulse_us, s.move_time_ms = 1, 3000, 300    # 超出脉宽范围
    servo, store = SimServo(), Store(":memory:")
    ex = Executor(servo, store, s)
    ev = FallEvent(event_id="e2", t_wall=1.0, mode=Mode.ARMED, simulated_input=True)
    assert ex.execute(ev) is DeployStatus.SEND_FAILED
    s.release_pulse_us = 1900
    assert ex.execute(ev) is DeployStatus.SKIPPED_DUPLICATE
    assert servo.moves == []


def test_message_never_claims_deployment():
    for st in DeployStatus:
        ev = FallEvent("x", 0.0, Mode.ARMED, False, deploy_status=st)
        msg = event_message(ev)
        assert "success" not in msg.lower() and "deployed" not in msg.lower()
