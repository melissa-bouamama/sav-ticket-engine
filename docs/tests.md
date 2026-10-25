# Tests : ce qu'ils prouvent

Une seule commande suffit : `python -m pytest`. Elle lance 186 tests en quelques secondes, sans en ignorer aucun. Seul le test de l'application Streamlit ne tourne que si Streamlit est installé. Cinq fichiers ont aussi un rapport lisible qui affiche OK ou ÉCHEC pour chaque vérification : `python -m tests.test_ingestion`, et de la même façon `test_index`, `test_modeles`, `test_benchmark` et `test_demo`.

## Méthode

1. Le cas normal d'abord, puis les cas difficiles : fichier vide, ligne vide, JSON coupé, priorité `P2` ou `P7`, doublon, file vide, requête vide, conseiller sans capacité, ticket absent.
2. Une comparaison avec une référence simple. Quand le code est malin, on le compare à une version naïve dont on est sûr : le tas contre heapq, la dichotomie contre bisect, l'index contre un parcours de tous les tickets. Ces deux modules sont interdits dans le paquet `moteur_sav/`, car le but est de les recoder, mais ils sont permis dans les tests.
3. Des séquences aléatoires avec une graine fixe (42). Elles sont reproductibles et essaient des combinaisons qu'on n'aurait pas pensé à écrire.
4. Des tests qui cherchent à casser le code. Des défauts introduits exprès, comme un décalage dans la dichotomie, un ET devenu OU, des accents non retirés, une réindexation sans retrait ou un import interdit, sont chacun détectés par au moins un test.
5. Des règles de conception contrôlées par le code lui même : une analyse de l'arbre syntaxique vérifie que le paquet n'importe ni heapq ni bisect.
6. Le jeu complet quand il est là. Les tests utilisent `donnees/tickets.jsonl` s'il existe (voir `scripts/generer_donnees.py`), sinon l'échantillon synthétique versionné. De petits fichiers d'exemple de 13 lignes, une par cas difficile, servent partout.

## Ce que chaque fichier prouve

| Fichier | Tests | Ce qui est prouvé |
|---|---|---|
| `test_modeles.py` | 14 | Les délais (P1 4 h, P2 24 h, P3 72 h, P4 168 h), l'échéance, la clé d'urgence (échéance, puis priorité, puis date) et les compétences d'un conseiller. |
| `test_ingestion.py` | 30 | Chaque règle de nettoyage, l'ordre des vérifications, les rejets avec le bon numéro de ligne, la lecture des conseillers et la copie protégée. |
| `test_file_priorite.py` | 11 | File vide (erreur `IndexError`), ordre croissant, `consulter` ne retire rien, premier arrivé premier servi à priorité égale, éléments non comparables, et conformité à heapq sur 10 000 opérations aléatoires. |
| `test_historique.py` | 25 | Les trois actions et leur inverse, l'échéance recalculée, une nouvelle action qui vide la pile de rétablissement, une action qui échoue non enregistrée, et une séquence aléatoire qui reste cohérente. |
| `test_index.py` | 26 | La normalisation, la dichotomie (contre bisect sur 2 000 cas), le ET, le OU, le début de mot, les requêtes vides, la réindexation, et le vocabulaire trié refait seulement quand l'index change. |
| `test_affectation.py` | 23 | Lot vide, aucun conseiller, capacité nulle. Chaque ticket est affecté une seule fois et aucune capacité n'est dépassée. Le conseiller le moins occupé est choisi, et le taux de délais tenus est vérifié à la main. |
| `test_pseudonymisation.py` | 17 | Emails et téléphones masqués (six formes), numéros de commande intacts, pseudonyme stable et dépendant du sel, copie sans modifier l'original, sel vide refusé. |
| `test_cli.py` | 7 | Les commandes bilan, urgents, chercher, prefixe et repartir, le code de sortie en cas d'erreur, et l'absence de message brut en sortie. |
| `test_benchmark.py` et `test_mesure_tas.py` | 8 et 3 | Les mesures sont bien formées et reproductibles, et l'interprétation est tirée des chiffres. |
| `test_demo.py` et `test_demo_repartition.py` | 18 et 4 | Les calculs de la démo, et la confidentialité : aucune sortie ne contient un message ni un identifiant client. |

## Les preuves les plus fortes

- File de priorité : le tas donne exactement les mêmes extractions que heapq sur 10 000 opérations aléatoires.
- Historique : après n'importe quelle suite aléatoire d'actions, d'annulations et de rétablissements, l'état reste cohérent.
- Index : mêmes résultats qu'un parcours naïf sur 500 requêtes, et aussi après 300 remplacements de tickets.
- Répartition : sur un lot aléatoire, chaque ticket apparaît une fois et aucune capacité n'est dépassée.
- Confidentialité : un rejet ne contient jamais le message du client, et la démo comme la ligne de commande n'affichent que l'identifiant, la catégorie, la priorité, l'échéance et le sujet.

## Ce que les tests ne prouvent pas

- Les temps de calcul. Ils varient selon la machine : les tests vérifient que les mesures sont bien formées et que les variantes donnent le même résultat, et la vitesse est mesurée par les scripts de `benchmarks/`.
- L'aspect de la démo. Streamlit est testé par ses calculs et par un parcours automatique de la page, pas à l'œil.
- Les noms propres dans un message libre. La pseudonymisation masque les emails et les téléphones, pas les noms.
