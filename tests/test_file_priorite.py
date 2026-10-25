"""Tests de la file de priorité : file de priorité en tas binaire codé à la main."""

import ast
import heapq
import inspect
import random

import pytest

from moteur_sav import file_priorite
from moteur_sav.file_priorite import FilePriorite

from .fabrique import fabriquer_ticket


def respecte_le_tas(f):
    """Vérifie la propriété du tas : chaque parent est plus petit que ses enfants."""
    tas = f._tas
    return all(tas[(i - 1) // 2] < tas[i] for i in range(1, len(tas)))

# ------------------------------------------------------------------ file vide

def test_file_vide():
    f = FilePriorite()
    assert len(f) == 0 and f.est_vide()
    with pytest.raises(IndexError):
        f.consulter()
    with pytest.raises(IndexError):
        f.extraire()


def test_un_seul_element():
    f = FilePriorite()
    f.ajouter("seul", 7)
    assert len(f) == 1 and not f.est_vide()
    assert f.extraire() == "seul"
    assert f.est_vide()
    with pytest.raises(IndexError):
        f.extraire()


def test_remplir_vider_remplir():
    f = FilePriorite()
    for x in (3, 1, 2):
        f.ajouter(x, x)
    assert [f.extraire() for _ in range(3)] == [1, 2, 3]
    f.ajouter("après", 0)
    assert f.consulter() == "après" and len(f) == 1

# ------------------------------------------------------------------ ordre

def test_ordre_croissant():
    f = FilePriorite()
    for nom, prio in [("A", 5), ("B", 3), ("C", 8), ("D", 1), ("E", 9), ("F", 2)]:
        f.ajouter(nom, prio)
        assert respecte_le_tas(f)
    assert [f.extraire() for _ in range(len(f))] == ["D", "F", "B", "A", "C", "E"]


def test_consulter_ne_retire_pas():
    f = FilePriorite()
    f.ajouter("A", 2)
    f.ajouter("B", 1)
    assert f.consulter() == "B" and f.consulter() == "B" and len(f) == 2


def test_egalite_premier_arrive_premier_servi():
    f = FilePriorite()
    for i in range(20):
        f.ajouter(f"t{i}", 5)  # même priorité pour tous
    assert [f.extraire() for _ in range(20)] == [f"t{i}" for i in range(20)]


def test_egalite_melangee_avec_autres_priorites():
    f = FilePriorite()
    for nom, prio in [("a1", 2), ("b1", 1), ("a2", 2), ("b2", 1), ("a3", 2)]:
        f.ajouter(nom, prio)
    assert [f.extraire() for _ in range(5)] == ["b1", "b2", "a1", "a2", "a3"]


def test_elements_non_comparables():
    # Deux objets sans comparaison possible, à priorité égale : aucune TypeError.
    class Objet:
        pass
    premier, second = Objet(), Objet()
    f = FilePriorite()
    f.ajouter(premier, 1)
    f.ajouter(second, 1)
    assert f.extraire() is premier and f.extraire() is second

# ------------------------------------------------------------------ tickets

def test_tickets_par_cle_urgence():
    a = fabriquer_ticket(id="A", cree_le="2026-03-10T09:00:00", priorite=3)  # échéance 13/03 09:00
    b = fabriquer_ticket(id="B", cree_le="2026-03-14T09:00:00", priorite=1)  # échéance 14/03 13:00
    c = fabriquer_ticket(id="C", cree_le="2026-03-11T09:00:00", priorite=3)  # échéance 14/03 09:00
    d = fabriquer_ticket(id="D", cree_le="2026-03-13T09:00:00", priorite=2)  # échéance 14/03 09:00
    f = FilePriorite()
    for t in (b, c, a, d):
        f.ajouter(t, t.cle_urgence())
    # A : échéance la plus proche. D et C : même échéance, la priorité 2 passe avant la 3.
    # B : priorité 1, mais son échéance est la plus lointaine.
    assert [f.extraire().id for _ in range(4)] == ["A", "D", "C", "B"]

# ------------------------------------------------------------------ preuve contre heapq

def test_conforme_a_heapq_sur_10000_operations():
    rng = random.Random(42)  # graine fixe : le test est reproductible
    f, reference, numero = FilePriorite(), [], 0
    for _ in range(10_000):
        if reference and rng.random() < 0.4:  # 40 % d'extractions, 60 % d'ajouts
            assert f.extraire() == heapq.heappop(reference)[2]
        else:
            prio = rng.randint(0, 50)  # beaucoup d'égalités, exprès
            f.ajouter(numero, prio)
            heapq.heappush(reference, (prio, numero, numero))
            numero += 1
        assert len(f) == len(reference)
        if reference:
            assert f.consulter() == reference[0][2]
    while reference:  # on vide les deux files jusqu'au bout
        assert f.extraire() == heapq.heappop(reference)[2]
    assert f.est_vide()

# ------------------------------------------------------------------ règles du module

def test_aucun_outil_interdit_dans_le_module():
    # On analyse le CODE du module, pas son texte : la docstring cite heapq sans l'utiliser.
    arbre = ast.parse(inspect.getsource(file_priorite))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert not {a.name for a in noeud.names} & {"heapq", "bisect"}
        if isinstance(noeud, ast.ImportFrom):
            assert noeud.module not in ("heapq", "bisect")
        if isinstance(noeud, ast.Name):
            assert noeud.id != "sorted"
        if isinstance(noeud, ast.Attribute):
            assert noeud.attr != "sort"
