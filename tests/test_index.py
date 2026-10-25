"""Tests de l'index : normalisation, dichotomie, index inversé, recherche par début de mot.

    python -m pytest                 # avec tous les tests du projet
    python -m tests.test_index       # rapport lisible : OK / ÉCHEC, puis la démo sur les données

Du plus simple au plus difficile : texte, dichotomie, index, préfixes, comparaison avec une
recherche « naïve » sur des données aléatoires, jeu complet. `bisect` est autorisé ici,
comme référence ; il est interdit dans moteur_sav/index.py (un test le vérifie).
Aucun message de client n'est affiché.
"""

import bisect
import random
import re
import time
from pathlib import Path

from moteur_sav.index import IndexInverse, borne_inferieure, normaliser, sans_accents
from moteur_sav.ingestion import charger_tickets

from .fabrique import fabriquer_ticket
from .test_rapport import lancer

RACINE = Path(__file__).resolve().parents[1]
DONNEES = RACINE / "donnees"


def indexer(*textes):
    """Index de tickets T0, T1... dont le sujet est le texte donné (message vide)."""
    index = IndexInverse()
    for i, texte in enumerate(textes):
        index.ajouter(fabriquer_ticket(id=f"T{i}", sujet=texte, message=""))
    return index


def leve(exception, fonction, *args, **kwargs):
    """Vrai si fonction(*args, **kwargs) lève l'exception attendue."""
    try:
        fonction(*args, **kwargs)
    except exception:
        return True
    return False


# --------------------------------------------------------------------------- texte


def test_sans_accents():
    """Accents retirés, casse conservée, ligatures séparées (« Abîmée » -> « Abimee », « œuf » -> « oeuf »)"""
    assert sans_accents("Abîmée") == "Abimee"
    assert sans_accents("Ça été à noël, où ? ÉÈÊ") == "Ca ete a noel, ou ? EEE"
    assert sans_accents("cœur Œuf æ") == "coeur OEuf ae"
    assert sans_accents("") == "" and sans_accents("abc 123") == "abc 123"


def test_normaliser():
    """Normaliser : minuscules, sans accents, ponctuation retirée, sans mots vides ni mots d'une lettre"""
    assert normaliser("Bonjour, le POT est Cassé !") == ["pot", "casse"]
    assert normaliser("Colis non reçu") == ["colis", "non", "recu"]
    assert normaliser("l'article n°12 est abîmé") == ["article", "12", "abime"]
    assert normaliser("pot-de-fleurs") == ["pot", "fleurs"]
    assert normaliser("ÉCHANGE de taille") == ["echange", "taille"]


def test_normaliser_cas_limites():
    """Normaliser : texte vide, que des mots vides, que de la ponctuation, mots répétés conservés"""
    for texte in ("", "   ", "le la les", "!!! ... ???", "a b c", "Bonjour, merci"):
        assert normaliser(texte) == [], repr(texte)
    assert normaliser("pot pot POT") == ["pot", "pot", "pot"]


# --------------------------------------------------------------------------- dichotomie


def test_borne_inferieure_exemples():
    """Dichotomie : exemples simples, liste vide, cible avant tout, après tout, doublons"""
    assert borne_inferieure(["a", "c", "e"], "b") == 1
    assert borne_inferieure(["a", "c", "e"], "c") == 1       # égal : on renvoie le premier
    assert borne_inferieure(["a", "c", "e"], "") == 0
    assert borne_inferieure(["a", "c", "e"], "z") == 3
    assert borne_inferieure([], "a") == 0
    assert borne_inferieure(["a", "c", "c", "c", "e"], "c") == 1


def test_borne_inferieure_contre_bisect():
    """Dichotomie : même résultat que bisect.bisect_left sur 2 000 listes et cibles aléatoires"""
    hasard = random.Random(4)
    alphabet = "abcdef"
    for _ in range(2000):
        liste = sorted("".join(hasard.choices(alphabet, k=hasard.randint(1, 4))) for _ in range(hasard.randint(0, 30)))
        cible = "".join(hasard.choices(alphabet, k=hasard.randint(0, 4)))
        assert borne_inferieure(liste, cible) == bisect.bisect_left(liste, cible), (liste, cible)


