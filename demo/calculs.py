"""Calculs de la démo : un par question de la démo. Aucun import de streamlit : testable seul.

Règle de la démo : on n'affiche jamais un message brut ni un client_id. Toutes les lignes
affichables passent par `ligne_ticket`, la seule fonction qui décide quels champs sortent.
"""

from __future__ import annotations

import copy
import importlib.util
import random
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from moteur_sav import ingestion as ing
from moteur_sav.affectation import NON_AFFECTES, affecter, affecter_naif, taux_sla
from moteur_sav.file_priorite import FilePriorite
from moteur_sav.historique import AffecterTicket, ChangerPriorite, ChangerStatut, Historique
from moteur_sav.index import IndexInverse
from moteur_sav.ingestion import charger_agents, charger_tickets
from moteur_sav.modeles import PRIORITE_PAR_DEFAUT, SLA_HEURES, STATUTS, Agent, Ticket, calculer_echeance

RACINE = Path(__file__).resolve().parents[1]
DONNEES = RACINE / "donnees"

#: Dates du lot type (répartition).
LOT_DEPUIS = datetime(2026, 9, 28)
LOT_DEBUT = datetime(2026, 10, 1, 8, 0)
DUREE_MINUTES = 20


#: Les graphiques de mesure déjà produits par les scripts de benchmarks/.
RESULTATS = RACINE / "benchmarks" / "resultats"


# --------------------------------------------------------------------------- données

def charger(donnees: Path = DONNEES) -> dict:
    """Charge les données complètes si elles sont là, sinon l'échantillon synthétique versionné (traité sur une copie)."""
    complet = (donnees / "tickets.jsonl").exists()
    fichier_tickets = donnees / ("tickets.jsonl" if complet else "echantillon_tickets.jsonl")
    fichier_agents = donnees / ("agents.csv" if (donnees / "agents.csv").exists() else "echantillon_conseillers.csv")
    tickets, rejets = charger_tickets(fichier_tickets, copie=True)
    return {
        "tickets": tickets, "rejets": rejets, "agents": charger_agents(fichier_agents, copie=True),
        "source": fichier_tickets.name, "complet": complet,
        "par_id": {t.id: t for t in tickets},
    }


def ligne_ticket(t: Ticket) -> dict:
    """Ce qu'on a le droit d'afficher d'un ticket : identifiant, catégorie, priorité, statut, échéance, sujet."""
    return {"id": t.id, "catégorie": t.categorie, "priorité": f"P{t.priorite}", "statut": t.statut,
            "échéance": t.echeance.strftime("%d/%m/%Y %H:%M"), "sujet": t.sujet}


# --------------------------------------------------------------------------- 1. bilan

def bilan(tickets: list[Ticket], rejets: list[dict]) -> dict:
    """Combien de tickets exploitables, combien d'écartés, et pour quels motifs."""
    motifs = Counter(r["motif"] for r in rejets)
    return {
        "exploitables": len(tickets), "ecartes": len(rejets),
        "motifs": [{"motif": m, "tickets": n} for m, n in motifs.most_common()],
        "priorites_estimees": sum(t.priorite_estimee for t in tickets),
        "dates_estimees": sum(t.date_estimee for t in tickets),
    }


def _heure(h: int) -> str:
    return {0: "minuit", 12: "midi"}.get(h, f"{h} h")


