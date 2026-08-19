"""
Interface graphique de l'agent de conformite (livrable Semaine 3).

Lancement :
    streamlit run app.py

L'interface n'implemente aucune regle : elle ne fait qu'appeler l'agent et
mettre en forme son rapport. Toute la logique metier reste dans src/regles.py,
ce qui garantit que la demonstration et le traitement par lot rendent
exactement la meme decision sur un meme document.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st

from src.agent import AgentConformite
from src.llm import ClientOllama, ErreurLLM, charger_client
from src.models import DossierClient, RapportConformite, Severite, StatutConformite
from src.rapport import formater_markdown, formater_texte

RACINE = Path(__file__).parent
DOSSIER_DOCUMENTS = RACINE / "data" / "documents"
FICHIER_CAS = RACINE / "data" / "cas_de_test.json"

COULEURS = {
    StatutConformite.VALIDE: ("#0f7b3f", "#e7f6ec", "VALIDE"),
    StatutConformite.REJETE: ("#a02020", "#fbeaea", "REJETE"),
    StatutConformite.A_VERIFIER: ("#8a6100", "#fdf3e0", "A VERIFIER"),
}

st.set_page_config(page_title="Agent de conformite KYC", page_icon="[]", layout="wide")


# ---------------------------------------------------------------------------
# Chargement des donnees
# ---------------------------------------------------------------------------

@st.cache_data
def charger_cas_de_test() -> dict:
    if not FICHIER_CAS.exists():
        return {"cas": [], "date_reference": date.today().isoformat()}
    return json.loads(FICHIER_CAS.read_text(encoding="utf-8"))


def lister_documents() -> list[str]:
    if not DOSSIER_DOCUMENTS.exists():
        return []
    return sorted(p.name for p in DOSSIER_DOCUMENTS.glob("*.txt"))


# ---------------------------------------------------------------------------
# Affichage d'un rapport
# ---------------------------------------------------------------------------

def afficher_rapport(rapport: RapportConformite) -> None:
    couleur, fond, libelle = COULEURS[rapport.statut]

    st.markdown(
        f"""
        <div style="background:{fond};border-left:6px solid {couleur};
                    padding:16px 20px;border-radius:6px;margin-bottom:18px;">
          <div style="color:{couleur};font-size:26px;font-weight:700;">{libelle}</div>
          <div style="color:#444;font-size:14px;margin-top:4px;">
            {rapport.type_document.value} &nbsp;·&nbsp; dossier {rapport.dossier_id}
            &nbsp;·&nbsp; {rapport.duree_traitement_ms} ms
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if rapport.motifs_rejet:
        st.markdown("#### Motifs de rejet")
        for motif in rapport.motifs_rejet:
            st.error(motif, icon=None)

    if rapport.avertissements:
        st.markdown("#### Avertissements")
        for avertissement in rapport.avertissements:
            st.warning(avertissement, icon=None)

    if not rapport.anomalies:
        st.success("Aucune anomalie detectee. Le document satisfait tous les controles.")

    colonne_controles, colonne_donnees = st.columns(2)

    with colonne_controles:
        st.markdown(
            f"#### Controles ({rapport.nb_controles_reussis}/{len(rapport.controles)})"
        )
        for controle in rapport.controles:
            marque = "OK" if controle.reussi else "KO"
            detail = f" — {controle.detail}" if controle.detail else ""
            if controle.reussi:
                st.markdown(f"**`{marque}`** {controle.nom}{detail}")
            else:
                st.markdown(f"**`{marque}`** :red[{controle.nom}]{detail}")

    with colonne_donnees:
        st.markdown("#### Donnees extraites")
        document = rapport.document
        if document:
            champs = {
                "Nom": document.nom_complet or "—",
                "Numero CIN": document.numero_cin or "—",
                "Date d'emission": (
                    f"{document.date_emission:%d/%m/%Y}" if document.date_emission else "—"
                ),
                "Date de validite": (
                    f"{document.date_validite:%d/%m/%Y}" if document.date_validite else "—"
                ),
                "Emetteur": document.emetteur_canonique or document.emetteur or "—",
                "Adresse": document.adresse or "—",
                "Confiance": f"{document.confiance:.2f}",
            }
            st.table({"Champ": list(champs), "Valeur": list(champs.values())})

    with st.expander("Rapport complet (JSON) — piste d'audit"):
        st.code(rapport.model_dump_json(indent=2), language="json")

    st.download_button(
        "Telecharger le rapport (Markdown)",
        formater_markdown(rapport),
        file_name=f"rapport_{rapport.dossier_id}_{rapport.nom_fichier or 'document'}.md",
        mime="text/markdown",
    )


# ---------------------------------------------------------------------------
# Barre laterale : configuration
# ---------------------------------------------------------------------------

st.sidebar.title("Configuration")

moteur_choisi = st.sidebar.selectbox(
    "Moteur d'extraction",
    ["auto", "ollama", "simule"],
    help=(
        "auto : Ollama s'il repond, sinon repli sur le mode simule. "
        "simule : extraction par expressions regulieres, sans aucun modele."
    ),
)

