"""Règles de conservation des tomates mûres.

Repères (tomates mûres) : idéal 7–10 °C pour quelques jours, acceptable jusqu'à
~20 °C ; au-dessus de 25–30 °C elles s'abîment vite ; humidité idéale 85–95 %.

Le ventilateur ne refroidit pas : il remplace l'air intérieur par l'air extérieur.
Il évacue la chaleur produite par les fruits, l'humidité en excès et les gaz.

Hystérésis : le ventilateur démarre au-dessus d'un seuil et ne s'arrête qu'en
dessous d'un seuil plus bas, pour éviter qu'il s'allume et s'éteigne sans arrêt.
"""

from dataclasses import dataclass, field

DEFAULTS = {
    "temp_ventilateur_marche": 24.0,
    "temp_ventilateur_arret": 22.0,
    "temp_alerte_haute": 30.0,
    "temp_alerte_basse": 7.0,
    "humidite_alerte_basse": 60.0,
    # Désactivé par défaut : le DHT11 ne mesure pas au-dessus de 80 %.
    # Avec un DHT22, mettre par exemple 95 (marche) et 90 (arrêt).
    "humidite_ventilateur_marche": None,
    "humidite_ventilateur_arret": 90.0,
    "ventiler_si_air_vicie": True,
}


@dataclass
class StorageDecision:
    fan_on: bool
    reasons: list = field(default_factory=list)  # pourquoi le ventilateur tourne
    alerts: list = field(default_factory=list)   # messages d'alerte conservation


class StorageRules:
    def __init__(self, config=None):
        self.cfg = {**DEFAULTS, **(config or {})}
        self._fan_for_temp = False
        self._fan_for_humidity = False

    def update(self, temperature, humidity, air_bad):
        """Calcule l'état voulu du ventilateur et les alertes.

        temperature, humidity : None si le capteur ne répond pas.
        air_bad : True / False, ou None (MQ-135 en préchauffage).
        """
        c = self.cfg
        alerts = []
        reasons = []

        if temperature is None:
            alerts.append("Capteur DHT11 hors service")
        else:
            if temperature > c["temp_ventilateur_marche"]:
                self._fan_for_temp = True
            elif temperature < c["temp_ventilateur_arret"]:
                self._fan_for_temp = False
            if temperature >= c["temp_alerte_haute"]:
                alerts.append(f"Température trop haute : {temperature:.0f} °C (dégradation rapide des tomates)")
            elif temperature <= c["temp_alerte_basse"]:
                alerts.append(f"Température trop basse : {temperature:.0f} °C (dommage par le froid)")

        if humidity is not None:
            on, off = c["humidite_ventilateur_marche"], c["humidite_ventilateur_arret"]
            if on is not None:
                if humidity > on:
                    self._fan_for_humidity = True
                elif humidity < off:
                    self._fan_for_humidity = False
            if humidity <= c["humidite_alerte_basse"]:
                alerts.append(f"Air trop sec : {humidity:.0f} % (les tomates se déshydratent)")

        if self._fan_for_temp:
            reasons.append("température")
        if self._fan_for_humidity:
            reasons.append("humidité")
        if air_bad and c["ventiler_si_air_vicie"]:
            reasons.append("air vicié")

        return StorageDecision(bool(reasons), reasons, alerts)