def test_borne_inferieure_rapide_et_sans_effet_de_bord():
    """Dichotomie : 1 000 recherches dans 1 000 000 de mots en moins de 2 s ; la liste n'est pas modifiée"""
    liste = [f"{i:07d}" for i in range(1_000_000)]
    debut = time.perf_counter()
    for i in range(0, 1_000_000, 1000):
        assert borne_inferieure(liste, f"{i:07d}") == i
    assert time.perf_counter() - debut < 2   # une recherche linéaire ferait ~500 000 000 de comparaisons
    assert liste[0] == "0000000" and liste[-1] == "0999999" and len(liste) == 1_000_000


# --------------------------------------------------------------------------- index et recherche


def test_ajouter_et_compter():
    """Index : __len__ compte les tickets ; sujet ET message sont indexés ; message vide accepté"""
    index = IndexInverse()
    assert len(index) == 0
    index.ajouter(fabriquer_ticket(id="A", sujet="Pot cassé", message="Livraison tardive"))
    index.ajouter(fabriquer_ticket(id="B", sujet="Facture", message=""))
    assert len(index) == 2
    assert index.rechercher("tardive") == ["A"]   # trouvé dans le message
    assert index.rechercher("facture") == ["B"]   # trouvé dans le sujet


def test_recherche_et():
    """Recherche ET : tous les mots, dans n'importe quel ordre, résultats triés et sans doublon"""
    index = indexer("pot cassé", "pot de fleurs", "cassé pot", "vase cassé", "pot cassé pot cassé")
    assert index.rechercher("pot cassé") == ["T0", "T2", "T4"]
    assert index.rechercher("cassé pot") == ["T0", "T2", "T4"]
    assert index.rechercher("pot") == ["T0", "T1", "T2", "T4"]
    assert index.rechercher("pot cassé vase") == []


def test_recherche_ou():
    """Recherche OU : au moins un mot ; un mot inconnu n'empêche pas de trouver les autres"""
    index = indexer("pot cassé", "pot de fleurs", "vase cassé", "colis perdu")
    assert index.rechercher("fleurs vase", mode="OU") == ["T1", "T2"]
    assert index.rechercher("pot inconnu", mode="OU") == ["T0", "T1"]
    assert index.rechercher("inconnu", mode="OU") == []


def test_recherche_insensible_a_la_casse_et_aux_accents():
    """Recherche : « POT CASSÉ », « pot casse » et « Pot Cassé » donnent le même résultat"""
    index = indexer("Pot cassé à la réception", "Pot de fleurs")
    for requete in ("POT CASSÉ", "pot casse", "Pot Cassé", "  pot,   cassé !  "):
        assert index.rechercher(requete) == ["T0"], requete
    assert index.rechercher("RECEPTION") == ["T0"] and index.rechercher("réception") == ["T0"]


def test_recherche_requete_sans_mot_significatif():
    """Recherche : requête vide, mots vides ou ponctuation -> liste vide (ET et OU)"""
    index = indexer("pot cassé")
    for requete in ("", "   ", "le la de", "!!!", "a"):
        for mode in ("ET", "OU"):
            assert index.rechercher(requete, mode=mode) == [], (requete, mode)


def test_recherche_mode_invalide():
    """Recherche : un mode autre que ET / OU lève ValueError (même avec une requête vide)"""
    index = indexer("pot cassé")
    for mode in ("XOR", "et", "", "ET ", None):
        assert leve(ValueError, index.rechercher, "pot", mode), repr(mode)
    assert leve(ValueError, index.rechercher, "", "XOR")


def test_recherche_sur_index_vide():
    """Recherche et préfixes sur un index vide : listes vides, aucune erreur"""
    index = IndexInverse()
    assert index.rechercher("pot") == [] and index.rechercher("pot", "OU") == [] and index.prefixe("po") == []


