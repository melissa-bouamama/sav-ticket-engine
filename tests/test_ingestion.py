"""Tests de l'ingestion : ingestion des tickets et des conseillers.

Deux commandes, même résultat :

    python -m pytest                 # avec tous les tests du projet
    python -m tests.test_ingestion   # rapport lisible : OK / ÉCHEC, bilan, verdict

Principes :
- les cas sont fabriqués ici ou lus dans donnees/exemple_* (versionnés) ; les vraies
  données (donnees/tickets.jsonl) sont facultatives et seulement lues, jamais modifiées ;
- chaque test regroupe les cas d'une même règle et nomme le cas fautif quand il échoue ;
- aucun message de client n'est affiché, ni dans le rapport, ni dans un rejet.
"""

import atexit
import json
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from moteur_sav.ingestion import (
    CORRESPONDANCE_CATEGORIES,
    LigneInvalide,
    charger_agents,
    charger_tickets,
    construire_ticket,
    copier_donnees,
    empreinte,
    normaliser_priorite,
)
from moteur_sav.modeles import CATEGORIES, SLA_HEURES

DONNEES = Path(__file__).resolve().parents[1] / "donnees"

# Dossier temporaire commun à tous les tests, supprimé à la fin.
TMP = Path(tempfile.mkdtemp(prefix="test_ingestion_"))
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


# --------------------------------------------------------------------------- outils


def brut(**champs):
    """Ticket brut valide. Une valeur None retire le champ (pour tester son absence)."""
    ticket = {
        "id": "T1", "cree_le": "2026-03-14T09:30:00", "client_id": "C1", "canal": "email",
        "categorie": "livraison", "priorite": 2, "sujet": "Colis non reçu",
        "message": "Bonjour", "statut": "ouvert",
    }
    ticket.update(champs)
    return {cle: valeur for cle, valeur in ticket.items() if valeur is not None}


def motif(**champs):
    """Motif de rejet d'un ticket brut, ou None s'il est accepté."""
    try:
        construire_ticket(brut(**champs))
    except LigneInvalide as erreur:
        return erreur.motif
    return None


def ecrire(nom, contenu):
    """Écrit un fichier de test (texte ou octets) dans le dossier temporaire."""
    chemin = TMP / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contenu, bytes):
        chemin.write_bytes(contenu)
    else:
        chemin.write_text(contenu, encoding="utf-8", newline="")
    return chemin


def fichier(*lignes, nom="tickets.jsonl"):
    """Fichier .jsonl : un dict devient une ligne JSON, un texte est écrit tel quel."""
    textes = [json.dumps(ligne) if isinstance(ligne, dict) else ligne for ligne in lignes]
    return ecrire(nom, "\n".join(textes) + "\n")


def leve(exception, fonction, *args):
    """Vrai si fonction(*args) lève l'exception attendue."""
    try:
        fonction(*args)
    except exception:
        return True
    return False


# --------------------------------------------------------------------------- priorité


def test_priorite_valeurs_valides():
    """Priorité : entier, « 2 », « P2 », « urgent » ; absente -> 3 signalée ; hors échelle corrigée"""
    cas = [
        (2, (2, False)), ("2", (2, False)), ("P2", (2, False)), (" p1 ", (1, False)),
        ("urgent", (1, False)), (2.7, (2, False)),
        (None, (3, True)), ("", (3, True)),   # absente : 3, signalée comme estimée
        (0, (3, True)), (-1, (3, True)),      # inférieure à 1 : 3, estimée
        (9, (4, True)), ("P7", (4, True)),    # supérieure à 4 : 4, estimée
    ]
    for valeur, attendu in cas:
        assert normaliser_priorite(valeur) == attendu, f"priorité {valeur!r}"


def test_priorite_illisible_gardee_en_p4():
    """Priorité : texte, liste, dictionnaire, NaN -> ticket gardé en P4, signalé « estimée »"""
    for valeur in ("abc", "haute", "critique", "normale", "P", "PP2", [], [2], {}, float("nan"), float("inf")):
        assert normaliser_priorite(valeur) == (4, True), f"priorité {valeur!r}"
        ticket = construire_ticket(brut(priorite=valeur))
        assert (ticket.priorite, ticket.priorite_estimee) == (4, True), f"priorité {valeur!r}"
        assert (ticket.echeance - ticket.cree_le).total_seconds() == SLA_HEURES[4] * 3600


