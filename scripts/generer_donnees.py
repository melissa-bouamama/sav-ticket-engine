"""Génère des données SYNTHÉTIQUES de service client (tickets JSON Lines + conseillers CSV).

Aucune donnée réelle : tout est tiré au hasard avec une graine fixe, donc reproductible.
Les adresses e-mail utilisent le domaine réservé `example.com` et les numéros de téléphone
la plage `06 39 98 xx xx`, réservée à la fiction.

Le fichier produit imite les défauts d'un export de production, pour exercer l'ingestion :
lignes JSON tronquées, champs manquants, dates dans plusieurs formats ou impossibles,
priorités écrites « P2 », « urgent » ou fantaisistes, canaux en casse libre, catégories
aux variantes, doublons exacts ou à identifiant réutilisé.

Usage :
    python scripts/generer_donnees.py                       # échantillon versionné (donnees/)
    python scripts/generer_donnees.py --n 25000 --sortie donnees/tickets.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

DEBUT = datetime(2026, 1, 5)
FIN = datetime(2026, 9, 30, 23, 59)
CATEGORIES = ["livraison", "produit_abime", "facturation", "conseil_plante", "retour", "autre"]
POIDS_CATEGORIES = [28, 18, 16, 20, 12, 6]
PRIORITES = [1, 2, 3, 4]
POIDS_PRIORITES = [8, 22, 45, 25]

PLANTES = ["Monstera deliciosa", "Ficus lyrata", "Pothos", "Aloe vera", "Yucca", "Calathea", "Orchidée"]
ARTICLES = ["Pot terre cuite 21 cm", "Arrosoir 2 L", "Terreau universel 10 L", "Engrais liquide",
            "Soucoupe en grès", "Brumisateur", "Tuteur en bambou"]
VILLES = ["Lyon", "Lille", "Nantes", "Rennes", "Bordeaux", "Toulouse", "Dijon"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"]

#: (sujet, message) par catégorie ; {plante}, {article}, {ville}, {cmd} sont remplacés.
MODELES: dict[str, list[tuple[str, str]]] = {
    "livraison": [
        ("Colis non reçu", "Bonjour, toujours aucun colis pour la commande {cmd} à {ville}."),
        ("Retard de livraison", "Le colis de la commande {cmd} devait arriver hier."),
        ("Adresse de livraison erronée", "Le transporteur est passé à la mauvaise adresse pour {cmd}."),
    ],
    "produit_abime": [
        ("Pot cassé à la réception", "Bonjour, l'article « {article} » est arrivé cassé ({cmd})."),
        ("Tige cassée pendant le transport", "La tige de ma plante « {plante} » est cassée, photo à l'appui."),
        ("Feuilles abîmées", "Les feuilles de « {plante} » sont jaunies et abîmées à l'arrivée."),
    ],
    "facturation": [
        ("Double prélèvement", "J'ai été prélevé deux fois pour {cmd}."),
        ("Remboursement non reçu", "Le remboursement de {cmd} n'est toujours pas arrivé."),
        ("Facture manquante", "Pouvez-vous m'envoyer la facture de {cmd} ?"),
    ],
    "conseil_plante": [
        ("Présence de cochenilles", "J'ai repéré des cochenilles sur ma plante « {plante} »."),
        ("Arrosage", "À quelle fréquence arroser « {plante} » en hiver ?"),
        ("Feuilles qui jaunissent", "Les feuilles de ma plante « {plante} » jaunissent, que faire ?"),
    ],
    "retour": [
        ("Demande de retour", "Je souhaite retourner l'article « {article} » ({cmd})."),
        ("Échange de taille", "Puis-je échanger « {article} » contre un modèle plus grand ?"),
    ],
    "autre": [
        ("Carte cadeau", "Le code de ma carte cadeau ne fonctionne pas."),
        ("Horaires", "Quels sont les horaires du service client le samedi ?"),
    ],
}

#: Compétences et capacité journalière des 12 conseillers fictifs.
CONSEILLERS = [
    ("livraison;retour", 40), ("livraison;autre", 35), ("conseil_plante;produit_abime", 30),
    ("conseil_plante", 25), ("facturation;retour;autre", 40), ("facturation", 30),
    ("produit_abime;retour", 30), ("livraison;facturation", 35), ("conseil_plante;autre", 25),
    ("livraison;produit_abime;retour", 45), ("facturation;autre", 30), ("conseil_plante;livraison", 25),
]


def _signature_contact(hasard: random.Random) -> str:
    """Parfois, un client laisse un e-mail ou un téléphone (faux) dans son message."""
    tirage = hasard.random()
    if tirage < 0.12:
        return f" Contact : client{hasard.randint(1, 9999)}@example.com."
    if tirage < 0.20:
        return f" Rappelez-moi au 06 39 98 {hasard.randint(0, 99):02d} {hasard.randint(0, 99):02d}."
    return ""


def _date_aleatoire(hasard: random.Random, debut: datetime, fin: datetime) -> datetime:
    """Une date de bureau (lun-sam, 8 h-20 h), à la minute près."""
    while True:
        seconde = hasard.randint(0, int((fin - debut).total_seconds()))
        date = (debut + timedelta(seconds=seconde)).replace(second=0)
        if date.weekday() < 6 and 8 <= date.hour < 20:
            return date


def _ticket_propre(hasard: random.Random, numero: int, date: datetime, recent: bool) -> dict:
    categorie = hasard.choices(CATEGORIES, POIDS_CATEGORIES)[0]
    sujet, message = hasard.choice(MODELES[categorie])
    message = message.format(
        plante=hasard.choice(PLANTES), article=hasard.choice(ARTICLES),
        ville=hasard.choice(VILLES), cmd=f"CMD-{hasard.randint(1, 99999):05d}",
    ) + _signature_contact(hasard)
    if recent:  # les tickets de la dernière rafale sont surtout encore à traiter
        statut = hasard.choices(["resolu", "ouvert", "en_cours"], [25, 50, 25])[0]
    else:
        statut = hasard.choices(["resolu", "ouvert", "en_cours"], [82, 10, 8])[0]
    return {
        "id": f"TCK-{numero:06d}",
        "cree_le": date.strftime("%Y-%m-%dT%H:%M:%S"),
        "client_id": f"CLI-{hasard.randint(1, 3000):04d}",
        "canal": hasard.choices(["email", "chat", "telephone", "formulaire"], [40, 25, 20, 15])[0],
        "categorie": categorie,
        "priorite": hasard.choices(PRIORITES, POIDS_PRIORITES)[0],
        "sujet": sujet,
        "message": message,
        "statut": statut,
    }


def _abimer(hasard: random.Random, t: dict) -> dict:
    """Ajoute des défauts de saisie à un ticket propre (le dictionnaire est modifié)."""
    date = datetime.fromisoformat(t["cree_le"])
    tirage = hasard.random()
    if tirage < 0.70:
        pass  # ISO avec « T » : déjà le cas
    elif tirage < 0.85:
        t["cree_le"] = date.strftime("%Y-%m-%d %H:%M:%S")
    elif tirage < 0.90:
        t["cree_le"] = date.strftime("%d/%m/%Y %Hh%M")
    elif tirage < 0.93:
        t["cree_le"] = f"{date.day:02d} {MOIS_EN[date.month - 1]} {date.year} {date:%H:%M}"
    elif tirage < 0.96:
        t["cree_le"] = date.strftime("%d/%m/%Y")  # sans heure : l'ingestion la fixera
    elif tirage < 0.9965:
        pass
    else:
        t["cree_le"] = hasard.choice(["", "hier soir", "2026-02-30T10:00:00", "31/04/2026 10h00"])

    p = t["priorite"]
    tirage = hasard.random()
    if tirage < 0.60:
        pass
    elif tirage < 0.72:
        t["priorite"] = f"P{p}"
    elif tirage < 0.82:
        t["priorite"] = str(p)
    elif tirage < 0.85:
        t["priorite"] = float(p)
    elif tirage < 0.87 and p == 1:
        t["priorite"] = hasard.choice(["urgent", "URGENT"])
    elif tirage < 0.92:
        del t["priorite"]
    elif tirage < 0.945:
        t["priorite"] = hasard.choice([0, -1, 7, "P9", "haute", "critique", None])

    tirage = hasard.random()
    if tirage < 0.08:
        t["canal"] = hasard.choice([t["canal"].upper(), f" {t['canal']} ", t["canal"].capitalize()])
    elif tirage < 0.095:
        t["canal"] = hasard.choice(["fax", "courrier"])
    elif tirage < 0.105:
        del t["canal"]

    tirage = hasard.random()
    if tirage < 0.05:
        t["categorie"] = t["categorie"].capitalize()
    elif tirage < 0.06 and t["categorie"] == "livraison":
        t["categorie"] = "livraisons"
    elif tirage < 0.07 and t["categorie"] == "facturation":
        t["categorie"] = hasard.choice(["SAV", "remboursement"])
    elif tirage < 0.08:
        del t["categorie"]

    tirage = hasard.random()
    if tirage < 0.02:
        del t["sujet"]
    elif tirage < 0.03:
        t["message"] = ""
    elif tirage < 0.032:
        del t["sujet"]
        t["message"] = ""
    if hasard.random() < 0.01:
        del t["statut"]
    if hasard.random() < 0.004:
        del t[hasard.choice(["id", "cree_le", "client_id"])]
    return t


def generer_tickets(n: int, graine: int = 42, rafale: int = 240) -> list[str]:
    """Renvoie `n` lignes de texte (JSON, parfois tronqué ou en double), dans l'ordre d'arrivée."""
    hasard = random.Random(graine)
    rafale = min(rafale, n // 4)
    debut_rafale = datetime(2026, 9, 28)
    dates = [_date_aleatoire(hasard, DEBUT, debut_rafale) for _ in range(n - rafale)]
    dates += [_date_aleatoire(hasard, debut_rafale, FIN) for _ in range(rafale)]
    dates.sort()

    lignes: list[str] = []
    precedents: list[dict] = []
    for i, date in enumerate(dates, start=1):
        ticket = _abimer(hasard, _ticket_propre(hasard, i, date, recent=date >= debut_rafale))
        tirage = hasard.random()
        if tirage < 0.004 and precedents:  # copie exacte d'un ticket précédent
            ticket = dict(hasard.choice(precedents))
        elif tirage < 0.007 and precedents and "id" in ticket:  # même identifiant, autre contenu
            ticket["id"] = hasard.choice(precedents)["id"]
        precedents.append(ticket)
        ligne = json.dumps(ticket, ensure_ascii=False)
        if hasard.random() < 0.008:  # ligne coupée en route
            ligne = ligne[: hasard.randint(30, max(31, len(ligne) - 10))]
        lignes.append(ligne)
    return lignes


def generer_conseillers() -> str:
    lignes = ["agent_id,nom,competences,capacite_jour"]
    for i, (competences, capacite) in enumerate(CONSEILLERS, start=1):
        lignes.append(f"AG-{i:02d},Conseiller {i:02d},{competences},{capacite}")
    return "\n".join(lignes) + "\n"


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--n", type=int, default=2500, help="nombre de lignes de tickets (défaut 2500)")
    parseur.add_argument("--graine", type=int, default=42)
    parseur.add_argument("--rafale", type=int, default=240,
                         help="tickets arrivés du 28 au 30/09 (un arriéré à répartir)")
    parseur.add_argument("--sortie", type=Path, default=RACINE / "donnees" / "echantillon_tickets.jsonl")
    parseur.add_argument("--agents", type=Path, default=None,
                         help="chemin du CSV des conseillers (défaut : à côté des tickets)")
    args = parseur.parse_args()

    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text("\n".join(generer_tickets(args.n, args.graine, args.rafale)) + "\n", encoding="utf-8")
    chemin_agents = args.agents or args.sortie.with_name(
        "echantillon_conseillers.csv" if "echantillon" in args.sortie.name else "agents.csv")
    chemin_agents.write_text(generer_conseillers(), encoding="utf-8")
    print(f"{args.n} lignes -> {args.sortie}\n12 conseillers -> {chemin_agents}")


if __name__ == "__main__":
    main()
