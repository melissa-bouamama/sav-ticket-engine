"""Index inversé pour la recherche plein texte dans les tickets.

Structure : dictionnaire mot normalisé -> ensemble d'identifiants de tickets.
- `rechercher("pot cassé")` en mode « ET » : intersection des ensembles (en partant
  du plus petit) ; mode « OU » : union ;
- `prefixe("cass")` : mots du vocabulaire commençant par « cass », trouvés par
  RECHERCHE DICHOTOMIQUE codée à la main (pas de `bisect`) dans la liste triée du
  vocabulaire, qui n'est retriée que quand l'index a changé.

Choix de conception :
- un mot est une suite de lettres ou de chiffres sans accent ; il n'y a pas de
  racinisation : « cassé » et « cassée » sont deux mots, `prefixe("cass")` les réunit ;
- indexer deux fois le même identifiant remplace la première version (aucun mot
  ancien ne reste, aucun doublon dans le compte) ;
- `prefixe` ne retire ni mots vides ni mots d'une lettre : « c » ou « le » sont des
  débuts de mot valables ; un début vide donne une liste vide.
"""

from __future__ import annotations

import re
import unicodedata

from .modeles import Ticket

MOTS_VIDES: frozenset[str] = frozenset("""
a au aux avec ce ces cette d de des du elle en est et etait il ils j je l la le les
leur lui m ma mais me mes mon n ne nos notre nous on ou par pas pour qu que qui s sa
sans se ses si son sur t ta te tes ton tu un une vos votre vous y c ca ete etre ai
as avez avons bonjour bonsoir merci cordialement salut madame monsieur
""".split())

#: Ligatures que la décomposition Unicode ne sépare pas : « cœur » -> « coeur ».
_LIGATURES = str.maketrans({"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE"})

#: Un mot : lettres minuscules sans accent ou chiffres.
_MOT = re.compile(r"[a-z0-9]+")

MODES = ("ET", "OU")


def sans_accents(texte: str) -> str:
    """Retire les accents : « Abîmée » -> « Abimee ».

    Indice : unicodedata.normalize("NFD", ...) puis retirer les caractères de
    catégorie « Mn ».
    """
    decompose = unicodedata.normalize("NFD", texte.translate(_LIGATURES))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def normaliser(texte: str) -> list[str]:
    """Découpe un texte en mots normalisés : minuscules, sans accents, seulement
    lettres et chiffres, sans mots vides, sans mots d'une seule lettre.

    Exemple : « Bonjour, le POT est Cassé ! » -> ["pot", "casse"]
    """
    mots = _MOT.findall(sans_accents(texte).lower())
    return [mot for mot in mots if len(mot) > 1 and mot not in MOTS_VIDES]


def borne_inferieure(liste_triee: list[str], cible: str) -> int:
    """Premier indice i tel que liste_triee[i] >= cible (len(liste) si aucun). O(log n).

    Exemple : borne_inferieure(["a", "c", "e"], "b") == 1
    """
    bas, haut = 0, len(liste_triee)  # la réponse est dans [bas, haut]
    while bas < haut:
        milieu = (bas + haut) // 2
        if liste_triee[milieu] < cible:
            bas = milieu + 1  # tout ce qui est avant « milieu » est trop petit
        else:
            haut = milieu     # « milieu » convient peut-être, mais un indice plus petit aussi
    return bas


class IndexInverse:
    """Index inversé mot -> ensemble d'identifiants de tickets."""

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = {}
        self._nb_documents = 0
        self._vocabulaire_trie: list[str] = []
        self._a_jour = True
        self._mots_par_id: dict[str, set[str]] = {}  # pour remplacer un ticket déjà indexé

    def __len__(self) -> int:
        """Nombre de tickets indexés."""
        return self._nb_documents

    @property
    def nb_mots(self) -> int:
        """Nombre de mots différents dans l'index (la taille du vocabulaire)."""
        return len(self._index)

    def ajouter(self, ticket: Ticket) -> None:
        """Indexe le sujet et le message du ticket.

        Si l'identifiant est déjà indexé, l'ancienne version est d'abord retirée.
        """
        if ticket.id in self._mots_par_id:
            self._retirer(ticket.id)
        mots = set(normaliser(f"{ticket.sujet} {ticket.message}"))
        for mot in mots:
            if mot not in self._index:
                self._index[mot] = set()
                self._a_jour = False  # nouveau mot : le vocabulaire trié est à refaire
            self._index[mot].add(ticket.id)
        self._mots_par_id[ticket.id] = mots
        self._nb_documents = len(self._mots_par_id)

    def _retirer(self, id_ticket: str) -> None:
        """Retire un ticket de l'index (utilisé quand il est indexé une seconde fois)."""
        for mot in self._mots_par_id.pop(id_ticket):
            self._index[mot].discard(id_ticket)
            if not self._index[mot]:
                del self._index[mot]
                self._a_jour = False  # mot disparu : le vocabulaire trié est à refaire

    def rechercher(self, requete: str, mode: str = "ET") -> list[str]:
        """Renvoie les identifiants (triés) des tickets correspondant à la requête.

        mode « ET » : tous les mots présents ; « OU » : au moins un (insensible à
        la casse). Requête sans mot significatif : liste vide. Autre mode : ValueError.
        """
        if mode not in MODES:
            raise ValueError(f"mode inconnu : {mode!r} (attendu : « ET » ou « OU »)")
        mots = set(normaliser(requete))
        if not mots:
            return []
        if mode == "OU":
            trouves: set[str] = set()
            for mot in mots:
                trouves |= self._index.get(mot, set())
            return sorted(trouves)
        # ET : un mot absent de l'index suffit à conclure ; sinon on part du plus petit ensemble.
        ensembles = [self._index.get(mot) for mot in mots]
        if any(e is None for e in ensembles):
            return []
        ensembles.sort(key=len)
        trouves = set(ensembles[0])
        for ensemble in ensembles[1:]:
            trouves &= ensemble
            if not trouves:
                break
        return sorted(trouves)

    def prefixe(self, debut: str, limite: int | None = None) -> list[str]:
        """Mots du vocabulaire commençant par `debut` (normalisé), triés, au plus `limite`."""
        if limite is not None and limite < 0:
            raise ValueError("limite doit être positive ou nulle")
        mots = _MOT.findall(sans_accents(debut).lower())
        if not mots or limite == 0:
            return []
        debut = mots[0]  # un seul mot : le premier
        if not self._a_jour:  # on ne retrie que si l'index a changé
            self._vocabulaire_trie = sorted(self._index)
            self._a_jour = True
        vocabulaire = self._vocabulaire_trie
        resultat: list[str] = []
        i = borne_inferieure(vocabulaire, debut)  # premier mot >= debut
        while i < len(vocabulaire) and vocabulaire[i].startswith(debut):
            if limite is not None and len(resultat) == limite:
                break
            resultat.append(vocabulaire[i])
            i += 1
        return resultat
