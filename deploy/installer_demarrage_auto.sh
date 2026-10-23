#!/usr/bin/env bash
# Installe SmEcoFarm comme service : il démarre tout seul à chaque allumage du Pi,
# sans terminal, et redémarre automatiquement en cas d'erreur.
#   bash deploy/installer_demarrage_auto.sh             installer et démarrer
#   bash deploy/installer_demarrage_auto.sh --retirer   désinstaller
set -e
PROJET="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
SERVICE=/etc/systemd/system/smecofarm.service

if [ "${1:-}" = "--retirer" ]; then
    sudo systemctl disable --now smecofarm 2>/dev/null || true
    sudo rm -f "$SERVICE"
    sudo systemctl daemon-reload
    echo "Démarrage automatique retiré."
    exit 0
fi

chmod +x "$PROJET/lancer.sh"
# Les guillemets permettent les espaces dans le chemin (ex. « FINAL PROJECT »)
sudo tee "$SERVICE" >/dev/null <<SERVICE_EOF
[Unit]
Description=SmEcoFarm - champ, entrepôt et contrôle d'accès
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$PROJET
ExecStart=/bin/bash "$PROJET/lancer.sh"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable --now smecofarm
echo
echo "SmEcoFarm démarre maintenant tout seul à chaque allumage du Pi."
echo "  Voir les messages : journalctl -u smecofarm -f"
echo "  Arrêter           : sudo systemctl stop smecofarm"
echo "  Redémarrer        : sudo systemctl restart smecofarm"
echo "  Désinstaller      : bash deploy/installer_demarrage_auto.sh --retirer"
