"""Tests de la répartition : répartition gloutonne, répartition naïve, taux de délais tenus."""

import random
from datetime import datetime

import pytest

from moteur_sav.affectation import NON_AFFECTES, affecter, affecter_naif, taux_sla
from moteur_sav.modeles import CATEGORIES, Agent

from .fabrique import fabriquer_ticket

DEBUT = datetime(2026, 3, 14, 8, 0)


def agent(agent_id, competences=("livraison",), capacite=2):
    return Agent(agent_id, "Test", frozenset(competences), capacite)


def ticket(id, cree_le="2026-03-14T07:00:00", priorite=3, categorie="livraison"):
    return fabriquer_ticket(id=id, cree_le=cree_le, priorite=priorite, categorie=categorie)


def verifier_partition(affectations, tickets, agents):
    """Chaque ticket apparaît exactement une fois, et aucune capacité n'est dépassée."""
    tous = [i for ids in affectations.values() for i in ids]
    assert sorted(tous) == sorted(t.id for t in tickets)
    assert set(affectations) == {a.agent_id for a in agents} | {NON_AFFECTES}
    categories = {t.id: t.categorie for t in tickets}
    for a in agents:
        assert len(affectations[a.agent_id]) <= a.capacite_jour
        assert all(a.sait_traiter(categories[i]) for i in affectations[a.agent_id])

# ------------------------------------------------------------------ cas limites communs

@pytest.mark.parametrize("repartir", [affecter, affecter_naif])
def test_aucun_ticket(repartir):
    agents = [agent("AG-01"), agent("AG-02")]
    assert repartir([], agents) == {"AG-01": [], "AG-02": [], NON_AFFECTES: []}


@pytest.mark.parametrize("repartir", [affecter, affecter_naif])
def test_aucun_conseiller(repartir):
    assert repartir([ticket("T1")], []) == {NON_AFFECTES: ["T1"]}


@pytest.mark.parametrize("repartir", [affecter, affecter_naif])
def test_aucun_conseiller_competent(repartir):
    aff = repartir([ticket("T1", categorie="facturation")], [agent("AG-01")])
    assert aff == {"AG-01": [], NON_AFFECTES: ["T1"]}


@pytest.mark.parametrize("repartir", [affecter, affecter_naif])
def test_conseiller_sans_capacite(repartir):
    # Capacité 0 : jamais choisi, et surtout pas de division par zéro.
    agents = [agent("AG-00", capacite=0), agent("AG-01", capacite=1)]
    aff = repartir([ticket("T1"), ticket("T2")], agents)
    assert aff["AG-00"] == [] and aff["AG-01"] == ["T1"] and aff[NON_AFFECTES] == ["T2"]


@pytest.mark.parametrize("repartir", [affecter, affecter_naif])
def test_partition_et_capacites_sur_lot_aleatoire(repartir):
    rng = random.Random(3)
    categories = sorted(CATEGORIES)
    agents = [agent(f"AG-{i:02d}", rng.sample(categories, rng.randint(1, 3)), rng.randint(0, 15))
              for i in range(8)]
    tickets = [ticket(f"T{i:03d}", cree_le=f"2026-03-{rng.randint(10, 14)}T{rng.randint(0, 23):02d}:00:00",
                      priorite=rng.randint(1, 4), categorie=rng.choice(categories))
               for i in range(150)]
    verifier_partition(repartir(tickets, agents), tickets, agents)

# ------------------------------------------------------------------ répartition gloutonne

def test_glouton_du_plus_urgent_au_moins_urgent():
    t_p4 = ticket("P4", priorite=4)
    t_p1 = ticket("P1", priorite=1)
    t_p3 = ticket("P3", priorite=3)
    aff = affecter([t_p4, t_p1, t_p3], [agent("AG-01", capacite=5)])
    assert aff["AG-01"] == ["P1", "P3", "P4"]


def test_glouton_choisit_le_taux_d_occupation_le_plus_faible():
    # AG-01 peut en traiter 4, AG-02 seulement 2.
    agents = [agent("AG-01", capacite=4), agent("AG-02", capacite=2)]
    tickets = [ticket(f"T{i}", priorite=1 + i) for i in range(3)]
    aff = affecter(tickets, agents)
    # T0 : égalité 0/4 et 0/2 -> plus petit id, AG-01.
    # T1 : AG-01 à 1/4, AG-02 à 0/2 -> AG-02.
    # T2 : AG-01 à 1/4 = 25 %, AG-02 à 1/2 = 50 % -> AG-01, bien qu'il ait déjà plus de tickets.
    assert aff["AG-01"] == ["T0", "T2"] and aff["AG-02"] == ["T1"]