def explication_estimations(nb_priorites: int, nb_dates: int) -> str:
    """Ce que veulent dire « priorité estimée » et « date estimée ». Les valeurs viennent du code d'ingestion."""
    h = ing.HEURE_SI_ABSENTE
    return (
        f"**Priorité estimée : {nb_priorites} tickets.** Leur priorité était absente, vide, hors de l'échelle 1 à 4 "
        "ou illisible (« haute », une liste...). "
        f"Plutôt que de les écarter, on leur donne la priorité **P{PRIORITE_PAR_DEFAUT}** "
        f"({SLA_HEURES[PRIORITE_PAR_DEFAUT]} h de délai) si elle manquait ou était inférieure à 1, "
        f"**P{ing.PRIORITE_ILLISIBLE}** si elle dépassait 4 ou n'était pas lisible, "
        "et on les marque `priorite_estimee`, pour ne jamais faire passer cette valeur pour une vraie priorité. "
        "Elle décide pourtant de l'échéance, donc du rang dans la file d'urgence. "
        "Quand un conseiller fixe la priorité (action « Changer la priorité »), le marqueur repasse à faux.\n\n"
        f"**Date estimée : {nb_dates} tickets.** Leur date de création n'avait pas d'heure (par exemple `14/03/2026`). "
        f"On fixe l'heure d'après la priorité : **{_heure(h[1])}** pour P1 et P2 (hypothèse prudente : échéance au plus tôt), "
        f"**{_heure(h[3])}** pour P3 et P4. Ces tickets sont marqués `date_estimee`. "
        "Sans heure, il n'y aurait pas d'échéance exacte."
    )


def regles_nettoyage() -> list[dict]:
    """Les règles d'ingestion, une par ligne ; « écart » = règle plus souple qu'une lecture stricte."""
    canaux = ", ".join(f"{k} → {v}" for k, v in ing.CORRESPONDANCE_CANAUX.items())
    categories = ", ".join(f"{k} → {v}" for k, v in ing.CORRESPONDANCE_CATEGORIES.items())
    h = ing.HEURE_SI_ABSENTE
    return [
        {"cas": "Ligne vide", "décision": "ignorée (ni ticket, ni rejet)", "écart": ""},
        {"cas": "Ligne JSON tronquée ou qui n'est pas un objet", "décision": f"rejet « {ing.MOTIF_JSON} »", "écart": ""},
        {"cas": "id, cree_le ou client_id absent ; ni sujet ni message",
         "décision": f"rejet « {ing.MOTIF_CHAMP} »", "écart": ""},
        {"cas": "Message vide, mais sujet présent", "décision": "ticket gardé (le sujet donne le problème)", "écart": "oui"},
        {"cas": "Date : ISO avec T ou espace", "décision": "lue telle quelle", "écart": ""},
        {"cas": "Date : JJ/MM/AAAA, « 01 May 2026 », heure 13h29", "décision": "convertie en ISO (conversion exacte)", "écart": "oui"},
        {"cas": "Date sans heure", "décision": f"heure fixée : {_heure(h[1])} (P1, P2) ou {_heure(h[3])} (P3, P4), `date_estimee`",
         "écart": ""},
        {"cas": "Date vide, illisible ou impossible (30 février)", "décision": f"rejet « {ing.MOTIF_DATE} »", "écart": ""},
        {"cas": "Priorité « P2 », « 2 », 2.0", "décision": "lue comme 2", "écart": ""},
        {"cas": "Priorité « urgent »", "décision": "lue comme 1", "écart": "oui"},
        {"cas": "Priorité absente, vide ou inférieure à 1",
         "décision": f"P{PRIORITE_PAR_DEFAUT}, `priorite_estimee`", "écart": ""},
        {"cas": "Priorité supérieure à 4", "décision": "P4, `priorite_estimee`", "écart": "oui"},
        {"cas": "Priorité illisible (« haute », « critique », une liste, NaN...)",
         "décision": f"P{ing.PRIORITE_ILLISIBLE}, `priorite_estimee` (jamais de rejet pour une priorité)", "écart": "oui"},
        {"cas": "Canal : casse et espaces variables", "décision": "mis en minuscules, espaces retirés", "écart": ""},
        {"cas": f"Canal : {', '.join(ing.CORRESPONDANCE_CANAUX)}", "décision": canaux, "écart": "oui"},
        {"cas": "Canal absent ou vide", "décision": f"« {ing.CANAL_PAR_DEFAUT} » (le canal ne sert à aucune décision)", "écart": "oui"},
        {"cas": "Canal inconnu", "décision": f"rejet « {ing.MOTIF_CANAL} »", "écart": ""},
        {"cas": "Catégorie absente ou vide", "décision": f"« {ing.CATEGORIE_PAR_DEFAUT} »", "écart": "oui"},
        {"cas": "Catégorie : variantes vues dans le fichier", "décision": categories, "écart": "oui"},
        {"cas": "Catégorie inconnue", "décision": f"rejet « {ing.MOTIF_CATEGORIE} »", "écart": ""},
        {"cas": "Statut absent ou vide", "décision": "« ouvert »", "écart": ""},
        {"cas": "Statut inconnu", "décision": f"rejet « {ing.MOTIF_STATUT} »", "écart": ""},
        {"cas": "Même id, copie exacte d'un ticket gardé", "décision": f"rejet « {ing.MOTIF_DOUBLON} »", "écart": ""},
        {"cas": "Même id, contenu différent", "décision": "gardé sous un nouvel id (TCK-000042-2, -3...)", "écart": "oui"},
        {"cas": "Fichier original", "décision": f"jamais modifié : on lit une copie en lecture seule (`{ing.NOM_DOSSIER_COPIES}/`)",
         "écart": "oui"},
    ]


