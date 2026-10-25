"""Rapport lisible pour `python -m tests.test_xxx` : OK / ÉCHEC par test, puis un verdict.

Chaque fichier de tests l'utilise ainsi, à la fin :

    if __name__ == "__main__":
        raise SystemExit(lancer(globals(), "TITRE", bilan=ma_fonction_facultative))
"""


def lancer(espace, titre, bilan=None):
    """Exécute les fonctions `test_*` de `espace` (globals() du fichier de tests).

    Le libellé d'un test est la première ligne de sa docstring, ou son nom à défaut.
    `bilan` (facultatif) est une fonction sans argument qui affiche un résumé après les tests.
    Renvoie 0 si tout va bien, 1 sinon (code de sortie du programme).
    """
    tests = [(nom, f) for nom, f in espace.items() if nom.startswith("test_") and callable(f)]
    print("=" * 72, f"\n {titre}\n", "=" * 72, sep="")
    echecs = 0
    for nom, fonction in tests:  # globals() conserve l'ordre du fichier
        libelle = (fonction.__doc__ or nom.removeprefix("test_").replace("_", " ")).strip().splitlines()[0]
        try:
            fonction()
            print(f"[OK]    {libelle}")
        except Exception as erreur:  # AssertionError, mais aussi tout plantage imprévu
            echecs += 1
            print(f"[ÉCHEC] {libelle}\n        -> {type(erreur).__name__}: {str(erreur)[:100]}")
    if bilan is not None:
        print("-" * 72)
        bilan()
    print("=" * 72)
    if echecs:
        print(f" ✘ PROBLÈMES : {echecs} vérification(s) en échec sur {len(tests)}.")
    else:
        print(f" ✔ TOUT VA BIEN : {len(tests)} vérifications réussies.")
    print("=" * 72)
    return 1 if echecs else 0
