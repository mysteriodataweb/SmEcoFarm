"""Stations : Champ (oiseaux, maladies) et Entrepôt (conservation, incendie)."""

from .champ import FieldStation
from .entrepot import WarehouseStation

__all__ = ["FieldStation", "WarehouseStation"]
