"""Tests du benchmark (benchmarks/benchmark_index.py) : l'image, la reproductibilité, la forme des résultats.

    python -m pytest                    # avec tous les tests du projet
    python -m tests.test_benchmark      # rapport lisible : OK / ÉCHEC

On ne teste jamais les temps eux-mêmes (ils varient avec la charge de l'ordinateur) : seulement ce qui est
écrit, reproductible ou bien formé. La justesse des variantes mesurées est vérifiée par `mesurer`
(il s'arrête si deux variantes donnent des résultats différents).
"""

import importlib.util
import tempfile
from pathlib import Path

from .test_rapport import lancer

CHEMIN = Path(__file__).resolve().parents[1] / "benchmarks" / "benchmark_index.py"
SIGNATURE_PNG = b"\x89PNG\r\n\x1a\n"
CLES = {"n", "mots", "construction", "index", "balayage", "dichotomie", "lineaire", "retri"}


def charger_benchmark():
    """Importe le script du benchmark (le dossier benchmarks/ n'est pas un paquet)."""
    spec = importlib.util.spec_from_file_location("benchmark_index", CHEMIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = charger_benchmark()


def fausses_mesures():
    """Trois lignes de mesures inventées (une par taille), sans lancer les vraies mesures."""
    return [{"n": n, "mots": n // 2, "construction": 0.1, "index": 5.0 + i, "balayage": n / 100,
             "dichotomie": 2.0 + i, "lineaire": n / 50, "retri": n / 8} for i, n in enumerate([1_000, 10_000, 100_000])]


def test_le_graphique_est_un_fichier_png():
    """graphique() écrit une vraie image PNG non vide"""
    with tempfile.TemporaryDirectory() as dossier:
        chemin = bench.graphique(fausses_mesures(), Path(dossier))
        contenu = chemin.read_bytes()
        assert chemin.name == "benchmark_index.png", chemin.name
        assert contenu.startswith(SIGNATURE_PNG), "ce n'est pas un PNG"
        assert len(contenu) > 5_000, f"image suspecte ({len(contenu)} octets)"


def test_le_dossier_de_sortie_est_cree():
    """graphique() crée le dossier resultats s'il n'existe pas (même imbriqué)"""
    with tempfile.TemporaryDirectory() as dossier:
        cible = Path(dossier) / "a" / "resultats"
        assert not cible.exists()
        assert bench.graphique(fausses_mesures(), cible).exists()


def test_la_sortie_est_a_cote_du_script():
    """le graphique est prévu dans benchmarks/resultats, à côté du script"""
    assert bench.SORTIE == CHEMIN.parent / "resultats", bench.SORTIE


def test_le_jeu_de_donnees_est_reproductible():
    """corpus() donne les mêmes tickets à graine égale, d'autres à graine différente"""
    def resume(graine):
        tickets, requetes, debuts = bench.corpus(300, graine)
        return [(t.id, t.sujet, t.message) for t in tickets], requetes, debuts

    assert resume(42) == resume(42)
    assert resume(42) != resume(7)


def test_mesurer_renvoie_des_resultats_bien_formes():
    """mesurer() renvoie toutes les clés, avec des temps positifs (300 tickets)"""
    resultat = bench.mesurer(*bench.corpus(300))
    assert set(resultat) == CLES, set(resultat) ^ CLES
    assert resultat["n"] == 300
    assert resultat["mots"] > 0
    for cle in CLES - {"n", "mots"}:
        assert resultat[cle] > 0, cle


def test_les_tableaux_ont_une_ligne_par_taille():
    """tableaux() écrit les deux tableaux, une ligne par taille mesurée"""
    texte = bench.tableaux(fausses_mesures())
    lignes = [ligne for ligne in texte.splitlines() if ligne.startswith("| ") and "---" not in ligne]
    assert len(lignes) == 2 * (1 + 3), lignes          # 2 tableaux × (en-tête + 3 tailles)
    assert texte.count("×") == 2 * 3                   # un gain par taille et par tableau
    assert "1 000" in texte and "100 000" in texte


def test_l_interpretation_reprend_les_gains_mesures():
    """interpretation() cite les gains de la plus grande taille, pas des nombres écrits en dur"""
    lignes = fausses_mesures()
    grand = lignes[-1]                                  # 100 000 : balayage 1 000 µs, index 7 µs
    texte = bench.interpretation(lignes)
    assert f"×{grand['balayage'] / grand['index']:.0f}" in texte
    assert f"×{grand['lineaire'] / grand['dichotomie']:.0f}" in texte
    assert "O(n)" in texte and "O(log V + r)" in texte   # le lien avec la complexité théorique
    # Une ligne « jeu complet » ajoute sa propre phrase ; sans elle, rien n'est inventé.
    assert "jeu complet" not in texte
    complet = dict(grand, n=24_592, index=270.0, balayage=4_674.0, complet=True)
    assert "jeu complet" in bench.interpretation(lignes + [complet])


def test_les_resultats_sont_ecrits_dans_un_fichier_markdown():
    """ecrire_resultats() écrit index.md avec les tableaux et l'interprétation"""
    with tempfile.TemporaryDirectory() as dossier:
        cible = Path(dossier) / "resultats"              # le dossier n'existe pas encore
        chemin = bench.ecrire_resultats(fausses_mesures(), cible)
        texte = chemin.read_text(encoding="utf-8")
        assert chemin.name == "index.md", chemin.name
        assert texte.startswith("# Mesures de la recherche")
        assert bench.tableaux(fausses_mesures()) in texte
        assert bench.interpretation(fausses_mesures()) in texte


if __name__ == "__main__":
    raise SystemExit(lancer(globals(), "VÉRIFICATION DU BENCHMARK (benchmarks/benchmark_index.py)"))