def test_glouton_egalite_plus_petit_identifiant_pas_ordre_de_la_liste():
    agents = [agent("AG-09"), agent("AG-01")]  # liste volontairement dans le désordre
    assert affecter([ticket("T1")], agents)["AG-01"] == ["T1"]


def test_glouton_respecte_les_competences():
    agents = [agent("AG-01", ["livraison"], 5), agent("AG-02", ["retour"], 5)]
    tickets = [ticket("L", categorie="livraison"), ticket("R", categorie="retour")]
    aff = affecter(tickets, agents)
    assert aff["AG-01"] == ["L"] and aff["AG-02"] == ["R"]

# ------------------------------------------------------------------ répartition naïve

def test_naif_ordre_de_creation():
    tickets = [ticket("T3", cree_le="2026-03-14T03:00:00"), ticket("T1", cree_le="2026-03-14T01:00:00"),
               ticket("T2", cree_le="2026-03-14T02:00:00", priorite=1)]
    assert affecter_naif(tickets, [agent("AG-01", capacite=5)])["AG-01"] == ["T1", "T2", "T3"]


def test_naif_remplit_le_premier_conseiller_d_abord():
    agents = [agent("AG-01", capacite=3), agent("AG-02", capacite=3)]
    tickets = [ticket(f"T{i}", cree_le=f"2026-03-14T0{i}:00:00") for i in range(4)]
    aff = affecter_naif(tickets, agents)
    assert aff["AG-01"] == ["T0", "T1", "T2"] and aff["AG-02"] == ["T3"]


def test_naif_suit_l_ordre_de_la_liste_pas_les_identifiants():
    agents = [agent("AG-09"), agent("AG-01")]
    assert affecter_naif([ticket("T1")], agents)["AG-09"] == ["T1"]

# ------------------------------------------------------------------ taux de délais tenus

def test_taux_calcule_a_la_main():
    # Le petit cas de la cellule 5.a : 4 tickets tenus sur 5.
    tickets = [ticket("T1", "2026-03-14T09:00:00", 3), ticket("T2", "2026-03-14T08:00:00", 1),
               ticket("T3", "2026-03-14T10:00:00", 2), ticket("T4", "2026-03-14T11:00:00", 4),
               ticket("T5", "2026-03-14T12:00:00", 4)]
    aff = {"AG-01": ["T2", "T1"], "AG-03": ["T3", "T4"], NON_AFFECTES: ["T5"]}
    assert taux_sla(aff, tickets, DEBUT) == pytest.approx(0.8)


def test_taux_lot_vide():
    assert taux_sla({}, [], DEBUT) == 0.0


def test_taux_non_affectes_comptent_comme_rates():
    tickets = [ticket("T1"), ticket("T2")]
    assert taux_sla({"AG-01": ["T1"], NON_AFFECTES: ["T2"]}, tickets, DEBUT) == 0.5
    assert taux_sla({NON_AFFECTES: ["T1", "T2"]}, tickets, DEBUT) == 0.0


def test_taux_fini_pile_a_l_echeance_est_tenu():
    # P1 créée à 4 h 20 : échéance à 8 h 20, et le 1er ticket finit à 8 h 20.
    t = ticket("T1", cree_le="2026-03-14T04:20:00", priorite=1)
    assert taux_sla({"AG-01": ["T1"]}, [t], DEBUT) == 1.0
    # Une minute de traitement en plus, et il est raté.
    assert taux_sla({"AG-01": ["T1"]}, [t], DEBUT, duree_minutes=21) == 0.0


def test_taux_la_position_dans_la_liste_compte():
    # Échéance à 8 h 30 : tenu en 1re position (8 h 20), raté en 2e (8 h 40).
    urgent = ticket("U", cree_le="2026-03-14T04:30:00", priorite=1)
    autre = ticket("A", cree_le="2026-03-13T09:00:00", priorite=3)
    assert taux_sla({"AG-01": ["U", "A"]}, [urgent, autre], DEBUT) == 1.0
    assert taux_sla({"AG-01": ["A", "U"]}, [urgent, autre], DEBUT) == 0.5

# ------------------------------------------------------------------ la comparaison

def test_glouton_tient_plus_de_delais_que_naif():
    # Le naïf sert d'abord le plus ancien et met l'urgent en 2e position chez AG-01.
    # Le glouton sert l'urgent d'abord et répartit sur les deux conseillers.
    urgent = ticket("U", cree_le="2026-03-14T04:30:00", priorite=1)   # échéance 8 h 30
    ancien = ticket("A", cree_le="2026-03-13T09:00:00", priorite=3)   # échéance 16/03
    agents = [agent("AG-01"), agent("AG-02")]
    lot = [ancien, urgent]
    assert taux_sla(affecter_naif(lot, agents), lot, DEBUT) == 0.5
    assert taux_sla(affecter(lot, agents), lot, DEBUT) == 1.0
