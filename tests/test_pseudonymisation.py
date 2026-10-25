"""Tests de la pseudonymisation : e-mails, téléphones, identifiant client haché."""

import pytest

from moteur_sav.pseudonymisation import masquer_texte, pseudonyme_client, pseudonymiser
from tests.fabrique import fabriquer_ticket


@pytest.mark.parametrize("telephone", [
    "06 39 98 00 42", "06.39.98.00.42", "0639980042", "+33 6 39 98 00 42", "+33639980042", "06-39-98-00-42",
])
def test_telephones_masques(telephone):
    assert masquer_texte(f"Rappelez-moi au {telephone} merci") == "Rappelez-moi au [telephone] merci"


def test_email_masque():
    assert masquer_texte("écrivez à jean.dupont+sav@example.com ou à x@a.fr") == "écrivez à [email] ou à [email]"


@pytest.mark.parametrize("texte", [
    "commande CMD-00042 à Lyon", "colis 1234567890123", "référence 12 34 56", "TCK-000011", "", "Bonjour",
])
def test_rien_a_masquer(texte):
    """Numéros de commande, identifiants et nombres trop longs ou trop courts ne sont pas des téléphones."""
    assert masquer_texte(texte) == texte


def test_masquer_texte_est_idempotent():
    une_fois = masquer_texte("a@b.fr et 0639980042")
    assert masquer_texte(une_fois) == une_fois == "[email] et [telephone]"


def test_pseudonyme_stable_et_depend_du_sel():
    assert pseudonyme_client("CLI-0001", "sel") == pseudonyme_client("CLI-0001", "sel")
    assert pseudonyme_client("CLI-0001", "sel") != pseudonyme_client("CLI-0002", "sel")
    assert pseudonyme_client("CLI-0001", "sel") != pseudonyme_client("CLI-0001", "autre")
    pseudo = pseudonyme_client("CLI-0001", "sel")
    assert pseudo.startswith("CLI-") and len(pseudo) == 14 and "0001" not in pseudo


def test_pseudonymiser_renvoie_une_copie():
    ticket = fabriquer_ticket(
        client_id="CLI-0042", sujet="Écrire à a@b.fr",
        message="Mon numéro : 06 39 98 00 42, commande CMD-00042.",
    )
    copie = pseudonymiser(ticket, "sel")
    assert copie is not ticket
    assert copie.client_id != "CLI-0042" and copie.sujet == "Écrire à [email]"
    assert copie.message == "Mon numéro : [telephone], commande CMD-00042."
    # l'original est intact, les autres champs aussi
    assert ticket.client_id == "CLI-0042" and "a@b.fr" in ticket.sujet
    assert (copie.id, copie.echeance, copie.priorite) == (ticket.id, ticket.echeance, ticket.priorite)


def test_sel_vide_refuse():
    with pytest.raises(ValueError):
        pseudonymiser(fabriquer_ticket(), "")
