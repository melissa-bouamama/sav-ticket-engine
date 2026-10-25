# Moteur de tickets SAV en Python pur

*English version: [README.md](README.md)*

Outil de service après vente pour une boutique de plantes en ligne fictive : lire des tickets clients désordonnés, les classer par urgence, annuler une action, retrouver un ticket par mot, répartir le travail entre conseillers. Les algorithmes du cœur sont écrits à la main avec la seule bibliothèque standard (ni pandas, ni heapq, ni bisect). Chacun est testé contre une implémentation de référence et mesuré. Toutes les données du dépôt sont synthétiques.

| Module | Rôle |
|---|---|
| `moteur_sav/ingestion.py` | Lecture robuste des tickets et des conseillers, rejets motivés, valeurs devinées signalées |
| `moteur_sav/file_priorite.py` | Tas binaire min codé à la main : ajout et extraction en O(log n), consultation en O(1) |
| `moteur_sav/historique.py` | Annuler et rétablir : patron commande et deux piles, tout en O(1) |
| `moteur_sav/index.py` | Index inversé, recherche ET et OU, début de mot par dichotomie codée à la main |
| `moteur_sav/affectation.py` | Répartition gloutonne contre naïve, taux de délais tenus |
| `moteur_sav/pseudonymisation.py` | Masquage des emails et des téléphones, identifiant client haché avec un sel |
| `moteur_sav/cli.py` | Ligne de commande `python -m moteur_sav` avec les commandes bilan, urgents, chercher, prefixe, repartir |

## Démarrer

```bash
pip install -r requirements.txt
python -m pytest                          # 186 tests
python -m moteur_sav bilan                # 2 439 tickets exploitables, 61 rejetés
python -m moteur_sav chercher "pot cassé"
streamlit run demo/app.py                 # la démo, un onglet par question
python scripts/generer_donnees.py --n 25000 --sortie donnees/tickets.jsonl   # jeu complet synthétique
python benchmarks/benchmark_file_priorite.py && python benchmarks/benchmark_index.py   # mesures
```

## Documentation

- [docs/nettoyage.md](docs/nettoyage.md) : chaque règle de nettoyage des données, et pourquoi.
- [docs/tests.md](docs/tests.md) : ce que les 186 tests prouvent, et ce qu'ils ne prouvent pas.
- [benchmarks/resultats/index.md](benchmarks/resultats/index.md) : mesures de la recherche, avec les graphiques dans le même dossier.

## Règles du projet

- heapq et bisect sont interdits dans le paquet `moteur_sav/`. Ils restent autorisés dans les tests et les benchmarks, comme références.
- On n'affiche jamais un message brut ni un identifiant client : l'identifiant du ticket, la catégorie, la priorité, l'échéance et le sujet suffisent.
- Les tests doivent rester verts avant chaque modification.

Licence MIT : voir [LICENSE](LICENSE).
