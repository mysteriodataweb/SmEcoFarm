"""Tests de bout en bout en simulation, avec une horloge accélérée."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from smecofarm.app import App  # noqa: E402
from smecofarm.regles import ALERTE  # noqa: E402
from smecofarm.services.blynk import NullBlynk  # noqa: E402
from smecofarm.services.config import load_config  # noqa: E402
from smecofarm.vision import FireDetector  # noqa: E402
from smecofarm.vision.camera import SyntheticFireCamera  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send_alert(self, subject, body, image=None):
        self.sent.append((subject, body, image))
        return True


class FakeBlynk(NullBlynk):
    def __init__(self, controls=None):
        self.controls = dict(controls or {})
        self.events = []
        self.values = {}

    def publish(self, values):
        self.values.update(values)

    def event(self, code, description):
        self.events.append(code)

    def control(self, pin, default=None):
        return self.controls.get(pin, default)

    def write_now(self, pin, value):
        self.controls[pin] = str(value)


def make_app(scenario, stations=("entrepot",), blynk=None, tmp_path=None):
    config = load_config(ROOT / "config.yaml", env_path=ROOT / "inexistant.env")
    config["journal"]["dossier"] = str(tmp_path)
    clock = FakeClock()
    notifier = FakeNotifier()
    app = App(config, stations, simulation=scenario, clock=clock, blynk=blynk or FakeBlynk(), notifier=notifier)
    return app, clock, notifier


def run(app, clock, seconds, step=0.5):
    for _ in range(int(seconds / step)):
        app.tick()
        clock.now += step


def test_normal_scenario(tmp_path):
    app, clock, notifier = make_app("normal", tmp_path=tmp_path)
    run(app, clock, 120)
    assert app.warehouse.fire.level == 0
    assert not app.warehouse.fan.is_on
    assert notifier.sent == []
    assert list(tmp_path.glob("*.csv")), "le journal CSV doit être créé"


def test_heat_scenario_starts_fan(tmp_path):
    app, clock, notifier = make_app("chaleur", tmp_path=tmp_path)
    run(app, clock, 150)
    assert app.warehouse.fan.is_on
    assert "température" in app.warehouse.decision.reasons
    assert app.warehouse.fire.level == 0  # montée lente : pas un incendie
    assert notifier.sent == []
    assert app.blynk.events.count("conservation") == 1  # 30, 31, 32 °C : une seule notification


def test_fire_scenario(tmp_path):
    blynk = FakeBlynk()
    app, clock, notifier = make_app("incendie", blynk=blynk, tmp_path=tmp_path)
    run(app, clock, 25)
    assert app.warehouse.fire.level == 0
    run(app, clock, 40)
    assert app.warehouse.fire.level == ALERTE
    assert not app.warehouse.fan.is_on and app.buzzer.siren_on
    assert len(notifier.sent) == 1
    subject, body, image = notifier.sent[0]
    assert "INCENDIE" in subject and image is not None
    assert "incendie" in blynk.events
    assert blynk.values["V10"] == ALERTE
    assert list((tmp_path / "photos").glob("*incendie.jpg"))

    # Réarmement depuis Blynk : l'alerte retombe, mais le feu continue -> nouvelle alerte
    blynk.controls["V11"] = "1"
    run(app, clock, 1)
    assert blynk.controls["V11"] == "0"


def test_fan_manual_mode(tmp_path):
    blynk = FakeBlynk({"V9": "1"})  # marche forcée
    app, clock, _ = make_app("normal", blynk=blynk, tmp_path=tmp_path)
    run(app, clock, 5)
    assert app.warehouse.fan.is_on
    blynk.controls["V9"] = "2"      # arrêt forcé
    run(app, clock, 1)
    assert not app.warehouse.fan.is_on


def test_field_station_detects_bird(tmp_path):
    app, clock, _ = make_app("normal", stations=("champ",), tmp_path=tmp_path)
    run(app, clock, 10, step=1.0)  # parcourt les 7 photos d'oiseaux
    assert app.field.bird_count >= 1
    assert app.field.prediction is not None
    assert list((tmp_path / "photos").glob("*oiseau.jpg"))


def test_bird_buzzer_can_be_disabled(tmp_path):
    blynk = FakeBlynk({"V4": "0"})
    app, clock, _ = make_app("normal", stations=("champ",), blynk=blynk, tmp_path=tmp_path)
    calls = []
    app.buzzer.bird_alert = lambda: calls.append(1)
    run(app, clock, 10, step=1.0)
    assert app.field.bird_count >= 1 and calls == []


def test_fire_detector_needs_flicker():
    detector = FireDetector(consecutive_frames=3)
    camera = SyntheticFireCamera(lambda: True)
    results = [detector.analyse(camera.read()) for _ in range(5)]
    assert results[-1].confirmed and results[-1].box is not None

    # Une image orange immobile (photo, objet) n'est pas confirmée comme flamme
    still = camera.read()
    detector = FireDetector(consecutive_frames=3)
    assert not any(detector.analyse(still).confirmed for _ in range(5))

    # Une pièce sans flamme
    detector = FireDetector()
    empty = SyntheticFireCamera(lambda: False).read()
    assert detector.analyse(np.array(empty)).ratio == 0