# --------------------------------------------------------------------------- 2. urgents

def plus_urgents(tickets: list[Ticket], n: int = 10) -> list[Ticket]:
    """Les n tickets ouverts les plus urgents, extraits de NOTRE file de priorité."""
    file: FilePriorite[Ticket] = FilePriorite()
    for t in tickets:
        if t.statut == "ouvert":
            file.ajouter(t, t.cle_urgence())
    return [file.extraire() for _ in range(min(n, len(file)))]


def _ligne(operation: str, complexite: str, ici: str) -> dict:
    """Une ligne des tableaux de complexité : l'opération, son coût, et ce que ça donne sur nos données."""
    return {"opération": operation, "complexité": complexite, "ici": ici}


def complexite_lecture(nb_lignes: int) -> list[dict]:
    """Ingestion : une seule lecture du fichier."""
    return [
        _ligne("Lire et nettoyer le fichier", "O(L)", f"{nb_lignes} lignes lues une seule fois, L = nombre de lignes"),
        _ligne("Repérer un identifiant en double", "O(1) en moyenne", "dictionnaire : identifiant → versions déjà vues"),
    ]


def complexite_urgents(nb_ouverts: int) -> list[dict]:
    """File de priorité : le coût de chaque opération de la file de priorité, pour `nb_ouverts` tickets."""
    niveaux = nb_ouverts.bit_length()          # nombre de niveaux d'un tas binaire de cette taille
    return [
        _ligne("Ajouter un ticket", "O(log n)", f"au plus {niveaux} niveaux à remonter, sur {nb_ouverts} tickets"),
        _ligne("Consulter le plus urgent", "O(1)", "une lecture : il est toujours à la racine"),
        _ligne("Extraire le plus urgent", "O(log n)", f"au plus {niveaux} niveaux à descendre : 10 extractions pour ce tableau"),
        _ligne("Garder la file à jour (un ticket arrive)", "O(log n)",
               "contre O(n log n) en retriant toute la liste (mesuré ci-dessous)"),
    ]


def complexite_recherche(nb_tickets: int, nb_mots: int) -> list[dict]:
    """Recherche : le coût de chaque opération de recherche, pour nos tickets et notre vocabulaire."""
    return [
        _ligne("Indexer un ticket", "O(m)", f"m = nombre de mots du ticket ; {nb_tickets} tickets indexés une seule fois"),
        _ligne("Recherche ET", "O(plus petit ensemble)", "on croise les listes en partant de la plus petite"),
        _ligne("Recherche OU", "O(somme des ensembles)", "on réunit les listes de chaque mot"),
        _ligne("Début de mot", "O(log V + r)",
               f"V = {nb_mots} mots dans le vocabulaire : environ {nb_mots.bit_length()} essais ; r = mots trouvés"),
        _ligne("Sans index : balayer les tickets", "O(n)", f"relire les {nb_tickets} tickets à chaque recherche"),
    ]


