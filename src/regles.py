"""
Etape 3 du pipeline : les regles de conformite.

C'est ici que la decision est prise, et nulle part ailleurs. Aucune fonction de
ce module n'appelle un LLM : elles ne recoivent que des donnees deja extraites
et normalisees. Consequence directe : le meme document produit toujours la meme
decision, et chaque rejet se rattache a une regle nommee, citable devant un
controleur.

Chaque controle renvoie un couple (trace, anomalies) :
  - la trace atteste que le controle a bien ete execute, meme s'il a reussi ;
  - les anomalies, s'il y en a, portent le motif du rejet.

Toutes les fonctions acceptent une `date_reference` injectable. Sans cela, les
tests dependraient de la date du jour et cesseraient de passer avec le temps.
"""

from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher

from dateutil.relativedelta import relativedelta

from .config import (
    ALERTE_EXPIRATION_CIN_JOURS,
    ANCIENNETE_MAX_JUSTIFICATIF_MOIS,
    CODES_ANOMALIE,
    EMETTEURS_JUSTIFICATIF_DOMICILE,
    REGEX_NUMERO_CIN,
    SEUIL_CORRESPONDANCE_NOM,
    VILLES_CONNUES,
)
from .extraction import supprimer_accents
from .models import (
    Anomalie,
    Controle,
    DocumentNormalise,
    DossierClient,
    Severite,
    StatutConformite,
    TypeDocument,
)

# Confiance d'extraction en dessous de laquelle on refuse de decider seul.
SEUIL_CONFIANCE = 0.5

ResultatControle = tuple[Controle, list[Anomalie]]


def _anomalie(code: str, severite: Severite, detail: str = "", **valeurs: str | None) -> Anomalie:
    """Fabrique une anomalie a partir de son code, en reprenant le libelle officiel."""
    return Anomalie(
        code=code,
        libelle=CODES_ANOMALIE.get(code, code),
        severite=severite,
        detail=detail or CODES_ANOMALIE.get(code, code),
        valeur_attendue=valeurs.get("attendue"),
        valeur_constatee=valeurs.get("constatee"),
    )


# ---------------------------------------------------------------------------
# Controles transverses
# ---------------------------------------------------------------------------

def controler_type_document(doc: DocumentNormalise) -> ResultatControle:
    """Le document doit appartenir a une categorie que l'agent sait traiter."""
    if doc.type_document is TypeDocument.INCONNU:
        return (
            Controle(nom="Type de document", reussi=False, detail="Type non reconnu"),
            [
                _anomalie(
                    "DOC_TYPE_INCONNU",
                    Severite.BLOQUANT,
                    "Le document ne correspond ni a une CIN ni a un justificatif de domicile.",
                )
            ],
        )
    return (
        Controle(nom="Type de document", reussi=True, detail=doc.type_document.value),
        [],
    )


def controler_confiance(doc: DocumentNormalise) -> ResultatControle:
    """Une lecture peu sure doit partir en revue humaine, pas en decision automatique."""
    if doc.confiance < SEUIL_CONFIANCE:
        return (
            Controle(
                nom="Fiabilite de l'extraction",
                reussi=False,
                detail=f"confiance {doc.confiance:.2f} < {SEUIL_CONFIANCE}",
            ),
            [
                _anomalie(
                    "EXTRACTION_PEU_FIABLE",
                    Severite.AVERTISSEMENT,
                    f"Lecture du document peu fiable (confiance {doc.confiance:.2f}). "
                    "Verification manuelle requise.",
                    attendue=f">= {SEUIL_CONFIANCE}",
                    constatee=f"{doc.confiance:.2f}",
                )
            ],
        )
    return (
        Controle(
            nom="Fiabilite de l'extraction",
            reussi=True,
            detail=f"confiance {doc.confiance:.2f}",
        ),
        [],
    )


def controler_erreurs_format(doc: DocumentNormalise) -> ResultatControle:
    """Un champ present mais illisible n'est pas un champ absent : on le signale a part."""
    if doc.erreurs_normalisation:
        return (
            Controle(
                nom="Format des donnees",
                reussi=False,
                detail=" ; ".join(doc.erreurs_normalisation),
            ),
            [
                _anomalie(
                    "DATE_EMISSION_ILLISIBLE",
                    Severite.BLOQUANT,
                    f"Donnee presente mais au format non reconnu : {erreur}",
                )
                for erreur in doc.erreurs_normalisation
            ],
        )
    return (Controle(nom="Format des donnees", reussi=True), [])


# ---------------------------------------------------------------------------
# Correspondance du nom
# ---------------------------------------------------------------------------

