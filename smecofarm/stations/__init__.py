"""Stations : Champ (oiseaux, maladies), Entrepôt (conservation, incendie)
et Accès (badge RFID, porte)."""

from .acces import AccessStation
from .champ import FieldStation
from .entrepot import WarehouseStation

__all__ = ["AccessStation", "FieldStation", "WarehouseStation"]