def complexite_historique() -> list[dict]:
    """Historique : annuler et rétablir, avec deux piles."""
    return [
        _ligne("Exécuter une action", "O(1)", "on ajoute en fin de pile ; vider « rétablir » = remplacer la liste"),
        _ligne("Annuler", "O(1)", "on retire la dernière action de la pile « annuler » et on l'inverse"),
        _ligne("Rétablir", "O(1)", "on retire la dernière action de la pile « rétablir » et on la réapplique"),
        _ligne("Afficher le journal", "O(k)", "k = nombre d'actions en vigueur"),
    ]


def complexite_repartition(nb_tickets: int, nb_agents: int) -> list[dict]:
    """Répartition : le glouton passe par la file de priorité, le naïf par un tri."""
    return [
        _ligne("Répartition gloutonne", "O(n log n + n·a)",
               f"n = {nb_tickets} tickets : n ajouts et n extractions dans la file ; a = {nb_agents} conseillers à comparer par ticket"),
        _ligne("Répartition naïve", "O(n log n + n·a)", "un tri par date de création, puis le premier conseiller libre"),
        _ligne("Taux de délais tenus", "O(n)", "chaque ticket est vérifié une fois contre son échéance"),
    ]


# --------------------------------------------------------------------------- 3. recherche

def construire_index(tickets: list[Ticket]) -> IndexInverse:
    """Index inversé de tous les tickets (sujet et message)."""
    index = IndexInverse()
    for t in tickets:
        index.ajouter(t)
    return index


def chercher(index: IndexInverse, par_id: dict[str, Ticket], requete: str, mode: str = "ET",
             limite: int = 10) -> tuple[int, list[dict], float]:
    """(nombre de tickets trouvés, `limite` premières lignes affichables, durée en microsecondes)."""
    debut = time.perf_counter()
    ids = index.rechercher(requete, mode)
    duree = (time.perf_counter() - debut) * 1e6
    return len(ids), [ligne_ticket(par_id[i]) for i in ids[:limite]], duree


#: Les quatre accords du mot « cassé » : sans racinisation, ce sont quatre mots différents.
FORMES_CASSE = ("cassé", "cassée", "cassés", "cassées")


def formes_du_mot(index: IndexInverse, base: str = "pot", formes: tuple[str, ...] = FORMES_CASSE
                  ) -> tuple[list[dict], int]:
    """([{recherche, tickets}, ...] une ligne par forme, nombre de tickets trouvés par l'une ou l'autre)."""
    trouves = {forme: set(index.rechercher(f"{base} {forme}")) for forme in formes}
    lignes = [{"recherche": f"{base} {forme}", "tickets trouvés": len(ids)} for forme, ids in trouves.items()]
    return lignes, len(set().union(*trouves.values()))


# --------------------------------------------------------------------------- 4. annuler / rétablir

#: Les trois actions de l'historique, avec ce qu'on peut leur donner comme valeur.
ACTIONS = ("Changer le statut", "Changer la priorité", "Affecter à un conseiller")


class Atelier:
    """Un historique branché sur des COPIES de tickets : les vrais tickets ne sont jamais modifiés."""

    def __init__(self, tickets: list[Ticket]) -> None:
        self.tickets = {t.id: copy.copy(t) for t in tickets}
        self.affectations: dict[str, list[str]] = {}
        self.historique = Historique()

    def faire(self, action: str, ticket_id: str, valeur: str | int) -> None:
        """Exécute une des trois actions sur le ticket `ticket_id`."""
        ticket = self.tickets[ticket_id]
        if action == ACTIONS[0]:
            self.historique.executer(ChangerStatut(ticket, valeur))
        elif action == ACTIONS[1]:
            self.historique.executer(ChangerPriorite(ticket, int(valeur)))
        else:
            self.historique.executer(AffecterTicket(self.affectations, ticket_id, valeur))

    def lignes(self) -> list[dict]:
        """Les tickets de l'atelier, avec le conseiller éventuel."""
        affecte = {i: agent for agent, ids in self.affectations.items() for i in ids}
        return [{**ligne_ticket(t), "conseiller": affecte.get(t.id, "—")} for t in self.tickets.values()]