def test_echeance():
    """Échéance = création + délai de la priorité (P1 4 h, P2 24 h, P3 72 h, P4 168 h)"""
    for priorite, heures in SLA_HEURES.items():
        ticket = construire_ticket(brut(priorite=priorite))
        assert (ticket.echeance - ticket.cree_le).total_seconds() == heures * 3600, f"P{priorite}"


# --------------------------------------------------------------------------- dates


def test_dates_formats_acceptes():
    """Dates : ISO (T ou espace), JJ/MM/AAAA, mois en lettres (anglais ou français)"""
    cas = [
        ("2026-03-14T09:32:00", datetime(2026, 3, 14, 9, 32)),
        ("2026-03-14 09:32", datetime(2026, 3, 14, 9, 32)),
        ("14/03/2026 09h32", datetime(2026, 3, 14, 9, 32)),
        ("5/3/2026 13H29", datetime(2026, 3, 5, 13, 29)),
        ("01 May 2026 10:15", datetime(2026, 5, 1, 10, 15)),
        ("12 février 2026 08:00", datetime(2026, 2, 12, 8, 0)),
        ("2024-02-29T12:00:00", datetime(2024, 2, 29, 12, 0)),  # année bissextile
    ]
    for texte, attendu in cas:
        assert construire_ticket(brut(cree_le=texte)).cree_le == attendu, texte


def test_dates_sans_heure():
    """Date sans heure : minuit pour P1-P2, midi pour P3-P4, signalée, échéance sur l'heure fixée"""
    for priorite, heure in {1: 0, 2: 0, 3: 12, 4: 12}.items():
        ticket = construire_ticket(brut(cree_le="2026-03-14", priorite=priorite))
        assert ticket.cree_le == datetime(2026, 3, 14, heure), f"P{priorite}"
        assert ticket.date_estimee is True
    ticket = construire_ticket(brut(cree_le="14/03/2026", priorite=3))
    assert ticket.echeance == datetime(2026, 3, 17, 12)
    assert construire_ticket(brut()).date_estimee is False


def test_dates_rejetees():
    """Dates : texte libre, format américain, mois 13, 30 février, 25 h -> « date invalide »"""
    for texte in ("hier soir", "2026", "03-14-2026", "2026-13-01T10:00:00", "30/02/2026 10h00",
                  "2025-02-29T12:00:00", "2026-03-14T25:00:00", "31 Foo 2026 10:00"):
        assert motif(cree_le=texte) == "date invalide", texte


def test_dates_formats_non_prevus_rejetes():
    """Dates : fuseau horaire, millisecondes, année sur 2 chiffres, nombre -> rejetées (format non prévu)"""
    for texte in ("2026-03-14T09:30:00Z", "2026-03-14T09:30:00+01:00", "2026-03-14T09:30:00.123", "14/03/26"):
        assert motif(cree_le=texte) == "date invalide", texte
    assert motif(cree_le=1710408600) == "champ manquant"  # un nombre n'est pas un texte de date


# --------------------------------------------------------------------------- champs


def test_champs_obligatoires():
    """id, cree_le, client_id absents, vides ou blancs -> « champ manquant »"""
    for champ in ("id", "cree_le", "client_id"):
        for vide in (None, "", "   ", "\t\n"):
            assert motif(**{champ: vide}) == "champ manquant", f"{champ}={vide!r}"


def test_canal():
    """Canal : absent -> « autre », fax/courrier -> email, casse normalisée, inconnu rejeté"""
    for vide in (None, "", "  "):
        assert construire_ticket(brut(canal=vide)).canal == "autre", repr(vide)
    for valeur, attendu in [("fax", "email"), (" COURRIER ", "email"), ("CHAT", "chat"), (" Autre ", "autre")]:
        assert construire_ticket(brut(canal=valeur)).canal == attendu, valeur
    for valeur in ("sms", "minitel", 12, ["email"]):
        assert motif(canal=valeur) == "canal inconnu", repr(valeur)


def test_canal_sans_effet_sur_l_urgence():
    """Le canal n'entre dans aucune décision : même échéance et même clé d'urgence"""
    a, b = construire_ticket(brut(canal="email")), construire_ticket(brut(canal=None))
    assert a.cle_urgence() == b.cle_urgence()


