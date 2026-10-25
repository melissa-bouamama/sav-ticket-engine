# Ingestion : comment les données sont nettoyées

Le code est dans `moteur_sav/ingestion.py` et les tests dans `tests/test_ingestion.py`. Un rapport lisible s'obtient avec `python -m tests.test_ingestion`. Les chiffres de ce document viennent de l'échantillon synthétique `donnees/echantillon_tickets.jsonl` (2 500 lignes) et de la commande `python -m moteur_sav bilan`.

## Le résultat en une phrase

2 439 tickets exploitables et 61 lignes rejetées, chacune avec son numéro de ligne et un motif : 19 JSON invalides, 19 champs manquants, 16 identifiants en double et 7 dates invalides. Aucune ligne n'est perdue sans trace.

## Principe

Un rejet fait perdre un ticket, donc un client. On ne rejette que si on ne peut pas réparer sans inventer une valeur : pas d'identifiant, pas de date, pas de client, ou une ligne coupée. Dans tous les autres cas, on garde le ticket, on applique une règle simple écrite dans le code, et on le signale avec `priorite_estimee` ou `date_estimee`. Ainsi, une valeur devinée ne passe jamais pour une valeur lue.

Le chargement ne plante jamais. Chaque règle qui échoue lève une exception interne portant le motif, et la boucle de lecture la transforme en rejet avec trois champs : la ligne, le motif et le détail.

## Le chemin d'une ligne

Les vérifications se font toujours dans cet ordre, et la première qui échoue donne le motif :

1. Une ligne vide est ignorée, sans ticket ni rejet.
2. Le JSON doit être lisible et être un objet, sinon le motif est « json invalide ».
3. Les champs obligatoires doivent être présents, sinon « champ manquant ».
4. La date doit être lisible, sinon « date invalide ».
5. Le canal, la catégorie, la priorité et le statut sont corrigés ou rejetés.
6. Enfin, on cherche les doublons d'identifiant.

## Règle par règle

### Ce qui est rejeté, et pourquoi

| Cas | Pourquoi on ne répare pas |
|---|---|
| Ligne JSON coupée | Réparer reviendrait à deviner la fin de la ligne, et le statut est toujours perdu. |
| `id`, `cree_le` ou `client_id` manquant, ou ni sujet ni message | Sans identifiant on ne retrouve rien. Sans date on ne calcule pas l'échéance. Sans client on ne peut pas le joindre. |
| Date vide, illisible ou impossible, par exemple le 30 février | L'échéance dépend de la date. |
| Canal, catégorie ou statut inconnus, hors variantes ci dessous | On ne sait pas à quelle valeur officielle les rattacher. |
| Copie exacte d'un ticket déjà gardé | Elle n'apporte aucune information en plus. |

### Ce qui est réparé, et pourquoi

| Cas | Décision | Pourquoi |
|---|---|---|
| Date `14/03/2026 09h32`, `01 May 2026`, heure `13h29` | Convertie au format ISO 8601 | La conversion est exacte, rien n'est deviné. |
| Date sans heure | Heure fixée à 00 h pour P1 et P2, 12 h pour P3 et P4, et ticket marqué `date_estimee` | Une heure est nécessaire pour l'échéance. Minuit pour les urgents donne une échéance plus tôt, donc plus prudente. |
| Priorité `P2`, `"2"` ou `2.0` | Lue comme 2 | Le sens est évident. |
| Priorité `urgent` | Lue comme 1 | Le mot dit lui même le niveau. |
| Priorité absente, vide ou inférieure à 1 | Fixée à 3, avec `priorite_estimee` | Valeur par défaut neutre. |
| Priorité supérieure à 4 | Ramenée à 4, avec `priorite_estimee` | On prend la limite la plus proche. |
| Priorité illisible (`haute`, une liste, NaN) | Fixée à 4, avec `priorite_estimee` | Une priorité ne doit pas faire perdre un ticket. Le niveau le moins urgent évite qu'une valeur douteuse passe devant de vrais P1. |
| Message vide mais sujet présent | Ticket gardé | Le sujet donne le problème, et ni l'urgence, ni l'échéance, ni la répartition ne dépendent du message. |
| Canal en majuscules ou avec des espaces | Minuscules, espaces retirés | C'est la même valeur écrite autrement. |
| Canal `fax` ou `courrier` | Remplacé par `email` | Ce sont des canaux écrits, sans réponse immédiate. |
| Canal absent ou vide | Remplacé par `autre` | Le canal n'entre dans aucune décision, et un test vérifie qu'il ne change ni l'échéance ni la clé d'urgence. |
| Catégorie absente ou vide | Remplacée par `autre` | C'est la catégorie générique. |
| Catégorie `livraisons`, `sav` ou `remboursement` | Remplacée par `livraison`, `facturation` et `facturation` | Ce sont des variantes courantes. Le rattachement de `sav` et `remboursement` est un choix de conception. |
| Statut absent ou vide | Remplacé par `ouvert` | Un ticket sans statut n'est pas encore traité. |
| Même identifiant mais contenu différent | Gardé sous un nouvel identifiant (`TCK-000042-2`, puis `-3`) | Ce sont deux demandes différentes, et n'en garder qu'une ferait perdre un client. |

## Les fichiers d'origine sont protégés

Avec `charger_tickets(chemin, copie=True)`, le fichier est copié dans `donnees/copie_travail/` en lecture seule, et c'est la copie qui est lue. La fonction `empreinte` calcule une empreinte SHA256 qui permet de prouver que l'original est identique avant et après.

## Comment c'est vérifié

- Un fichier d'exemple de 13 lignes, une par cas difficile, et des tableaux de cas par règle : 30 tests dans `tests/test_ingestion.py`.
- Des cas qui cherchent à casser le code : fichier vide, ligne vide, JSON coupé, priorités `P2`, `P7` et `0`, NaN, doublon exact, doublon différent, canal absent, date impossible.
- Des défauts introduits exprès, que chacun au moins un test détecte.
- Aucun message ni identifiant client n'apparaît dans les rapports, les tests ou la démo.

## Limites

- Une priorité illisible devient P4. Si le vrai niveau était urgent, le ticket est traité plus tard que prévu, mais le drapeau `priorite_estimee` permet de les relire.
- Une heure fixée à minuit ou à midi est approximative, et le drapeau `date_estimee` le signale.
- Les lignes JSON coupées sont perdues, car les réparer reviendrait à inventer une fin de ligne.
