"""Interface de la démo : les cinq questions de la démo, une par onglet.

Lancer depuis la racine du dépôt :   streamlit run demo/app.py
Aucun message de client ni client_id n'est jamais affiché. Les calculs sont dans demo/calculs.py.
"""

from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pour importer moteur_sav et demo

from demo import calculs as c  # noqa: E402

st.set_page_config(page_title="Moteur SAV", page_icon="🌿", layout="wide")


@st.cache_resource(show_spinner="Lecture des données (sur une copie)...")
def donnees() -> dict:
    return c.charger()


@st.cache_resource(show_spinner="Construction de l'index...")
def index():
    return c.construire_index(D["tickets"])


@st.cache_resource
def urgents():
    return c.plus_urgents(D["tickets"])


def tableau(lignes: list[dict], **colonnes) -> None:
    st.dataframe(lignes, hide_index=True, width="stretch", column_config=colonnes or None)


def complexite(lignes: list[dict], titre: str = "Complexité") -> None:
    st.markdown(f"**{titre}**")
    tableau(lignes)


def structures(etape: int) -> None:
    """Les structures de données de l'étape, et pourquoi ces choix."""
    with st.expander("Structures de données utilisées, et pourquoi"):
        tableau(c.STRUCTURES[etape])


def mesure(image: str, commande: str, legende: str) -> None:
    """Le graphique de mesure déjà produit, ou la commande pour le produire."""
    chemin = c.RESULTATS / image
    if chemin.exists():
        st.image(str(chemin), caption=legende)
    else:
        st.info(f"Pas encore de mesure : `{commande}` produit `benchmarks/resultats/{image}`.")


D = donnees()

# --------------------------------------------------------------------------- en-tête
st.title("🌿 Moteur SAV")
if D["complet"]:
    st.caption(f"Données : `{D['source']}`, traitées sur une copie. Aucun message ni client_id n'est affiché.")
else:
    st.warning(f"Jeu complet absent de `donnees/` : démo sur l'échantillon synthétique `{D['source']}` (pour le générer : `python scripts/generer_donnees.py --n 25000 --sortie donnees/tickets.jsonl`). "
               "Aucun message ni client_id n'est affiché.")

onglets = st.tabs(["1 · Bilan", "2 · Les plus urgents", "3 · Recherche", "4 · Annuler / rétablir",
                   "5 · Répartition", "Limite et suite"])

# --------------------------------------------------------------------------- 1. bilan
with onglets[0]:
    st.subheader("Combien de tickets sont exploitables, et pourquoi les autres sont écartés ?")
    b = c.bilan(D["tickets"], D["rejets"])
    total = b["exploitables"] + b["ecartes"]
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Exploitables", f"{b['exploitables']:,}".replace(",", " "), f"{b['exploitables'] / total:.1%} des lignes")
    a2.metric("Écartés", f"{b['ecartes']:,}".replace(",", " "), f"{b['ecartes'] / total:.1%} des lignes", delta_color="off")
    a3.metric("Priorité estimée", b["priorites_estimees"])
    a4.metric("Date estimée", b["dates_estimees"])
    with st.expander("Que veulent dire « priorité estimée » et « date estimée » ?"):
        st.markdown(c.explication_estimations(b["priorites_estimees"], b["dates_estimees"]))
    if b["motifs"]:
        tableau(b["motifs"], tickets=st.column_config.ProgressColumn(
            "tickets", min_value=0, max_value=b["motifs"][0]["tickets"], format="%d"))   # la barre = la part du 1er motif
    with st.expander("Voir des lignes écartées (numéro, motif, détail : jamais le message)"):
        tableau([{"ligne": r["ligne"], "motif": r["motif"], "détail": r["detail"]} for r in D["rejets"][:15]])
    complexite(c.complexite_lecture(total))
    structures(1)
    with st.expander("Comment les données ont été nettoyées (ingestion)"):
        st.caption("Une règle par ligne. « Écart » : règle plus souple qu'une lecture stricte, justifiée par le nombre de tickets sauvés.")
        tableau(c.regles_nettoyage())