def test_categorie():
    """Catégorie : absente -> « autre », variantes connues ramenées, casse normalisée, inconnue rejetée"""
    for vide in (None, "", "  "):
        assert construire_ticket(brut(categorie=vide)).categorie == "autre", repr(vide)
    for officielle in CATEGORIES:
        assert construire_ticket(brut(categorie=f" {officielle.upper()} ")).categorie == officielle
    for variante, officielle in CORRESPONDANCE_CATEGORIES.items():
        assert construire_ticket(brut(categorie=variante)).categorie == officielle, variante
    for valeur in ("jardinage", "xyz", 12, ["livraison"]):
        assert motif(categorie=valeur) == "categorie inconnue", repr(valeur)


def test_message_vide_accepte_si_sujet():
    """Message absent ou vide : ticket gardé si le sujet existe ; rejeté si sujet ET message vides"""
    for vide in (None, "", "   "):
        ticket = construire_ticket(brut(message=vide))
        assert (ticket.message, ticket.sujet) == ("", "Colis non reçu"), repr(vide)
        assert motif(message=vide, sujet=vide) == "champ manquant", repr(vide)
    assert motif(message=12) == "champ manquant"  # un message qui n'est pas du texte
    assert construire_ticket(brut(message="  Bonjour  ")).message == "Bonjour"


def test_statut_et_sujet():
    """Statut : absent -> ouvert, casse normalisée, inconnu rejeté ; sujet absent -> chaîne vide"""
    assert construire_ticket(brut(statut=None)).statut == "ouvert"
    assert construire_ticket(brut(statut=" RESOLU ")).statut == "resolu"
    assert construire_ticket(brut(statut="En_Cours")).statut == "en_cours"
    for valeur in ("archive", 3, ["ouvert"]):
        assert motif(statut=valeur) == "statut inconnu", repr(valeur)
    assert construire_ticket(brut(sujet=None)).sujet == ""
    assert construire_ticket(brut(sujet="  Pot cassé  ")).sujet == "Pot cassé"


def test_ordre_des_verifications():
    """Ordre : champ manquant, date, canal, catégorie, statut (le premier défaut gagne)"""
    cas = [
        (dict(client_id=None, cree_le="x", canal="sms", categorie="x", priorite="abc", statut="zz"), "champ manquant"),
        (dict(cree_le="x", canal="sms", categorie="x", priorite="abc", statut="zz"), "date invalide"),
        (dict(canal="sms", categorie="x", priorite="abc", statut="zz"), "canal inconnu"),
        (dict(categorie="x", priorite="abc", statut="zz"), "categorie inconnue"),
        (dict(priorite="abc", statut="zz"), "statut inconnu"),        # la priorité illisible ne rejette pas
        (dict(statut="zz"), "statut inconnu"),
    ]
    for fautes, attendu in cas:
        assert motif(**fautes) == attendu, attendu


# --------------------------------------------------------------------------- fichiers


def test_fichier_json_invalide_lignes_vides_ordre():
    """Fichier : JSON tronqué rejeté avec son n° de ligne, lignes vides ignorées, ordre conservé"""
    chemin = fichier(brut(id="C"), "", '{"id": "X", "cree_le": "2026-03', "pas du json", "[1, 2]", brut(id="A"))
    tickets, rejets = charger_tickets(chemin)
    assert [t.id for t in tickets] == ["C", "A"]
    assert [(r["ligne"], r["motif"]) for r in rejets] == [(3, "json invalide"), (4, "json invalide"), (5, "json invalide")]


def test_fichier_cas_limites():
    """Fichier : vide, introuvable, avec BOM et fins de ligne Windows, octet illisible, JSON très imbriqué"""
    assert charger_tickets(fichier()) == ([], [])
    assert leve(FileNotFoundError, charger_tickets, TMP / "absent.jsonl")
    windows = "\r\n".join(json.dumps(brut(id=i)) for i in ("A", "B")) + "\r\n"
    tickets, rejets = charger_tickets(ecrire("bom.jsonl", b"\xef\xbb\xbf" + windows.encode("utf-8")))
    assert [t.id for t in tickets] == ["A", "B"] and rejets == []
    abime = json.dumps(brut(id="A", message="avant APRES")).encode("utf-8").replace(b"APRES", b"\xff\xfe")
    tickets, _ = charger_tickets(ecrire("octet.jsonl", abime + b"\n"))
    assert [t.id for t in tickets] == ["A"]
    tickets, rejets = charger_tickets(fichier("[" * 5000 + "]" * 5000, brut(id="OK")))
    assert [t.id for t in tickets] == ["OK"] and [r["motif"] for r in rejets] == ["json invalide"]


