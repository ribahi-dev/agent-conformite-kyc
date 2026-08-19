"""
Etapes 1 et 2 du pipeline : extraction par le LLM, puis normalisation.

L'extraction est probabiliste (un modele lit un texte). La normalisation est
deterministe (du code Python convertit des chaines en types). Les deux sont
separees pour qu'un echec de lecture soit distinguable d'un echec de format :
"date absente" et "date illisible" ne sont pas le meme motif de rejet.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime

from dateutil import parser as parseur_dates

from .config import (
    EMETTEURS_JUSTIFICATIF_DOMICILE,
    FORMATS_DATE,
    VARIANTES_EMETTEUR_CIN,
)
from .llm import ClientLLM, ErreurLLM
from .models import DocumentNormalise, ExtractionBrute, TypeDocument
from .prompts import SYSTEM_EXTRACTION, construire_prompt_extraction


# ---------------------------------------------------------------------------
# Etape 1 : appel du LLM
# ---------------------------------------------------------------------------

def extraire(texte_document: str, client: ClientLLM) -> ExtractionBrute:
    """Demande au LLM de lire le document et renvoie sa lecture brute.

    Leve ErreurLLM si le moteur est injoignable ou si sa reponse ne contient
    aucun JSON exploitable. L'appelant (l'agent) traite cette erreur comme un
    document non analysable, jamais comme un document valide.
    """
    prompt = construire_prompt_extraction(texte_document)
    reponse = client.generer(prompt, system=SYSTEM_EXTRACTION)

    donnees = _extraire_json(reponse)
    if donnees is None:
        raise ErreurLLM(
            "Le moteur n'a pas renvoye de JSON exploitable. "
            f"Debut de reponse : {reponse[:200]!r}"
        )

    return ExtractionBrute(
        type_document=_texte_ou_none(donnees.get("type_document")),
        nom_titulaire=_texte_ou_none(donnees.get("nom_titulaire")),
        prenom_titulaire=_texte_ou_none(donnees.get("prenom_titulaire")),
        numero_cin=_texte_ou_none(donnees.get("numero_cin")),
        date_emission=_texte_ou_none(donnees.get("date_emission")),
        date_validite=_texte_ou_none(donnees.get("date_validite")),
        emetteur=_texte_ou_none(donnees.get("emetteur")),
        adresse=_texte_ou_none(donnees.get("adresse")),
        confiance=_confiance(donnees.get("confiance")),
        reponse_brute=reponse,
    )


def _extraire_json(reponse: str) -> dict | None:
    """Isole l'objet JSON dans une reponse qui peut contenir du texte autour.

    Les modeles locaux entourent frequemment leur JSON d'une phrase
    d'introduction ou de balises de code, malgre la consigne.
    """
    reponse = reponse.strip()

    # Cas nominal : la reponse entiere est du JSON.
    try:
        donnees = json.loads(reponse)
        return donnees if isinstance(donnees, dict) else None
    except json.JSONDecodeError:
        pass

    # Repli : on retire d'eventuelles balises de code puis on cherche le premier
    # objet equilibre.
    sans_balises = re.sub(r"^```(?:json)?|```$", "", reponse, flags=re.MULTILINE).strip()
    debut = sans_balises.find("{")
    if debut == -1:
        return None

    profondeur = 0
    for position, caractere in enumerate(sans_balises[debut:], start=debut):
        if caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                try:
                    donnees = json.loads(sans_balises[debut : position + 1])
                    return donnees if isinstance(donnees, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _texte_ou_none(valeur: object) -> str | None:
    """Convertit une valeur du JSON en chaine propre, ou None.

    Les modeles renvoient parfois la chaine "null", "N/A" ou "" au lieu de null.
    """
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if not texte or texte.lower() in {"null", "none", "n/a", "na", "-", "inconnu", "non precise"}:
        return None
    return texte


def _confiance(valeur: object) -> float:
    try:
        score = float(valeur)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, score))


# ---------------------------------------------------------------------------
# Etape 2 : normalisation
# ---------------------------------------------------------------------------

def normaliser(extraction: ExtractionBrute) -> DocumentNormalise:
    """Convertit la lecture brute en donnees typees et canoniques."""
    erreurs: list[str] = []

    type_document = _normaliser_type(extraction.type_document)

    date_emission = None
    if extraction.date_emission:
        date_emission = _parser_date(extraction.date_emission)
        if date_emission is None:
            erreurs.append(f"date_emission illisible : {extraction.date_emission!r}")

    date_validite = None
    if extraction.date_validite:
        date_validite = _parser_date(extraction.date_validite)
        if date_validite is None:
            erreurs.append(f"date_validite illisible : {extraction.date_validite!r}")

    emetteur_canonique = None
    if extraction.emetteur:
        emetteur_canonique = canoniser_emetteur(extraction.emetteur)

    numero_cin = None
    if extraction.numero_cin:
        # On retire espaces et tirets internes avant tout controle de format :
        # "BE 745 123" et "BE745123" designent le meme numero.
        numero_cin = re.sub(r"[\s\-]", "", extraction.numero_cin).upper()

    return DocumentNormalise(
        type_document=type_document,
        nom_titulaire=_nettoyer_nom(extraction.nom_titulaire),
        prenom_titulaire=_nettoyer_nom(extraction.prenom_titulaire),
        numero_cin=numero_cin,
        date_emission=date_emission,
        date_validite=date_validite,
        emetteur=extraction.emetteur,
        emetteur_canonique=emetteur_canonique,
        adresse=extraction.adresse,
        confiance=extraction.confiance,
        erreurs_normalisation=erreurs,
        extraction=extraction,
    )


def _normaliser_type(valeur: str | None) -> TypeDocument:
    if not valeur:
        return TypeDocument.INCONNU
    normalise = supprimer_accents(valeur).upper().replace(" ", "_")
    if "CIN" in normalise or "IDENTITE" in normalise:
        return TypeDocument.CIN
    if "DOMICILE" in normalise or "RESIDENCE" in normalise or "FACTURE" in normalise:
        return TypeDocument.JUSTIFICATIF_DOMICILE
    return TypeDocument.INCONNU


def _parser_date(texte: str) -> date | None:
    """Convertit une date ecrite en objet date.

    Les formats explicites de config.py sont essayes en premier. Le repli sur
    dateutil utilise dayfirst=True : au Maroc comme en France, 03/04/2026 se lit
    3 avril, jamais 4 mars. Se tromper ici fausserait le calcul d'anciennete.
    """
    texte = texte.strip()

    for format_date in FORMATS_DATE:
        try:
            return datetime.strptime(texte, format_date).date()
        except ValueError:
            continue

    try:
        return parseur_dates.parse(texte, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def canoniser_emetteur(emetteur: str) -> str | None:
    """Ramene un nom d'emetteur a sa forme canonique, ou None s'il est inconnu.

    "Lyonnaise des Eaux de Casablanca", "LYDEC" et "lydec sa" doivent tous
    donner "LYDEC", sans quoi le controle de liste blanche rejetterait des
    documents parfaitement valides sur une simple variation d'ecriture.
    """
    reference = supprimer_accents(emetteur).lower().strip()

    if any(variante in reference for variante in VARIANTES_EMETTEUR_CIN):
        return "DGSN"

    for canonique, variantes in EMETTEURS_JUSTIFICATIF_DOMICILE.items():
        if any(variante in reference for variante in variantes):
            return canonique

    return None


def _nettoyer_nom(nom: str | None) -> str | None:
    """Retire les civilites et la ponctuation parasite d'un nom."""
    if not nom:
        return None
    nettoye = re.sub(
        r"^\s*(?:M\.?|Mr\.?|Mme\.?|Mlle\.?|Monsieur|Madame|Mademoiselle)\s+",
        "",
        nom,
        flags=re.IGNORECASE,
    )
    nettoye = re.sub(r"\s+", " ", nettoye).strip(" .,;:-")
    return nettoye or None


def supprimer_accents(texte: str) -> str:
    """Remplace les caracteres accentues par leur equivalent non accentue.

    Indispensable pour comparer des noms : un dossier saisi "Benali" et un
    document imprime "Bénali" designent la meme personne.
    """
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")