# --------------------------------------------------------------------------- 2. urgents
with onglets[1]:
    st.subheader("Quels sont les 10 tickets ouverts les plus urgents ?")
    st.caption("Extraits de notre file de priorité (tas binaire) avec la clé : échéance, puis priorité, puis date de création.")
    tableau([c.ligne_ticket(t) for t in urgents()])
    nb_ouverts = sum(t.statut == "ouvert" for t in D["tickets"])
    complexite(c.complexite_urgents(nb_ouverts), f"Complexité (n = {nb_ouverts} tickets ouverts dans la file)")
    structures(2)
    st.caption("À urgence égale, le premier arrivé passe d'abord : chaque ticket garde son numéro d'arrivée.")
    st.markdown("**Mesure : notre tas, `heapq` et une liste retriée à chaque ajout**")
    st.caption("Mesure faite en direct : n ajouts puis n extractions, mêmes clés aléatoires (graine 42), "
               "meilleur de 3 essais. La liste retriée n'est pas mesurée à 100 000 (plusieurs minutes).")
    # Clé du bouton distincte de celle des résultats : streamlit range l'état du bouton sous sa clé.
    if st.button("Lancer la mesure (3 à 4 secondes)", key="bouton_mesure_tas"):
        with st.spinner("Mesure en cours..."):
            st.session_state["mesure_tas"] = c.mesurer_tas()
    if "mesure_tas" in st.session_state:
        lignes = st.session_state["mesure_tas"]
        graphique = alt.Chart(alt.Data(values=lignes)).mark_line(
            strokeWidth=2, point=alt.OverlayMarkDef(size=80, filled=True)
        ).encode(
            x=alt.X("n:Q", scale=alt.Scale(type="log"), title="n : nombre d'éléments (n ajouts puis n extractions)"),
            y=alt.Y("temps_ms:Q", scale=alt.Scale(type="log"), title="temps en ms (meilleur de 3)"),
            color=alt.Color("methode:N", title="méthode",
                            scale=alt.Scale(domain=["tas maison", "heapq", "liste retriée"],
                                            range=["#2a78d6", "#eb6834", "#1baf7a"]),
                            legend=alt.Legend(orient="top")),
            tooltip=[alt.Tooltip("methode:N", title="méthode"),
                     alt.Tooltip("n:Q", format=",", title="n"),
                     alt.Tooltip("temps_ms:Q", format=".2f", title="temps (ms)")],
        ).properties(height=360)
        st.altair_chart(graphique, width="stretch")
        st.markdown("**Par combien le temps est-il multiplié quand n est multiplié par 10 ?**")
        tableau(c.facteurs_croissance(lignes))
        st.caption("Environ ×13 : coût en n log n (tas, heapq). Bien plus que ×10 : coût en n² (liste retriée).")

# --------------------------------------------------------------------------- 3. recherche
with onglets[2]:
    st.subheader("Quels tickets parlent de « pot cassé » ? Quels mots commencent par « cochen » ?")
    gauche, droite = st.columns(2)
    with gauche:
        requete = st.text_input("Mots recherchés", "pot cassé")
        mode = st.radio("Mode", ["ET", "OU"], horizontal=True, help="ET : tous les mots. OU : au moins un.")
        total_trouves, lignes, duree = c.chercher(index(), D["par_id"], requete, mode)
        st.metric("Tickets trouvés", total_trouves, f"en {duree:.0f} µs", delta_color="off")
        if lignes:
            st.caption(f"Les {len(lignes)} premiers :")
            tableau(lignes)
    with droite:
        debut = st.text_input("Début de mot", "cochen")
        mots = index().prefixe(debut, limite=30)
        st.metric("Mots trouvés", len(mots), help="Recherche dichotomique dans le vocabulaire trié (30 au plus).")
        if mots:
            st.write(", ".join(f"`{m}`" for m in mots))
    complexite(c.complexite_recherche(len(index()), index().nb_mots))
    structures(4)
    st.markdown("**Mesure : index contre balayage, dichotomie contre parcours linéaire**")
    mesure("benchmark_index.png", "python benchmarks/benchmark_index.py",
           "Gauche : recherche ET. Droite : début de mot. Plus la courbe est haute, plus c'est lent.")
    tableaux_mesures = c.RESULTATS / "index.md"
    if tableaux_mesures.exists():
        with st.expander("Tableaux de mesure et interprétation"):
            st.markdown(tableaux_mesures.read_text(encoding="utf-8"))