def test_doublons():
    """Doublons : copie exacte rejetée ; même id et contenu différent gardé sous « id-2 », « id-3 »"""
    tickets, rejets = charger_tickets(fichier(
        brut(id="A"), brut(id="A"),                          # copie exacte : rejetée
        brut(id="A", client_id="C2"), brut(id="A", client_id="C3"),
        brut(id="A", client_id="C2"),                        # copie exacte d'une version renommée
    ))
    assert [(t.id, t.client_id) for t in tickets] == [("A", "C1"), ("A-2", "C2"), ("A-3", "C3")]
    assert [(r["ligne"], r["motif"]) for r in rejets] == [(2, "identifiant en double"), (5, "identifiant en double")]


def test_doublons_identifiants_toujours_distincts():
    """Un identifiant renommé n'entre jamais en collision avec un identifiant existant"""
    tickets, _ = charger_tickets(fichier(
        brut(id="A", client_id="C1"), brut(id="A", client_id="C2"), brut(id="A-2", client_id="C3"),
    ))
    assert len({t.id for t in tickets}) == len(tickets) == 3


def test_rejets_sans_donnees_personnelles():
    """Un rejet ne contient jamais le message du client"""
    secret = "MESSAGE-CONFIDENTIEL-42"
    chemin = fichier(
        brut(message=secret, cree_le="hier"), brut(message=secret, canal="sms"),
        brut(message=secret, statut="zz"), brut(message=secret, client_id=None),
        '{"id": "F", "message": "' + secret,
    )
    _, rejets = charger_tickets(chemin)
    assert len(rejets) == 5 and secret not in json.dumps(rejets)


def test_format_des_rejets():
    """Rejets : exactement {ligne, motif, detail}, n° de ligne physique (1 = première), motifs attendus"""
    motifs_attendus = {"json invalide", "champ manquant", "date invalide", "canal inconnu", "categorie inconnue",
                     "statut inconnu", "identifiant en double"}      # « priorite invalide » : plus jamais émis
    _, rejets = charger_tickets(fichier(
        "pas du json", "", brut(id="A", cree_le="hier"), brut(id="B", canal="sms"), brut(id="C", categorie="xyz"),
        brut(id="D", priorite="abc"), brut(id="E", statut="zz"), brut(id="F", client_id=None),
        brut(id="G"), brut(id="G"),
    ))
    assert [r["ligne"] for r in rejets] == [1, 3, 4, 5, 7, 8, 10]       # D (ligne 6) est gardé, en P4  # la ligne vide (2) compte dans la numérotation
    assert {r["motif"] for r in rejets} == motifs_attendus
    for rejet in rejets:
        assert set(rejet) == {"ligne", "motif", "detail"} and isinstance(rejet["ligne"], int)
        assert isinstance(rejet["motif"], str) and isinstance(rejet["detail"], str)


def test_chargement_deterministe():
    """Deux chargements du même fichier donnent exactement le même résultat"""
    chemin = DONNEES / "exemple_tickets.jsonl"
    assert charger_tickets(chemin) == charger_tickets(chemin)


def test_volume():
    """Volume : 50 000 lignes se chargent vite ; 2 000 tickets au même id restent tous distincts"""
    debut = time.perf_counter()
    tickets, rejets = charger_tickets(fichier(*[brut(id=f"V{i}", client_id=f"C{i % 999}") for i in range(50000)]))
    assert len(tickets) == 50000 and not rejets and time.perf_counter() - debut < 10
    tickets, _ = charger_tickets(fichier(*[brut(id="MEME", client_id=f"C{i}") for i in range(2000)]))
    assert len({t.id for t in tickets}) == 2000


def test_fichier_d_exemple():
    """exemple_tickets.jsonl : tickets valides gardés, ligne tronquée et champ manquant rejetés"""
    tickets, rejets = charger_tickets(DONNEES / "exemple_tickets.jsonl")
    assert {"TCK-000001", "TCK-000003", "TCK-000011"} <= {t.id for t in tickets}
    assert {"json invalide", "champ manquant"} <= {r["motif"] for r in rejets}
    assert len({t.id for t in tickets}) == len(tickets)


