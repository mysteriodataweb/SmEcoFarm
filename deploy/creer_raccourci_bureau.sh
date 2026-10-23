#!/usr/bin/env bash
# Crée une icône « SmEcoFarm » sur le bureau du Pi : double-clic pour lancer le
# programme dans une fenêtre (fermer la fenêtre arrête le programme).
set -e
PROJET="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
BUREAU="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
chmod +x "$PROJET/lancer.sh"
cat > "$BUREAU/SmEcoFarm.desktop" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=SmEcoFarm
Comment=Lancer la surveillance du champ, de l'entrepôt et de l'accès
Exec=lxterminal --title=SmEcoFarm -e bash -c '"$PROJET/lancer.sh"; echo; read -p "Programme arrêté. Appuyez sur Entrée pour fermer."'
Icon=applications-science
Terminal=false
DESKTOP_EOF
chmod +x "$BUREAU/SmEcoFarm.desktop"
# Évite la question « Exécuter / Exécuter dans un terminal » du gestionnaire de fichiers
gio set "$BUREAU/SmEcoFarm.desktop" metadata::trusted true 2>/dev/null || true
echo "Icône créée sur le bureau : $BUREAU/SmEcoFarm.desktop"
