"""Tests de la démo (demo/calculs.py et demo/app.py) : les réponses aux cinq questions, et la confidentialité.

    python -m pytest                 # avec tous les tests du projet
    python -m tests.test_demo        # rapport lisible : OK / ÉCHEC

Les calculs sont testés seuls, sans streamlit ; l'application est lancée sans navigateur (AppTest) si
streamlit est installé. La règle principale : ni message brut ni client_id dans ce qui s'affiche.
"""

from datetime import datetime

from demo import calculs as c
from moteur_sav.modeles import PRIORITE_PAR_DEFAUT

from .fabrique import fabriquer_ticket
from .test_rapport import lancer

DONNEES = c.charger()          # l'extrait de 500 lignes si les données complètes ne sont pas là


def ticket(id, **champs):
    """Ticket de test avec un message et un client_id repérables dans toute sortie."""
    return fabriquer_ticket(id=id, message=f"MESSAGE-SECRET-{id}", client_id=f"CLI-SECRET-{id}", **champs)


# --------------------------------------------------------------------------- confidentialité

def test_une_ligne_affichable_n_a_ni_message_ni_client_id():
    """ligne_ticket() ne montre que id, catégorie, priorité, statut, échéance et sujet"""
    ligne = c.ligne_ticket(ticket("T1"))
    assert set(ligne) == {"id", "catégorie", "priorité", "statut", "échéance", "sujet"}
    assert "SECRET" not in " ".join(map(str, ligne.values()))


def test_aucune_sortie_de_la_demo_ne_contient_de_message_ni_de_client_id():
    """recherche, urgents et atelier ne laissent rien passer du message ni du client_id"""
    tickets = [ticket(f"T{i}", sujet="Pot cassé", priorite=1 + i % 4) for i in range(12)]
    par_id = {t.id: t for t in tickets}
    index = c.construire_index(tickets)
    sorties = [c.chercher(index, par_id, "secret", "OU")[1],              # le message est indexé...
               c.chercher(index, par_id, "pot cassé")[1],                  # ... mais jamais affiché
               [c.ligne_ticket(t) for t in c.plus_urgents(tickets)],
               c.Atelier(tickets).lignes()]
    assert "SECRET" not in str(sorties)


# --------------------------------------------------------------------------- 1. bilan

def test_le_bilan_compte_chaque_ligne_une_fois():
    """exploitables + écartés = lignes lues ; la somme des motifs = les écartés"""
    b = c.bilan(DONNEES["tickets"], DONNEES["rejets"])
    assert b["exploitables"] == len(DONNEES["tickets"])
    assert b["ecartes"] == sum(m["tickets"] for m in b["motifs"]) == len(DONNEES["rejets"])
    assert [m["tickets"] for m in b["motifs"]] == sorted((m["tickets"] for m in b["motifs"]), reverse=True)


def test_l_explication_des_estimations_donne_les_chiffres_et_les_regles_du_code():
    """explication_estimations() cite les deux nombres, P3, 72 h et l'heure fixée, tirés de l'ingestion"""
    texte = c.explication_estimations(326, 32)
    assert "326 tickets" in texte and "32 tickets" in texte
    assert "P3" in texte and "72 h" in texte and "minuit" in texte and "midi" in texte
    assert f"**P{PRIORITE_PAR_DEFAUT}**" in texte and "**P4** si elle dépassait 4 ou n'était pas lisible" in texte
    assert "priorite_estimee" in texte and "date_estimee" in texte


def test_chaque_motif_de_rejet_est_explique_dans_les_regles():
    """regles_nettoyage() : les 7 motifs de rejet de l'ingestion y figurent, une fois au moins chacun"""
    from moteur_sav import ingestion as ing
    motifs = {v for nom, v in vars(ing).items() if nom.startswith("MOTIF_")}
    assert len(motifs) == 7                                    # « priorite invalide » n'existe plus
    decisions = " ".join(r["décision"] for r in c.regles_nettoyage())
    assert [m for m in motifs if f"« {m} »" not in decisions] == []
    assert all(set(r) == {"cas", "décision", "écart"} for r in c.regles_nettoyage())


# --------------------------------------------------------------------------- 2. urgents

def test_les_plus_urgents_sont_ouverts_et_dans_l_ordre():
    """plus_urgents() : seulement des tickets ouverts, au plus 10, du plus au moins urgent"""
    tickets = [ticket(f"T{i}", cree_le=f"2026-03-{1 + i % 20:02d}T09:00:00", priorite=1 + i % 4,
                      statut=("ouvert", "en_cours", "resolu")[i % 3]) for i in range(60)]
    urgents = c.plus_urgents(tickets)
    attendus = sorted((t for t in tickets if t.statut == "ouvert"), key=lambda t: t.cle_urgence())[:10]
    assert [t.id for t in urgents] == [t.id for t in attendus]
    assert len(urgents) == 10 and all(t.statut == "ouvert" for t in urgents)


