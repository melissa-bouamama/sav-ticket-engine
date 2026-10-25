# Mesures de la recherche (index)

Produit par `python benchmarks/benchmark_index.py` le 25/10/2026. Temps en microsecondes par requête, meilleur de 3 répétitions, mêmes données pour toutes les variantes (graine 42).

### (a) Recherche « ET » de deux mots

| tickets | mots | construction de l'index (s) | index (µs) | balayage (µs) | gain |
|---|---|---|---|---|---|
| 1 000 | 500 | 0.03 | 6.7 | 60 | ×9 |
| 10 000 | 4 966 | 0.30 | 14.8 | 735 | ×50 |
| 100 000 | 49 197 | 2.97 | 49.6 | 13830 | ×279 |

### (b) et (c) Mots qui commencent par un début donné

| tickets | mots | dichotomie (µs) | parcours linéaire (µs) | gain | dichotomie + retri à chaque appel (µs) |
|---|---|---|---|---|---|
| 1 000 | 500 | 3.0 | 17 | ×6 | 57 |
| 10 000 | 4 966 | 2.8 | 127 | ×45 | 898 |
| 100 000 | 49 197 | 6.5 | 1154 | ×177 | 13961 |

### Interprétation

À 100 000 tickets, le « ET » est ×279 plus rapide que le balayage : le balayage relit tous les tickets, soit O(n), alors que l'index ne parcourt que le plus petit ensemble de la requête.

Le début de mot est ×177 plus rapide que le parcours du vocabulaire : O(log V + r) contre O(V), où V est la taille du vocabulaire et r le nombre de mots trouvés.

Retrier le vocabulaire à chaque appel coûte 13961 µs contre 6.5 µs : c'est un O(V log V) payé à chaque requête au lieu d'une fois par changement de l'index.