def test_fichier_d_exemple_ligne_par_ligne():
    """exemple_tickets.jsonl : les 13 lignes (une par cas difficile) donnent exactement le résultat attendu"""
    tickets, rejets = charger_tickets(DONNEES / "exemple_tickets.jsonl")
    obtenu = [(t.id, t.canal, t.categorie, t.priorite, t.statut) for t in tickets]
    assert obtenu == [
        ("TCK-000001", "email", "produit_abime", 1, "ouvert"),
        ("TCK-000002", "chat", "livraison", 2, "en_cours"),       # canal « CHAT », catégorie « Livraison », « P2 »
        ("TCK-000003", "formulaire", "conseil_plante", 3, "ouvert"),  # priorité absente
        ("TCK-000005", "email", "retour", 3, "ouvert"),           # date « 14/03/2026 09h32 »
        ("TCK-000007", "chat", "livraison", 1, "ouvert"),         # priorité « urgent »
        ("TCK-000008", "chat", "facturation", 3, "ouvert"),       # catégorie « SAV » (choix de conception)
        ("TCK-000009", "email", "autre", 4, "ouvert"),            # canal « fax » (choix de conception)
        ("TCK-000001-2", "email", "retour", 3, "ouvert"),         # même id, autre ticket (choix de conception)
        ("TCK-000011", "telephone", "retour", 4, "resolu"),       # priorité « 4 », canal « Telephone »
        ("TCK-000013", "email", "autre", 4, "ouvert"),            # sujet et statut absents
    ]
    assert [(r["ligne"], r["motif"]) for r in rejets] == [(4, "json invalide"), (6, "champ manquant")]
    par_id = {t.id: t for t in tickets}
    assert par_id["TCK-000003"].priorite_estimee and not par_id["TCK-000002"].priorite_estimee
    assert par_id["TCK-000005"].cree_le == datetime(2026, 3, 14, 9, 32)
    assert par_id["TCK-000013"].sujet == ""


# --------------------------------------------------------------------------- agents


def test_agents():
    """Agents : exemple lu ; vrai format (« capacite_jour;; », « 40; ») lu ; capacité illisible -> ValueError"""
    agents = charger_agents(DONNEES / "exemple_agents.csv")
    assert [(a.agent_id, a.capacite_jour) for a in agents] == [("AG-01", 2), ("AG-02", 1), ("AG-03", 2)]
    assert agents[0].sait_traiter("retour") and not agents[0].sait_traiter("facturation")

    vrai = ecrire("agents.csv", "agent_id,nom,competences,capacite_jour;;\r\n"
                                "AG-01,Zoé,Livraison;RETOUR,40;\r\nAG-02,Hugo,livraison,25\r\n")
    agents = charger_agents(vrai)
    assert [a.capacite_jour for a in agents] == [40, 25]
    assert agents[0].competences == frozenset({"livraison", "retour"})

    for capacite in ("beaucoup", "", "-2", "2.5"):
        abime = ecrire("agents_abime.csv", f"agent_id,nom,competences,capacite_jour\nAG-01,Zoé,retour,{capacite}\n")
        assert leve(ValueError, charger_agents, abime), f"capacité {capacite!r}"


def test_agents_cas_limites():
    """Agents : fichier vide, en-tête seul, lignes vides, BOM -> lus ; colonne manquante -> ValueError"""
    entete = "agent_id,nom,competences,capacite_jour\n"
    assert charger_agents(ecrire("a1.csv", "")) == []
    assert charger_agents(ecrire("a2.csv", entete)) == []
    agents = charger_agents(ecrire("a3.csv", "\ufeff" + entete + "\nAG-01,Zoé,retour,3\n\n"))
    assert [(a.agent_id, a.capacite_jour) for a in agents] == [("AG-01", 3)]
    assert charger_agents(ecrire("a4.csv", entete + "AG-01,Zoé,,0\n"))[0].competences == frozenset()
    assert leve(ValueError, charger_agents, ecrire("a5.csv", "agent_id,nom,competences\nAG-01,Zoé,retour\n"))


# --------------------------------------------------------------------------- copie de travail


def test_copie_laisse_l_original_intact():
    """Copie : l'original n'est pas modifié, la copie est identique et en lecture seule"""
    original = fichier(brut(id="A"), brut(id="B"), nom="originaux/tickets.jsonl")
    avant = empreinte(original)
    copie = copier_donnees(original)
    assert copie != original and copie.parent.name == "copie_travail"
    assert empreinte(copie) == avant == empreinte(original)
    assert not copie.stat().st_mode & 0o200, "la copie doit être en lecture seule"


