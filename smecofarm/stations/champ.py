"""Station Champ : chasse aux oiseaux et analyse des maladies (une webcam)."""

import logging

from ..vision import BirdDetector, DiseaseClassifier

log = logging.getLogger(__name__)

DEFAULTS = {
    "intervalle_oiseaux_s": 1.0,
    "seuil_oiseaux": 0.5,
    "pause_buzzer_s": 30,
    "intervalle_maladies_s": 1800,
    "plante": "tomato",
    "seuil_maladies": 0.6,
}


class FieldStation:
    def __init__(self, config, camera, buzzer, blynk, logger, pins):
        self.cfg = {**DEFAULTS, **(config or {})}
        self.camera = camera
        self.buzzer = buzzer
        self.blynk = blynk
        self.logger = logger
        self.pins = pins
        self.bird_detector = BirdDetector(score_threshold=self.cfg["seuil_oiseaux"])
        self.disease_classifier = DiseaseClassifier(crop=self.cfg["plante"],
                                                    confidence_threshold=self.cfg["seuil_maladies"])
        self._next_bird = 0.0
        self._next_disease = 0.0  # première analyse dès le démarrage
        self._last_buzz = None
        self.bird_present = False
        self.bird_count = 0
        self.prediction = None

    def tick(self, now):
        if now < self._next_bird:
            return
        self._next_bird = now + self.cfg["intervalle_oiseaux_s"]
        frame = self.camera.read()
        if frame is None:
            return

        detections = self.bird_detector.detect(frame)
        present = bool(detections)
        if present and not self.bird_present:
            self.bird_count += 1
            log.info("Oiseau détecté (%.0f %%), total : %d", detections[0].score * 100, self.bird_count)
            self.logger.save_photo(frame, "oiseau")
        self.bird_present = present

        buzzer_enabled = self.blynk.control(self.pins.get("buzzer_oiseaux_actif"), "1") != "0"
        cooldown_over = self._last_buzz is None or now - self._last_buzz >= self.cfg["pause_buzzer_s"]
        if present and buzzer_enabled and cooldown_over:
            self.buzzer.bird_alert()
            self._last_buzz = now

        if now >= self._next_disease:
            self._next_disease = now + self.cfg["intervalle_maladies_s"]
            self.prediction = self.disease_classifier.predict(frame)
            p = self.prediction
            log.info("Analyse maladie : %s (%.0f %%)%s", p.name, p.confidence * 100,
                     " - incertain" if p.uncertain else "")
            if not p.healthy and not p.uncertain:
                self.logger.save_photo(frame, "maladie")
                self.blynk.event("maladie", f"{p.name} ({p.confidence:.0%})")

    def state(self):
        """Valeurs pour Blynk et le journal."""
        p = self.prediction
        if p is None:
            disease_text, confidence = "en attente", 0
        else:
            disease_text = f"{p.name} (incertain)" if p.uncertain else p.name
            confidence = round(p.confidence * 100)
        return {
            "oiseau_present": int(self.bird_present),
            "oiseaux_compteur": self.bird_count,
            "maladie": disease_text,
            "maladie_confiance": confidence,
        }
