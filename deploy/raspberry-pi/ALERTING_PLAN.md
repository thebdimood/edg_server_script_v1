# Plan d’alertes et de redémarrage Raspberry Pi

Statut : supervision des workers, watchdog du service, reprise différée et
indicateurs applicatifs implémentés dans le dépôt. Voir [RECOVERY_SETUP.md](RECOVERY_SETUP.md)
pour l’installation et [ALERT_RULES.md](ALERT_RULES.md) pour les règles distantes.
Aucun déploiement en production effectué. Le reboot du Pi et la sous-tension
restent à traiter après validation matérielle. L’état actuel ci-dessous décrit
le point de départ du plan, avant cette implémentation.
Les seuils ci-dessous sont des valeurs initiales à valider sur un Pi pilote.

## 1. État actuel

- Lecture Modbus toutes les 30 secondes ; reconnexion après une erreur ; sortie
  du processus après 5 échecs consécutifs, soit environ 2 à 3 minutes selon les délais.
- `edge.service` relance le processus avec `Restart=always` et `RestartSec=5`.
- Heartbeat toutes les 60 secondes : il prouve seulement que la boucle principale tourne.
- Les mesures sont conservées dans SQLite pendant une panne API ; tentative HTTP
  toutes les 60 secondes, avec un timeout de 10 secondes par requête.
- Alloy collecte localement vers `loki.echo`. Aucun envoi distant ni notification
  n’est configuré dans les fichiers actuels.
- Aucun watchdog applicatif ni redémarrage automatique du Pi n’est configuré ici.

## 2. Alertes proposées

| Signal | Seuil initial | Niveau | Réaction |
|---|---|---|---|
| `modbus_failure` | Au moins 3 événements en 5 min | Avertissement | Reconnexion locale existante |
| `modbus_fatal` ou `application_crash` | Dès le premier événement | Critique | Redémarrage du service par systemd |
| Démarrages répétés | Au moins 3 `application_start` en 15 min | Critique | Diagnostiquer la boucle de redémarrage |
| Kernel CH341 `urb stopped` | Dès le premier événement | Avertissement | Corréler avec les lectures et les reconnexions |
| Aucune lecture valide de la jauge | 3 min, après grâce au démarrage | Critique | Distinguer données invalides, liaison coupée et worker bloqué |
| Aucune insertion SQLite valide | 10 min | Critique | Examiner acquisition, verrouillage, stockage et erreurs SQLite |
| `sync_failure` | Au moins 5 événements en 10 min | Avertissement | Continuer acquisition et stockage local |
| Âge de la plus ancienne mesure en attente | Plus de 30 min / 6 h | Avertissement / critique | Diagnostiquer réseau et API ; aucun reboot |
| Heartbeat absent pour un appareil attendu | 5 min | Critique | Signaler « appareil ou collecte injoignable » depuis le serveur |
| Espace disque utilisé | Plus de 80 % / 90 % pendant 5 min | Avertissement / critique | Libérer de l’espace selon une politique de rétention validée |
| Sous-tension persistante | Signal actif pendant 1 min | Critique | Vérifier alimentation et câble ; aucun reboot automatique |

Les événements d’erreur, de démarrage et le heartbeat existent déjà. Les âges
de lecture/insertion, la file d’attente et l’état matériel doivent être ajoutés.
Un événement kernel isolé ne prouve pas une panne persistante.

## 3. Détection de santé à ajouter

Enrichir le heartbeat avec l’âge de la dernière lecture valide, de la dernière
insertion réussie, le nombre de mesures en attente et l’âge de la plus ancienne.
Ajouter des événements distincts pour les erreurs SQLite et les valeurs invalides :
actuellement une erreur d’insertion peut être comptée comme une erreur Modbus,
et des valeurs hors plage peuvent laisser le compteur d’erreurs à zéro.

Chaque worker doit exposer son début de cycle et sa dernière fin de cycle,
y compris en cas d’échec traité. Mesurer ces durées avec une horloge monotone.
La supervision doit lire cet état sans dépendre du verrou SQLite ni du port série.
Étendre la liste des champs conservés par `JsonFormatter` dans `logging_config.py`.

Détecter un cycle Modbus bloqué au-delà de 90 secondes. Pour HTTP, établir une
durée totale maximale du lot et vérifier sa progression : un lot de 50 requêtes
peut dépasser plusieurs minutes. Une panne réseau traitée normalement ne doit
pas être interprétée comme un worker bloqué. Une file vide est un état sain.

Vérifier la fenêtre d’agrégation avant de finaliser les seuils : le code annonce
5 minutes mais peut fermer la fenêtre dès 3 valeurs par flotteur.

## 4. Reprise automatique par niveaux

1. **Liaison série** : conserver la fermeture/recréation du client Modbus.
2. **Processus** : conserver la sortie après 5 erreurs consécutives ; ajouter
   la détection des workers bloqués et un arrêt borné par systemd.
