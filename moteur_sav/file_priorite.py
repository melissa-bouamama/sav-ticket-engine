"""File de priorité : tas binaire min codé à la main (sans `heapq`, `sorted` ni `list.sort`).

Représentation : une liste `self._tas` où l'élément d'indice i a pour enfants 2i + 1 et
2i + 2, et pour parent (i - 1) // 2. Chaque case stocke le triplet
(priorite, numero_d_insertion, element) : le numéro, unique, départage les priorités égales
dans l'ordre d'arrivée (FIFO) et évite de comparer les éléments eux-mêmes (deux `Ticket`
ne sont pas comparables).

Complexités : ajouter O(log n), extraire O(log n), consulter O(1).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

T = TypeVar("T")


class FilePriorite(Generic[T]):
    """File de priorité min : `extraire()` renvoie l'élément de plus petite priorité.

    Pour les tickets, la priorité à utiliser est `ticket.cle_urgence()`.
    """

    def __init__(self) -> None:
        self._tas: list[tuple[Any, int, T]] = []
        self._compteur = 0

    def __len__(self) -> int:
        return len(self._tas)

    def est_vide(self) -> bool:
        """Vrai si la file ne contient aucun élément."""
        return not self._tas  # une liste vide vaut False

    def ajouter(self, element: T, priorite: Any) -> None:
        """Insère `element` avec la `priorite` donnée (toute valeur comparable)."""
        # 1. En bas du tas, avec son numéro d'arrivée (unique, croissant).
        self._tas.append((priorite, self._compteur, element))
        self._compteur += 1
        # 2. On le fait remonter à sa place : O(log n).
        self._remonter(len(self._tas) - 1)

    def consulter(self) -> T:
        """Renvoie l'élément le plus prioritaire sans le retirer. IndexError si vide."""
        if not self._tas:
            raise IndexError("consulter() sur une file vide")
        # La racine (case 0) est toujours la plus petite : O(1).
        # On renvoie seulement l'élément, 3e case du triplet (priorite, numero, element).
        return self._tas[0][2]

    def extraire(self) -> T:
        """Retire et renvoie l'élément le plus prioritaire. IndexError si vide."""
        tas = self._tas
        if not tas:
            raise IndexError("extraire() sur une file vide")
        racine = tas[0]
        dernier = tas.pop()  # retirer la fin d'une liste : O(1)
        if tas:  # s'il restait d'autres éléments, le dernier bouche le trou de la racine
            tas[0] = dernier
            self._descendre(0)
        return racine[2]  # seulement l'élément, 3e case du triplet

    # --- opérations internes (suggestion) --------------------------------------

    def _remonter(self, i: int) -> None:
        """Fait remonter la case i tant qu'elle est plus petite que son parent."""
        tas = self._tas
        while i > 0:
            parent = (i - 1) // 2
            # Python compare les triplets case par case : d'abord la priorité,
            # puis, à égalité, le numéro d'arrivée. Les numéros étant tous
            # différents, la comparaison s'arrête toujours avant l'élément :
            # deux Ticket ne sont donc jamais comparés entre eux.
            if tas[i] < tas[parent]:
                tas[i], tas[parent] = tas[parent], tas[i]  # échange
                i = parent
            else:
                break  # le parent est plus urgent : la place est trouvée

    def _descendre(self, i: int) -> None:
        """Fait descendre la case i vers le plus petit de ses enfants."""
        tas = self._tas
        n = len(tas)
        while True:
            gauche, droite = 2 * i + 1, 2 * i + 2
            plus_petit = i
            # On cherche le plus petit parmi la case i et ses enfants qui existent.
            if gauche < n and tas[gauche] < tas[plus_petit]:
                plus_petit = gauche
            if droite < n and tas[droite] < tas[plus_petit]:
                plus_petit = droite
            if plus_petit == i:
                break  # la case i est plus petite que ses enfants : la place est trouvée
            tas[i], tas[plus_petit] = tas[plus_petit], tas[i]
            i = plus_petit