def test_ajouter_deux_fois_le_meme_ticket_le_remplace():
    """Index : réindexer un identifiant remplace l'ancienne version (compte inchangé, anciens mots retirés)"""
    index = IndexInverse()
    index.ajouter(fabriquer_ticket(id="A", sujet="pot cassé", message=""))
    index.ajouter(fabriquer_ticket(id="A", sujet="pot cassé", message=""))
    assert len(index) == 1
    index.ajouter(fabriquer_ticket(id="A", sujet="vase fendu", message=""))
    assert len(index) == 1
    assert index.rechercher("cassé") == [] and index.rechercher("vase") == ["A"]
    assert index.prefixe("cass") == [] and index.prefixe("fend") == ["fendu"]


# --------------------------------------------------------------------------- début de mot


def test_prefixe_exemples():
    """Préfixe : « cochen » trouve « cochenilles » ; résultat trié, sans accent, sans doublon"""
    index = indexer("Cochenilles sur le ficus", "cochenille farineuse", "cassé", "cassée", "casserole", "colis")
    assert index.prefixe("cochen") == ["cochenille", "cochenilles"]
    assert index.prefixe("COCHEN") == ["cochenille", "cochenilles"]
    assert index.prefixe("cass") == ["casse", "cassee", "casserole"]
    assert index.prefixe("cassé") == ["casse", "cassee", "casserole"]   # accent ignoré
    assert index.prefixe("colis") == ["colis"] and index.prefixe("co") == ["cochenille", "cochenilles", "colis"]


def test_prefixe_cas_limites():
    """Préfixe : introuvable, plus grand que tout, vide, une lettre, mot vide (« le »), ponctuation"""
    index = indexer("lettre livraison", "zèbre", "abricot")
    assert index.prefixe("xyz") == [] and index.prefixe("zzz") == [] and index.prefixe("aaa") == []
    assert index.prefixe("") == [] and index.prefixe("  ") == [] and index.prefixe("!!") == []
    assert index.prefixe("l") == ["lettre", "livraison"]       # une lettre est un début valable
    assert index.prefixe("le") == ["lettre"]                    # « le » est un mot vide, mais un début valable
    assert index.prefixe("zebre") == ["zebre"] and index.prefixe("zebrex") == []
    assert index.prefixe("liv!") == ["livraison"]               # ponctuation ignorée


def test_prefixe_limite():
    """Préfixe : `limite` borne le nombre de mots ; 0 -> vide ; supérieure au total -> tous ; négative -> ValueError"""
    index = indexer("pot pote potion potager potasse")
    tous = ["pot", "potager", "potasse", "pote", "potion"]
    assert index.prefixe("pot") == tous
    assert index.prefixe("pot", limite=2) == tous[:2]
    assert index.prefixe("pot", limite=0) == []
    assert index.prefixe("pot", limite=99) == tous
    assert leve(ValueError, index.prefixe, "pot", -1)


def test_vocabulaire_retrie_seulement_si_l_index_change():
    """Préfixe : le vocabulaire trié est réutilisé tant que l'index ne change pas, refait quand un mot apparaît"""
    index = indexer("pot cassé", "vase fendu")
    index.prefixe("po")
    premier = index._vocabulaire_trie
    index.prefixe("va")
    assert index._vocabulaire_trie is premier and index._a_jour
    index.ajouter(fabriquer_ticket(id="Z", sujet="pot cassé", message=""))   # aucun mot nouveau
    index.prefixe("po")
    assert index._vocabulaire_trie is premier
    index.ajouter(fabriquer_ticket(id="Y", sujet="plante verte", message=""))  # mots nouveaux
    assert not index._a_jour
    assert index.prefixe("pla") == ["plante"] and index._vocabulaire_trie is not premier


# --------------------------------------------------------------------------- données aléatoires


def _corpus_aleatoire(graine, nb_tickets=300):
    """Tickets aléatoires : 3 à 12 mots tirés d'un vocabulaire de 60 mots (certains avec accents)."""
    hasard = random.Random(graine)
    mots = [f"mot{i}" for i in range(50)] + ["cassé", "casse", "cassée", "cochenille", "cochenilles", "été", "école",
                                              "pot", "vase", "colis"]
    tickets = [fabriquer_ticket(id=f"T{i:04d}", sujet=" ".join(hasard.choices(mots, k=hasard.randint(3, 12))), message="")
               for i in range(nb_tickets)]
    return hasard, mots, tickets


