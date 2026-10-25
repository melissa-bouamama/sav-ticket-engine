"""Mesures de la recherche : l'index inversé et la dichotomie valent-ils leur coût ?  [JUSTIFICATION DES CHOIX]

Trois comparaisons, mêmes données pour toutes les variantes (graine fixe), meilleur de 3 répétitions :

(a) recherche « ET » de deux mots : IndexInverse.rechercher contre un balayage de tous les tickets
    (la référence est favorable au balayage : les mots de chaque ticket sont calculés une fois pour toutes) ;
(b) mots qui commencent par un début donné : dichotomie sur le vocabulaire trié contre un parcours
    linéaire du vocabulaire ;
(c) même dichotomie, mais en retriant le vocabulaire à chaque appel (ce qu'on s'interdit de faire).

Chaque variante est comparée à la précédente : un résultat différent arrête la mesure.

Lancer depuis la racine du dépôt :   python benchmarks/benchmark_index.py
Écrit les tableaux et leur interprétation dans benchmarks/resultats/index.md, et le graphique dans
benchmarks/resultats/benchmark_index.png (rien n'est affiché à l'écran).
Si donnees/tickets.jsonl existe (voir scripts/generer_donnees.py), une ligne « jeu complet » est ajoutée (traitée sur une copie).
"""

from __future__ import annotations

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                                # pas de fenêtre : le graphique est seulement enregistré
import matplotlib.pyplot as plt  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from moteur_sav.index import IndexInverse, borne_inferieure, normaliser  # noqa: E402
from moteur_sav.ingestion import charger_tickets  # noqa: E402
from moteur_sav.modeles import Ticket  # noqa: E402

TAILLES = [1_000, 10_000, 100_000]
SORTIE = Path(__file__).resolve().parent / "resultats"   # le graphique est écrit ici
REQUETES_REELLES = ["pot casse", "colis livraison", "remboursement facture", "feuilles jaunissent", "carte cadeau",
                    "suivi commande", "code promo", "echange taille", "retard livraison", "double prelevement"]
DEBUTS_REELS = ["cochen", "cass", "livr", "remb", "fact", "plan", "feuil", "coli", "pot", "comm"]


def graphique(lignes, dossier: Path) -> Path:
    """Deux graphiques log-log (temps par requête selon le nombre de tickets), enregistrés dans `dossier`."""
    synthetiques = [r for r in lignes if not r.get("complet")]
    n = [r["n"] for r in synthetiques]

    figure, (gauche, droite) = plt.subplots(1, 2, figsize=(11, 4.2))

    gauche.plot(n, [r["index"] for r in synthetiques], "o-", color="#2a78d6", linewidth=2, label="index inversé")
    gauche.plot(n, [r["balayage"] for r in synthetiques], "s-", color="#eb6834", linewidth=2, label="balayage des tickets")
    gauche.set_title("Recherche « ET » de deux mots")

    droite.plot(n, [r["dichotomie"] for r in synthetiques], "o-", color="#2a78d6", linewidth=2, label="dichotomie")
    droite.plot(n, [r["lineaire"] for r in synthetiques], "s-", color="#eb6834", linewidth=2, label="parcours linéaire")
    droite.plot(n, [r["retri"] for r in synthetiques], "^-", color="#1baf7a", linewidth=2, label="dichotomie + retri")
    droite.set_title("Mots qui commencent par un début donné")

    for axe in (gauche, droite):
        axe.set_xscale("log")
        axe.set_yscale("log")
        axe.set_xlabel("nombre de tickets")
        axe.set_ylabel("temps par requête (µs)")
        axe.grid(True, alpha=0.3)
        axe.legend()

    figure.tight_layout()
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "benchmark_index.png"
    figure.savefig(chemin, dpi=130)
    return chemin


def chrono(fonction, repetitions: int = 3) -> float:
    """Meilleur temps (en secondes) de `fonction()` sur quelques répétitions."""
    meilleur = float("inf")
    for _ in range(repetitions):
        debut = time.perf_counter()
        fonction()
        meilleur = min(meilleur, time.perf_counter() - debut)
    return meilleur


