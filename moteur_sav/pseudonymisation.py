"""Pseudonymisation des tickets (inspirée du RGPD).

- les adresses e-mail du message et du sujet sont remplacées par « [email] » ;
- les numéros de téléphone français sont remplacés par « [telephone] »
  (formes gérées : « 06 39 98 00 42 », « 06.39.98.00.42 », « 0639980042 »,
  « +33 6 39 98 00 42 ») ; un numéro de commande « CMD-00042 » n'est PAS masqué ;
- `client_id` est remplacé par un hachage salé : « CLI- » suivi des 10 premiers
  caractères hexadécimaux de sha256(sel + client_id). Le même client et le même sel donnent
  toujours le même pseudonyme, donc on peut regrouper les tickets d'un client sans le connaître.

Avec ce module, on peut afficher des messages sans exposer de donnée personnelle directe.
Limite : un nom écrit dans un message libre n'est pas détecté (il faudrait une reconnaissance
d'entités nommées).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from .modeles import Ticket

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Téléphone français : 0X ou +33 X, puis quatre paires de chiffres séparées (ou non) par
# un espace, un point ou un tiret. Les bornes évitent de couper un nombre plus long
# (numéro de commande, identifiant).
_TELEPHONE = re.compile(
    r"(?<![\w+])(?:\+33[\s.-]?|0033[\s.-]?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)"
)


def pseudonyme_client(client_id: str, sel: str) -> str:
    """Renvoie un pseudonyme stable « CLI-xxxxxxxxxx » pour ce client et ce sel."""
    empreinte = hashlib.sha256((sel + client_id).encode("utf-8")).hexdigest()
    return "CLI-" + empreinte[:10]


def masquer_texte(texte: str) -> str:
    """Masque d'abord les e-mails, puis les téléphones, dans un texte libre."""
    return _TELEPHONE.sub("[telephone]", _EMAIL.sub("[email]", texte))


def pseudonymiser(ticket: Ticket, sel: str) -> Ticket:
    """Renvoie une COPIE pseudonymisée du ticket (l'original n'est pas modifié).

    Lève ValueError si le sel est vide : sans sel, le hachage serait trivialement
    reconstructible à partir de la liste des identifiants clients.
    """
    if not sel:
        raise ValueError("le sel ne peut pas être vide")
    return replace(
        ticket,
        client_id=pseudonyme_client(ticket.client_id, sel),
        sujet=masquer_texte(ticket.sujet),
        message=masquer_texte(ticket.message),
    )
