"""Ingestion robuste des tickets (JSON Lines) et des agents (CSV).

Le chargement ne plante jamais : chaque ligne devient un `Ticket` propre ou un rejet
`{"ligne", "motif", "detail"}`. Principe : on ne rejette que si l'on ne peut pas réparer
sans inventer une valeur ; sinon on garde le ticket, on applique une règle simple et on le
SIGNALE (`priorite_estimee`, `date_estimee`) pour qu'une valeur devinée ne passe pas pour
une valeur lue. Les règles sont des constantes lisibles en haut de ce fichier.

- champs obligatoires : id, cree_le, client_id (absent, None ou vide -> rejet
  « champ manquant ») ; `canal` et `categorie` absents ou vides reçoivent « autre »
  (CHAMPS_AVEC_DEFAUT) ;
- `message` absent ou vide -> chaîne vide, le ticket est GARDÉ si le `sujet` existe ;
  rejet « champ manquant » (détail « message ») seulement si sujet ET message sont vides ;
- `cree_le` : ISO 8601 (T ou espace), JJ/MM/AAAA ou « 01 May 2026 », heure
  facultative (« 09:32 », « 13h29 », « 13H29 ») ; sans heure, l'heure est fixée
  selon la priorité (HEURE_SI_ABSENTE) et `date_estimee = True` ; aucune date
  reconnue ou date impossible -> rejet « date invalide » ;
- `canal` : espaces retirés, minuscules ; « courrier » et « fax » ramenés à « email »
  (CORRESPONDANCE_CANAUX) ; sinon valeur dans CANAUX, ou « canal inconnu » ;
- `categorie` : variantes ramenées par CORRESPONDANCE_CATEGORIES ; sinon valeur dans
  CATEGORIES, ou « categorie inconnue » ;
- `priorite` : voir normaliser_priorite (« urgent » -> 1, < 1 -> 3, > 4 -> 4, illisible -> 4) ;
  une priorité ne provoque jamais de rejet : le ticket est gardé et marqué `priorite_estimee` ;
- `sujet` absent : chaîne vide ; `statut` absent : « ouvert » ; statut hors
  STATUTS : rejet « statut inconnu » ;
- doublons : copie exacte -> rejet « identifiant en double » ; même id avec
  un contenu différent -> ticket gardé sous un nouvel id unique (« TCK-000042-2 ») ;
- une ligne qui n'est pas un objet JSON valide : rejet « json invalide » ;
- les lignes vides sont ignorées (ni ticket, ni rejet) ;
- les données peuvent être traitées sur une COPIE (`copie=True`) : le fichier original
  n'est jamais ouvert en écriture ni modifié (voir copier_donnees).
Ordre des vérifications : JSON, champs obligatoires, date, canal, catégorie,
priorité, statut, doublon.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .modeles import (  # noqa: F401  (tout sera utile)
    CANAUX,
    CATEGORIES,
    PRIORITE_PAR_DEFAUT,
    SLA_HEURES,
    STATUTS,
    Agent,
    Ticket,
    calculer_echeance,
)

# Les six champs obligatoires.
CHAMPS_OBLIGATOIRES = ("id", "cree_le", "client_id", "canal", "categorie", "message")

# Parmi eux, ceux qui reçoivent une valeur par défaut (« autre ») au lieu d'un rejet
# quand ils sont absents ou vides (choix de conception) : voir CANAL_PAR_DEFAUT et
# CATEGORIE_PAR_DEFAUT. Les autres champs obligatoires provoquent un rejet.
CHAMPS_AVEC_DEFAUT = ("canal", "categorie")

# `message` reste obligatoire, mais un message absent ou vide est accepté (chaîne vide) à
# condition que le sujet existe : ni l'urgence, ni l'échéance, ni la répartition n'en dépendent.
CHAMPS_VIDES_SI_SUJET = ("message",)

#: Canal appliqué quand le champ est absent ou vide (choix de conception).
CANAL_PAR_DEFAUT = "autre"

#: Canaux hors liste rencontrés dans les données, ramenés à un canal officiel (choix de conception).
CORRESPONDANCE_CANAUX: dict[str, str] = {
    "courrier": "email",  # écrit, sans réponse immédiate
    "fax": "email",
}

#: Catégorie appliquée quand le champ est absent ou vide (choix de conception).
CATEGORIE_PAR_DEFAUT = "autre"

#: Variantes rencontrées dans les données, ramenées à une catégorie officielle (clés en minuscules).
CORRESPONDANCE_CATEGORIES: dict[str, str] = {
    "livraisons": "livraison",
    "sav": "facturation",
    "remboursement": "facturation",
}

# Motifs de rejet (valeurs exactes attendues par les tests)
MOTIF_JSON = "json invalide"
MOTIF_CHAMP = "champ manquant"
MOTIF_DATE = "date invalide"
MOTIF_CANAL = "canal inconnu"
MOTIF_CATEGORIE = "categorie inconnue"
MOTIF_STATUT = "statut inconnu"
MOTIF_DOUBLON = "identifiant en double"


class LigneInvalide(ValueError):
    """Erreur interne : porte le motif et le détail du rejet."""

    def __init__(self, motif: str, detail: str = "") -> None:
        super().__init__(motif)
        self.motif = motif
        self.detail = detail


#: Priorité donnée à une valeur illisible : la moins urgente (choix de conception).
PRIORITE_ILLISIBLE = 4


def normaliser_priorite(valeur: object) -> tuple[int, bool]:
    """Convertit la priorité brute en entier 1 à 4.

    Renvoie (priorité, estimée). Règles retenues, d'après les
    valeurs rencontrées dans les données :
    - absente, None ou chaîne vide -> (3, True) ;
    - « urgent » (casse et espaces libres) -> (1, False) ;
    - entier, flottant (partie entière), chaîne « 2 » ou « P2 » -> ce nombre ;
    - nombre inférieur à 1 -> (3, True) ; supérieur à 4 -> (4, True) ;
    - valeur illisible (« haute », « P », liste, objet, NaN, infini) -> (4, True) : le ticket est gardé,
      au plus bas niveau d'urgence (PRIORITE_ILLISIBLE), et signalé comme estimé.
    Exemples : 2 -> (2, False) ; "P2" -> (2, False) ; "P7" -> (4, True) ; 0 -> (3, True) ; "haute" -> (4, True).
    """
    # 1. Absente ou vide : valeur par défaut, signalée.
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return PRIORITE_PAR_DEFAUT, True

    # 2. Ramener la valeur à un entier.
    if isinstance(valeur, int):  # pas de contrôle des booléens : absents du fichier
        nombre = valeur
    elif isinstance(valeur, float):
        # NaN et l'infini n'ont pas de partie entière.
        if not math.isfinite(valeur):
            return PRIORITE_ILLISIBLE, True
        nombre = int(valeur)  # 2.7 -> 2
    elif isinstance(valeur, str):
        texte = valeur.strip().upper()
        if texte == "URGENT":
            return 1, False
        if texte.startswith("P"):
            texte = texte[1:]
        try:
            nombre = int(texte)
        except ValueError:
            return PRIORITE_ILLISIBLE, True  # « haute », « P », « PP2 »...
    else:
        return PRIORITE_ILLISIBLE, True  # liste, objet JSON...

    # 3. Ramener l'entier dans la plage 1 à 4 ; une valeur corrigée est signalée.
    if nombre < 1:
        return PRIORITE_PAR_DEFAUT, True
    if nombre > 4:
        return 4, True
    return nombre, False


def _texte_obligatoire(brut: dict, champ: str) -> str:
    """Renvoie le champ sans espaces autour ; rejet « champ manquant » sinon."""
    valeur = brut.get(champ)
    # Absent (get renvoie None), None, autre type qu'une chaîne, ou chaîne vide.
    if not isinstance(valeur, str) or not valeur.strip():
        raise LigneInvalide(MOTIF_CHAMP, champ)
    return valeur.strip()


#: Heure fixée quand la date n'en a pas : minuit pour les urgents (prudent), midi sinon.
HEURE_SI_ABSENTE: dict[int, int] = {1: 0, 2: 0, 3: 12, 4: 12}

#: Noms de mois acceptés, en anglais et en français (avec et sans accents).
MOIS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}

# Heure facultative : « T09:32 », « 09:32:00 », « 13h29 », « 13H29 ».
_HEURE = r"(?:[T ](?P<h>\d{1,2})[:hH](?P<mi>\d{2})(?::(?P<s>\d{2}))?)?"
_DATE_ISO = re.compile(r"(?P<a>\d{4})-(?P<m>\d{2})-(?P<j>\d{2})" + _HEURE)
_DATE_FR = re.compile(r"(?P<j>\d{1,2})/(?P<m>\d{1,2})/(?P<a>\d{4})" + _HEURE)
_DATE_MOIS = re.compile(r"(?P<j>\d{1,2}) (?P<nom>[^\W\d_]+) (?P<a>\d{4})" + _HEURE)


def _lire_date(texte: str) -> tuple[datetime, bool]:
    """Lit une date ISO, française (JJ/MM/AAAA) ou avec le mois en lettres.

    Renvoie (date, heure_connue). Sans heure, la date est à minuit et
    heure_connue vaut False : construire_ticket fixe l'heure selon la priorité.
    Rejet « date invalide » s'il n'y a aucune date reconnaissable ou si elle est impossible.
    """
    # On essaie les trois formes ; fullmatch exige que TOUTE la chaîne corresponde.
    for forme in (_DATE_ISO, _DATE_FR, _DATE_MOIS):
        trouve = forme.fullmatch(texte)
        if trouve:
            break
    else:  # aucune forme ne correspond (« hier soir »)
        raise LigneInvalide(MOTIF_DATE, "aucune date reconnue")

    morceaux = trouve.groupdict()
    if "nom" in morceaux:  # forme avec le mois en lettres
        mois = MOIS.get(morceaux["nom"].lower())
        if mois is None:
            raise LigneInvalide(MOTIF_DATE, f"mois inconnu : {morceaux['nom']}")
    else:
        mois = int(morceaux["m"])

    heure_connue = morceaux["h"] is not None
    # datetime vérifie que la date existe (mois 13, 30 février, 25 h... -> ValueError).
    try:
        date = datetime(
            int(morceaux["a"]), mois, int(morceaux["j"]),
            int(morceaux["h"] or 0), int(morceaux["mi"] or 0), int(morceaux["s"] or 0),
        )
    except ValueError:
        raise LigneInvalide(MOTIF_DATE, "date impossible") from None
    return date, heure_connue


def construire_ticket(brut: dict) -> Ticket:
    """Valide et normalise un dictionnaire brut. Lève LigneInvalide sinon."""
    # 1. Champs obligatoires, tous vérifiés avant le reste.
    champs = {
        nom: _texte_obligatoire(brut, nom)
        for nom in CHAMPS_OBLIGATOIRES
        if nom not in CHAMPS_AVEC_DEFAUT  # canal et categorie : traités plus bas, avec « autre »
        and nom not in CHAMPS_VIDES_SI_SUJET  # message : traité juste après, avec le sujet
    }

    # Sujet facultatif : absent ou d'un type inattendu -> chaîne vide.
    sujet = brut.get("sujet")
    sujet = sujet.strip() if isinstance(sujet, str) else ""

    # Message : absent ou vide -> chaîne vide, accepté seulement si le sujet existe.
    message = brut.get("message")
    if message is None or (isinstance(message, str) and not message.strip()):
        if not sujet:
            raise LigneInvalide(MOTIF_CHAMP, "message")
        message = ""
    elif not isinstance(message, str):
        raise LigneInvalide(MOTIF_CHAMP, "message")
    else:
        message = message.strip()

    # 2. Date de création (l'heure manquante sera fixée après la priorité).
    cree_le, heure_connue = _lire_date(champs["cree_le"])

    # 3. Canal : absent ou vide -> « autre » ; sinon minuscules, variante connue
    #    ramenée à un canal officiel.
    canal = brut.get("canal")
    if canal is None or (isinstance(canal, str) and not canal.strip()):
        canal = CANAL_PAR_DEFAUT
    elif not isinstance(canal, str):
        raise LigneInvalide(MOTIF_CANAL, f"type {type(canal).__name__}")
    else:
        canal = canal.strip().lower()
        canal = CORRESPONDANCE_CANAUX.get(canal, canal)
        if canal not in CANAUX:
            raise LigneInvalide(MOTIF_CANAL, canal)

    # 4. Catégorie : absente ou vide -> « autre » ; variante connue -> catégorie officielle.
    categorie = brut.get("categorie")
    if categorie is None or (isinstance(categorie, str) and not categorie.strip()):
        categorie = CATEGORIE_PAR_DEFAUT
    elif not isinstance(categorie, str):
        raise LigneInvalide(MOTIF_CATEGORIE, f"type {type(categorie).__name__}")
    else:
        categorie = categorie.strip().lower()
        categorie = CORRESPONDANCE_CATEGORIES.get(categorie, categorie)
        if categorie not in CATEGORIES:
            raise LigneInvalide(MOTIF_CATEGORIE, categorie)

    # 5. Priorité : le morceau 1.a (clé absente -> get renvoie None -> 3, estimée).
    priorite, estimee = normaliser_priorite(brut.get("priorite"))

    # Heure absente : on la fixe selon la priorité, maintenant connue.
    if not heure_connue:
        cree_le = cree_le.replace(hour=HEURE_SI_ABSENTE[priorite])

    # 6. Statut : absent ou vide -> « ouvert » ; sinon il doit être connu.
    statut = brut.get("statut")
    if statut is None or (isinstance(statut, str) and not statut.strip()):
        statut = "ouvert"
    elif not isinstance(statut, str) or statut.strip().lower() not in STATUTS:
        raise LigneInvalide(MOTIF_STATUT, repr(statut))
    else:
        statut = statut.strip().lower()

    return Ticket(
        id=champs["id"],
        cree_le=cree_le,
        client_id=champs["client_id"],
        canal=canal,
        categorie=categorie,
        priorite=priorite,
        sujet=sujet,
        message=message,
        statut=statut,
        echeance=calculer_echeance(cree_le, priorite),  # calculée APRÈS avoir fixé l'heure
        priorite_estimee=estimee,
        date_estimee=not heure_connue,
    )


#: Nom du dossier, à côté de l'original, où sont rangées les copies de travail (ignoré par Git).
NOM_DOSSIER_COPIES = "copie_travail"


def empreinte(chemin: str | Path) -> str:
    """Empreinte SHA-256 d'un fichier : prouve qu'un original n'a pas changé."""
    hachage = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1 << 20), b""):
            hachage.update(bloc)
    return hachage.hexdigest()