def test_moins_de_dix_tickets_ouverts():
    """plus_urgents() renvoie ce qu'il y a quand il y a moins de dix tickets ouverts, et [] sinon"""
    assert len(c.plus_urgents([ticket("A"), ticket("B", statut="resolu")])) == 1
    assert c.plus_urgents([]) == []


def test_la_complexite_affichee_suit_la_taille_de_la_file():
    """complexite_urgents() : O(log n) pour ajouter et extraire, O(1) pour consulter, niveaux = taille du tas"""
    lignes = {l["opération"]: l for l in c.complexite_urgents(12_000)}
    assert lignes["Ajouter un ticket"]["complexité"] == lignes["Extraire le plus urgent"]["complexité"] == "O(log n)"
    assert lignes["Consulter le plus urgent"]["complexité"] == "O(1)"
    assert "14 niveaux" in lignes["Ajouter un ticket"]["ici"]              # un tas de 12 000 cases : 14 niveaux
    assert "1 niveaux" in c.complexite_urgents(1)[0]["ici"]
    assert "0 niveaux" in c.complexite_urgents(0)[0]["ici"]


def test_chaque_etape_a_son_tableau_de_complexite():
    """les 5 tableaux de complexité ont la même forme, des coûts « O(...) », et citent nos nombres"""
    tableaux = {"lecture": c.complexite_lecture(500), "urgents": c.complexite_urgents(12_000),
                "recherche": c.complexite_recherche(24_592, 10_943), "historique": c.complexite_historique(),
                "repartition": c.complexite_repartition(300, 12)}
    for nom, lignes in tableaux.items():
        assert lignes, nom
        for ligne in lignes:
            assert set(ligne) == {"opération", "complexité", "ici"} and ligne["complexité"].startswith("O("), (nom, ligne)
    assert "500 lignes" in tableaux["lecture"][0]["ici"]
    assert all(l["complexité"] == "O(1)" for l in tableaux["historique"][:3])          # exécuter, annuler, rétablir
    assert "10943" in " ".join(l["ici"] for l in tableaux["recherche"])                 # la taille du vocabulaire
    assert "300 tickets" in tableaux["repartition"][0]["ici"] and "12 conseillers" in tableaux["repartition"][0]["ici"]


# --------------------------------------------------------------------------- 3. recherche

def test_la_recherche_renvoie_le_total_et_limite_l_affichage():
    """chercher() compte tous les tickets trouvés, n'en affiche que `limite`, et mesure sa durée"""
    tickets = [ticket(f"T{i}", sujet="Pot cassé") for i in range(25)] + [ticket("Z", sujet="Plante")]
    index, par_id = c.construire_index(tickets), {t.id: t for t in tickets}
    total, lignes, duree = c.chercher(index, par_id, "pot cassé", "ET", limite=10)
    assert (total, len(lignes)) == (25, 10) and duree >= 0
    assert c.chercher(index, par_id, "pot plante", "ET")[0] == 0
    assert c.chercher(index, par_id, "pot plante", "OU")[0] == 26
    assert c.chercher(index, par_id, "", "ET")[:2] == (0, [])        # requête vide : rien, sans erreur


def test_les_formes_d_un_mot_sont_comptees_une_par_une_puis_ensemble():
    """formes_du_mot() : une ligne par accord, et le total compte chaque ticket une seule fois"""
    sujets = ["Pot cassé"] * 3 + ["Pot cassée"] * 2 + ["Pot cassés"] + ["Pot cassées", "Plante"]
    tickets = [ticket(f"T{i}", sujet=s) for i, s in enumerate(sujets)]
    lignes, total = c.formes_du_mot(c.construire_index(tickets))
    assert [ligne["tickets trouvés"] for ligne in lignes] == [3, 2, 1, 1]
    assert lignes[0]["recherche"] == "pot cassé"
    assert total == 7                                   # le ticket « Plante » n'est dans aucune forme


# --------------------------------------------------------------------------- 4. annuler / rétablir

def test_atelier_action_annulation_retablissement():
    """une action, son annulation, son rétablissement ; les vrais tickets ne bougent pas"""
    vrai = ticket("T1", statut="ouvert", priorite=3)
    atelier = c.Atelier([vrai])
    atelier.faire(c.ACTIONS[1], "T1", 1)
    assert atelier.tickets["T1"].priorite == 1 and vrai.priorite == 3
    assert atelier.tickets["T1"].echeance < vrai.echeance          # l'échéance a été recalculée
    assert atelier.historique.annuler() and atelier.tickets["T1"].priorite == 3
    assert atelier.historique.retablir() and atelier.tickets["T1"].priorite == 1
    assert vrai.priorite == 3 and vrai.statut == "ouvert"          # l'original n'a jamais changé