# --------------------------------------------------------------------------- 5. répartition

def lot_par_defaut(tickets: list[Ticket]) -> tuple[datetime, datetime]:
    """(créés depuis, traités à partir de). Les dates du lot type si les données les atteignent,
    sinon les 3 derniers jours des données : elles n'atteignent pas la date du lot type."""
    derniere = max(t.cree_le for t in tickets)
    if derniere >= LOT_DEPUIS:
        return LOT_DEPUIS, LOT_DEBUT
    jour = derniere.replace(hour=0, minute=0, second=0, microsecond=0)
    return jour - timedelta(days=3), jour + timedelta(days=1, hours=8)


def lot_conseille(tickets: list[Ticket], depuis: datetime) -> list[Ticket]:
    """Les tickets non résolus créés depuis `depuis`."""
    return [t for t in tickets if t.statut != "resolu" and t.cree_le >= depuis]


def comparer(lot: list[Ticket], agents: list[Agent], debut: datetime) -> list[dict]:
    """Taux de délais tenus du glouton et du naïf, sur le MÊME lot."""
    lignes = []
    for nom, repartir in (("Glouton (du plus urgent au moins urgent)", affecter),
                          ("Naïf (premier arrivé, premier conseiller libre)", affecter_naif)):
        affectations = repartir(lot, agents)
        lignes.append({"répartition": nom, "délais tenus": taux_sla(affectations, lot, debut, DUREE_MINUTES),
                       "non affectés": len(affectations[NON_AFFECTES])})
    return lignes


def conclusion(lignes: list[dict], nb_lot: int) -> str:
    """Une phrase chiffrée, qui dit aussi quand il n'y a pas de différence."""
    glouton, naif = lignes
    ecart = (glouton["délais tenus"] - naif["délais tenus"]) * 100
    base = (f"Sur {nb_lot} tickets, le glouton tient {glouton['délais tenus']:.1%} des délais "
            f"et le naïf {naif['délais tenus']:.1%}")
    if abs(ecart) < 0.05:
        return base + " : aucune différence sur ce lot."
    sens = "gagne" if ecart > 0 else "perd"
    return base + f" : le glouton {sens} {abs(ecart):.1f} points."


#: Valeurs proposées pour les actions de l'atelier.
STATUTS_PROPOSES = tuple(STATUTS)
PRIORITES_PROPOSEES = tuple(sorted(SLA_HEURES))


# --------------------------------------------------------------------------- mesure du tas (file de priorité)

