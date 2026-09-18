# Installation de la supervision

Les fichiers sont prêts dans le dépôt, pas installés sur le Pi. Le serveur
indiqué est `38.242.228.212`, avec Loki sur le port `3100` et Grafana sur le port
`3000`. Loki est actuellement sans authentification. Le modèle suppose HTTP
sur le port 3100 ; adapter `LOKI_URL` si TLS est configuré. Le destinataire des
notifications reste à préciser. Ces services n’ont pas été
interrogés depuis cette session.

## Raspberry Pi : reprise du service

Déployer ensemble le code Python et `edge.service` : l’unité attend maintenant
`READY=1` et les notifications du watchdog. Depuis la racine du projet sur le Pi :

```bash
venv/bin/python -m unittest discover -s tests -v
sudoedit /etc/edge/edge.env
```

Ajouter `MODBUS_SERIAL_PORT=/dev/serial/by-id/...` avec le chemin réel de la jauge.
Conserver les paramètres d’identité et de logs existants. Puis :

```bash
sudo install -m 0644 edge.service /etc/systemd/system/edge.service
sudo install -m 0644 deploy/raspberry-pi/edge-recovery.service /etc/systemd/system/edge-recovery.service
sudo install -m 0644 deploy/raspberry-pi/edge-recovery.timer /etc/systemd/system/edge-recovery.timer
sudo systemd-analyze verify /etc/systemd/system/edge.service /etc/systemd/system/edge-recovery.service /etc/systemd/system/edge-recovery.timer
sudo systemctl daemon-reload
sudo systemctl enable --now edge-recovery.timer
sudo systemctl enable edge.service
sudo systemctl restart edge.service
sudo systemctl status edge.service edge-recovery.timer --no-pager
sudo journalctl -u edge.service --since '5 minutes ago' --no-pager
```

Le service redémarre après 30 secondes en cas de sortie. Les démarrages sont
limités à 5 sur 15 minutes ; le timer retente ensuite toutes les 15 minutes si
le service est en échec. Le watchdog systemd expire après 120 secondes sans
notification. La supervision Python détecte un manque de progression Modbus
après 90 secondes et HTTP après 120 secondes avec les intervalles par défaut.
L’arrêt et le démarrage sont bornés respectivement à 30 et 90 secondes.

Un lot HTTP cesse d’ajouter des requêtes après 45 secondes ; une requête déjà
engagée peut dépasser cette durée. Son blocage est couvert par la supervision.
Les échecs API traités et les lots vides mettent à jour la progression.

Pour une maintenance, créer le marqueur **avant** d’arrêter le service :

```bash
sudo touch /etc/edge/maintenance
sudo systemctl stop edge.service
```

Pour reprendre :

```bash
sudo rm -f /etc/edge/maintenance
sudo systemctl reset-failed edge.service
sudo systemctl start edge.service
```

## Collecte distante

Conserver les sources du `config.alloy` existant. Remplacer les trois références
`loki.echo.local_check.receiver` par `loki.write.remote.receiver`, supprimer le
bloc `loki.echo` et ajouter le contenu de `remote-output.alloy`.
Ajouter dans `/etc/edge/edge.env` :

```ini
LOKI_URL=http://38.242.228.212:3100/loki/api/v1/push
```

Le modèle correspond au Loki actuel sans authentification : aucun identifiant
ni fichier de mot de passe n’est nécessaire. L’installation initiale ne remplace
pas un `edge.env` existant ; ajouter cette variable aussi sur les Pi déjà configurés.

Valider avec les variables d’environnement comme décrit dans `README.md`, puis
activer Alloy. Les retries sont limités et aucune file persistante de logs n’est
activée par ce modèle. Vérifier la réception des nouveaux heartbeats dans Loki ;
les mesures SQLite conservent leur propre mécanisme de reprise.

## Règles Grafana

Créer une règle par appareil attendu avec les requêtes de `ALERT_RULES.md`.
Évaluer chaque minute et configurer le contact d’astreinte, le groupement
`site, device, alertname` et les rappels du plan. Tester une notification réelle
et sa résolution. Une erreur de datasource doit ouvrir un incident de supervision.

## Recette pilote et limites

- Débrancher la jauge : erreurs puis redémarrage ; rebrancher : lectures valides.
- Couper uniquement l’API : acquisition maintenue, backlog croissant ; rétablir
  l’API et vérifier sa vidange.
- Sur le Pi pilote, envoyer `sudo systemctl kill --kill-whom=main --signal=SIGSTOP edge.service`
  pour simuler un gel ; vérifier le remplacement du PID après expiration du watchdog.
- Provoquer des échecs répétés sur le pilote ; vérifier la limite de démarrages,
  la reprise différée et l’absence de reprise pendant une maintenance.
- Arrêter Alloy : l’alerte de heartbeat doit apparaître sur le serveur indépendant.

Les tests Python sont exécutables sans matériel. La validation native de systemd,
Alloy, la réception des notifications et les essais matériels restent à effectuer
sur les machines cibles. Le reboot du Pi et le watchdog matériel restent une phase
distincte : aucun reboot automatique n’est activé par cette installation.
La télémétrie de sous-tension reste également à intégrer après identification du Pi.

Pour revenir en arrière, arrêter/désactiver `edge-recovery.timer` et restaurer
ensemble la version précédente du code et de l’unité, puis `daemon-reload` et
redémarrer le service. Conserver la base SQLite et le fichier d’environnement.

Références : [systemd.service](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml),
[sortie Alloy vers Loki](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/).