def test_copie_remplacee_et_non_imbriquee():
    """Copie : une nouvelle copie remplace l'ancienne ; copier une copie ne crée pas de sous-dossier"""
    original = fichier(brut(id="A"), nom="remplace/tickets.jsonl")
    premiere = copier_donnees(original)
    original.write_text(json.dumps(brut(id="B")) + "\n", encoding="utf-8")
    seconde = copier_donnees(original)
    assert seconde == premiere and json.loads(seconde.read_text(encoding="utf-8"))["id"] == "B"
    assert copier_donnees(seconde) == seconde
    assert leve(FileNotFoundError, copier_donnees, TMP / "absent.jsonl")


def test_chargement_sur_copie():
    """copie=True : mêmes résultats que sur l'original, qui reste intact (tickets et agents)"""
    original = fichier(brut(id="A"), "pas du json", brut(id="B"), nom="charge/tickets.jsonl")
    avant = empreinte(original)
    assert charger_tickets(original, copie=True) == charger_tickets(original)
    assert (original.parent / "copie_travail" / "tickets.jsonl").exists()
    agents = DONNEES / "exemple_agents.csv"
    assert charger_agents(agents, copie=True) == charger_agents(agents)
    assert empreinte(original) == avant


# --------------------------------------------------------------------------- vraies données


def _fichier_complet():
    """Le fichier complet s'il est présent, sinon l'échantillon synthétique versionné."""
    complet = DONNEES / "tickets.jsonl"
    return complet if complet.exists() else DONNEES / "echantillon_tickets.jsonl"


def test_jeu_complet():
    """Jeu complet : chaque ligne est un ticket ou un rejet, ids uniques, échéances et textes cohérents"""
    chemin = _fichier_complet()
    avant = empreinte(chemin)
    lignes = sum(1 for ligne in open(chemin, encoding="utf-8", errors="replace") if ligne.strip())
    tickets, rejets = charger_tickets(chemin, copie=True)
    assert len(tickets) + len(rejets) == lignes, "une ligne a disparu"
    assert len({t.id for t in tickets}) == len(tickets)
    for t in tickets:
        assert t.echeance == t.cree_le + timedelta(hours=SLA_HEURES[t.priorite]), t.id
        assert t.message or t.sujet, t.id
    assert empreinte(chemin) == avant, "l'original a été modifié"


# --------------------------------------------------------------------------- rapport


def _rapport():
    """Exécute tous les tests, affiche OK / ÉCHEC, le bilan des données et le verdict."""
    tests = [(nom, f) for nom, f in globals().items() if nom.startswith("test_") and callable(f)]
    print("=" * 72, "\n VÉRIFICATION DE L'INGESTION (ingestion)\n", "=" * 72, sep="")
    echecs = 0
    for nom, fonction in tests:  # globals() conserve l'ordre du fichier
        try:
            fonction()
            print(f"[OK]    {fonction.__doc__}")
        except Exception as erreur:  # AssertionError, mais aussi tout plantage imprévu
            echecs += 1
            print(f"[ÉCHEC] {fonction.__doc__}\n        -> {type(erreur).__name__}: {str(erreur)[:100]}")

    chemin = _fichier_complet()
    tickets, rejets = charger_tickets(chemin, copie=True)
    total = max(len(tickets) + len(rejets), 1)
    print("-" * 72, f"\n BILAN SUR LES DONNÉES ({chemin.name}, traité sur une copie)")
    print(f"   {len(tickets)} tickets exploitables, {len(rejets)} rejetés ({100 * len(rejets) / total:.1f} %)")
    for raison, nombre in Counter(r["motif"] for r in rejets).most_common():
        print(f"     - {raison:<22}: {nombre}")
    print(f"   {sum(t.priorite_estimee for t in tickets)} priorités estimées, "
          f"{sum(t.date_estimee for t in tickets)} dates à l'heure estimée, "
          f"{sum(t.canal == 'autre' for t in tickets)} canaux « autre », "
          f"{sum(t.message == '' for t in tickets)} sans message")
    print("=" * 72)
    if echecs:
        print(f" ✘ PROBLÈMES : {echecs} vérification(s) en échec sur {len(tests)}.")
    else:
        print(f" ✔ TOUT VA BIEN : {len(tests)} vérifications réussies.")
    print("=" * 72)
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(_rapport())