# --------------------------------------------------------------------------- 4. annuler / rétablir
with onglets[3]:
    st.subheader("Une action, son annulation, son rétablissement")
    st.caption("Les 10 tickets les plus urgents, en copie : les vrais tickets ne sont jamais modifiés.")
    if "atelier" not in st.session_state:
        st.session_state.atelier = c.Atelier(urgents())
    atelier = st.session_state.atelier

    f1, f2, f3 = st.columns(3)
    ticket_id = f1.selectbox("Ticket", list(atelier.tickets))
    action = f2.radio("Action", c.ACTIONS)
    if action == c.ACTIONS[0]:
        valeur = f3.selectbox("Nouveau statut", c.STATUTS_PROPOSES)
    elif action == c.ACTIONS[1]:
        valeur = f3.selectbox("Nouvelle priorité", c.PRIORITES_PROPOSEES, format_func=lambda p: f"P{p}")
    else:
        valeur = f3.selectbox("Conseiller", [a.agent_id for a in D["agents"]])

    b1, b2, b3 = st.columns(3)
    try:
        if b1.button("Exécuter", type="primary", width="stretch"):
            atelier.faire(action, ticket_id, valeur)
        if b2.button("↶ Annuler (Ctrl+Z)", width="stretch") and not atelier.historique.annuler():
            st.info("Rien à annuler.")
        if b3.button("↷ Rétablir (Ctrl+Y)", width="stretch") and not atelier.historique.retablir():
            st.info("Rien à rétablir.")
    except ValueError as erreur:
        st.error(str(erreur))

    tableau(atelier.lignes())
    journal = atelier.historique.journal()
    st.markdown("**Journal des actions en vigueur** (de la plus ancienne à la plus récente)")
    st.code("\n".join(journal) if journal else "(aucune action)", language=None)
    complexite(c.complexite_historique())
    structures(3)

