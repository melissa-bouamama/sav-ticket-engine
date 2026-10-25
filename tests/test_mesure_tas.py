"""Tests de la mesure en direct du tas (demo/calculs.py)."""

from demo import calculs as c


def test_mesurer_tas_forme_des_resultats():
    lignes = c.mesurer_tas(tailles=(100, 1_000), repetitions=1)
    assert len(lignes) == 6  # 2 tailles × 3 méthodes (liste mesurée sous la limite)
    assert {l["methode"] for l in lignes} == {"tas maison", "heapq", "liste retriée"}
    assert all(l["temps_ms"] >= 0 for l in lignes)


def test_liste_retriee_pas_mesuree_au_dela_de_la_limite():
    lignes = c.mesurer_tas(tailles=(20_000,), repetitions=1)
    assert {l["methode"] for l in lignes} == {"tas maison", "heapq"}


def test_facteurs_croissance():
    lignes = [{"n": 10, "methode": "tas maison", "temps_ms": 1.0},
              {"n": 100, "methode": "tas maison", "temps_ms": 13.0}]
    assert c.facteurs_croissance(lignes) == [{"méthode": "tas maison", "taille": "10 → 100",
                                              "n multiplié par": 10, "temps multiplié par": 13.0}]
