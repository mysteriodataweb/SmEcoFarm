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
    assert blynk.values["V15"] == ALERTE
    assert list((tmp_path / "photos").glob("*incendie.jpg"))

    # Réarmement depuis Blynk : l'alerte retombe, mais le feu continue -> nouvelle alerte
    blynk.controls["V16"] = "1"
    run(app, clock, 1)
    assert blynk.controls["V16"] == "0"


def test_fan_manual_mode(tmp_path):
    blynk = FakeBlynk({"V14": "1"})  # marche forcée
    app, clock, _ = make_app("normal", blynk=blynk, tmp_path=tmp_path)
    run(app, clock, 5)
    assert app.warehouse.fan.is_on
    blynk.controls["V14"] = "2"      # arrêt forcé
    run(app, clock, 1)
    assert not app.warehouse.fan.is_on


def test_field_station_detects_bird(tmp_path):
    app, clock, _ = make_app("normal", stations=("champ",), tmp_path=tmp_path)
    run(app, clock, 10, step=1.0)  # parcourt les 7 photos d'oiseaux
    assert app.field.bird_count >= 1
    assert app.field.prediction is not None
    assert list((tmp_path / "photos").glob("*oiseau.jpg"))


def test_bird_buzzer_can_be_disabled(tmp_path):
    blynk = FakeBlynk({"V12": "0"})
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

    # Une pièce sans flamme mais avec une caisse de tomates rouges (même couleur qu'une flamme)
    detector = FireDetector()
    room = SyntheticFireCamera(lambda: False)
    results = [detector.analyse(np.array(room.read())) for _ in range(5)]
    assert results[-1].ratio >= 0.02          # les tomates ont bien une « couleur de flamme »...
    assert not any(r.flame for r in results)  # ... mais ne bougent pas : pas de flamme


# --- contrôle d'accès -----------------------------------------------------

AUTHORIZED = 1046817149299


def test_authorized_card_opens_door(tmp_path):
    blynk = FakeBlynk()
    app, clock, _ = make_app("normal", stations=("acces",), blynk=blynk, tmp_path=tmp_path)
    run(app, clock, 9)
    assert not app.access.door.is_open
    run(app, clock, 2)                       # carte autorisée présentée à 10 s
    assert app.access.door.is_open and app.led.is_on
    assert blynk.values["V6"] == str(AUTHORIZED) and blynk.values["V1"] == 1
    assert blynk.values["V7"].startswith("Accès autorisé")
    run(app, clock, 4)                       # fermeture après 4 s
    assert not app.access.door.is_open and not app.led.is_on
    log = next(tmp_path.glob("acces_*.csv")).read_text(encoding="utf-8")
    assert f"{AUTHORIZED};autorisé" in log


def test_unknown_card_is_refused(tmp_path):
    blynk = FakeBlynk()
    app, clock, _ = make_app("normal", stations=("acces",), blynk=blynk, tmp_path=tmp_path)
    calls = []
    original = app.buzzer.refused_alert
    app.buzzer.refused_alert = lambda d: (calls.append(d), original(d))
    run(app, clock, 22)                      # carte inconnue présentée à 20 s
    assert calls == [2]
    assert not app.access.door.is_open
    assert "acces_refuse" in blynk.events
    assert blynk.values["V7"] == "Carte non reconnue"
    assert "refusé" in next(tmp_path.glob("acces_*.csv")).read_text(encoding="utf-8")


def test_remote_open_from_blynk(tmp_path):
    blynk = FakeBlynk()
    app, clock, _ = make_app("normal", stations=("acces",), blynk=blynk, tmp_path=tmp_path)
    blynk.controls["V2"] = "1"
    run(app, clock, 1)
    assert app.access.door.is_open and blynk.controls["V2"] == "0"


def test_fire_opens_door_for_evacuation(tmp_path):
    blynk = FakeBlynk()
    app, clock, notifier = make_app("incendie", stations=("entrepot", "acces"), blynk=blynk, tmp_path=tmp_path)
    run(app, clock, 65)
    assert app.warehouse.fire.level == ALERTE
    assert app.access.door.is_open and app.access.evacuation
    assert "évacuation" in notifier.sent[0][1]
    run(app, clock, 30)                      # la porte reste ouverte pendant l'alerte
    assert app.access.door.is_open


def test_led_on_when_hot(tmp_path):
    app, clock, _ = make_app("chaleur", tmp_path=tmp_path)
    run(app, clock, 30)
    assert not app.led.is_on
    run(app, clock, 120)                     # 32 °C > 30 °C
    assert app.led.is_on