def normaliser_pour_comparaison(texte: str) -> set[str]:
    """Reduit un nom a un ensemble de mots comparables.

    Accents, casse, ponctuation et ordre des mots sont neutralises : "Bénali
    Youssef", "YOUSSEF BENALI" et "benali, youssef" produisent le meme ensemble.
    L'ordre nom/prenom varie d'un document a l'autre et ne doit jamais causer un
    rejet.
    """
    sans_accents = supprimer_accents(texte).lower()
    mots = re.split(r"[^a-z0-9]+", sans_accents)
    return {mot for mot in mots if len(mot) > 1}


def score_correspondance_nom(nom_document: str, nom_dossier: str) -> float:
    """Score de 0 a 1 entre deux ecritures d'un nom.

    On combine deux mesures :
      - le recouvrement des ensembles de mots (gere l'ordre et les mots en trop) ;
      - la similarite caractere par caractere (gere les fautes de frappe et les
        variantes de translitteration, frequentes sur les noms arabes : Youssef /
        Youssuf, El Amrani / Elamrani).
    Le score retenu est le meilleur des deux.
    """
    mots_document = normaliser_pour_comparaison(nom_document)
    mots_dossier = normaliser_pour_comparaison(nom_dossier)

    if not mots_document or not mots_dossier:
        return 0.0

    communs = mots_document & mots_dossier
    recouvrement = len(communs) / max(len(mots_document), len(mots_dossier))

    chaine_document = " ".join(sorted(mots_document))
    chaine_dossier = " ".join(sorted(mots_dossier))
    similarite = SequenceMatcher(None, chaine_document, chaine_dossier).ratio()

    return max(recouvrement, similarite)