modele_choisi = st.sidebar.text_input("Modele Ollama", value="llama3.2")

# Diagnostic du moteur, affiche en clair : une demonstration doit toujours
# indiquer ce qui a reellement produit le resultat.
sonde = ClientOllama(modele=modele_choisi)
if sonde.disponible():
    modeles = sonde.modeles_installes()
    st.sidebar.success("Ollama detecte")
    if modeles:
        st.sidebar.caption("Modeles installes : " + ", ".join(modeles))
    if modeles and not any(m.startswith(modele_choisi) for m in modeles):
        st.sidebar.warning(f"'{modele_choisi}' absent. Lance : ollama pull {modele_choisi}")
else:
    st.sidebar.info("Ollama non detecte — le mode simule sera utilise.")

st.sidebar.divider()
st.sidebar.subheader("Dossier client")

nom_client = st.sidebar.text_input("Nom", value="BENALI")
prenom_client = st.sidebar.text_input("Prenom", value="Youssef")
identifiant_dossier = st.sidebar.text_input("Identifiant du dossier", value="D-2026-001")

donnees_cas = charger_cas_de_test()
date_defaut = date.fromisoformat(donnees_cas["date_reference"])
date_examen = st.sidebar.date_input(
    "Date d'examen du dossier",
    value=date_defaut,
    help=(
        "Toutes les regles de date se calculent par rapport a cette date. "
        "La modifier permet de rejouer un dossier tel qu'il aurait ete traite "
        "a une date passee."
    ),
)

st.sidebar.divider()
st.sidebar.caption(
    "Donnees entierement fictives. Projet pedagogique — cet agent ne remplace "
    "pas une validation par un analyste conformite."
)


# ---------------------------------------------------------------------------
# Page principale
# ---------------------------------------------------------------------------

st.title("Agent d'analyse de conformite KYC")
st.caption(
    "Le modele de langage lit le document. Les regles metier decident. "
    "Chaque decision est motivee, tracee et reproductible."
)

onglet_document, onglet_lot, onglet_regles = st.tabs(
    ["Analyser un document", "Traitement par lot", "Regles appliquees"]
)


def construire_agent() -> AgentConformite | None:
    try:
        return AgentConformite(client=charger_client(moteur_choisi, modele_choisi))
    except ErreurLLM as erreur:
        st.error(f"Moteur indisponible : {erreur}")
        return None


# -- Onglet 1 : un document ------------------------------------------------

with onglet_document:
    source = st.radio(
        "Source du document",
        ["Jeu de donnees fictives", "Coller un texte", "Televerser un fichier"],
        horizontal=True,
    )

    texte_document = ""
    nom_document = None

    if source == "Jeu de donnees fictives":
        documents = lister_documents()
        if not documents:
            st.warning("Aucun document. Lance d'abord : python generer_donnees.py")
        else:
            nom_document = st.selectbox("Document", documents)
            texte_document = (DOSSIER_DOCUMENTS / nom_document).read_text(encoding="utf-8")

            # Pre-remplissage du dossier client attendu pour ce document, afin
            # d'eviter les faux rejets dus a une saisie manuelle incoherente.
            correspondance = next(
                (c for c in donnees_cas["cas"] if c["fichier"] == nom_document), None
            )
            if correspondance:
                attendu = correspondance["statut_attendu"]
                st.caption(
                    f"Cas de test — attendu : **{attendu}** · {correspondance['description']}"
                )
                st.caption(
                    "Dossier associe : "
                    f"{correspondance['dossier']['prenom']} {correspondance['dossier']['nom']} "
                    f"({correspondance['dossier']['dossier_id']})"
                )

            with st.expander("Contenu du document"):
                st.text(texte_document)

    elif source == "Coller un texte":
        texte_document = st.text_area("Contenu du document", height=280)
        nom_document = "saisie_manuelle.txt"

    else:
        fichier = st.file_uploader("Fichier texte", type=["txt", "md"])
        if fichier is not None:
            texte_document = fichier.read().decode("utf-8", errors="replace")
            nom_document = fichier.name
            with st.expander("Contenu du document"):
                st.text(texte_document)

    if st.button("Analyser", type="primary", disabled=not texte_document.strip()):
        agent = construire_agent()
        if agent:
            with st.spinner(f"Analyse en cours ({agent.client.nom})..."):
                rapport = agent.analyser(
                    texte_document,
                    DossierClient(
                        dossier_id=identifiant_dossier, nom=nom_client, prenom=prenom_client
                    ),
                    date_reference=date_examen,
                    nom_fichier=nom_document,
                )
            afficher_rapport(rapport)


# -- Onglet 2 : lot --------------------------------------------------------

