"""
Configuration metier de l'agent de conformite KYC.

Tout ce qui releve de la REGLE BANCAIRE est centralise ici, jamais code en dur
ailleurs. Un responsable conformite doit pouvoir modifier un seuil ou ajouter un
emetteur sans toucher a la logique de l'agent.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Seuils reglementaires
# ---------------------------------------------------------------------------

# Anciennete maximale d'un justificatif de domicile, en mois.
# Reference : pratique standard KYC (justificatif "recent" = moins de 3 mois).
ANCIENNETE_MAX_JUSTIFICATIF_MOIS = 3

# Marge d'alerte avant expiration d'une CIN : on accepte le document mais on
# leve un avertissement, car le compte sera ouvert avec une piece bientot caduque.
ALERTE_EXPIRATION_CIN_JOURS = 30

# Score de similarite minimal entre le nom du dossier et le nom du document.
# En dessous : rejet. Entre ce seuil et 1.0 : acceptation avec avertissement.
SEUIL_CORRESPONDANCE_NOM = 0.85


# ---------------------------------------------------------------------------
# Emetteurs autorises
# ---------------------------------------------------------------------------

# Emetteurs acceptes pour un justificatif de domicile (contexte marocain).
# Cle = nom canonique, valeur = variantes rencontrees sur les documents reels.
EMETTEURS_JUSTIFICATIF_DOMICILE: dict[str, list[str]] = {
    "LYDEC": ["lydec", "lyonnaise des eaux de casablanca"],
    "REDAL": ["redal", "redal veolia"],
    "AMENDIS": ["amendis", "amendis tanger", "amendis tetouan"],
    "ONEE": [
        "onee",
        "office national de l'electricite et de l'eau potable",
        "office national de l electricite et de l eau potable",
        "one",
        "onep",
    ],
    "MAROC TELECOM": ["maroc telecom", "iam", "itissalat al-maghrib", "itissalat al maghrib"],
    "ORANGE MAROC": ["orange maroc", "orange", "meditel", "medi telecom"],
    "INWI": ["inwi", "wana corporate"],
}

# Emetteur unique et exclusif d'une CIN marocaine.
EMETTEUR_CIN = "DGSN"
VARIANTES_EMETTEUR_CIN = [
    "dgsn",
    "direction generale de la surete nationale",
    "surete nationale",
    "royaume du maroc - dgsn",
]


# ---------------------------------------------------------------------------
# Formats de donnees
# ---------------------------------------------------------------------------

# Numero de CIN marocaine : 1 ou 2 lettres suivies de 5 a 6 chiffres.
# Exemples valides : A123456, BE745123, K98765
REGEX_NUMERO_CIN = r"^[A-Z]{1,2}\d{5,6}$"

# Formats de date acceptes a l'extraction, du plus au moins courant.
FORMATS_DATE = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d %B %Y",
]

# Villes marocaines connues, utilisees pour un controle de plausibilite d'adresse.
VILLES_CONNUES = [
    "casablanca", "rabat", "marrakech", "fes", "tanger", "agadir", "meknes",
    "oujda", "kenitra", "tetouan", "sale", "temara", "mohammedia", "el jadida",
    "beni mellal", "nador", "taza", "settat", "berrechid", "khouribga",
]


# ---------------------------------------------------------------------------
# Codes d'anomalie
# ---------------------------------------------------------------------------
# Chaque controle produit un code stable. C'est ce code qui est journalise et
# qui permet de produire des statistiques de rejet par motif.

CODES_ANOMALIE = {
    "DOC_TYPE_INCONNU": "Type de document non reconnu",
    "DOC_ILLISIBLE": "Document illisible ou champs majeurs absents",
    "NOM_ABSENT": "Nom du titulaire absent du document",
    "NOM_DIVERGENT": "Nom du document different du nom du dossier",
    "NOM_APPROXIMATIF": "Nom proche mais non identique au dossier",
    "DATE_EMISSION_ABSENTE": "Date d'emission absente",
    "DATE_EMISSION_ILLISIBLE": "Date d'emission au format non reconnu",
    "DATE_EMISSION_FUTURE": "Date d'emission posterieure a la date du jour",
    "JUSTIFICATIF_PERIME": "Justificatif de domicile de plus de 3 mois",
    "CIN_EXPIREE": "CIN expiree",
    "CIN_EXPIRE_BIENTOT": "CIN expirant dans moins de 30 jours",
    "CIN_DATE_VALIDITE_ABSENTE": "Date de validite de la CIN absente",
    "CIN_NUMERO_ABSENT": "Numero de CIN absent",
    "CIN_NUMERO_FORMAT_INVALIDE": "Numero de CIN non conforme au format attendu",
    "EMETTEUR_ABSENT": "Emetteur du document absent",
    "EMETTEUR_NON_AUTORISE": "Emetteur absent de la liste des organismes acceptes",
    "ADRESSE_ABSENTE": "Adresse absente du justificatif de domicile",
    "ADRESSE_NON_PLAUSIBLE": "Adresse sans ville identifiable",
    "EXTRACTION_PEU_FIABLE": "Confiance d'extraction insuffisante",
}
