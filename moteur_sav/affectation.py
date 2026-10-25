"""Affectation des tickets aux agents.

Stratégie gloutonne (`affecter`) :
1. extraire les tickets du plus urgent au moins urgent (avec `FilePriorite` et la clé
   `ticket.cle_urgence()`) ;
2. pour chaque ticket, choisir parmi les agents compétents pour sa catégorie
   et dont la capacité journalière n'est pas atteinte celui dont le taux
   d'occupation (charge / capacité) est le plus faible (égalité : plus petit
   agent_id) ;
3. un ticket sans agent disponible va dans la liste NON_AFFECTES.

Stratégie naïve (`affecter_naif`), pour comparaison : ordre de création,
premier agent compétent de la liste qui a encore de la capacité.

`taux_sla` mesure la part des tickets traités avant leur échéance avec un modèle
simple : chaque agent traite ses tickets dans l'ordre de sa liste, un ticket
toutes les `duree_minutes`, à partir de `debut` (le k-ième ticket d'un agent se
termine à debut + k × duree_minutes, k commençant à 1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .file_priorite import FilePriorite  # noqa: F401
from .modeles import Agent, Ticket

NON_AFFECTES = "non_affectes"


def affecter(tickets: list[Ticket], agents: list[Agent]) -> dict[str, list[str]]:
    """Affectation gloutonne : le plus urgent d'abord, à l'agent compétent le moins occupé.

    Renvoie {agent_id: [ids dans l'ordre de traitement], ..., NON_AFFECTES: [...]}
    avec une clé pour CHAQUE agent (liste éventuellement vide).
    """
    # Une liste par conseiller, même vide, plus la liste des non affectés.
    affectations: dict[str, list[str]] = {a.agent_id: [] for a in agents}
    affectations[NON_AFFECTES] = []

    # 1. Du plus urgent au moins urgent, grâce à la file de la file de priorité.
    file: FilePriorite[Ticket] = FilePriorite()
    for t in tickets:
        file.ajouter(t, t.cle_urgence())

    while not file.est_vide():
        ticket = file.extraire()
        # 2. Conseillers compétents qui ont encore de la place.
        #    Une capacité de 0 n'est jamais « libre » : pas de division par zéro plus bas.
        candidats = [
            a for a in agents
            if a.sait_traiter(ticket.categorie)
            and len(affectations[a.agent_id]) < a.capacite_jour
        ]
        if not candidats:
            # 3. Personne de disponible : le ticket reste en attente.
            affectations[NON_AFFECTES].append(ticket.id)
            continue
        # Le moins occupé (charge / capacité), puis le plus petit identifiant.
        choisi = min(candidats,
                     key=lambda a: (len(affectations[a.agent_id]) / a.capacite_jour, a.agent_id))
        affectations[choisi.agent_id].append(ticket.id)

    return affectations


def affecter_naif(tickets: list[Ticket], agents: list[Agent]) -> dict[str, list[str]]:
    """Stratégie de référence : ordre de création, premier agent compétent disponible."""
    affectations: dict[str, list[str]] = {a.agent_id: [] for a in agents}
    affectations[NON_AFFECTES] = []

    # Ordre de création. Le tri de Python est STABLE : à date égale, l'ordre
    # du fichier est conservé. (sorted n'est interdit que dans file_priorite.py.)
    for ticket in sorted(tickets, key=lambda t: t.cree_le):
        # Le premier conseiller de la liste, compétent et pas encore plein.
        for agent in agents:
            if agent.sait_traiter(ticket.categorie) and \
                    len(affectations[agent.agent_id]) < agent.capacite_jour:
                affectations[agent.agent_id].append(ticket.id)
                break
        else:
            # La boucle n'a trouvé personne (aucun break) : ticket non affecté.
            affectations[NON_AFFECTES].append(ticket.id)

    return affectations


def taux_sla(
    affectations: dict[str, list[str]],
    tickets: list[Ticket],
    debut: datetime,
    duree_minutes: int = 20,
) -> float:
    """Part (entre 0 et 1) des tickets traités au plus tard à leur échéance.

    Les tickets non affectés comptent comme hors délai. 0.0 s'il n'y a aucun ticket.
    """
    if not tickets:
        return 0.0
    echeances = {t.id: t.echeance for t in tickets}  # retrouver une échéance en O(1)
    pas = timedelta(minutes=duree_minutes)
    tenus = 0
    for agent_id, ids in affectations.items():
        if agent_id == NON_AFFECTES:
            continue  # jamais traités : hors délai, ils ne comptent pas dans « tenus »
        for k, ticket_id in enumerate(ids, start=1):
            fin = debut + k * pas  # le k-ième ticket de ce conseiller
            if fin <= echeances[ticket_id]:
                tenus += 1
    # On divise par TOUS les tickets du lot : les non affectés font baisser le taux.
    return tenus / len(tickets)
