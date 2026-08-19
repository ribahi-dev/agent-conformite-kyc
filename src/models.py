"""
Modeles de donnees de l'agent (Pydantic v2).

Le pipeline suit trois etapes, chacune avec son modele :

    texte brut  --[LLM]-->  ExtractionBrute  --[normalisation]-->  DocumentNormalise
                                                                          |
                                                                  [regles metier]
                                                                          v
                                                                 RapportConformite

Separer l'extraction (probabiliste, faite par le LLM) de la validation
(deterministe, faite par du code Python) est le choix d'architecture central de
ce projet : le LLM ne decide jamais de la conformite, il ne fait que lire.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TypeDocument(str, Enum):
    CIN = "CIN"
    JUSTIFICATIF_DOMICILE = "JUSTIFICATIF_DOMICILE"
    INCONNU = "INCONNU"


class StatutConformite(str, Enum):
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    A_VERIFIER = "A_VERIFIER"


class Severite(str, Enum):
    # Une anomalie BLOQUANTE entraine mecaniquement le rejet du document.
    BLOQUANT = "BLOQUANT"
    # Un AVERTISSEMENT n'empeche pas la validation mais impose une revue humaine.
    AVERTISSEMENT = "AVERTISSEMENT"


# ---------------------------------------------------------------------------
# Entree : le dossier client
# ---------------------------------------------------------------------------

class DossierClient(BaseModel):
    """Identite declaree par le client a l'ouverture du compte.

    C'est la reference contre laquelle le document est confronte.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    dossier_id: str
    nom: str
    prenom: str
    adresse_declaree: str | None = None

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"


# ---------------------------------------------------------------------------
# Etape 1 : sortie du LLM
# ---------------------------------------------------------------------------

class ExtractionBrute(BaseModel):
    """Ce que le LLM a lu dans le document, sans aucune interpretation.

    Tous les champs sont des chaines ou None : on n'impose aucun format au LLM,
    la normalisation est faite ensuite par du code Python maitrise. Un LLM a qui
    on demande de produire une date au format ISO produira parfois autre chose ;
    on prefere accepter sa sortie telle quelle et la nettoyer nous-memes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    type_document: str | None = None
    nom_titulaire: str | None = None
    prenom_titulaire: str | None = None
    numero_cin: str | None = None
    date_emission: str | None = None
    date_validite: str | None = None
    emetteur: str | None = None
    adresse: str | None = None

    # Auto-evaluation du LLM sur la lisibilite du document (0.0 a 1.0).
    confiance: float = Field(default=1.0, ge=0.0, le=1.0)
    # Trace de ce que le modele a renvoye, conservee pour l'audit.
    reponse_brute: str = ""


# ---------------------------------------------------------------------------
# Etape 2 : donnees normalisees
# ---------------------------------------------------------------------------

class DocumentNormalise(BaseModel):
    """Extraction convertie en types Python exploitables.

    Les champs qui n'ont pas pu etre convertis restent a None et l'echec est
    consigne dans `erreurs_normalisation` : on ne perd jamais l'information
    "le champ etait present mais illisible", qui est un motif de rejet distinct
    de "le champ etait absent".
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    type_document: TypeDocument = TypeDocument.INCONNU
    nom_titulaire: str | None = None
    prenom_titulaire: str | None = None
    numero_cin: str | None = None
    date_emission: date | None = None
    date_validite: date | None = None
    emetteur: str | None = None
    emetteur_canonique: str | None = None
    adresse: str | None = None
    confiance: float = 1.0

    erreurs_normalisation: list[str] = Field(default_factory=list)
    extraction: ExtractionBrute | None = None

    @property
    def nom_complet(self) -> str | None:
        parties = [p for p in (self.prenom_titulaire, self.nom_titulaire) if p]
        return " ".join(parties) if parties else None


# ---------------------------------------------------------------------------
# Etape 3 : resultat des controles
# ---------------------------------------------------------------------------

class Anomalie(BaseModel):
    """Un controle qui a echoue."""

    code: str
    libelle: str
    severite: Severite
    detail: str = ""
    valeur_attendue: str | None = None
    valeur_constatee: str | None = None

    def __str__(self) -> str:
        return f"[{self.severite.value}] {self.code} - {self.detail or self.libelle}"


class Controle(BaseModel):
    """Trace d'un controle execute, qu'il ait reussi ou echoue.

    Le rapport liste tous les controles et pas seulement les echecs : un auditeur
    doit pouvoir verifier qu'un controle a bien ete execute, et non deduire son
    execution de son silence.
    """

    nom: str
    reussi: bool
    detail: str = ""


class RapportConformite(BaseModel):
    """Livrable de l'agent : la decision et sa justification complete."""

    dossier_id: str
    nom_fichier: str | None = None
    statut: StatutConformite
    type_document: TypeDocument
    anomalies: list[Anomalie] = Field(default_factory=list)
    controles: list[Controle] = Field(default_factory=list)
    document: DocumentNormalise | None = None
    horodatage: datetime
    duree_traitement_ms: int = 0
    moteur_llm: str = ""

    @property
    def motifs_rejet(self) -> list[str]:
        return [a.detail or a.libelle for a in self.anomalies if a.severite is Severite.BLOQUANT]

    @property
    def avertissements(self) -> list[str]:
        return [a.detail or a.libelle for a in self.anomalies if a.severite is Severite.AVERTISSEMENT]

    @property
    def nb_controles_reussis(self) -> int:
        return sum(1 for c in self.controles if c.reussi)
