"""Tests de l'historique : actions réversibles et historique à deux piles."""

import random
from dataclasses import replace
from datetime import datetime

import pytest

from moteur_sav.historique import (
    Action,
    AffecterTicket,
    ChangerPriorite,
    ChangerStatut,
    Historique,
)

from .fabrique import fabriquer_ticket


def photo(ticket, affectations):
    """Copie indépendante de l'état, pour comparer avant et après."""
    return replace(ticket), {agent: list(ids) for agent, ids in affectations.items()}


class EchoueAAppliquer(Action):
    def appliquer(self):
        raise RuntimeError("échec volontaire")

    def inverser(self):
        pass


class EchoueAInverser(Action):
    def appliquer(self):
        pass

    def inverser(self):
        raise RuntimeError("échec volontaire")

# ------------------------------------------------------------------ ChangerStatut

def test_changer_statut():
    t = fabriquer_ticket(statut="ouvert")
    action = ChangerStatut(t, "resolu")
    action.appliquer()
    assert t.statut == "resolu"
    action.inverser()
    assert t.statut == "ouvert"
    with pytest.raises(ValueError):
        ChangerStatut(t, "ferme")

# ------------------------------------------------------------------ ChangerPriorite

def test_changer_priorite_recalcule_l_echeance():
    t = fabriquer_ticket(cree_le="2026-03-14T09:00:00", priorite=3)
    assert t.echeance == datetime(2026, 3, 17, 9, 0)
    action = ChangerPriorite(t, 1)
    action.appliquer()
    assert (t.priorite, t.echeance) == (1, datetime(2026, 3, 14, 13, 0))
    action.inverser()
    assert (t.priorite, t.echeance) == (3, datetime(2026, 3, 17, 9, 0))


def test_changer_priorite_restaure_le_drapeau_estimee():
    t = replace(fabriquer_ticket(priorite=3), priorite_estimee=True)
    avant = replace(t)
    action = ChangerPriorite(t, 2)
    action.appliquer()
    assert t.priorite_estimee is False  # fixée par un conseiller
    action.inverser()
    assert t == avant  # retour EXACT, drapeau compris


@pytest.mark.parametrize("mauvaise", [0, 5, -1, True, False, "1", None, 2.0])
def test_changer_priorite_valeur_invalide(mauvaise):
    with pytest.raises(ValueError):
        ChangerPriorite(fabriquer_ticket(), mauvaise)


def test_inverser_avant_appliquer():
    with pytest.raises(AssertionError):
        ChangerPriorite(fabriquer_ticket(), 1).inverser()

# ------------------------------------------------------------------ AffecterTicket

def test_affecter_dans_une_liste_existante():
    affectations = {"AG-01": ["TCK-A"]}
    action = AffecterTicket(affectations, "TCK-B", "AG-01")
    action.appliquer()
    assert affectations == {"AG-01": ["TCK-A", "TCK-B"]}
    action.inverser()
    assert affectations == {"AG-01": ["TCK-A"]}


def test_affecter_cree_puis_supprime_la_liste():
    affectations = {}
    action = AffecterTicket(affectations, "TCK-A", "AG-02")
    action.appliquer()
    assert affectations == {"AG-02": ["TCK-A"]}
    action.inverser()
    assert affectations == {}  # la liste créée par appliquer disparaît


def test_affecter_garde_une_liste_vide_preexistante():
    affectations = {"AG-01": []}
    action = AffecterTicket(affectations, "TCK-A", "AG-01")
    action.appliquer()
    action.inverser()
    assert affectations == {"AG-01": []}  # elle existait avant : on la garde


def test_affecter_liste_modifiee_hors_historique():
    affectations = {}
    action = AffecterTicket(affectations, "TCK-A", "AG-01")
    action.appliquer()
    affectations["AG-01"].append("TCK-Z")  # modification extérieure
    action.inverser()
    assert affectations == {"AG-01": ["TCK-Z"]}


def test_affecter_inverser_un_ticket_absent():
    affectations = {}
    action = AffecterTicket(affectations, "TCK-A", "AG-01")
    action.appliquer()
    affectations["AG-01"].clear()
    with pytest.raises(ValueError):
        action.inverser()

