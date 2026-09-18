# Requêtes d’alertes Grafana / Loki

Créer chaque règle pour **chaque appareil de l’inventaire**, en remplaçant
`TKS-111` et `default`. Ces valeurs sont les valeurs par défaut du dépôt et ne
confirment pas l’identité du matériel déployé. Requête instantanée, évaluation
toutes les minutes, condition Grafana « supérieur à » au seuil indiqué.
Ajouter les labels statiques `device`, `site`, `severity` à chaque règle.

## Heartbeat absent : critique, seuil 0, sans délai supplémentaire

```logql
absent_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="heartbeat" [5m]) or vector(0)
```

Cette règle détecte aussi un appareil jamais vu. Ne pas la remplacer par une
agrégation des seuls appareils présents. Elle signale une perte de visibilité,
qui peut provenir du Pi, du réseau ou d’Alloy.

## Erreurs Modbus : avertissement, seuil 2

```logql
sum(count_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="modbus_failure" [5m])) or vector(0)
```

## Crash, seuil fatal ou worker bloqué : critique, seuil 0

```logql
sum(count_over_time({job="edge-app",device="TKS-111",site="default"} | json | event=~"modbus_fatal|application_crash|worker_stalled" [5m])) or vector(0)
```

## Démarrages répétés : critique, seuil 2

```logql
sum(count_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="application_start" [15m])) or vector(0)
```

## Échecs HTTP : avertissement, seuil 4

```logql
sum(count_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="sync_failure" [10m])) or vector(0)
```

## Erreur SQLite : critique, seuil 0

```logql
sum(count_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="database_failure" [5m])) or vector(0)
```

## Lectures valides trop anciennes : critique, seuil 180

```logql
max(last_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="heartbeat" | unwrap read_age_seconds | __error__="" [2m]))
```

Pour les insertions, dupliquer avec `insert_age_seconds` et un seuil de 600.
Ces âges repartent au démarrage ; la règle de démarrages répétés couvre les resets
fréquents. Ils ne prouvent pas une continuité de santé entre deux processus.

## Backlog : avertissement 1800, critique 21600

```logql
max(last_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="storage_health" | unwrap oldest_pending_age_seconds | __error__="" [3m]))
```

## Disque : avertissement 80, critique 90, délai 5 minutes

```logql
max(last_over_time({job="edge-app",device="TKS-111",site="default"} | json | event="storage_health" | unwrap disk_used_percent | __error__="" [3m]))
```

Cette mesure concerne le volume de la base SQLite. Ajouter une supervision hôte
si les logs sont sur un autre volume. Si le worker HTTP est bloqué, ces métriques
ne sont plus rafraîchies.

## CH341 : avertissement, seuil 0

```logql
sum(count_over_time({job="edge-kernel",device="TKS-111",site="default"} |~ "(?i)ch341.*urb stopped" [5m])) or vector(0)
```

## Données absentes et résolution

Les compteurs utilisent `or vector(0)` pour représenter une fenêtre sans événement.
La fin d’une alerte de compteur indique seulement la fin de sa fenêtre ; valider
le rétablissement grâce aux âges des lectures et insertions. Configurer les règles
de métriques sans données sur **Alerting**, et les erreurs de datasource sur
**Error**, routées vers l’astreinte. Ne pas ajouter de zéro aux métriques d’âge ou
de disque : cela masquerait une absence de télémétrie.

Référence : [fonctions métriques LogQL](https://grafana.com/docs/loki/latest/query/metric_queries/).
