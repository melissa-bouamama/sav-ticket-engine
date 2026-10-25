"""Modèles de données du moteur SAV (boutique de plantes en ligne fictive).

Ce module fixe le vocabulaire commun. Les autres modules en dépendent : l'ingestion produit
des `Ticket` et des `Agent`, la file de priorité les ordonne avec `Ticket.cle_urgence`,
l'historique modifie leur statut ou leur priorité, l'index lit leur texte et la
répartition associe `Ticket.categorie` aux `Agent.competences`.

Contenu :
- les valeurs autorisées (CANAUX, CATEGORIES, STATUTS) et les délais (SLA_HEURES) ;
- calculer_echeance : date limite d'un ticket ;
- Ticket : une demande client, nettoyée ;
- Agent : un conseiller du service client.

Deux champs sont des ajouts au modèle de base, signalés (ajout) ci-dessous :
le canal « autre » et le champ `date_estimee`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# --------------------------------------------------------------------------- constantes

#: Délai de traitement maximal, en heures, selon la priorité (1 = la plus urgente).
#: Ces délais sont la promesse faite aux clients (SLA : service level agreement).
SLA_HEURES: dict[int, int] = {1: 4, 2: 24, 3: 72, 4: 168}

#: Canaux autorisés après normalisation.
#: (ajout) « autre » regroupe les tickets dont le canal est absent du fichier ; le canal
#: n'intervient dans aucune décision du moteur (urgence, échéance, affectation).
CANAUX: frozenset[str] = frozenset({"email", "chat", "telephone", "formulaire", "autre"})

#: Catégories autorisées ; elles correspondent aux compétences des conseillers.
CATEGORIES: frozenset[str] = frozenset(
    {"livraison", "produit_abime", "facturation", "conseil_plante", "retour", "autre"}
)

#: Statuts autorisés d'un ticket.
STATUTS: frozenset[str] = frozenset({"ouvert", "en_cours", "resolu"})

#: Priorité appliquée quand le champ est absent du fichier (le ticket est alors signalé
#: par `Ticket.priorite_estimee`).
PRIORITE_PAR_DEFAUT: int = 3


# --------------------------------------------------------------------------- fonctions


def calculer_echeance(cree_le: datetime, priorite: int) -> datetime:
    """Renvoie la date limite de traitement : création + délai (SLA) de la priorité.

    Exemple : un ticket de priorité 1 créé à 09:00 doit être traité avant 13:00.
    Lève KeyError si la priorité n'est pas dans SLA_HEURES (1 à 4).
    """
    return cree_le + timedelta(hours=SLA_HEURES[priorite])


# --------------------------------------------------------------------------- classes


@dataclass
class Ticket:
    """Un ticket du service client, après ingestion et normalisation.

    Attributs lus dans le fichier (après nettoyage) :
        id: identifiant unique, par exemple « TCK-000042 ».
        cree_le: date et heure de création, sans fuseau horaire.
        client_id: identifiant du client (donnée personnelle indirecte).
        canal: un élément de CANAUX.
        categorie: un élément de CATEGORIES.
        priorite: entier de 1 (urgent) à 4.
        sujet: titre court, chaîne vide s'il est absent.
        message: texte libre du client, chaîne vide s'il est absent ; il peut contenir
            des e-mails et des téléphones : ne jamais l'afficher brut.
        statut: un élément de STATUTS.

    Attributs calculés :
        echeance: date limite de traitement (calculer_echeance).
        priorite_estimee: vrai si la priorité était absente ou hors échelle et a été fixée
            par le moteur.
        date_estimee: (ajout) vrai si l'heure de création était absente et a été fixée
            selon la priorité.
    """

    id: str
    cree_le: datetime
    client_id: str
    canal: str
    categorie: str
    priorite: int
    sujet: str
    message: str
    statut: str
    echeance: datetime
    priorite_estimee: bool = False
    date_estimee: bool = False

    def cle_urgence(self) -> tuple[datetime, int, datetime]:
        """Clé d'ordre du moteur : (échéance, priorité, date de création).

        Plus la clé est petite, plus le ticket est urgent. À échéance égale, la priorité
        la plus forte (le plus petit chiffre) passe d'abord, puis le plus ancien.
        """
        return (self.echeance, self.priorite, self.cree_le)


@dataclass
class Agent:
    """Un conseiller du service client.

    Attributs:
        agent_id: identifiant, par exemple « AG-01 ».
        nom: nom affichable.
        competences: catégories (éléments de CATEGORIES) que le conseiller sait traiter.
        capacite_jour: nombre maximal de tickets traités par jour.
    """

    agent_id: str
    nom: str
    competences: frozenset[str] = field(default_factory=frozenset)
    capacite_jour: int = 0

    def sait_traiter(self, categorie: str) -> bool:
        """Indique si le conseiller est compétent pour cette catégorie de ticket."""
        return categorie in self.competences