def copier_donnees(source: str | Path, dossier: str | Path | None = None) -> Path:
    """Copie `source` dans un dossier de travail et renvoie le chemin de la copie.

    Par défaut le dossier est `copie_travail/`, à côté de l'original. La copie est mise
    en lecture seule et remplace une copie précédente. L'original n'est que lu.
    """
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    if dossier is None and source.parent.name == NOM_DOSSIER_COPIES:
        return source  # c'est déjà une copie de travail
    dossier = Path(dossier) if dossier is not None else source.parent / NOM_DOSSIER_COPIES
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / source.name
    if cible.exists():
        if cible.resolve() == source.resolve():  # déjà une copie de travail : rien à faire
            return source
        cible.chmod(0o644)  # la copie précédente est en lecture seule
        cible.unlink()
    shutil.copyfile(source, cible)
    cible.chmod(0o444)
    return cible


def charger_tickets(chemin: str | Path, copie: bool = False) -> tuple[list[Ticket], list[dict]]:
    """Lit un fichier JSON Lines de tickets.

    Avec `copie=True`, le fichier est d'abord copié (copier_donnees) et c'est la copie
    qui est lue : l'original reste intact.

    Renvoie (tickets valides dans l'ordre du fichier, rejets).
    Un rejet est un dictionnaire {"ligne": int, "motif": str, "detail": str},
    « ligne » étant le numéro de ligne dans le fichier (1 = première ligne).

    Doublons (choix de conception) : une copie
    exacte d'un ticket déjà gardé est rejetée ; un ticket différent qui réutilise
    un identifiant est gardé sous un nouvel identifiant « TCK-000042-2 », « -3 »...
    Les identifiants des tickets renvoyés sont tous distincts.
    """
    if copie:
        chemin = copier_donnees(chemin)
    tickets: list[Ticket] = []
    rejets: list[dict] = []
    versions: dict[str, list[Ticket]] = {}  # id lu dans le fichier -> tickets gardés
    ids_emis: set[str] = set()              # TOUS les id attribués : test en O(1)

    # utf-8-sig retire un éventuel BOM en début de fichier ;
    # errors="replace" évite de planter sur un octet non UTF-8.
    with open(chemin, encoding="utf-8-sig", errors="replace") as fichier:
        for numero, ligne in enumerate(fichier, start=1):
            # Lignes vides : ni ticket, ni rejet.
            if not ligne.strip():
                continue
            try:
                # 1. JSON invalide : ligne tronquée, ou valeur qui n'est pas un objet.
                try:
                    brut = json.loads(ligne)
                except json.JSONDecodeError:
                    raise LigneInvalide(MOTIF_JSON, "ligne non décodable") from None
                if not isinstance(brut, dict):
                    raise LigneInvalide(MOTIF_JSON, f"pas un objet : {type(brut).__name__}")

                # 2. à 7. Tous les contrôles du morceau 1.b.
                ticket = construire_ticket(brut)

                # 8. Doublons, vérifiés en dernier.
                anciens = versions.setdefault(ticket.id, [])
                # Copie exacte d'une version déjà gardée : vrai doublon, rejeté.
                if ticket in anciens:  # dataclass : == compare tous les champs
                    raise LigneInvalide(MOTIF_DOUBLON, f"{ticket.id} : copie exacte")
                anciens.append(ticket)  # version d'origine, avant tout renommage

                # Identifiant déjà attribué (d'origine OU créé par nous) : on en
                # cherche un libre, « -2 » pour la 2e version, « -3 » pour la 3e...
                if ticket.id in ids_emis:
                    rang = max(2, len(anciens))
                    while f"{ticket.id}-{rang}" in ids_emis:
                        rang += 1
                    ticket = replace(ticket, id=f"{ticket.id}-{rang}")
            except LigneInvalide as erreur:
                rejets.append({"ligne": numero, "motif": erreur.motif, "detail": erreur.detail})
                continue

            # Ici, ticket.id n'est dans ids_emis sous aucune forme : il est unique.
            ids_emis.add(ticket.id)
            tickets.append(ticket)

    return tickets, rejets


