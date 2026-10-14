"""Tests des règles de conservation et d'incendie (sans matériel)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smecofarm.regles import ALERTE, NORMAL, VIGILANCE, FireRules, StorageRules  # noqa: E402


# --- conservation ---------------------------------------------------------

def test_fan_hysteresis():
    rules = StorageRules()
    assert not rules.update(23, 70, False).fan_on      # sous le seuil de marche
    assert rules.update(25, 70, False).fan_on          # > 24 °C : marche
    assert rules.update(23, 70, False).fan_on          # entre 22 et 24 : reste en marche
    assert not rules.update(21, 70, False).fan_on      # < 22 °C : arrêt
    assert not rules.update(23, 70, False).fan_on      # entre 22 et 24 : reste arrêté


def test_fan_for_bad_air():
    decision = StorageRules().update(20, 70, True)
    assert decision.fan_on and decision.reasons == ["air vicié"]
    assert not StorageRules({"ventiler_si_air_vicie": False}).update(20, 70, True).fan_on


def test_mq135_preheating_is_ignored():
    assert not StorageRules().update(20, 70, None).fan_on


def test_alerts():
    rules = StorageRules()
    assert any("trop haute" in a for a in rules.update(31, 70, False).alerts)
    assert any("trop basse" in a for a in rules.update(6, 70, False).alerts)
    assert any("trop sec" in a for a in rules.update(20, 55, False).alerts)
    assert rules.update(20, 70, False).alerts == []
    assert any("hors service" in a for a in rules.update(None, None, False).alerts)


def test_humidity_rule_disabled_by_default_and_configurable():
    assert not StorageRules().update(20, 96, False).fan_on
    rules = StorageRules({"humidite_ventilateur_marche": 95, "humidite_ventilateur_arret": 90})
    assert rules.update(20, 96, False).fan_on
    assert rules.update(20, 92, False).fan_on
    assert not rules.update(20, 88, False).fan_on


# --- incendie --------------------------------------------------------------

def test_one_indicator_is_vigilance_only():
    rules = FireRules()
    assert rules.update(0, 20, False, False).level == NORMAL
    status = rules.update(1, 20, False, True)
    assert status.level == VIGILANCE and status.indicators == ["flamme"]
    assert rules.update(2, 20, True, False).level == VIGILANCE


def test_two_indicators_raise_latched_alarm():
    rules = FireRules()
    status = rules.update(0, 20, True, True)
    assert status.level == ALERTE and status.new_alarm
    # L'alerte reste active même si les indices disparaissent...
    status = rules.update(5, 20, False, False)
    assert status.level == ALERTE and not status.new_alarm
    # ... jusqu'au réarmement
    rules.reset()
    assert rules.update(6, 20, False, False).level == NORMAL


def test_temperature_rate_of_rise():
    rules = FireRules({"hausse_temp_c": 5, "fenetre_hausse_s": 60})
    for t, temp in [(0, 20), (20, 21), (40, 23)]:
        assert rules.update(t, temp, False, False).level == NORMAL
    status = rules.update(55, 25, False, False)  # +5 °C en 55 s
    assert status.level == VIGILANCE and status.indicators == ["temperature"]


def test_slow_rise_is_not_fire():
    rules = FireRules({"hausse_temp_c": 5, "fenetre_hausse_s": 60})
    for i in range(20):  # +1 °C toutes les 30 s : montée lente (journée chaude)
        status = rules.update(i * 30, 20 + i, False, False)
    assert status.level == NORMAL


def test_high_temperature_plus_smoke_is_alarm():
    rules = FireRules()
    status = rules.update(0, 46, True, False)
    assert status.level == ALERTE and set(status.indicators) == {"temperature", "fumee"}