def test_et_ou_contre_recherche_naive():
    """ET et OU : mêmes résultats qu'un parcours naïf de tous les tickets, sur 500 requêtes aléatoires"""
    hasard, mots, tickets = _corpus_aleatoire(7)
    index = IndexInverse()
    mots_par_ticket = {}
    for ticket in tickets:
        index.ajouter(ticket)
        mots_par_ticket[ticket.id] = set(normaliser(ticket.sujet))
    for _ in range(500):
        requete = hasard.choices(mots + ["inconnu"], k=hasard.randint(1, 4))
        voulus = set(normaliser(" ".join(requete)))
        attendu_et = sorted(i for i, m in mots_par_ticket.items() if voulus <= m) if voulus else []
        attendu_ou = sorted(i for i, m in mots_par_ticket.items() if voulus & m)
        assert index.rechercher(" ".join(requete), "ET") == attendu_et, requete
        assert index.rechercher(" ".join(requete), "OU") == attendu_ou, requete


def test_prefixe_contre_recherche_naive():
    """Préfixe : mêmes mots qu'un parcours complet du vocabulaire, pour tous les débuts de tous les mots"""
    _, _, tickets = _corpus_aleatoire(11)
    index = IndexInverse()
    for ticket in tickets:
        index.ajouter(ticket)
    vocabulaire = sorted({m for t in tickets for m in normaliser(t.sujet)})
    debuts = {mot[:n] for mot in vocabulaire for n in range(1, len(mot) + 1)} | {"zz", "mot9x", "ab"}
    for debut in debuts:
        attendu = [m for m in vocabulaire if m.startswith(debut)]
        assert index.prefixe(debut) == attendu, debut
        assert index.prefixe(debut, limite=3) == attendu[:3], debut


def test_index_et_recherche_restent_justes_apres_des_remplacements():
    """Index : après 300 remplacements aléatoires de tickets, la recherche reste égale à la recherche naïve"""
    hasard, mots, tickets = _corpus_aleatoire(21, nb_tickets=60)
    index = IndexInverse()
    etat = {}
    for ticket in tickets:
        index.ajouter(ticket)
        etat[ticket.id] = ticket.sujet
    for _ in range(300):
        id_ticket = f"T{hasard.randrange(60):04d}"
        etat[id_ticket] = " ".join(hasard.choices(mots, k=hasard.randint(3, 8)))
        index.ajouter(fabriquer_ticket(id=id_ticket, sujet=etat[id_ticket], message=""))
    assert len(index) == 60
    for mot in set(mots):
        voulu = set(normaliser(mot))
        attendu = sorted(i for i, texte in etat.items() if voulu <= set(normaliser(texte))) if voulu else []
        assert index.rechercher(mot) == attendu, mot


# --------------------------------------------------------------------------- règles et volume


def test_bisect_et_heapq_interdits_dans_le_module():
    """Règle du projet : moteur_sav/index.py n'importe ni bisect ni heapq"""
    source = (RACINE / "moteur_sav" / "index.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:import|from)\s+(\w+)", source, flags=re.MULTILINE)
    assert "bisect" not in imports and "heapq" not in imports, imports


def test_volume():
    """Volume : 25 000 tickets sont indexés en quelques secondes, et une recherche répond en un instant"""
    hasard = random.Random(3)
    mots = [f"mot{i}" for i in range(2000)] + ["pot", "casse", "cochenilles"]
    index = IndexInverse()
    debut = time.perf_counter()
    for i in range(25000):
        index.ajouter(fabriquer_ticket(id=f"T{i}", sujet=" ".join(hasard.choices(mots, k=6)), message=" ".join(hasard.choices(mots, k=20))))
    assert time.perf_counter() - debut < 20
    debut = time.perf_counter()
    for _ in range(200):
        index.rechercher("pot casse")
        index.prefixe("cochen")
    assert time.perf_counter() - debut < 5
    assert len(index) == 25000