def test_atelier_les_trois_actions_et_la_pile_de_retablissement():
    """statut, priorité et affectation se défont ; une nouvelle action vide le rétablissement"""
    atelier = c.Atelier([ticket("T1")])
    atelier.faire(c.ACTIONS[0], "T1", "resolu")
    atelier.faire(c.ACTIONS[2], "T1", "AG-01")
    assert atelier.lignes()[0]["conseiller"] == "AG-01" and atelier.lignes()[0]["statut"] == "resolu"
    assert len(atelier.historique.journal()) == 2
    atelier.historique.annuler()
    assert atelier.lignes()[0]["conseiller"] == "—"
    atelier.faire(c.ACTIONS[1], "T1", 2)                           # nouvelle action : le futur est caduc
    assert atelier.historique.retablir() is False


def test_atelier_refuse_une_valeur_invalide():
    """une priorité hors échelle est refusée et n'entre pas dans le journal"""
    atelier = c.Atelier([ticket("T1")])
    for mauvaise in (0, 9):
        try:
            atelier.faire(c.ACTIONS[1], "T1", mauvaise)
            raise AssertionError("priorité invalide acceptée")
        except ValueError:
            pass
    assert atelier.historique.journal() == []


# --------------------------------------------------------------------------- 5. répartition

def test_le_lot_ne_garde_que_les_non_resolus_recents():
    """lot_conseille() : statut non résolu et créé depuis la date donnée (incluse)"""
    tickets = [ticket("A", cree_le="2026-09-27T23:59:00"), ticket("B", cree_le="2026-09-28T00:00:00"),
               ticket("C", cree_le="2026-09-29T10:00:00", statut="resolu"),
               ticket("D", cree_le="2026-09-30T10:00:00", statut="en_cours")]
    assert [t.id for t in c.lot_conseille(tickets, c.LOT_DEPUIS)] == ["B", "D"]


def test_le_lot_par_defaut_suit_le_lot_type_quand_les_donnees_l_atteignent():
    """dates du lot type si les données vont jusqu'au 28/09, sinon les derniers jours des données"""
    assert c.lot_par_defaut([ticket("A", cree_le="2026-09-30T10:00:00")]) == (c.LOT_DEPUIS, c.LOT_DEBUT)
    depuis, debut = c.lot_par_defaut([ticket("A", cree_le="2026-01-10T10:41:00")])
    assert depuis == datetime(2026, 1, 7) and debut == datetime(2026, 1, 11, 8, 0)


def test_la_comparaison_et_sa_conclusion_disent_la_verite():
    """comparer() donne les deux taux sur le même lot ; conclusion() ne prétend pas un écart qui n'existe pas"""
    urgent = ticket("U", cree_le="2026-03-14T04:30:00", priorite=1)     # le glouton le sert d'abord
    ancien = ticket("A", cree_le="2026-03-13T09:00:00", priorite=3)
    agents = [c.Agent("AG-01", "A", frozenset({"livraison"}), 5), c.Agent("AG-02", "B", frozenset({"livraison"}), 5)]
    lignes = c.comparer([ancien, urgent], agents, datetime(2026, 3, 14, 8, 0))
    assert [l["délais tenus"] for l in lignes] == [1.0, 0.5]
    assert "gagne 50.0 points" in c.conclusion(lignes, 2)
    egal = [{"délais tenus": 0.4, "non affectés": 0}] * 2
    assert "aucune différence" in c.conclusion(egal, 10)
    pire = [{"délais tenus": 0.2, "non affectés": 0}, {"délais tenus": 0.4, "non affectés": 0}]
    assert "perd 20.0 points" in c.conclusion(pire, 10)


# --------------------------------------------------------------------------- l'application

def test_l_application_demarre_et_la_demo_d_annulation_marche():
    """l'application s'ouvre sans erreur, exécute puis annule une action, et n'affiche aucun client_id"""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return                                                      # streamlit facultatif : test ignoré
    app = AppTest.from_file(str(c.RACINE / "demo" / "app.py"), default_timeout=90).run()
    assert not app.exception, [e.value for e in app.exception]
    assert len(app.tabs) == 6

    def bouton(debut):
        return next(b for b in app.button if b.label.startswith(debut))

    bouton("Exécuter").click().run()
    assert not app.exception and "statut ->" in app.code[0].value
    textes = " ".join(d.value.to_string() for d in app.dataframe)      # to_string : jamais de colonnes abrégées
    assert "O(log V + r)" in textes and "O(n log n + n·a)" in textes and "O(1)" in textes   # complexités de chaque étape
    bouton("↶ Annuler").click().run()
    assert app.code[0].value == "(aucune action)"
    bouton("↷ Rétablir").click().run()
    assert "statut ->" in app.code[0].value
    vu = " ".join(str(e.value) for e in app.markdown) + textes
    assert "CLI-" not in vu


if __name__ == "__main__":
    raise SystemExit(lancer(globals(), "VÉRIFICATION DE LA DÉMO (demo/calculs.py et demo/app.py)"))
