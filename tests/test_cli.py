"""Tests de la ligne de commande : sorties attendues, et jamais de message brut."""


import pytest

from moteur_sav.cli import main
from tests.conftest import DONNEES


def lancer(capsys, *args):
    code = main([*map(str, args)])
    sortie = capsys.readouterr()
    return code, sortie.out, sortie.err


def test_bilan(capsys):
    code, sortie, _ = lancer(capsys, "--tickets", DONNEES / "exemple_tickets.jsonl", "bilan")
    assert code == 0
    assert "10 tickets exploitables, 2 écartés" in sortie
    assert "json invalide" in sortie and "champ manquant" in sortie


def test_urgents_ordre_et_limite(capsys):
    code, sortie, _ = lancer(capsys, "--tickets", DONNEES / "exemple_tickets.jsonl", "urgents", "-n", 2)
    lignes = sortie.strip().splitlines()
    assert code == 0 and len(lignes) == 2
    # P1 créé à 9 h 30 (échéance 13 h 30), puis P1 « urgent » créé à 12 h 30 (échéance 16 h 30)
    assert lignes[0].startswith("TCK-000001") and lignes[1].startswith("TCK-000007")


def test_chercher_et_prefixe(capsys):
    fichier = DONNEES / "exemple_tickets.jsonl"
    _, sortie, _ = lancer(capsys, "--tickets", fichier, "chercher", "pot cassé")
    assert "1 ticket(s)" in sortie and "TCK-000001" in sortie
    _, sortie, _ = lancer(capsys, "--tickets", fichier, "chercher", "pot livraison", "--mode", "OU")
    assert "TCK-000001" in sortie and "TCK-000007" in sortie
    _, sortie, _ = lancer(capsys, "--tickets", fichier, "prefixe", "cochen")
    assert sortie.strip() == "cochenilles"


def test_aucun_message_brut(capsys):
    """La sortie ne contient ni le message ni l'e-mail ou le téléphone de l'exemple."""
    fichier = DONNEES / "exemple_tickets.jsonl"
    sortie = "".join(
        lancer(capsys, "--tickets", fichier, *cmd)[1]
        for cmd in (["bilan"], ["urgents", "-n", 20], ["chercher", "remboursement"], ["chercher", "colis", "--mode", "OU"])
    )
    assert "client.test@example.org" not in sortie and "06 39 98" not in sortie
    assert "CLI-" not in sortie  # pas de client_id


def test_repartir_sur_echantillon(capsys):
    code, sortie, _ = lancer(capsys, "repartir")
    assert code == 0 and "gloutonne" in sortie and "naïve" in sortie and "%" in sortie


def test_fichier_absent(capsys):
    code, _, erreur = lancer(capsys, "--tickets", "absent.jsonl", "bilan")
    assert code == 1 and erreur.startswith("erreur")


def test_commande_inconnue():
    with pytest.raises(SystemExit):
        main(["danse"])