3. **Watchdog du service** : implémenter les notifications `WATCHDOG=1`, puis
   activer `WatchdogSec=120s`. Envoyer une notification toutes les 30 secondes
   seulement si les workers progressent dans leurs délais autorisés. Un simple
   heartbeat de la boucle principale ne suffit pas. Si `Type=notify` est choisi,
   envoyer aussi `READY=1` après initialisation. Ne pas activer le watchdog avant
   que le code de notification soit en place.
4. **Protection contre les boucles** : proposer `RestartSec=30s`,
   `TimeoutStopSec=30s`, `StartLimitIntervalSec=15min`, `StartLimitBurst=5`.
   La limite compte les démarrages, y compris manuels. Après atteinte de la limite,
   systemd laisse le service en échec ; l’expiration de la fenêtre ne programme
   pas une nouvelle tentative. Prévoir un timer local indépendant qui tente un
   démarrage toutes les 15 minutes si le service est en échec, hors maintenance.
   Une alerte critique reste ouverte tant que l’acquisition ne revient pas.
5. **Raspberry Pi** : réserver le reboot logiciel à un blocage local persistant,
   confirmé après plusieurs reprises du service. Préparer un superviseur local
   distinct, avec au plus un reboot automatique sur 6 heures et un compteur
   persistant ; en cas de compteur illisible ou d’heure non fiable, inhiber le
   reboot automatique. Journaliser la cause avant un reboot ordonné. Après récidive,
   alerter pour intervention matérielle. Aucun reboot pour une panne API,
   un disque plein, une sous-tension ou une simple absence de logs distants.

Pour un gel du système entier, étudier séparément le watchdog matériel piloté
par systemd (`RuntimeWatchdogSec`) après vérification du modèle, du pilote et de
`/dev/watchdog0`. Il peut provoquer un reset et ne partage pas le quota logiciel
de reboot : le tester séparément. Une coupure d’alimentation nécessite une
alimentation secourue ou une intervention, pas un redémarrage logiciel.

## 5. Collecte et notifications

Configurer Alloy vers un Loki distant authentifié en HTTPS, puis Grafana Alerting
sur un serveur indépendant du Pi. Définir un inventaire des `device`/`site`
attendus et surveiller chaque appareil, même s’il n’a encore jamais émis de logs.
Une absence globale de données et la disparition d’un seul appareil doivent être
traitées explicitement ; une série disparue ne prouve pas un rétablissement.

Prévoir une règle d’absence de heartbeat par appareil attendu, une alerte séparée
sur les erreurs de requête Loki et une supervision externe du serveur d’alertes.
L’absence de heartbeat ne distingue pas seule panne électrique, réseau, Alloy
ou application. Ajouter les métriques hôte via un collecteur système pour le
disque et un signal de sous-tension adapté au Pi.

Configurer un contact d’astreinte, par exemple email, puis tester réception et
rétablissement. Grouper par site, appareil et type d’incident ; rappel toutes les
30 minutes pour les critiques, 4 heures pour les avertissements. Prévoir des
silences de maintenance. Un rétablissement Modbus nécessite des lectures valides,
pas seulement `modbus_reconnected`. Ne pas supprimer les alertes matérielles
utiles lorsqu’une alerte d’absence de heartbeat est active.

Ne pas supprimer de mesures `synced=FALSE` pour libérer de l’espace : la méthode
de nettoyage actuelle ne filtre pas ce champ. Corriger cette politique avant de
planifier le nettoyage. Le transport des logs reste distinct du stockage des mesures.

## 6. Ordre de réalisation et recette

1. Ajouter les indicateurs de santé et la distinction des erreurs ; tests avec
   faux clients série/HTTP, données invalides et erreurs SQLite.
2. Mettre en service Loki, Alloy distant, règles Grafana et contact d’astreinte.
3. Implémenter les notifications watchdog, l’arrêt propre sur SIGTERM, la limite
   de redémarrages et la reprise périodique après limite.
4. Tester sur un Pi pilote : débrancher/rebrancher la jauge, bloquer un worker,
   arrêter le processus, couper l’accès API puis le réseau, arrêter Alloy.
5. Vérifier : alerte reçue dans la fenêtre prévue avec la marge d’évaluation,
   redémarrage du service en cas de crash/blocage, acquisition maintenue sans API,
   livraison des mesures en attente après retour réseau et absence de boucle rapide.
6. Simuler les limites de stockage dans un environnement de test ; vérifier
   conservation des mesures non synchronisées et diagnostic exploitable.
7. Tester la saturation du quota de démarrages, la reprise par timer et le mode
   maintenance. Valider ensuite, séparément, reboot logiciel et watchdog matériel.
8. Observer le pilote pendant 48 heures avant généralisation ; conserver les
   anciennes unités/configurations pour revenir en arrière si nécessaire.

## Références techniques

- [systemd.service : Restart, WatchdogSec, TimeoutStopSec](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml)
- [systemd-system.conf : watchdog matériel](https://github.com/systemd/systemd/blob/main/man/systemd-system.conf.xml)
- [Grafana : alertes Loki](https://grafana.com/docs/grafana/latest/datasources/loki/alerting/)
- [Grafana : traitement des données manquantes](https://grafana.com/docs/grafana-cloud/alerting-and-irm/alerting/guides/missing-data/)
