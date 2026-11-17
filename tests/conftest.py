import pytest

from tech12000.actuators.base import SimLed, SimServo
from tech12000.config import Config
from tech12000.engine import Engine
from tech12000.recorder import NullRecorder
from tech12000.sources.sim import SimRadar, SimScenario, SimWristband
from tech12000.store import Store


class Rig:
    """用虚拟时间驱动引擎：100 Hz 手环 + 20 Hz 雷达，不 sleep。"""

    def __init__(self, cfg=None, store=None):
        self.cfg = cfg or Config()
        self.store = store or Store(":memory:")
        self.servo, self.led = SimServo(), SimLed()
        self.eng = Engine(self.cfg, self.store, self.servo, self.led, NullRecorder(), inline_actuation=True)
        self.scn = SimScenario()
        self.wrist, self.radar = SimWristband(self.eng, self.scn), SimRadar(self.eng, self.scn)
        self.t = 100.0
        self.states = []
        self.eng.listeners.append(lambda k, p: self.states.append(p["to"]) if k == "state" else None)

    def run(self, seconds, wrist=True, radar=True):
        for i in range(int(seconds * 100)):
            self.t += 0.01
            if wrist:
                self.eng.on_imu(self.wrist.make(self.t, wall=self.t))
            if radar and i % 5 == 0:
                self.eng.on_radar(self.radar.make(self.t, wall=self.t))
            self.eng.tick(self.t, self.t)

    def inject(self, kind):
        self.scn.inject(kind, self.t)
        self.eng.sim_label = self.scn.label

    def configure_servo(self):
        s = self.cfg.actuators.servo
        s.channel, s.home_pulse_us, s.release_pulse_us, s.demo_pulse_us, s.move_time_ms = 1, 1500, 1900, 1550, 300


@pytest.fixture
def rig():
    return Rig()