with onglet_lot:
    st.markdown(
        "Analyse l'ensemble du jeu de donnees fictives et confronte chaque decision "
        "au resultat attendu. C'est cette vue qui permet d'affirmer un taux de "
        "justesse plutot que de le supposer."
    )

    if not donnees_cas["cas"]:
        st.warning("Jeu de donnees absent. Lance : python generer_donnees.py")
    elif st.button("Lancer le traitement par lot", type="primary"):
        agent = construire_agent()
        if agent:
            documents = []
            for cas in donnees_cas["cas"]:
                chemin = DOSSIER_DOCUMENTS / cas["fichier"]
                if chemin.exists():
                    documents.append(
                        (
                            cas["fichier"],
                            chemin.read_text(encoding="utf-8"),
                            DossierClient(**cas["dossier"]),
                        )
                    )

            barre = st.progress(0.0, text="Analyse en cours...")
            rapports = []
            for index, (nom, texte, dossier) in enumerate(documents, start=1):
                rapports.append(
                    agent.analyser(
                        texte,
                        dossier,
                        date_reference=date.fromisoformat(donnees_cas["date_reference"]),
                        nom_fichier=nom,
                    )
                )
                barre.progress(index / len(documents), text=f"{index}/{len(documents)} — {nom}")
            barre.empty()

            attendus = {c["fichier"]: c["statut_attendu"] for c in donnees_cas["cas"]}
            corrects = sum(1 for r in rapports if attendus.get(r.nom_fichier) == r.statut.value)

            colonnes = st.columns(4)
            colonnes[0].metric("Documents", len(rapports))
            colonnes[1].metric(
                "Decisions correctes", f"{corrects}/{len(rapports)}",
                f"{100 * corrects / len(rapports):.0f} %",
            )
            colonnes[2].metric(
                "Rejetes", sum(1 for r in rapports if r.statut is StatutConformite.REJETE)
            )
            colonnes[3].metric(
                "Duree moyenne",
                f"{sum(r.duree_traitement_ms for r in rapports) // len(rapports)} ms",
            )

            lignes = []
            for rapport in rapports:
                attendu = attendus.get(rapport.nom_fichier, "?")
                lignes.append(
                    {
                        "Document": rapport.nom_fichier,
                        "Attendu": attendu,
                        "Obtenu": rapport.statut.value,
                        "Conforme au test": "oui" if attendu == rapport.statut.value else "NON",
                        "Motif principal": (
                            rapport.anomalies[0].code if rapport.anomalies else "—"
                        ),
                    }
                )
            st.dataframe(lignes, width="stretch", hide_index=True)

            ecarts = [ligne for ligne in lignes if ligne["Conforme au test"] == "NON"]
            if ecarts:
                st.subheader("Ecarts entre le resultat attendu et le resultat obtenu")
                for ecart in ecarts:
                    st.write(
                        f"**{ecart['Document']}** — attendu {ecart['Attendu']}, "
                        f"obtenu {ecart['Obtenu']} ({ecart['Motif principal']})"
                    )


# -- Onglet 3 : regles -----------------------------------------------------

with onglet_regles:
    from src.config import (
        ALERTE_EXPIRATION_CIN_JOURS,
        ANCIENNETE_MAX_JUSTIFICATIF_MOIS,
        CODES_ANOMALIE,
        EMETTEURS_JUSTIFICATIF_DOMICILE,
        REGEX_NUMERO_CIN,
        SEUIL_CORRESPONDANCE_NOM,
    )

    st.markdown(
        "Ces valeurs sont lues directement depuis `src/config.py`. Les modifier "
        "dans ce fichier change le comportement de l'agent sans toucher a son code."
    )

    colonne_gauche, colonne_droite = st.columns(2)

    with colonne_gauche:
        st.markdown("#### Seuils")
        st.write(f"- Anciennete maximale d'un justificatif : **{ANCIENNETE_MAX_JUSTIFICATIF_MOIS} mois**")
        st.write(f"- Alerte avant expiration d'une CIN : **{ALERTE_EXPIRATION_CIN_JOURS} jours**")
        st.write(f"- Score minimal de correspondance du nom : **{SEUIL_CORRESPONDANCE_NOM}**")
        st.write(f"- Format du numero de CIN : `{REGEX_NUMERO_CIN}`")

        st.markdown("#### Emetteurs autorises")
        st.write("**CIN** : DGSN exclusivement")
        st.write("**Justificatif de domicile** : " + ", ".join(EMETTEURS_JUSTIFICATIF_DOMICILE))

    with colonne_droite:
        st.markdown("#### Codes d'anomalie")
        st.dataframe(
            [{"Code": code, "Libelle": libelle} for code, libelle in CODES_ANOMALIE.items()],
            width="stretch",
            hide_index=True,
            height=420,
        )

    st.divider()
    st.markdown(
        """
        #### Regle de decision

        | Anomalies relevees | Statut |
        |---|---|
        | Au moins une anomalie **bloquante** | REJETE |
        | Uniquement des **avertissements** | A VERIFIER (revue humaine) |
        | Aucune | VALIDE |

        Un echec technique — moteur injoignable, document illisible — produit
        **REJETE**, jamais VALIDE : en conformite, l'absence de preuve ne vaut
        pas preuve de conformite.
        """
    )
