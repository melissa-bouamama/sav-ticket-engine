"""Benchmark reproductible de la file de priorité : tas maison, `heapq`, liste retriée.

Chaque comparaison suit la même méthode :
1. même jeu de données pour toutes les variantes (graine fixe) ;
2. plusieurs tailles : 1 000, 10 000, 100 000 ;
3. le meilleur de plusieurs répétitions (time.perf_counter) ;
4. un tableau et un graphique log-log dans benchmarks/resultats/.

Lancer depuis la racine du dépôt : python benchmarks/benchmark_file_priorite.py
(la comparaison de l'index inversé est dans benchmark_index.py)
"""

from __future__ import annotations

import heapq
import random
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from moteur_sav.file_priorite import FilePriorite  # noqa: E402  (après sys.path.insert)

TAILLES = [1_000, 10_000, 100_000]

#: Au-delà, la liste retriée prendrait plusieurs minutes : on ne la mesure pas.
LIMITE_LISTE = 10_000


def chrono(fonction, repetitions: int = 3) -> float:
    """Meilleur temps (en secondes) de `fonction()` sur quelques répétitions."""
    meilleur = float("inf")
    for _ in range(repetitions):
        debut = time.perf_counter()
        fonction()
        meilleur = min(meilleur, time.perf_counter() - debut)
    return meilleur


def avec_heapq(cles: list) -> None:
    """Référence : n ajouts puis n extractions avec heapq."""
    tas: list = []
    for i, c in enumerate(cles):
        heapq.heappush(tas, (c, i))
    while tas:
        heapq.heappop(tas)


def avec_file_maison(cles: list) -> None:
    """La même chose avec notre FilePriorite."""
    f = FilePriorite()
    for c in cles:
        f.ajouter(c, c)
    while not f.est_vide():
        f.extraire()


def avec_liste_retriee(cles: list) -> None:
    """Ajout puis tri complet à chaque insertion (très lent au-delà de 10 000)."""
    liste: list = []
    for i, c in enumerate(cles):
        liste.append((c, i))
        liste.sort(reverse=True)  # le plus petit à la FIN : pop() en O(1)
    while liste:
        liste.pop()


def main() -> None:
    rng = random.Random(42)
    variantes = {"heapq": avec_heapq, "tas maison": avec_file_maison,
                 "liste retriée": avec_liste_retriee}
    resultats: dict[str, dict[int, float]] = {nom: {} for nom in variantes}

    print("| n | heapq (s) | tas maison (s) | liste retriée (s) |")
    print("|---|---|---|---|")
    for n in TAILLES:
        cles = [rng.randint(0, 10**6) for _ in range(n)]  # mêmes clés pour toutes
        colonnes = [f"{n:,}".replace(",", " ")]
        for nom, fonction in variantes.items():
            if nom == "liste retriée" and n > LIMITE_LISTE:
                colonnes.append("non mesuré (trop lent)")
                continue
            temps = chrono(lambda: fonction(cles))
            resultats[nom][n] = temps
            colonnes.append(f"{temps:.4f}")
        print("| " + " | ".join(colonnes) + " |")

    tracer(resultats)


def tracer(resultats: dict[str, dict[int, float]]) -> None:
    """Graphique log-log dans benchmarks/resultats/ (seulement si matplotlib est installé)."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # écrit un fichier image, sans ouvrir de fenêtre
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib absent : pas de graphique.")
        return

    # Trois couleurs distinctes, dans un ordre fixe, lisibles par les daltoniens.
    couleurs = {"tas maison": "#2a78d6", "heapq": "#eb6834", "liste retriée": "#1baf7a"}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for nom, mesures in resultats.items():
        tailles = list(mesures)
        temps = [mesures[n] for n in tailles]
        ax.plot(tailles, temps, color=couleurs[nom], linewidth=2, marker="o",
                markersize=8, label=nom)
        # Étiquette directe au bout de chaque courbe, en plus de la légende.
        ax.annotate(nom, (tailles[-1], temps[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", color="#333333")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("n : nombre d'éléments (n ajouts puis n extractions)")
    ax.set_ylabel("temps en secondes (meilleur de 3)")
    ax.set_title("File de priorité : tas maison, heapq et une liste retriée")
    ax.grid(True, which="major", color="#dddddd", linewidth=0.8)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    chemin = RACINE / "benchmarks" / "resultats" / "file_priorite.png"
    fig.savefig(chemin, dpi=150)
    print("Graphique :", chemin)


if __name__ == "__main__":
    main()
