from datetime import datetime

import pytest

from moteur_sav.modeles import (
    CANAUX,
    CATEGORIES,
    PRIORITE_PAR_DEFAUT,
    SLA_HEURES,
    STATUTS,
    Agent,
    calculer_echeance,
)

from .fabrique import fabriquer_ticket


def test_sla_par_priorite():
    assert SLA_HEURES == {1: 4, 2: 24, 3: 72, 4: 168}


def test_echeance_ajoute_le_sla():
    debut = datetime(2026, 3, 14, 9, 0)
    assert calculer_echeance(debut, 1) == datetime(2026, 3, 14, 13, 0)
    assert calculer_echeance(debut, 4) == datetime(2026, 3, 21, 9, 0)


def test_cle_urgence_ordonne_par_echeance_puis_priorite():
    tot_p3 = fabriquer_ticket(id="A", cree_le="2026-03-10T09:00:00", priorite=3)  # échéance 13/03
    tard_p1 = fabriquer_ticket(id="B", cree_le="2026-03-14T09:00:00", priorite=1)  # échéance 14/03
    assert tot_p3.cle_urgence() < tard_p1.cle_urgence()


def test_agent_competence():
    a = Agent("AG-01", "Camille Roux", frozenset({"livraison"}), 10)
    assert a.sait_traiter("livraison")
    assert not a.sait_traiter("facturation")


# --- Tests ajoutés : constantes, échéance, clé d'urgence, valeurs par défaut ---


def test_valeurs_autorisees():
    assert CANAUX == {"email", "chat", "telephone", "formulaire", "autre"}
    assert CATEGORIES == {"livraison", "produit_abime", "facturation", "conseil_plante", "retour", "autre"}
    assert STATUTS == {"ouvert", "en_cours", "resolu"}


def test_priorite_par_defaut_a_un_delai():
    assert PRIORITE_PAR_DEFAUT in SLA_HEURES


def test_echeance_pour_chaque_priorite():
    debut = datetime(2026, 3, 14, 9, 0)
    for priorite, heures in SLA_HEURES.items():
        assert (calculer_echeance(debut, priorite) - debut).total_seconds() == heures * 3600


def test_echeance_priorite_inconnue_leve_keyerror():
    for priorite in (0, 5, -1):
        with pytest.raises(KeyError):
            calculer_echeance(datetime(2026, 3, 14, 9, 0), priorite)


def test_ticket_valeurs_par_defaut():
    ticket = fabriquer_ticket()
    assert ticket.priorite_estimee is False
    assert ticket.date_estimee is False


def test_cle_urgence_contenu():
    ticket = fabriquer_ticket(cree_le="2026-03-14T09:00:00", priorite=1)
    assert ticket.cle_urgence() == (datetime(2026, 3, 14, 13, 0), 1, datetime(2026, 3, 14, 9, 0))


def test_cle_urgence_a_echeance_egale_la_priorite_forte_passe_d_abord():
    p1 = fabriquer_ticket(id="A", cree_le="2026-03-14T09:00:00", priorite=1)  # échéance 14/03 13:00
    p2 = fabriquer_ticket(id="B", cree_le="2026-03-13T13:00:00", priorite=2)  # échéance 14/03 13:00
    assert p1.echeance == p2.echeance
    assert p1.cle_urgence() < p2.cle_urgence()


def test_cle_urgence_tickets_identiques_sont_egaux():
    assert fabriquer_ticket(id="A").cle_urgence() == fabriquer_ticket(id="B").cle_urgence()


def test_tri_par_cle_urgence():
    tickets = [
        fabriquer_ticket(id="tard", cree_le="2026-03-20T09:00:00", priorite=1),
        fabriquer_ticket(id="premier", cree_le="2026-03-10T09:00:00", priorite=2),
        fabriquer_ticket(id="milieu", cree_le="2026-03-14T09:00:00", priorite=3),
    ]
    assert [t.id for t in sorted(tickets, key=lambda t: t.cle_urgence())] == ["premier", "milieu", "tard"]


def test_agent_par_defaut_sans_competence_ni_capacite():
    agent = Agent("AG-01", "Camille Roux")
    assert agent.competences == frozenset()
    assert agent.capacite_jour == 0
    assert not agent.sait_traiter("livraison")


# --- Rapport lisible : python -m tests.test_modeles ---


def _rapport():
    """Exécute les tests de ce fichier et affiche OK / ÉCHEC pour chacun, puis le verdict."""
    tests = [(nom, f) for nom, f in globals().items() if nom.startswith("test_") and callable(f)]
    print("=" * 72, "\n VÉRIFICATION DES MODÈLES (modeles.py)\n", "=" * 72, sep="")
    echecs = 0
    for nom, fonction in tests:
        libelle = (fonction.__doc__ or nom.removeprefix("test_").replace("_", " ")).strip()
        try:
            fonction()
            print(f"[OK]    {libelle}")
        except Exception as erreur:
            echecs += 1
            print(f"[ÉCHEC] {libelle}\n        -> {type(erreur).__name__}: {str(erreur)[:100]}")
    print("=" * 72)
    if echecs:
        print(f" ✘ PROBLÈMES : {echecs} vérification(s) en échec sur {len(tests)}.")
    else:
        print(f" ✔ TOUT VA BIEN : {len(tests)} vérifications réussies.")
    print("=" * 72)
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(_rapport())
