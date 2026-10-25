"""Petite fabrique de tickets pour les tests (évite de dépendre des fichiers)."""

from datetime import datetime

from moteur_sav.modeles import Ticket, calculer_echeance


def fabriquer_ticket(
    id: str = "TCK-000001",
    cree_le: str = "2026-03-14T09:00:00",
    priorite: int = 3,
    categorie: str = "livraison",
    sujet: str = "Colis non reçu",
    message: str = "Bonjour, mon colis n'est pas arrivé.",
    statut: str = "ouvert",
    client_id: str = "CLI-0001",
    canal: str = "email",
) -> Ticket:
    date = datetime.fromisoformat(cree_le)
    return Ticket(
        id=id,
        cree_le=date,
        client_id=client_id,
        canal=canal,
        categorie=categorie,
        priorite=priorite,
        sujet=sujet,
        message=message,
        statut=statut,
        echeance=calculer_echeance(date, priorite),
    )
