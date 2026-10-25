"""Historique des actions d'un agent : annuler / rétablir avec DEUX PILES.

Patron « commande » : chaque action sait s'appliquer (`appliquer`) et se défaire
(`inverser`). L'historique ne connaît rien des tickets : il empile des actions.

- `executer(action)` : applique, empile sur la pile « annuler », VIDE la pile
  « rétablir » (une nouvelle action rend l'ancien futur caduc) ;
- `annuler()` : dépile de « annuler », inverse, empile sur « rétablir » ;
- `retablir()` : dépile de « rétablir », réapplique, empile sur « annuler ».
Toutes ces opérations sont en O(1).

`ChangerStatut` sert de modèle aux deux autres actions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .modeles import SLA_HEURES, STATUTS, Ticket, calculer_echeance  # noqa: F401


class Action(ABC):
    """Une action réversible."""

    @abstractmethod
    def appliquer(self) -> None:
        """Effectue l'action."""

    @abstractmethod
    def inverser(self) -> None:
        """Défait exactement ce que `appliquer` a fait."""

    def description(self) -> str:
        """Texte court pour l'affichage (peut être redéfini)."""
        return type(self).__name__


class ChangerStatut(Action):
    """Change le statut d'un ticket (ouvert, en_cours, resolu). modèle des deux autres actions."""

    def __init__(self, ticket: Ticket, nouveau_statut: str) -> None:
        if nouveau_statut not in STATUTS:
            raise ValueError(f"Statut inconnu : {nouveau_statut}")
        self.ticket = ticket
        self.nouveau = nouveau_statut
        self.ancien: str | None = None

    def appliquer(self) -> None:
        self.ancien = self.ticket.statut
        self.ticket.statut = self.nouveau

    def inverser(self) -> None:
        assert self.ancien is not None, "inverser() avant appliquer()"
        self.ticket.statut = self.ancien

    def description(self) -> str:
        return f"{self.ticket.id} : statut -> {self.nouveau}"


class ChangerPriorite(Action):
    """Change la priorité d'un ticket ET recalcule son échéance.

    Le constructeur lève ValueError si la priorité n'est pas dans SLA_HEURES.
    `appliquer` met aussi `priorite_estimee` à False ; `inverser` restaure la
    priorité, le drapeau `priorite_estimee` et l'échéance d'origine.
    """

    def __init__(self, ticket: Ticket, nouvelle_priorite: int) -> None:
        # Seul un vrai entier 1 à 4 est accepté : ni booléen (True vaut 1),
        # ni flottant (2.0 vaut 2), ni chaîne.
        if (not isinstance(nouvelle_priorite, int) or isinstance(nouvelle_priorite, bool)
                or nouvelle_priorite not in SLA_HEURES):
            raise ValueError(f"Priorité inconnue : {nouvelle_priorite}")
        self.ticket = ticket
        self.nouvelle = nouvelle_priorite
        # État d'avant, mémorisé par appliquer : (priorité, estimée, échéance).
        self.ancien: tuple | None = None

    def appliquer(self) -> None:
        t = self.ticket
        self.ancien = (t.priorite, t.priorite_estimee, t.echeance)
        t.priorite = self.nouvelle
        t.priorite_estimee = False  # fixée par un conseiller : plus une estimation
        t.echeance = calculer_echeance(t.cree_le, self.nouvelle)

    def inverser(self) -> None:
        assert self.ancien is not None, "inverser() avant appliquer()"
        t = self.ticket
        t.priorite, t.priorite_estimee, t.echeance = self.ancien

    def description(self) -> str:
        return f"{self.ticket.id} : priorité -> P{self.nouvelle}"


class AffecterTicket(Action):
    """Affecte un ticket à un agent dans un dictionnaire agent_id -> liste d'ids.

    `appliquer` ajoute l'id en fin de liste (en créant la liste si besoin) ;
    `inverser` le retire, et supprime la liste si c'est appliquer qui l'avait créée.
    """

    def __init__(self, affectations: dict[str, list[str]], ticket_id: str, agent_id: str) -> None:
        self.affectations = affectations
        self.ticket_id = ticket_id
        self.agent_id = agent_id
        self.liste_creee = False  # appliquer a-t-il dû créer la liste du conseiller ?

    def appliquer(self) -> None:
        self.liste_creee = self.agent_id not in self.affectations
        if self.liste_creee:
            self.affectations[self.agent_id] = []
        self.affectations[self.agent_id].append(self.ticket_id)  # O(1)

    def inverser(self) -> None:
        liste = self.affectations[self.agent_id]
        # Cas normal : on annule dans l'ordre inverse, le ticket est donc en fin de liste.
        if liste and liste[-1] == self.ticket_id:
            liste.pop()  # O(1)
        else:
            # Liste modifiée hors de l'historique : on retire la dernière occurrence.
            for i in range(len(liste) - 1, -1, -1):
                if liste[i] == self.ticket_id:
                    del liste[i]
                    break
            else:
                raise ValueError(f"{self.ticket_id} n'est pas affecté à {self.agent_id}")
        # On remet le dictionnaire exactement dans son état d'avant.
        if self.liste_creee and not liste:
            del self.affectations[self.agent_id]

    def description(self) -> str:
        return f"{self.ticket_id} : affecté à {self.agent_id}"


class Historique:
    """Gestionnaire annuler / rétablir à deux piles."""

    def __init__(self) -> None:
        # Deux piles : on n'ajoute et ne retire qu'en FIN de liste, donc en O(1).
        self._a_annuler: list[Action] = []
        self._a_retablir: list[Action] = []

    def executer(self, action: Action) -> None:
        """Applique l'action et l'enregistre ; vide la pile de rétablissement."""
        action.appliquer()  # si elle échoue, rien n'est enregistré
        self._a_annuler.append(action)
        # Une nouvelle action rend l'ancien futur caduc. On remplace la liste
        # au lieu de la vider case par case : O(1).
        self._a_retablir = []

    def annuler(self) -> bool:
        """Annule la dernière action. Renvoie False s'il n'y a rien à annuler."""
        if not self._a_annuler:
            return False
        action = self._a_annuler[-1]
        action.inverser()  # d'abord défaire : si cela échoue, l'action reste en place
        self._a_retablir.append(self._a_annuler.pop())
        return True

    def retablir(self) -> bool:
        """Rétablit la dernière action annulée. Renvoie False s'il n'y a rien à rétablir."""
        if not self._a_retablir:
            return False
        action = self._a_retablir[-1]
        action.appliquer()
        self._a_annuler.append(self._a_retablir.pop())
        return True

    def journal(self) -> list[str]:
        """Descriptions des actions actives, de la plus ancienne à la plus récente."""
        return [action.description() for action in self._a_annuler]
