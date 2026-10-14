"""Station Entrepôt : conservation des tomates et sécurité incendie."""

import logging

from ..regles import ALERTE, VIGILANCE, FireRules, StorageRules
from ..vision import FireDetector

log = logging.getLogger(__name__)

DEFAULTS = {
    "intervalle_capteurs_s": 3.0,
    "intervalle_camera_s": 1.0,
}

FAN_AUTO, FAN_FORCED_ON, FAN_FORCED_OFF = "0", "1", "2"
INDICATOR_NAMES = {"flamme": "flamme vue par la caméra", "temperature": "montée rapide de la température",
                   "fumee": "fumée / gaz détecté (MQ-135)"}


class WarehouseStation:
    def __init__(self, config, climate_sensor, gas_sensor, camera, fan, buzzer, blynk, notifier, logger, pins):
        cfg = config or {}
        self.cfg = {**DEFAULTS, **cfg}
        self.climate_sensor = climate_sensor
        self.gas_sensor = gas_sensor
        self.camera = camera
        self.fan = fan
        self.buzzer = buzzer
        self.blynk = blynk
        self.notifier = notifier
        self.logger = logger
        self.pins = pins
        self.storage_rules = StorageRules(cfg.get("conservation"))
        self.fire_rules = FireRules(cfg.get("incendie"))
        cam = cfg.get("camera_feu") or {}
        self.fire_detector = FireDetector(
            min_ratio=cam.get("proportion_min", 0.005),
            consecutive_frames=cam.get("images_consecutives", 3),
            require_flicker=cam.get("exiger_scintillement", True),
            min_flicker=cam.get("scintillement_min", 0.15),
        )

        self._next_sensors = 0.0
        self._next_camera = 0.0
        self._last_reset_value = None
        self._previous_alerts = set()
        self._last_frame = None
        self._flame_frame = None
        self.climate = None
        self.air_bad = None
        self.flame_confirmed = False
        self.decision = None
        self.fire = None
        self.fan_mode = FAN_AUTO

    def tick(self, now):
        if now >= self._next_sensors:
            self._next_sensors = now + self.cfg["intervalle_capteurs_s"]
            self.climate = self.climate_sensor.read()
            self.air_bad = self.gas_sensor.air_bad()

        if self.camera is not None and now >= self._next_camera:
            self._next_camera = now + self.cfg["intervalle_camera_s"]
            frame = self.camera.read()
            if frame is not None:
                result = self.fire_detector.analyse(frame)
                self._last_frame = frame
                if result.flame:
                    self._flame_frame = frame
                self.flame_confirmed = result.confirmed

        if self.climate is None:
            return
        self._handle_reset()

        temperature = self.climate.temperature if self.climate.ok else None
        humidity = self.climate.humidity if self.climate.ok else None
        previous_level = self.fire.level if self.fire else 0
        self.fire = self.fire_rules.update(now, temperature, self.air_bad, self.flame_confirmed)
        self.decision = self.storage_rules.update(temperature, humidity, self.air_bad)

        self._apply_actuators()

        if self.fire.new_alarm:
            self._raise_fire_alarm(temperature)
        elif self.fire.level == VIGILANCE and previous_level == 0:
            reasons = ", ".join(INDICATOR_NAMES[i] for i in self.fire.indicators)
            log.warning("Vigilance incendie : %s", reasons)
            if self._last_frame is not None:
                self.logger.save_photo(self._flame_frame if "flamme" in self.fire.indicators else self._last_frame,
                                       "vigilance")

        # Une notification par type d'alerte (le texte contient la valeur, qui varie)
        current = {message.split(" :")[0]: message for message in self.decision.alerts}
        for kind, message in current.items():
            if kind not in self._previous_alerts:
                log.warning("Conservation : %s", message)
                self.blynk.event("conservation", message)
        self._previous_alerts = set(current)

    def _handle_reset(self):
        """Bouton Blynk de réarmement : agit seulement quand il passe à 1."""
        pin = self.pins.get("rearmement")
        value = self.blynk.control(pin, "0")
        if value == "1" and self._last_reset_value != "1":
            log.info("Réarmement de l'alerte incendie depuis Blynk")
            self.fire_rules.reset()
            self.blynk.write_now(pin, 0)
        self._last_reset_value = value
        self.fan_mode = self.blynk.control(self.pins.get("mode_ventilateur"), FAN_AUTO)

    def _apply_actuators(self):
        if self.fire.level == ALERTE:
            # En cas d'incendie on coupe la ventilation : elle attiserait le feu.
            self.fan.set(False)
            self.buzzer.siren(True)
            return
        self.buzzer.siren(False)
        if self.fan_mode == FAN_FORCED_ON:
            self.fan.set(True)
        elif self.fan_mode == FAN_FORCED_OFF:
            self.fan.set(False)
        else:
            self.fan.set(self.decision.fan_on)

    def _raise_fire_alarm(self, temperature):
        reasons = "\n".join(f"  - {INDICATOR_NAMES[i]}" for i in self.fire.indicators)
        log.error("ALERTE INCENDIE : %s", ", ".join(self.fire.indicators))
        photo = self._flame_frame if self._flame_frame is not None else self._last_frame
        if photo is not None:
            self.logger.save_photo(photo, "incendie")
        temp_text = f"{temperature:.0f} °C" if temperature is not None else "inconnue"
        body = (
            "ALERTE INCENDIE dans l'entrepôt SmEcoFarm.\n\n"
            f"Indices détectés :\n{reasons}\n\n"
            f"Température : {temp_text}\n"
            "Le ventilateur a été coupé et la sirène est activée.\n"
            "Photo de la caméra en pièce jointe.\n\n"
            "Réarmez l'alarme depuis l'application Blynk une fois la situation vérifiée."
        )
        self.notifier.send_alert("🔥 SmEcoFarm : ALERTE INCENDIE dans l'entrepôt", body, photo)
        self.blynk.event("incendie", "Risque d'incendie : " + ", ".join(self.fire.indicators))

    def state(self):
        """Valeurs pour Blynk et le journal."""
        if self.climate is None:
            return {}
        if self.fire.level == ALERTE:
            message = "ALERTE INCENDIE : " + ", ".join(self.fire.indicators)
        elif self.decision.alerts:
            message = self.decision.alerts[0]
        elif self.fan.is_on:
            message = "Ventilation : " + (", ".join(self.decision.reasons) or "forcée")
        else:
            message = "Conditions normales"
        if self.gas_sensor.warming_up:
            message += " (MQ-135 en préchauffage)"
        values = {
            "air_anormal": int(bool(self.air_bad)),
            "ventilateur": int(self.fan.is_on),
            "niveau_incendie": self.fire.level,
            "message": message,
        }
        # Capteur en panne : on n'envoie pas de valeur (Blynk refuserait une valeur vide)
        if self.climate.ok:
            values["temperature"] = self.climate.temperature
            values["humidite"] = self.climate.humidity
        return values
