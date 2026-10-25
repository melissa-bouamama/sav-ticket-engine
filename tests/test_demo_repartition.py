"""Tests des calculs de l'onglet 5 de la démo (demo/calculs.py)."""

from datetime import datetime

from demo import calculs as c
from moteur_sav.modeles import Agent

from .fabrique import fabriquer_ticket

DEBUT = datetime(2026, 3, 14, 8, 0)


def test_perdus_d_avance():
    perdu = fabriquer_ticket(id="P", cree_le="2026-03-14T03:00:00", priorite=1)      # échéance 7 h
    sauvable = fabriquer_ticket(id="S", cree_le="2026-03-14T04:30:00", priorite=1)   # échéance 8 h 30
    assert c.perdus_d_avance([perdu, sauvable], DEBUT) == {"P"}


def test_details_repartition_maximum_et_charges():
    perdu = fabriquer_ticket(id="P", cree_le="2026-03-14T03:00:00", priorite=1)
    sauvable = fabriquer_ticket(id="S", cree_le="2026-03-14T04:30:00", priorite=1)
    agents = [Agent("AG-01", "Test", frozenset({"livraison"}), 2)]
    d = c.details_repartition([perdu, sauvable], agents, DEBUT)
    assert d["perdus"] == 1 and d["maximum"] == 0.5
    assert sum(l["tickets"] for l in d["charges"] if l["répartition"] == "gloutonne") == 2


def test_structures_de_chaque_etape_completes():
    assert set(c.STRUCTURES) == {1, 2, 3, 4, 5}
    for lignes in c.STRUCTURES.values():
        assert len(lignes) >= 5
        for ligne in lignes:
            assert set(ligne) == {"structure", "type Python", "où", "pourquoi"}
            assert all(ligne.values())  # aucune case vide


def test_exemple_a_la_main():
    lignes = c.exemple_a_la_main()
    tenus = {(l["répartition"], l["ticket"]): l["tenu"] for l in lignes}
    assert tenus[("gloutonne", "U")] == "oui" and tenus[("gloutonne", "A")] == "oui"
    assert tenus[("naïve", "U")] == "non" and tenus[("naïve", "A")] == "oui"