def _benchmark_file_priorite():
    """Importe benchmarks/benchmark_file_priorite.py (le dossier benchmarks/ n'est pas un paquet)."""
    chemin = RACINE / "benchmarks" / "benchmark_file_priorite.py"
    spec = importlib.util.spec_from_file_location("benchmark_file_priorite", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mesurer_tas(tailles: tuple[int, ...] = (1_000, 10_000, 100_000), repetitions: int = 3) -> list[dict]:
    """Mesure en direct n ajouts puis n extractions : notre tas, heapq et une liste retriée.

    Mêmes fonctions et même graine que benchmarks/benchmark_file_priorite.py. La liste retriée
    n'est pas mesurée au-delà de LIMITE_LISTE (plusieurs minutes).
    """
    g = _benchmark_file_priorite()
    rng = random.Random(42)
    variantes = {"tas maison": g.avec_file_maison, "heapq": g.avec_heapq,
                 "liste retriée": g.avec_liste_retriee}
    lignes = []
    for n in tailles:
        cles = [rng.randint(0, 10**6) for _ in range(n)]  # mêmes clés pour les trois
        for methode, fonction in variantes.items():
            if methode == "liste retriée" and n > g.LIMITE_LISTE:
                continue
            temps = g.chrono(lambda: fonction(cles), repetitions)
            lignes.append({"n": n, "methode": methode, "temps_ms": round(1000 * temps, 3)})
    return lignes


def facteurs_croissance(lignes: list[dict]) -> list[dict]:
    """Par combien le temps de chaque méthode est multiplié d'une taille à la suivante."""
    par_methode: dict[str, dict[int, float]] = {}
    for l in lignes:
        par_methode.setdefault(l["methode"], {})[l["n"]] = l["temps_ms"]
    resultat = []
    for methode, mesures in par_methode.items():
        tailles = sorted(mesures)
        for avant, apres in zip(tailles, tailles[1:]):
            resultat.append({
                "méthode": methode,
                "taille": f"{avant:,} → {apres:,}".replace(",", " "),
                "n multiplié par": apres // avant,
                "temps multiplié par": round(mesures[apres] / mesures[avant], 1),
            })
    return resultat


# --------------------------------------------------------------------------- détails de la répartition (répartition)

REPARTITIONS = {"gloutonne": affecter, "naïve": affecter_naif}


def perdus_d_avance(lot: list[Ticket], debut: datetime) -> set[str]:
    """Tickets dont l'échéance tombe avant la fin du tout premier traitement : impossibles à tenir."""
    premiere_fin = debut + timedelta(minutes=DUREE_MINUTES)
    return {t.id for t in lot if t.echeance < premiere_fin}


def _tenus(affectations: dict[str, list[str]], lot: list[Ticket], debut: datetime) -> set[str]:
    """Identifiants des tickets finis au plus tard à leur échéance (même modèle que taux_sla)."""
    echeances = {t.id: t.echeance for t in lot}
    pas = timedelta(minutes=DUREE_MINUTES)
    return {ticket_id for agent_id, ids in affectations.items() if agent_id != NON_AFFECTES
            for k, ticket_id in enumerate(ids, start=1) if debut + k * pas <= echeances[ticket_id]}


def details_repartition(lot: list[Ticket], agents: list[Agent], debut: datetime) -> dict:
    """Maximum atteignable, charge par conseiller et délais tenus par priorité, pour les deux répartitions."""
    perdus = perdus_d_avance(lot, debut)
    charges, par_priorite = [], []
    for nom, repartir in REPARTITIONS.items():
        affectations = repartir(lot, agents)
        tenus = _tenus(affectations, lot, debut)
        charges += [{"conseiller": a.agent_id, "répartition": nom, "tickets": len(affectations[a.agent_id]),
                     "capacité": a.capacite_jour} for a in agents]
        for p in sorted(SLA_HEURES):
            du_niveau = [t for t in lot if t.priorite == p]
            if du_niveau:
                par_priorite.append({"priorité": f"P{p}", "série": nom,
                                     "taux": sum(t.id in tenus for t in du_niveau) / len(du_niveau)})
    for p in sorted(SLA_HEURES):
        du_niveau = [t for t in lot if t.priorite == p]
        if du_niveau:
            par_priorite.append({"priorité": f"P{p}", "série": "maximum atteignable",
                                 "taux": sum(t.id not in perdus for t in du_niveau) / len(du_niveau)})
    return {"perdus": len(perdus), "maximum": (len(lot) - len(perdus)) / len(lot) if lot else 0.0,
            "charges": charges, "par_priorite": par_priorite}


def exemple_a_la_main() -> list[dict]:
    """Le petit exemple de la répartition : deux tickets inventés, deux conseillers, début le 14/03 à 8 h."""
    debut = datetime(2026, 3, 14, 8, 0)

    def inventer(id_: str, cree_le: str, priorite: int) -> Ticket:
        cree = datetime.fromisoformat(cree_le)
        return Ticket(id_, cree, "CLI-EXEMPLE", "email", "livraison", priorite, "", "", "ouvert",
                      calculer_echeance(cree, priorite))

    lot = [inventer("A", "2026-03-13T09:00:00", 3), inventer("U", "2026-03-14T04:30:00", 1)]
    agents = [Agent("AG-01", "Exemple", frozenset({"livraison"}), 2),
              Agent("AG-02", "Exemple", frozenset({"livraison"}), 2)]
    echeances = {t.id: t.echeance for t in lot}
    lignes = []
    for nom, repartir in REPARTITIONS.items():
        for agent_id, ids in repartir(lot, agents).items():
            if agent_id == NON_AFFECTES:
                continue
            for k, ticket_id in enumerate(ids, start=1):
                fin = debut + k * timedelta(minutes=DUREE_MINUTES)
                lignes.append({"répartition": nom, "conseiller": agent_id, "position": k, "ticket": ticket_id,
                               "fin": f"{fin:%H:%M}", "échéance": f"{echeances[ticket_id]:%d/%m %H:%M}",
                               "tenu": "oui" if fin <= echeances[ticket_id] else "non"})
    return lignes


def _structure(structure: str, type_python: str, ou: str, pourquoi: str) -> dict:
    return {"structure": structure, "type Python": type_python, "où": ou, "pourquoi": pourquoi}


#: Les structures de données de la répartition, et la raison de chaque choix.
STRUCTURES_ETAPE5: list[dict] = [
    _structure("File de priorité", "FilePriorite[Ticket] (le tas de la file de priorité)", "répartition gloutonne",
               "sortir les tickets du plus urgent au moins urgent, en log n par ticket, "
               "avec le premier arrivé d'abord à égalité"),
    _structure("Dictionnaire des affectations", "dict[str, list[str]]", "résultat des deux répartitions",
               "la liste d'un conseiller en temps constant ; la position d'un ticket donne son heure de fin"),
    _structure("Liste de tickets par conseiller", "list[str]", "dans le dictionnaire",
               "garde l'ordre de traitement ; sa longueur est la charge du conseiller"),
    _structure("Liste des conseillers", "list[Agent]", "entrée des deux fonctions",
               "la naïve a besoin de leur ordre : elle prend le premier qui a de la place"),
    _structure("Tuple (taux, identifiant)", "tuple dans min", "choix du conseiller (gloutonne)",
               "le moins occupé gagne ; l'égalité se règle par le plus petit identifiant"),
    _structure("Tri stable", "sorted sur la date de création", "répartition naïve",
               "ordre de création ; à date égale, l'ordre du fichier est gardé"),
    _structure("Dictionnaire des échéances", "dict[str, datetime]", "taux de délais tenus",
               "retrouver une échéance par identifiant en temps constant : n opérations au lieu de n × n"),
    _structure("Durée de traitement", "timedelta", "taux de délais tenus",
               "ajouter directement « k × 20 minutes » à l'heure de début"),
    _structure("Compétences d'un conseiller", "frozenset[str]", "classe Agent",
               "savoir en temps constant si un conseiller traite une catégorie"),
]


#: Les structures de données de chaque étape (une entrée par onglet de la démo).
STRUCTURES: dict[int, list[dict]] = {
    1: [
        _structure("Dictionnaire brut", "dict", "chaque ligne lue",
                   "json.loads le produit directement ; accès à un champ par son nom"),
        _structure("Classes Ticket et Agent", "classe @dataclass", "modeles.py",
                   "champs nommés et typés ; == compare tous les champs, ce qui repère les copies exactes"),
        _structure("Exception LigneInvalide", "classe (hérite de ValueError)", "construire_ticket",
                   "porte le motif et le détail ; la lecture l'attrape et continue sans jamais planter"),
        _structure("Tables de correspondance", "dict", "canaux, catégories, mois, heure si absente",
                   "une variante donne sa valeur officielle en temps constant ; une règle de plus = une ligne de plus"),
        _structure("Identifiants déjà attribués", "set", "doublons",
                   "« déjà vu ? » en temps constant, au lieu de parcourir une liste"),
        _structure("Versions d'un identifiant", "dict[str, list[Ticket]]", "doublons",
                   "retrouver les tickets déjà gardés sous un identifiant, pour repérer une copie exacte"),
        _structure("Tickets et rejets", "list", "résultat de la lecture",
                   "gardent l'ordre du fichier ; ajout en fin en temps constant"),
        _structure("Valeurs autorisées, compétences", "frozenset", "CANAUX, CATEGORIES, Agent",
                   "test d'appartenance en temps constant, et impossibles à modifier par erreur"),
        _structure("Expressions régulières", "re.Pattern", "dates",
                   "reconnaître trois formats de date (ISO, français, mois en lettres)"),
    ],
    2: [
        _structure("Tas binaire rangé dans une liste", "list", "FilePriorite._tas",
                   "case i : enfants 2i+1 et 2i+2, parent (i-1)//2 ; aucun objet nœud, accès par indice en temps constant"),
        _structure("Case du tas", "tuple (priorité, numéro, élément)", "chaque case",
                   "comparé case par case : urgence d'abord, puis ordre d'arrivée ; deux tickets ne sont jamais comparés"),
        _structure("Clé d'urgence", "tuple (échéance, priorité, création)", "Ticket.cle_urgence",
                   "trois critères dans l'ordre, sans écrire de code de comparaison"),
        _structure("Compteur d'arrivée", "int", "FilePriorite._compteur",
                   "unique et croissant : à urgence égale, premier arrivé, premier servi"),
        _structure("File de priorité", "classe générique FilePriorite[T]", "étapes 2 et 5",
                   "cache la liste interne : on n'utilise que ajouter, consulter, extraire"),
        _structure("Écarté : liste retriée à chaque ajout", "list + sort", "benchmark",
                   "chaque ajout retrie toute la liste : mesurée 28 fois plus lente que notre tas à 10 000 éléments"),
    ],
    3: [
        _structure("Deux piles : annuler et rétablir", "list (utilisée par la fin)", "Historique",
                   "la dernière action faite est la première annulée ; append et pop en fin en temps constant"),
        _structure("Action et ses sous-classes", "classe abstraite + héritage",
                   "ChangerStatut, ChangerPriorite, AffecterTicket",
                   "patron commande : chaque action sait s'appliquer et s'inverser ; l'historique ne connaît pas les tickets"),
        _structure("État d'avant", "tuple (priorité, estimée, échéance)", "ChangerPriorite",
                   "trois valeurs gardées ensemble et restaurées en une ligne"),
        _structure("Affectations", "dict[str, list[str]]", "AffecterTicket",
                   "la liste d'un conseiller en temps constant ; le ticket est retiré en fin de liste"),
        _structure("Liste créée ?", "bool", "AffecterTicket",
                   "remettre le dictionnaire exactement dans son état d'avant"),
        _structure("Écarté : copie complète du ticket à chaque action", "—", "—",
                   "coûte de la mémoire, et ne couvre pas les affectations, qui ne sont pas dans le ticket"),
    ],
    4: [
        _structure("Index inversé", "dict[str, set[str]]", "IndexInverse._index",
                   "les tickets d'un mot en temps constant, comme l'index d'un livre ; l'ensemble évite les doublons"),
        _structure("Recherche ET", "set (intersection)", "rechercher",
                   "on part du plus petit ensemble : le coût dépend du mot le plus rare"),
        _structure("Recherche OU", "set (union)", "rechercher",
                   "réunit les tickets de chaque mot, sans doublon"),
        _structure("Vocabulaire trié + dichotomie", "list[str]", "prefixe, borne_inferieure",
                   "début de mot en log m ; vocabulaire retrié seulement quand l'index a changé"),
        _structure("Mots de chaque ticket", "dict[str, set[str]]", "IndexInverse._mots_par_id",
                   "retirer les anciens mots quand un ticket est réindexé"),
        _structure("Mots vides", "frozenset", "normaliser",
                   "« le », « est »… écartés en temps constant par mot"),
    ],
    5: STRUCTURES_ETAPE5,
}
