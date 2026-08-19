"""
L'agent : orchestration du pipeline complet.

    texte --[extraction LLM]--> brut --[normalisation]--> normalise
                                                              |
                                                       [regles metier]
                                                              v
                                                      RapportConformite

L'agent lui-meme ne contient aucune regle de conformite. Son role est
d'enchainer les etapes, de mesurer, de tracer, et surtout de garantir qu'aucune
defaillance technique ne peut produire un "VALIDE" par accident : toute
exception non prevue devient un rejet motive, jamais une validation.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from . import regles
from .extraction import extraire, normaliser
from .llm import ClientLLM, ErreurLLM, charger_client
from .models import (
    Anomalie,
    Controle,
    DocumentNormalise,
    DossierClient,
    RapportConformite,
    Severite,
    StatutConformite,
    TypeDocument,
)

journal = logging.getLogger("agent_conformite")


class AgentConformite:
    """Analyse un document et rend un rapport de conformite.

    Exemple :
        agent = AgentConformite()
        dossier = DossierClient(dossier_id="D-001", nom="BENALI", prenom="Youssef")
        rapport = agent.analyser(texte_du_document, dossier)
        print(rapport.statut)
    """

    def __init__(self, client: ClientLLM | None = None, moteur: str = "auto") -> None:
        self.client = client or charger_client(moteur)

    # -- analyse d'un document ---------------------------------------------

    def analyser(
        self,
        texte_document: str,
        dossier: DossierClient,
        date_reference: date | None = None,
        nom_fichier: str | None = None,
    ) -> RapportConformite:
        """Traite un document et renvoie son rapport de conformite."""
        depart = perf_counter()
        date_reference = date_reference or date.today()

        if not texte_document or not texte_document.strip():
            return self._rapport_echec(
                dossier,
                nom_fichier,
                code="DOC_ILLISIBLE",
                detail="Le document fourni est vide.",
                depart=depart,
            )

        # Etape 1 : lecture par le LLM.
        try:
            brut = extraire(texte_document, self.client)
        except ErreurLLM as erreur:
            journal.warning("Extraction impossible (%s) : %s", nom_fichier, erreur)
            return self._rapport_echec(
                dossier,
                nom_fichier,
                code="DOC_ILLISIBLE",
                detail=f"Lecture du document impossible : {erreur}",
                depart=depart,
            )

        # Etape 2 : normalisation.
        document = normaliser(brut)

        # Etape 3 : regles metier.
        statut, anomalies, controles = regles.valider(document, dossier, date_reference)

        journal.info(
            "%s -> %s (%d anomalie(s))", nom_fichier or "document", statut.value, len(anomalies)
        )

        return RapportConformite(
            dossier_id=dossier.dossier_id,
            nom_fichier=nom_fichier,
            statut=statut,
            type_document=document.type_document,
            anomalies=anomalies,
            controles=controles,
            document=document,
            horodatage=datetime.now(),
            duree_traitement_ms=int((perf_counter() - depart) * 1000),
            moteur_llm=self.client.nom,
        )

    def analyser_fichier(
        self,
        chemin: str | Path,
        dossier: DossierClient,
        date_reference: date | None = None,
    ) -> RapportConformite:
        """Lit un fichier texte et l'analyse."""
        chemin = Path(chemin)
        texte = chemin.read_text(encoding="utf-8")
        return self.analyser(texte, dossier, date_reference, nom_fichier=chemin.name)

    def analyser_lot(
        self,
        documents: list[tuple[str, str, DossierClient]],
        date_reference: date | None = None,
    ) -> list[RapportConformite]:
        """Analyse une liste de (nom_fichier, texte, dossier).

        Un document qui echoue n'interrompt pas le lot : le traitement d'une
        file d'attente KYC ne doit pas s'arreter sur un document corrompu.
        """
        rapports: list[RapportConformite] = []
        for nom_fichier, texte, dossier in documents:
            try:
                rapports.append(self.analyser(texte, dossier, date_reference, nom_fichier))
            except Exception as erreur:  # filet de securite du traitement par lot
                journal.exception("Echec inattendu sur %s", nom_fichier)
                rapports.append(
                    self._rapport_echec(
                        dossier,
                        nom_fichier,
                        code="DOC_ILLISIBLE",
                        detail=f"Erreur inattendue : {erreur}",
                        depart=perf_counter(),
                    )
                )
        return rapports

    # -- gestion des echecs -------------------------------------------------

    def _rapport_echec(
        self,
        dossier: DossierClient,
        nom_fichier: str | None,
        code: str,
        detail: str,
        depart: float,
    ) -> RapportConformite:
        """Construit un rapport de rejet lorsque l'analyse n'a pas pu aboutir.

        Choix deliberé : un echec technique produit REJETE et non A_VERIFIER.
        En conformite, l'absence de preuve n'est pas une preuve d'absence de
        probleme ; le document repart en traitement manuel avec un motif clair.
        """
        return RapportConformite(
            dossier_id=dossier.dossier_id,
            nom_fichier=nom_fichier,
            statut=StatutConformite.REJETE,
            type_document=TypeDocument.INCONNU,
            anomalies=[
                Anomalie(
                    code=code,
                    libelle="Document non analysable",
                    severite=Severite.BLOQUANT,
                    detail=detail,
                )
            ],
            controles=[Controle(nom="Lecture du document", reussi=False, detail=detail)],
            document=DocumentNormalise(),
            horodatage=datetime.now(),
            duree_traitement_ms=int((perf_counter() - depart) * 1000),
            moteur_llm=self.client.nom,
        )