def test_nb_mots_compte_le_vocabulaire():
    """nb_mots : mots différents de l'index ; baisse quand un mot disparaît avec son dernier ticket"""
    index = indexer("pot cassé", "pot vase")
    assert index.nb_mots == 3                      # pot, casse, vase
    index.ajouter(fabriquer_ticket(id="T1", sujet="pot", message=""))   # T1 est réindexé : « casse » disparaît
    assert index.nb_mots == 2 and IndexInverse().nb_mots == 0


def test_fichier_d_exemple():
    """exemple_tickets.jsonl (13 lignes) : « pot cassé », « cochenilles », préfixes ; un ticket rejeté n'est pas indexé"""
    tickets, _ = charger_tickets(DONNEES / "exemple_tickets.jsonl")
    index = IndexInverse()
    for ticket in tickets:
        index.ajouter(ticket)
    assert len(index) == 10                                      # 13 lignes - 1 vide - 2 rejetées
    assert index.rechercher("pot cassé") == ["TCK-000001"]
    assert index.rechercher("Cochenilles") == ["TCK-000003"]
    assert index.rechercher("remboursement") == ["TCK-000011"]
    assert index.rechercher("double prélèvement") == []          # ce ticket (TCK-000006) a été rejeté : pas de client_id
    assert index.rechercher("pot cassé livraison", "OU") == ["TCK-000001", "TCK-000007"]
    assert index.prefixe("cochen") == ["cochenilles"]
    assert index.prefixe("co") == ["cochenilles", "code", "colis", "commande"]
    assert index.prefixe("co", limite=2) == ["cochenilles", "code"]


# --------------------------------------------------------------------------- jeu complet


def _fichier_complet():
    """Le fichier complet s'il est présent, sinon l'échantillon synthétique versionné."""
    complet = DONNEES / "tickets.jsonl"
    return complet if complet.exists() else DONNEES / "echantillon_tickets.jsonl"


def _index_complet():
    tickets, _ = charger_tickets(_fichier_complet(), copie=True)
    index = IndexInverse()
    for ticket in tickets:
        index.ajouter(ticket)
    return tickets, index


def test_jeu_complet():
    """Jeu complet : chaque résultat contient bien les mots cherchés ; aucun ticket oublié (vérifié sur 3 requêtes)"""
    tickets, index = _index_complet()
    assert len(index) == len(tickets)
    mots_par_id = {t.id: set(normaliser(f"{t.sujet} {t.message}")) for t in tickets}
    for requete in ("pot cassé", "colis", "remboursement facture"):
        voulus = set(normaliser(requete))
        attendu = sorted(i for i, m in mots_par_id.items() if voulus <= m)
        assert index.rechercher(requete) == attendu, requete
        assert index.rechercher(requete, "OU") == sorted(i for i, m in mots_par_id.items() if voulus & m), requete


# --------------------------------------------------------------------------- démo


def demo():
    """Réponses aux questions de la démo (index). Montre identifiant, catégorie et sujet, jamais le message."""
    tickets, index = _index_complet()
    par_id = {t.id: t for t in tickets}
    print(f" DÉMO SUR LES DONNÉES ({_fichier_complet().name}, traité sur une copie)")
    print(f"   {len(index)} tickets indexés, {len(index._index)} mots différents")
    for requete, mode in (("pot cassé", "ET"), ("pot cassé", "OU")):
        trouves = index.rechercher(requete, mode)
        print(f"\n   Tickets qui parlent de « {requete} » (mode {mode}) : {len(trouves)}")
        if mode == "ET":
            for id_ticket in trouves[:5]:
                t = par_id[id_ticket]
                print(f"     - {t.id} | {t.categorie} | {t.sujet}")
            if len(trouves) > 5:
                print(f"     ... et {len(trouves) - 5} autres")
    for debut in ("cochen", "cass", "livr"):
        print(f"\n   Mots qui commencent par « {debut} » : {index.prefixe(debut, limite=10)}")


if __name__ == "__main__":
    raise SystemExit(lancer(globals(), "VÉRIFICATION DE LA RECHERCHE (index.py)", bilan=demo))