def controler_nom(doc: DocumentNormalise, dossier: DossierClient) -> ResultatControle:
    """Le nom porte par le document doit etre celui du dossier client."""
    nom_document = doc.nom_complet
    if not nom_document:
        return (
            Controle(nom="Correspondance du nom", reussi=False, detail="nom absent"),
            [
                _anomalie(
                    "NOM_ABSENT",
                    Severite.BLOQUANT,
                    "Aucun nom de titulaire n'a pu etre lu sur le document.",
                    attendue=dossier.nom_complet,
                )
            ],
        )

    score = score_correspondance_nom(nom_document, dossier.nom_complet)

    if score >= 0.99:
        return (
            Controle(
                nom="Correspondance du nom",
                reussi=True,
                detail=f"{nom_document} (score {score:.2f})",
            ),
            [],
        )

    if score >= SEUIL_CORRESPONDANCE_NOM:
        return (
            Controle(
                nom="Correspondance du nom",
                reussi=True,
                detail=f"correspondance approximative (score {score:.2f})",
            ),
            [
                _anomalie(
                    "NOM_APPROXIMATIF",
                    Severite.AVERTISSEMENT,
                    f"Nom proche mais non identique (score {score:.2f}) : "
                    f"document '{nom_document}' contre dossier '{dossier.nom_complet}'.",
                    attendue=dossier.nom_complet,
                    constatee=nom_document,
                )
            ],
        )

    return (
        Controle(
            nom="Correspondance du nom",
            reussi=False,
            detail=f"divergence (score {score:.2f})",
        ),
        [
            _anomalie(
                "NOM_DIVERGENT",
                Severite.BLOQUANT,
                f"Le nom du document ('{nom_document}') ne correspond pas au dossier "
                f"('{dossier.nom_complet}').",
                attendue=dossier.nom_complet,
                constatee=nom_document,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Emetteur
# ---------------------------------------------------------------------------

def controler_emetteur(doc: DocumentNormalise) -> ResultatControle:
    """L'organisme emetteur doit figurer dans la liste blanche du type de document."""
    if not doc.emetteur:
        return (
            Controle(nom="Emetteur autorise", reussi=False, detail="emetteur absent"),
            [
                _anomalie(
                    "EMETTEUR_ABSENT",
                    Severite.BLOQUANT,
                    "Aucun organisme emetteur identifiable sur le document.",
                )
            ],
        )

    if doc.type_document is TypeDocument.CIN:
        attendu, autorises = "DGSN", {"DGSN"}
    else:
        attendu = ", ".join(EMETTEURS_JUSTIFICATIF_DOMICILE)
        autorises = set(EMETTEURS_JUSTIFICATIF_DOMICILE)

    if doc.emetteur_canonique in autorises:
        return (
            Controle(nom="Emetteur autorise", reussi=True, detail=doc.emetteur_canonique or ""),
            [],
        )

    return (
        Controle(
            nom="Emetteur autorise",
            reussi=False,
            detail=f"'{doc.emetteur}' hors liste blanche",
        ),
        [
            _anomalie(
                "EMETTEUR_NON_AUTORISE",
                Severite.BLOQUANT,
                f"L'emetteur '{doc.emetteur}' ne figure pas parmi les organismes acceptes.",
                attendue=attendu,
                constatee=doc.emetteur,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Regles propres a la CIN
# ---------------------------------------------------------------------------

def controler_numero_cin(doc: DocumentNormalise) -> ResultatControle:
    """Le numero doit exister et respecter le format national (1-2 lettres + 5-6 chiffres)."""
    if not doc.numero_cin:
        return (
            Controle(nom="Numero de CIN", reussi=False, detail="absent"),
            [_anomalie("CIN_NUMERO_ABSENT", Severite.BLOQUANT, "Numero de CIN absent du document.")],
        )

    if not re.match(REGEX_NUMERO_CIN, doc.numero_cin):
        return (
            Controle(nom="Numero de CIN", reussi=False, detail=f"format invalide : {doc.numero_cin}"),
            [
                _anomalie(
                    "CIN_NUMERO_FORMAT_INVALIDE",
                    Severite.BLOQUANT,
                    f"Le numero '{doc.numero_cin}' ne respecte pas le format attendu "
                    "(1 a 2 lettres suivies de 5 a 6 chiffres).",
                    attendue="ex. BE745123",
                    constatee=doc.numero_cin,
                )
            ],
        )

    return (Controle(nom="Numero de CIN", reussi=True, detail=doc.numero_cin), [])


def controler_validite_cin(doc: DocumentNormalise, date_reference: date) -> ResultatControle:
    """La CIN ne doit pas etre expiree a la date d'examen du dossier."""
    if doc.date_validite is None:
        return (
            Controle(nom="Validite de la CIN", reussi=False, detail="date de validite absente"),
            [
                _anomalie(
                    "CIN_DATE_VALIDITE_ABSENTE",
                    Severite.BLOQUANT,
                    "La date de validite de la CIN n'a pas pu etre lue.",
                )
            ],
        )

    if doc.date_validite < date_reference:
        jours = (date_reference - doc.date_validite).days
        return (
            Controle(
                nom="Validite de la CIN",
                reussi=False,
                detail=f"expiree depuis {jours} jours",
            ),
            [
                _anomalie(
                    "CIN_EXPIREE",
                    Severite.BLOQUANT,
                    f"CIN expiree le {doc.date_validite:%d/%m/%Y}, soit {jours} jours "
                    f"avant la date d'examen ({date_reference:%d/%m/%Y}).",
                    attendue=f"posterieure au {date_reference:%d/%m/%Y}",
                    constatee=f"{doc.date_validite:%d/%m/%Y}",
                )
            ],
        )

    jours_restants = (doc.date_validite - date_reference).days
    if jours_restants <= ALERTE_EXPIRATION_CIN_JOURS:
        return (
            Controle(
                nom="Validite de la CIN",
                reussi=True,
                detail=f"valide, expire dans {jours_restants} jours",
            ),
            [
                _anomalie(
                    "CIN_EXPIRE_BIENTOT",
                    Severite.AVERTISSEMENT,
                    f"La CIN expire dans {jours_restants} jours "
                    f"(le {doc.date_validite:%d/%m/%Y}). Prevoir un renouvellement.",
                    constatee=f"{doc.date_validite:%d/%m/%Y}",
                )
            ],
        )

    return (
        Controle(
            nom="Validite de la CIN",
            reussi=True,
            detail=f"valide jusqu'au {doc.date_validite:%d/%m/%Y}",
        ),
        [],
    )


# ---------------------------------------------------------------------------
# Regles propres au justificatif de domicile
# ---------------------------------------------------------------------------

def controler_anciennete_justificatif(
    doc: DocumentNormalise, date_reference: date
) -> ResultatControle:
    """Le justificatif doit avoir moins de 3 mois a la date d'examen.

    L'anciennete se calcule en mois calendaires (relativedelta) et non en jours :
    un justificatif du 31 janvier examine le 30 avril a bien plus de 3 mois, ce
    qu'un seuil fixe a 90 jours trancherait differemment selon les mois.
    """
    if doc.date_emission is None:
        return (
            Controle(nom="Anciennete du justificatif", reussi=False, detail="date absente"),
            [
                _anomalie(
                    "DATE_EMISSION_ABSENTE",
                    Severite.BLOQUANT,
                    "La date d'emission du justificatif n'a pas pu etre lue.",
                )
            ],
        )

    if doc.date_emission > date_reference:
        return (
            Controle(
                nom="Anciennete du justificatif",
                reussi=False,
                detail=f"date future : {doc.date_emission:%d/%m/%Y}",
            ),
            [
                _anomalie(
                    "DATE_EMISSION_FUTURE",
                    Severite.BLOQUANT,
                    f"La date d'emission ({doc.date_emission:%d/%m/%Y}) est posterieure "
                    f"a la date d'examen ({date_reference:%d/%m/%Y}).",
                    constatee=f"{doc.date_emission:%d/%m/%Y}",
                )
            ],
        )

    date_limite = date_reference - relativedelta(months=ANCIENNETE_MAX_JUSTIFICATIF_MOIS)

    if doc.date_emission < date_limite:
        jours = (date_reference - doc.date_emission).days
        return (
            Controle(
                nom="Anciennete du justificatif",
                reussi=False,
                detail=f"{jours} jours",
            ),
            [
                _anomalie(
                    "JUSTIFICATIF_PERIME",
                    Severite.BLOQUANT,
                    f"Justificatif emis le {doc.date_emission:%d/%m/%Y}, soit {jours} jours "
                    f"({ANCIENNETE_MAX_JUSTIFICATIF_MOIS} mois maximum autorises).",
                    attendue=f"emis apres le {date_limite:%d/%m/%Y}",
                    constatee=f"{doc.date_emission:%d/%m/%Y}",
                )
            ],
        )

    jours = (date_reference - doc.date_emission).days
    return (
        Controle(
            nom="Anciennete du justificatif",
            reussi=True,
            detail=f"emis il y a {jours} jours",
        ),
        [],
    )


def controler_adresse(doc: DocumentNormalise) -> ResultatControle:
    """Un justificatif de domicile sans adresse exploitable ne justifie rien."""
    if not doc.adresse:
        return (
            Controle(nom="Adresse", reussi=False, detail="absente"),
            [
                _anomalie(
                    "ADRESSE_ABSENTE",
                    Severite.BLOQUANT,
                    "Aucune adresse n'a pu etre lue sur le justificatif.",
                )
            ],
        )

    reference = supprimer_accents(doc.adresse).lower()
    if not any(ville in reference for ville in VILLES_CONNUES):
        return (
            Controle(nom="Adresse", reussi=False, detail="ville non identifiee"),
            [
                _anomalie(
                    "ADRESSE_NON_PLAUSIBLE",
                    Severite.AVERTISSEMENT,
                    f"Aucune ville connue identifiee dans l'adresse : '{doc.adresse}'. "
                    "Verification manuelle conseillee.",
                    constatee=doc.adresse,
                )
            ],
        )

    return (Controle(nom="Adresse", reussi=True, detail=doc.adresse), [])


# ---------------------------------------------------------------------------
# Orchestration des regles
# ---------------------------------------------------------------------------

def valider(
    doc: DocumentNormalise,
    dossier: DossierClient,
    date_reference: date | None = None,
) -> tuple[StatutConformite, list[Anomalie], list[Controle]]:
    """Applique tous les controles pertinents et rend la decision.

    Le statut se deduit mecaniquement des anomalies :
      - une anomalie BLOQUANTE          -> REJETE
      - uniquement des AVERTISSEMENTS   -> A_VERIFIER (revue humaine)
      - aucune anomalie                 -> VALIDE

    Aucun autre chemin ne mene a une decision : c'est ce qui garantit qu'un
    document rejete l'est toujours pour un motif explicite et nomme.
    """
    date_reference = date_reference or date.today()

    anomalies: list[Anomalie] = []
    controles: list[Controle] = []

    def executer(resultat: ResultatControle) -> None:
        controle, nouvelles = resultat
        controles.append(controle)
        anomalies.extend(nouvelles)

    # Controles communs a tous les types de document.
    executer(controler_type_document(doc))
    executer(controler_confiance(doc))
    executer(controler_erreurs_format(doc))

    # Un type inconnu rend les controles specifiques sans objet : on s'arrete la
    # plutot que d'empiler des anomalies derivees qui noieraient le vrai motif.
    if doc.type_document is TypeDocument.INCONNU:
        return StatutConformite.REJETE, anomalies, controles

    executer(controler_nom(doc, dossier))
    executer(controler_emetteur(doc))

    if doc.type_document is TypeDocument.CIN:
        executer(controler_numero_cin(doc))
        executer(controler_validite_cin(doc, date_reference))
    else:
        executer(controler_anciennete_justificatif(doc, date_reference))
        executer(controler_adresse(doc))

    if any(a.severite is Severite.BLOQUANT for a in anomalies):
        statut = StatutConformite.REJETE
    elif anomalies:
        statut = StatutConformite.A_VERIFIER
    else:
        statut = StatutConformite.VALIDE

    return statut, anomalies, controles