def faux_ticket(i: int, sujet: str, message: str) -> Ticket:
    """Ticket minimal : seuls l'identifiant, le sujet et le message servent à l'index."""
    date = datetime(2026, 3, 14, 9, 0)
    return Ticket(id=f"T{i:07d}", cree_le=date, client_id="C", canal="email", categorie="autre", priorite=3,
                  sujet=sujet, message=message, statut="ouvert", echeance=date)


def corpus(n: int, graine: int = 42):
    """n tickets de 15 mots tirés d'un vocabulaire de n/2 mots (fréquences décroissantes, comme un vrai texte)."""
    hasard = random.Random(graine)
    lettres = "abcdefghijklmnopqrstuvwxyz"
    mots = sorted({"".join(hasard.choices(lettres, k=hasard.randint(4, 9))) for _ in range(n // 2 + n // 20)})
    mots = mots[: n // 2]
    hasard.shuffle(mots)
    poids = [1 / (rang + 1) for rang in range(len(mots))]   # loi de Zipf : quelques mots très fréquents
    tickets = []
    for i in range(n):
        tirage = hasard.choices(mots, weights=poids, k=15)
        tickets.append(faux_ticket(i, " ".join(tirage[:3]), " ".join(tirage[3:])))
    requetes = [" ".join(hasard.sample(mots[:300], 2)) for _ in range(20)]       # deux mots plutôt fréquents
    debuts = [hasard.choice(mots)[: hasard.randint(2, 4)] for _ in range(50)]
    return tickets, requetes, debuts


def mesurer(tickets, requetes, debuts) -> dict:
    """Temps moyens (en microsecondes) par requête de chaque variante, et temps de construction."""
    index = IndexInverse()
    t0 = time.perf_counter()
    for ticket in tickets:
        index.ajouter(ticket)
    construction = time.perf_counter() - t0

    docs = [(t.id, frozenset(normaliser(f"{t.sujet} {t.message}"))) for t in tickets]   # référence favorable
    vocabulaire = sorted(index._index)
    index.prefixe("a")   # prépare le vocabulaire trié (coût payé une seule fois)

    def avec_index(q):
        return index.rechercher(q)

    def avec_balayage(q):
        voulus = set(normaliser(q))
        return sorted(i for i, mots in docs if voulus <= mots)

    def dichotomie(p):
        return index.prefixe(p)

    def lineaire(p):
        return [m for m in vocabulaire if m.startswith(p)]

    def dichotomie_avec_retri(p):
        voc = sorted(index._index)
        i, resultat = borne_inferieure(voc, p), []
        while i < len(voc) and voc[i].startswith(p):
            resultat.append(voc[i])
            i += 1
        return resultat

    for q in requetes:
        assert avec_index(q) == avec_balayage(q), q
    for p in debuts:
        assert dichotomie(p) == lineaire(p) == dichotomie_avec_retri(p), p

    def moyenne(fonction, entrees):
        return chrono(lambda: [fonction(e) for e in entrees]) / len(entrees) * 1e6

    return {
        "n": len(tickets), "mots": len(vocabulaire), "construction": construction,
        "index": moyenne(avec_index, requetes), "balayage": moyenne(avec_balayage, requetes),
        "dichotomie": moyenne(dichotomie, debuts), "lineaire": moyenne(lineaire, debuts),
        "retri": moyenne(dichotomie_avec_retri, debuts[:10]),
    }


def nombre(n: int) -> str:
    """Grand nombre lisible : 100000 -> « 100 000 »."""
    return f"{n:,}".replace(",", " ")


def tableaux(lignes) -> str:
    """Les deux tableaux Markdown (temps en microsecondes par requête)."""
    a = ["| tickets | mots | construction de l'index (s) | index (µs) | balayage (µs) | gain |", "|---|---|---|---|---|---|"]
    b = ["| tickets | mots | dichotomie (µs) | parcours linéaire (µs) | gain | dichotomie + retri à chaque appel (µs) |",
         "|---|---|---|---|---|---|"]
    for r in lignes:
        nom = nombre(r["n"]) + (" (complet)" if r.get("complet") else "")
        a.append(f"| {nom} | {nombre(r['mots'])} | {r['construction']:.2f} | {r['index']:.1f} | {r['balayage']:.0f} | ×{r['balayage'] / r['index']:.0f} |")
        b.append(f"| {nom} | {nombre(r['mots'])} | {r['dichotomie']:.1f} | {r['lineaire']:.0f} | ×{r['lineaire'] / r['dichotomie']:.0f} | {r['retri']:.0f} |")
    return "### (a) Recherche « ET » de deux mots\n\n" + "\n".join(a) + "\n\n### (b) et (c) Mots qui commencent par un début donné\n\n" + "\n".join(b) + "\n"


def interpretation(lignes) -> str:
    """Ce que les mesures disent, relié à la complexité théorique."""
    grand = [r for r in lignes if not r.get("complet")][-1]      # la plus grande taille synthétique
    phrases = [
        f"À {nombre(grand['n'])} tickets, le « ET » est ×{grand['balayage'] / grand['index']:.0f} plus rapide"
        " que le balayage : le balayage relit tous les tickets, soit O(n), alors que l'index ne parcourt"
        " que le plus petit ensemble de la requête.",
        f"Le début de mot est ×{grand['lineaire'] / grand['dichotomie']:.0f} plus rapide que le parcours du"
        " vocabulaire : O(log V + r) contre O(V), où V est la taille du vocabulaire et r le nombre de mots trouvés.",
        f"Retrier le vocabulaire à chaque appel coûte {grand['retri']:.0f} µs contre {grand['dichotomie']:.1f} µs :"
        " c'est un O(V log V) payé à chaque requête au lieu d'une fois par changement de l'index.",
    ]
    complets = [r for r in lignes if r.get("complet")]
    if complets:
        complet = complets[0]
        phrases.append(
            f"Sur les jeu complet ({nombre(complet['n'])} tickets), le gain du « ET » tombe à"
            f" ×{complet['balayage'] / complet['index']:.0f} : les requêtes de la démo sont fréquentes et renvoient"
            " des centaines de tickets ; construire et trier cette liste reste à faire, index ou pas."
        )
    return "\n\n".join(phrases)


def ecrire_resultats(lignes, dossier: Path) -> Path:
    """Écrit les tableaux et l'interprétation dans `dossier`/index.md et renvoie le chemin."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "index.md"
    chemin.write_text(
        "# Mesures de la recherche (index)\n\n"
        f"Produit par `python benchmarks/benchmark_index.py` le {datetime.now():%d/%m/%Y}. Temps en"
        " microsecondes par requête, meilleur de 3 répétitions, mêmes données pour toutes les variantes"
        " (graine 42).\n\n"
        + tableaux(lignes)
        + "\n### Interprétation\n\n" + interpretation(lignes) + "\n",
        encoding="utf-8",
    )
    return chemin


def main() -> None:
    lignes = []
    for n in TAILLES:
        print(f"mesure sur {n:,} tickets...".replace(",", " "), flush=True)
        lignes.append(mesurer(*corpus(n)))
    complet = RACINE / "donnees" / "tickets.jsonl"
    if complet.exists():
        print("mesure sur les jeu complet...", flush=True)
        tickets, _ = charger_tickets(complet, copie=True)
        resultat = mesurer(tickets, REQUETES_REELLES, DEBUTS_REELS)
        resultat["complet"] = True
        lignes.append(resultat)
    print("\n" + tableaux(lignes))
    print(f"Écrit : {ecrire_resultats(lignes, SORTIE)}")
    print(f"Écrit : {graphique(lignes, SORTIE)}")


if __name__ == "__main__":
    main()