# --------------------------------------------------------------------------- 5. répartition
with onglets[4]:
    st.subheader("Quel taux de délais tenus, avec notre répartition et avec la répartition naïve ?")
    depuis_defaut, debut_defaut = c.lot_par_defaut(D["tickets"])
    if not D["complet"]:
        st.info("Les données s'arrêtent avant la date du lot type : les dates proposées sont celles de leurs derniers jours, "
                "et non celles du lot type (créés depuis le 28/09, traités à partir du 01/10 à 8 h).")
    p1, p2, p3 = st.columns(3)
    depuis = datetime.combine(p1.date_input("Tickets non résolus créés depuis le", depuis_defaut.date()), time())
    debut_jour = p2.date_input("Traités à partir du", debut_defaut.date())
    debut_heure = p3.time_input("à", debut_defaut.time())
    traitement = datetime.combine(debut_jour, debut_heure)

    lot = c.lot_conseille(D["tickets"], depuis)
    st.caption(f"Lot : {len(lot)} tickets non résolus · {len(D['agents'])} conseillers · "
               f"un ticket toutes les {c.DUREE_MINUTES} minutes par conseiller.")
    if lot:
        comparaison = c.comparer(lot, D["agents"], traitement)
        details = c.details_repartition(lot, D["agents"], traitement)
        m1, m2, m3 = st.columns(3)
        for colonne, ligne in zip((m1, m2), comparaison):
            colonne.metric(ligne["répartition"], f"{ligne['délais tenus']:.1%}",
                           f"{ligne['non affectés']} non affectés", delta_color="off")
        m3.metric("Maximum atteignable", f"{details['maximum']:.1%}",
                  f"{details['perdus']} tickets déjà perdus au départ", delta_color="off")
        st.success(c.conclusion(comparaison, len(lot)))

        couleurs = alt.Scale(domain=["gloutonne", "naïve", "maximum atteignable"],
                             range=["#2a78d6", "#eb6834", "#8a8a8a"])

        st.markdown("**Charge par conseiller** : la naïve remplit les premiers de la liste, la gloutonne équilibre.")
        base = alt.Chart(alt.Data(values=details["charges"]))
        barres = base.mark_bar().encode(
            x=alt.X("conseiller:N", title=None), xOffset="répartition:N",
            y=alt.Y("tickets:Q", title="tickets reçus"),
            color=alt.Color("répartition:N", scale=couleurs, legend=alt.Legend(orient="top", title=None)),
            tooltip=["conseiller:N", "répartition:N", "tickets:Q", "capacité:Q"])
        capacite = base.mark_tick(color="#333333", thickness=2, size=28).encode(
            x="conseiller:N", y="capacité:Q", tooltip=["conseiller:N", "capacité:Q"])
        st.altair_chart((barres + capacite).properties(height=320), width="stretch")
        st.caption("Trait noir : capacité du conseiller.")

        st.markdown("**Délais tenus par priorité**, comparés au maximum atteignable.")
        st.altair_chart(alt.Chart(alt.Data(values=details["par_priorite"])).mark_bar().encode(
            x=alt.X("priorité:N", title=None), xOffset="série:N",
            y=alt.Y("taux:Q", title="délais tenus", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("série:N", scale=couleurs, legend=alt.Legend(orient="top", title=None)),
            tooltip=["priorité:N", "série:N", alt.Tooltip("taux:Q", format=".1%")],
        ).properties(height=300), width="stretch")

        with st.expander("Pourquoi la gloutonne gagne : un exemple calculé à la main"):
            st.markdown("Deux tickets inventés, deux conseillers, début à 8 h. **U** est une priorité 1 "
                        "d'échéance 8 h 30, **A** une priorité 3 créée la veille.")
            tableau(c.exemple_a_la_main())
            st.caption("La naïve sert A d'abord (plus ancien) : U finit à 8 h 40, trop tard. "
                       "La gloutonne sert U d'abord et donne A à l'autre conseiller : 100 % contre 50 %.")
    else:
        st.warning("Aucun ticket dans ce lot : choisis une date de début plus ancienne.")
    complexite(c.complexite_repartition(len(lot), len(D["agents"])))
    structures(5)

# --------------------------------------------------------------------------- limite et suite
with onglets[5]:
    st.subheader("Notre limite, puis la suite")
    st.markdown("#### Limite : la recherche ne reconnaît pas les accords")
    st.markdown("« cassé », « cassée », « cassés » et « cassées » sont quatre mots différents pour l'index. "
                "Un conseiller qui tape « pot cassé » ne voit pas les tickets écrits « pot cassée » :")
    lignes, total = c.formes_du_mot(index())
    tableau(lignes)
    premier = lignes[0]["tickets trouvés"]
    st.warning(f"« pot cassé » seul trouve {premier} tickets ; avec les quatre formes on en trouve {total}, "
               f"soit {total - premier} de plus qui passent inaperçus.")
    st.markdown("**Pourquoi** : nous comparons des mots entiers, sans chercher leur racine. C'est un choix de "
                "simplicité : l'index reste exact et rapide, mais il ne comprend pas la langue.  \n"
                "**En attendant** : taper le début du mot (`cass`, onglet 3) ou utiliser le mode OU.")
    st.markdown("#### La suite")
    st.markdown("""
1. **Racinisation simple** : retirer les terminaisons « -e », « -s » avant d'indexer, pour que les quatre formes se valent.
   On la juge en rejouant le tableau ci-dessus : « pot cassé » doit alors trouver à lui seul le total annoncé ci-dessus.
2. **Arbre de préfixes (trie)** pour l'autocomplétion, à mesurer contre notre dichotomie.
3. **Répartition** : tester une variante qui sert d'abord les tickets encore sauvables plutôt que les plus en retard.
""")
