# Configuration de Blynk

Le Raspberry Pi communique avec Blynk par l'**API HTTP** (aucune bibliothèque à installer).

## 1. Template et datastreams

Dans [Blynk Console](https://blynk.cloud) : **Developer Zone > My Templates > New Template** (matériel : *Raspberry Pi*, connexion : *WiFi*).
Puis onglet **Datastreams > New Datastream > Virtual Pin** :

| Pin | Nom | Type | Min / Max | Rôle |
|---|---|---|---|---|
| V0 | Oiseau présent | Integer | 0 / 1 | affichage |
| V1 | Oiseaux détectés | Integer | 0 / 100000 | affichage |
| V2 | Maladie | String | — | affichage |
| V3 | Confiance maladie | Integer | 0 / 100, unité % | affichage |
| V4 | Buzzer oiseaux actif | Integer | 0 / 1, valeur par défaut 1 | **commande** (interrupteur) |
| V5 | Température | Double | 0 / 50, unité °C | affichage |
| V6 | Humidité | Double | 0 / 100, unité % | affichage |
| V7 | Air anormal | Integer | 0 / 1 | affichage |
| V8 | Ventilateur | Integer | 0 / 1 | affichage |
| V9 | Mode ventilateur | Integer | 0 / 2 | **commande** : 0 auto, 1 marche, 2 arrêt |
| V10 | Niveau incendie | Integer | 0 / 2 | affichage : 0 normal, 1 vigilance, 2 alerte |
| V11 | Réarmement | Integer | 0 / 1 | **commande** (bouton) |
| V12 | Message | String | — | affichage |

Si votre offre Blynk limite le nombre de datastreams, supprimez les moins utiles (par exemple V1, V3, V7)
et mettez `null` à la place de la pin dans `config.yaml` (section `blynk.pins`).

## 2. Événements (notifications)

Onglet **Events > Add New Event**, avec ces **codes** exacts :

| Code | Nom | Type | Notifications conseillées |
|---|---|---|---|
| `incendie` | Alerte incendie | Critical | Push + e-mail |
| `conservation` | Alerte conservation | Warning | Push |
| `maladie` | Maladie détectée | Warning | Push |

Dans chaque événement, onglet *Notifications* : activer les notifications et choisir le destinataire.
Pensez à limiter la fréquence (*Limit*) pour ne pas être inondé.

## 3. Dashboard (application mobile ou web)

Widgets conseillés :

- **Gauge** : V5 (température), V6 (humidité)
- **LED** : V0 (oiseau), V7 (air anormal), V8 (ventilateur)
- **Value Display** : V1, V3 ; **Label** : V2 (maladie), V12 (message)
- **Switch** : V4 (buzzer oiseaux)
- **Segmented Switch** ou **Menu** : V9 (Auto / Marche / Arrêt → valeurs 0 / 1 / 2)
- **Level** ou **Value Display** coloré : V10 (incendie)
- **Button** en mode *Push* : V11 (réarmement)
- **Chart / SuperChart** : V5 et V6 pour l'historique

## 4. Device et token

**Devices > New Device > From template**, puis copier l'**Auth Token** dans le fichier `.env` :

```
BLYNK_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
```

Si votre compte est sur un serveur régional (l'adresse affichée dans le navigateur, par exemple `fra1.blynk.cloud`),
mettre ce nom dans `config.yaml` → `blynk.serveur`.