def charger_agents(chemin: str | Path, copie: bool = False) -> list[Agent]:
    """Lit agents.csv (agent_id,nom,competences,capacite_jour).

    Avec `copie=True`, la lecture se fait sur une copie (voir copier_donnees).

    Les compétences sont séparées par « ; » et stockées en frozenset (minuscules).
    """
    if copie:
        chemin = copier_donnees(chemin)
    agents: list[Agent] = []
    # newline="" : recommandé par la documentation du module csv.
    with open(chemin, encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.reader(fichier)
        # Le vrai fichier a des « ; » parasites (en-tête « capacite_jour;; », valeurs « 40; ») :
        # on les retire des noms de colonnes et de la capacité avant de lire.
        entete = next(lecteur, None) or []
        noms = [h.strip().strip(";").strip().lower() for h in entete]
        # Le compteur commence à 2 : la ligne 1 du fichier est l'en-tête.
        for numero, valeurs in enumerate(lecteur, start=2):
            if not any(v.strip() for v in valeurs):
                continue  # ligne vide
            ligne = dict(zip(noms, valeurs))
            if ligne.get("capacite_jour") is not None:
                ligne["capacite_jour"] = ligne["capacite_jour"].strip().strip(";").strip()
            competences = frozenset(
                c.strip().lower() for c in (ligne.get("competences") or "").split(";") if c.strip()
            )
            # Avec 12 conseillers, une capacité illisible doit se voir tout de suite.
            try:
                capacite = int(ligne.get("capacite_jour"))
            except (TypeError, ValueError):
                raise ValueError(f"ligne {numero} : capacité illisible") from None
            if capacite < 0:
                raise ValueError(f"ligne {numero} : capacité négative")
            agents.append(Agent(
                agent_id=(ligne.get("agent_id") or "").strip(),
                nom=(ligne.get("nom") or "").strip(),
                competences=competences,
                capacite_jour=capacite,
            ))
    return agents
