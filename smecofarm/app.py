"""Assemblage de l'application : crée les capteurs, actionneurs, services et
stations selon la configuration, puis fait tourner la boucle principale."""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .actionneurs import Buzzer, Door, Fan, Led
from .services.blynk import BlynkClient, NullBlynk
from .services.config import PROJECT_ROOT, secret
from .services.email_alert import GmailNotifier, NullNotifier
from .regles import ALERTE
from .services.journal import DataLogger

log = logging.getLogger("smecofarm")

CONTROL_PINS = ("buzzer_oiseaux_actif", "mode_ventilateur", "rearmement", "ouvrir_porte")
ALL_STATIONS = ("champ", "entrepot", "acces")

# Carte inconnue présentée en simulation (à 20 s), après une carte autorisée (à 10 s)
SIMULATED_UNKNOWN_CARD = 123456789


def setup_logging(folder, verbose=False):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(folder / "smecofarm.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)


class App:
    def __init__(self, config, stations=ALL_STATIONS, simulation=None, clock=time.monotonic,
                 blynk=None, notifier=None):
        """
        stations   : stations à lancer ("champ", "entrepot", "acces").
        simulation : None (matériel réel) ou nom de scénario ("normal", "chaleur", "incendie").
        blynk, notifier : à fournir pour les tests ; sinon créés selon config et .env.
        """
        self.config = config
        self.clock = clock
        self.simulation = simulation
        hw = config.get("materiel", {})
        blynk_cfg = config.get("blynk", {})
        pins_cfg = blynk_cfg.get("pins", {}) or {}
        self.pins = {name: pin for name, pin in pins_cfg.items() if pin}
        journal_cfg = config.get("journal", {})
        self.journal_interval = journal_cfg.get("intervalle_s", 60)
        self.logger = DataLogger(PROJECT_ROOT / journal_cfg.get("dossier", "data"))

        self.blynk = blynk or self._make_blynk(blynk_cfg)
        self.notifier = notifier or self._make_notifier(config.get("email", {}))
        simulated = simulation is not None
        self.buzzer = Buzzer(hw.get("buzzer_gpio", 23), simulated=simulated, clock=clock)
        self.led = Led(hw.get("led_gpio", 22), simulated=simulated)
        self.led_threshold = config.get("led", {}).get("seuil_temperature", 30)
        self._closables = [self.buzzer, self.led]

        self.scenario = None
        if simulated:
            from .capteurs.simulation import Scenario
            self.scenario = Scenario(simulation, clock)

        self.field = self.warehouse = self.access = None
        access_cfg = config.get("acces", {})
        access_on = "acces" in stations and access_cfg.get("actif", True)
        if "champ" in stations and config.get("champ", {}).get("actif", True):
            self.field = self._make_field(config.get("champ", {}))
        if "entrepot" in stations and config.get("entrepot", {}).get("actif", True):
            warehouse_cfg = {**config.get("entrepot", {}),
                             "porte_evacuation": access_on and access_cfg.get("ouvrir_si_incendie", True)}
            self.warehouse = self._make_warehouse(warehouse_cfg, hw)
        if access_on:
            self.access = self._make_access(access_cfg, hw)
        if not (self.field or self.warehouse or self.access):
            raise ValueError("Aucune station active (voir config.yaml)")
        self._next_journal = 0.0

    # --- construction ----------------------------------------------------
    def _make_blynk(self, cfg):
        token = secret("BLYNK_TOKEN")
        if not cfg.get("actif", True) or not token:
            if cfg.get("actif", True) and not token:
                log.warning("Blynk désactivé : BLYNK_TOKEN absent du fichier .env")
            return NullBlynk()
        control_pins = [self.pins[name] for name in CONTROL_PINS if name in self.pins]
        return BlynkClient(token, cfg.get("serveur", "blynk.cloud"), cfg.get("intervalle_s", 5), control_pins)

    def _make_notifier(self, cfg):
        user, password, to = secret("GMAIL_USER"), secret("GMAIL_APP_PASSWORD"), secret("EMAIL_TO")
        if not cfg.get("actif", True) or not (user and password and to):
            if cfg.get("actif", True):
                log.warning("E-mail désactivé : GMAIL_USER / GMAIL_APP_PASSWORD / EMAIL_TO absents du .env")
            return NullNotifier()
        return GmailNotifier(user, password, to, cooldown_s=cfg.get("pause_min", 10) * 60)

    def _make_field(self, cfg):
        from .stations import FieldStation
        if self.simulation is not None:
            from .vision.camera import ImageFolderCamera
            camera = ImageFolderCamera(PROJECT_ROOT / "test_images", name="caméra champ simulée")
            # En simulation, analyse maladie fréquente pour voir le résultat
            cfg = {**cfg, "intervalle_maladies_s": min(cfg.get("intervalle_maladies_s", 1800), 15)}
        else:
            from .vision.camera import UsbCamera
            camera = UsbCamera(cfg.get("camera", 0), name="webcam champ")
        self._closables.append(camera)
        return FieldStation(cfg, camera, self.buzzer, self.blynk, self.logger, self.pins)

    def _make_warehouse(self, cfg, hw):
        from .stations import WarehouseStation
        simulated = self.simulation is not None
        if simulated:
            from .capteurs.simulation import SimulatedDht11, SimulatedMq135
            from .vision.camera import SyntheticFireCamera
            climate = SimulatedDht11(self.scenario)
            gas = SimulatedMq135(self.scenario)
            camera = SyntheticFireCamera(self.scenario.fire_active)
        else:
            from .capteurs.dht11 import Dht11Sensor
            from .capteurs.mq135 import Mq135Digital
            from .vision.camera import UsbCamera
            climate = Dht11Sensor(hw.get("dht11_gpio", 4))
            gas = Mq135Digital(hw.get("mq135_do_gpio", 17), hw.get("mq135_actif_bas", True),
                               hw.get("mq135_prechauffage_s", 180))
            camera = UsbCamera(cfg.get("camera", 2), name="webcam entrepôt") if cfg.get("camera") is not None else None
        fan = Fan(hw.get("relais_ventilateur_gpio", 27), hw.get("relais_actif_bas", True), simulated=simulated)
        self._closables += [fan, climate, gas] + ([camera] if camera else [])
        return WarehouseStation(cfg, climate, gas, camera, fan, self.buzzer, self.blynk,
                                self.notifier, self.logger, self.pins)

    def _make_access(self, cfg, hw):
        from .stations import AccessStation
        simulated = self.simulation is not None
        if simulated:
            from .capteurs.rfid import SimulatedRfid
            cards = [int(uid) for uid in (cfg.get("cartes_autorisees") or {})]
            events = ([(10, cards[0])] if cards else []) + [(20, SIMULATED_UNKNOWN_CARD)]
            reader = SimulatedRfid(events, self.clock)
        else:
            from .capteurs.rfid import RfidReader
            reader = RfidReader(cfg.get("anti_rebond_s", 3))
        door = Door(hw.get("servo_porte_gpio", 26), cfg.get("angle_ferme", 0), cfg.get("angle_ouvert", 90),
                    simulated=simulated)
        self._closables += [reader, door]
        return AccessStation(cfg, reader, door, self.buzzer, self.blynk, self.logger, self.pins)

    # --- fonctionnement --------------------------------------------------
    def _fire_alarm(self):
        return bool(self.warehouse and self.warehouse.fire and self.warehouse.fire.level == ALERTE)

    def state(self):
        values = {}
        if self.field:
            values.update(self.field.state())
        if self.warehouse:
            values.update(self.warehouse.state())
        if self.access:
            values.update(self.access.state())
            # Message d'état (V7) : incendie > dernier événement de badge > état de l'entrepôt
            if self.access.message and not self._fire_alarm():
                values["message"] = self.access.message
            values.setdefault("message", "Système normal")
        values["led"] = int(self.led.is_on)
        return values

    def _update_led(self):
        """LED comme dans le code d'origine : température haute ou porte ouverte."""
        hot = False
        if self.warehouse and self.warehouse.climate and self.warehouse.climate.ok:
            hot = self.warehouse.climate.temperature > self.led_threshold
        door_open = bool(self.access and self.access.door.is_open)
        self.led.set(hot or door_open)

    def tick(self):
        now = self.clock()
        for station in (self.field, self.warehouse, self.access):
            if station is None:
                continue
            try:
                station.tick(now)
            except Exception:
                # Une erreur ponctuelle (caméra, capteur) ne doit pas arrêter la surveillance
                log.exception("Erreur dans la station %s", type(station).__name__)

        if self.access and self.warehouse and self.warehouse.cfg.get("porte_evacuation"):
            self.access.set_evacuation(now, self._fire_alarm())
        self._update_led()

        values = self.state()
        self.blynk.publish({self.pins[name]: value for name, value in values.items() if name in self.pins})

        if now >= self._next_journal and values:
            self._next_journal = now + self.journal_interval
            self.logger.log({
                "temperature_c": values.get("temperature", ""),
                "humidite_pct": values.get("humidite", ""),
                "air_anormal": values.get("air_anormal", ""),
                "ventilateur": values.get("ventilateur", ""),
                "niveau_incendie": values.get("niveau_incendie", ""),
                "oiseaux_detectes": values.get("oiseaux_compteur", ""),
                "maladie": values.get("maladie", ""),
                "confiance_maladie": values.get("maladie_confiance", ""),
            })
        return values

    def run(self, duration_s=None, period_s=0.1):
        start = self.clock()
        log.info("SmEcoFarm démarré (stations : %s%s)",
                 ", ".join(n for n, s in (("champ", self.field), ("entrepôt", self.warehouse),
                                          ("accès", self.access)) if s),
                 f", simulation « {self.simulation} »" if self.simulation else "")
        while duration_s is None or self.clock() - start < duration_s:
            self.tick()
            time.sleep(period_s)

    def close(self):
        """Remet le matériel dans un état sûr (ventilateur et buzzer arrêtés)."""
        for item in reversed(self._closables):
            try:
                item.close()
            except Exception:
                log.exception("Erreur à la fermeture de %s", type(item).__name__)
        self.blynk.close()