# ------------------------------------------------------------------ Historique

def test_historique_vide():
    h = Historique()
    assert h.annuler() is False
    assert h.retablir() is False
    assert h.journal() == []


def test_action_annulation_retablissement():
    t = fabriquer_ticket(statut="ouvert")
    h = Historique()
    h.executer(ChangerStatut(t, "en_cours"))
    assert t.statut == "en_cours" and h.journal() == [f"{t.id} : statut -> en_cours"]
    assert h.annuler() is True
    assert t.statut == "ouvert" and h.journal() == []
    assert h.retablir() is True
    assert t.statut == "en_cours" and len(h.journal()) == 1
    assert h.retablir() is False  # plus rien à rétablir


def test_nouvelle_action_vide_la_pile_retablir():
    t = fabriquer_ticket(statut="ouvert")
    h = Historique()
    h.executer(ChangerStatut(t, "en_cours"))
    h.annuler()
    h.executer(ChangerStatut(t, "resolu"))
    assert h.retablir() is False  # l'ancien futur est caduc
    assert t.statut == "resolu"


def test_plusieurs_annulations_puis_retablissements():
    t = fabriquer_ticket(priorite=3, statut="ouvert")
    affectations = {}
    h = Historique()
    depart = photo(t, affectations)
    actions = [ChangerPriorite(t, 1), AffecterTicket(affectations, t.id, "AG-01"),
               ChangerStatut(t, "en_cours"), ChangerPriorite(t, 2)]
    etats = [depart]
    for action in actions:
        h.executer(action)
        etats.append(photo(t, affectations))
    # On annule tout : chaque état intermédiaire est retrouvé, dans l'ordre inverse.
    for attendu in reversed(etats[:-1]):
        assert h.annuler()
        assert photo(t, affectations) == attendu
    assert h.annuler() is False
    # On rétablit tout : on repasse par les mêmes états, dans l'ordre.
    for attendu in etats[1:]:
        assert h.retablir()
        assert photo(t, affectations) == attendu
    assert len(h.journal()) == 4


def test_journal_du_plus_ancien_au_plus_recent():
    t = fabriquer_ticket(id="TCK-9")
    h = Historique()
    h.executer(ChangerPriorite(t, 1))
    h.executer(ChangerStatut(t, "resolu"))
    assert h.journal() == ["TCK-9 : priorité -> P1", "TCK-9 : statut -> resolu"]


def test_action_qui_echoue_n_est_pas_enregistree():
    h = Historique()
    with pytest.raises(RuntimeError):
        h.executer(EchoueAAppliquer())
    assert h.journal() == [] and h.annuler() is False


def test_inversion_qui_echoue_laisse_l_action_en_place():
    h = Historique()
    h.executer(EchoueAInverser())
    with pytest.raises(RuntimeError):
        h.annuler()
    assert h.journal() == ["EchoueAInverser"]  # toujours annulable, rien de perdu
    assert h.retablir() is False


def test_sequence_aleatoire_reste_coherente():
    # 2 000 opérations au hasard : après chaque annulation, l'état doit être
    # exactement celui d'avant la dernière action encore active.
    rng = random.Random(7)
    t = fabriquer_ticket(priorite=3, statut="ouvert")
    affectations = {}
    h = Historique()
    passe = [photo(t, affectations)]  # état avant chaque action active, + état courant
    futur = []                        # états rétablissables
    for _ in range(2000):
        choix = rng.random()
        if choix < 0.5:
            action = rng.choice([
                lambda: ChangerPriorite(t, rng.randint(1, 4)),
                lambda: ChangerStatut(t, rng.choice(["ouvert", "en_cours", "resolu"])),
                lambda: AffecterTicket(affectations, t.id, rng.choice(["AG-01", "AG-02"])),
            ])()
            h.executer(action)
            passe.append(photo(t, affectations))
            futur = []
        elif choix < 0.8:
            if h.annuler():
                futur.append(passe.pop())
        else:
            if h.retablir():
                passe.append(futur.pop())
        assert photo(t, affectations) == passe[-1]
        assert len(h.journal()) == len(passe) - 1
