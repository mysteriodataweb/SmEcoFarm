"""SmEcoFarm : programme principal à lancer sur le Raspberry Pi.

    python main.py                          # champ + entrepôt + accès avec le vrai matériel
    python main.py --station entrepot       # une seule station
    python main.py --simulation incendie    # sans matériel : scénario normal | chaleur | incendie
    python main.py --simulation chaleur --duree 180
"""

import argparse
import logging
import signal
import sys

from smecofarm.app import ALL_STATIONS, App, setup_logging
from smecofarm.capteurs.simulation import SCENARIOS
from smecofarm.services.config import PROJECT_ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--station", choices=["tout", "champ", "entrepot", "acces"], default="tout")
    parser.add_argument("--simulation", choices=SCENARIOS, help="faire tourner sans matériel")
    parser.add_argument("--duree", type=float, help="durée en secondes (par défaut : sans fin)")
    parser.add_argument("--config", help="fichier de configuration (par défaut : config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="afficher les messages de débogage")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(PROJECT_ROOT / config.get("journal", {}).get("dossier", "data"), args.verbose)
    stations = ALL_STATIONS if args.station == "tout" else (args.station,)

    # Arrêt propre aussi quand systemd arrête le service (signal SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    app = App(config, stations, simulation=args.simulation)
    try:
        app.run(args.duree)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logging.getLogger("smecofarm").info("Arrêt : ventilateur, buzzer et LED coupés, porte fermée")
        app.close()


if __name__ == "__main__":
    main()
