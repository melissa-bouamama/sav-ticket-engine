"""Ligne de commande : `python -m moteur_sav <commande>`.

Commandes : bilan, urgents, chercher, prefixe, repartir. Aucune ne montre un message
brut ni un `client_id` : seulement l'identifiant, la catégorie, la priorité, l'échéance
et le sujet.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .affectation import NON_AFFECTES, affecter, affecter_naif, taux_sla
from .file_priorite import FilePriorite
from .index import MODES, IndexInverse
from .ingestion import charger_agents, charger_tickets
from .modeles import Ticket

DONNEES = Path(__file__).resolve().parents[1] / "donnees"


def _ligne(t: Ticket) -> str:
    return f"{t.id}  P{t.priorite}  {t.categorie:<15} {t.echeance:%d/%m/%Y %H:%M}  {t.sujet}"


def _charger(args: argparse.Namespace):
    chemin = args.tickets or DONNEES / "echantillon_tickets.jsonl"
    tickets, rejets = charger_tickets(chemin)
    return tickets, rejets


def cmd_bilan(args: argparse.Namespace) -> int:
    tickets, rejets = _charger(args)
    print(f"{len(tickets)} tickets exploitables, {len(rejets)} écartés")
    for motif, n in Counter(r["motif"] for r in rejets).most_common():
        print(f"  {n:>5}  {motif}")
    print(f"{sum(t.priorite_estimee for t in tickets)} priorités estimées, "
          f"{sum(t.date_estimee for t in tickets)} dates estimées")
    return 0


def cmd_urgents(args: argparse.Namespace) -> int:
    tickets, _ = _charger(args)
    file: FilePriorite[Ticket] = FilePriorite()
    for t in tickets:
        if t.statut == "ouvert":
            file.ajouter(t, t.cle_urgence())
    for _ in range(min(args.n, len(file))):
        print(_ligne(file.extraire()))
    return 0


def cmd_chercher(args: argparse.Namespace) -> int:
    tickets, _ = _charger(args)
    index = IndexInverse()
    for t in tickets:
        index.ajouter(t)
    par_id = {t.id: t for t in tickets}
    ids = index.rechercher(args.requete, args.mode)
    print(f"{len(ids)} ticket(s) pour « {args.requete} » ({args.mode})")
    for i in ids[: args.limite]:
        print(_ligne(par_id[i]))
    return 0


def cmd_prefixe(args: argparse.Namespace) -> int:
    tickets, _ = _charger(args)
    index = IndexInverse()
    for t in tickets:
        index.ajouter(t)
    print(", ".join(index.prefixe(args.debut, limite=args.limite)) or "(aucun mot)")
    return 0


def cmd_repartir(args: argparse.Namespace) -> int:
    tickets, _ = _charger(args)
    agents = charger_agents(args.agents or DONNEES / "echantillon_conseillers.csv")
    depuis = datetime.fromisoformat(args.depuis)
    debut = datetime.fromisoformat(args.debut)
    lot = [t for t in tickets if t.statut != "resolu" and t.cree_le >= depuis]
    print(f"Lot : {len(lot)} tickets non résolus créés depuis le {depuis:%d/%m/%Y}, "
          f"début {debut:%d/%m/%Y %H:%M}, {args.duree} min par ticket")
    for nom, repartir in (("gloutonne", affecter), ("naïve", affecter_naif)):
        aff = repartir(lot, agents)
        charges = [len(v) for k, v in aff.items() if k != NON_AFFECTES]
        taux = taux_sla(aff, lot, debut, args.duree)
        print(f"  {nom:<10} délais tenus {taux:6.1%}  non affectés {len(aff[NON_AFFECTES]):>4}  "
              f"charge {min(charges)}-{max(charges)}")
    return 0


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(prog="python -m moteur_sav", description=__doc__.split("\n")[0])
    parseur.add_argument("--tickets", type=Path, help="fichier JSON Lines (défaut : l'échantillon synthétique)")
    parseur.add_argument("--agents", type=Path, help="fichier CSV des conseillers (défaut : l'échantillon)")
    sous = parseur.add_subparsers(dest="commande", required=True)

    sous.add_parser("bilan", help="tickets exploitables et motifs de rejet").set_defaults(fonction=cmd_bilan)

    p = sous.add_parser("urgents", help="les tickets ouverts les plus urgents")
    p.add_argument("-n", type=int, default=10)
    p.set_defaults(fonction=cmd_urgents)

    p = sous.add_parser("chercher", help="recherche plein texte (ET / OU)")
    p.add_argument("requete")
    p.add_argument("--mode", choices=MODES, default="ET")
    p.add_argument("--limite", type=int, default=20)
    p.set_defaults(fonction=cmd_chercher)

    p = sous.add_parser("prefixe", help="mots du vocabulaire qui commencent par un début donné")
    p.add_argument("debut")
    p.add_argument("--limite", type=int, default=20)
    p.set_defaults(fonction=cmd_prefixe)

    p = sous.add_parser("repartir", help="répartition gloutonne contre naïve sur un lot de tickets")
    p.add_argument("--depuis", default="2026-09-28", help="créés depuis cette date (ISO)")
    p.add_argument("--debut", default="2026-10-01T08:00", help="début du traitement (ISO)")
    p.add_argument("--duree", type=int, default=20, help="minutes par ticket")
    p.set_defaults(fonction=cmd_repartir)
    return parseur


def main(argv: list[str] | None = None) -> int:
    args = construire_parseur().parse_args(argv)
    try:
        return args.fonction(args)
    except (OSError, ValueError) as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
