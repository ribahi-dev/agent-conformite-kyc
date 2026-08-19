"""
Generateur du jeu de donnees fictives (livrable Semaine 1).

Pourquoi un generateur plutot que des fichiers figes : toutes les dates sont
calculees par rapport a une date de reference. Un justificatif "de moins de 3
mois" ecrit en dur cesserait d'etre valide trois mois plus tard, et le jeu de
test deviendrait faux tout seul. Ici on regenere, et le jeu reste coherent.

Chaque cas porte son resultat attendu : le jeu sert donc aussi de reference
pour mesurer le taux de justesse de l'agent (voir evaluer.py).

Usage :
    python generer_donnees.py                    # date de reference = aujourd'hui
    python generer_donnees.py --date 2026-08-18  # date figee (reproductible)

Tous les noms, adresses et numeros sont inventes.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta

RACINE = Path(__file__).parent
DOSSIER_DOCUMENTS = RACINE / "data" / "documents"
FICHIER_CAS = RACINE / "data" / "cas_de_test.json"


def jour(reference: date, jours: int = 0, mois: int = 0, annees: int = 0) -> str:
    """Date decalee par rapport a la reference, au format jj/mm/aaaa."""
    resultat = reference + relativedelta(months=mois, years=annees) + timedelta(days=jours)
    return resultat.strftime("%d/%m/%Y")


def construire_cas(ref: date) -> list[dict]:
    """Definit les 20 scenarios du jeu de donnees."""

    # Clients fictifs reutilises dans plusieurs cas.
    benali = {
        "dossier_id": "D-2026-001",
        "nom": "BENALI",
        "prenom": "Youssef",
        "adresse_declaree": "12 rue Ibn Sina, Maarif, Casablanca",
    }
    alaoui = {
        "dossier_id": "D-2026-002",
        "nom": "ALAOUI",
        "prenom": "Fatima Zahra",
        "adresse_declaree": "45 avenue Mohammed V, Agdal, Rabat",
    }
    tazi = {
        "dossier_id": "D-2026-003",
        "nom": "TAZI",
        "prenom": "Karim",
        "adresse_declaree": "8 boulevard Pasteur, Tanger",
    }
    elamrani = {
        "dossier_id": "D-2026-004",
        "nom": "EL AMRANI",
        "prenom": "Salma",
        "adresse_declaree": "27 rue Oued Ziz, Hay Riad, Rabat",
    }

    return [
        # ------------------------------------------------------------------
        # CIN - cas conformes
        # ------------------------------------------------------------------
        {
            "fichier": "cin_01_conforme.txt",
            "dossier": benali,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "CIN conforme, cas nominal",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : BENALI
Prenom : Youssef
Date de naissance : 14/03/1995
Lieu de naissance : Casablanca
Numero CIN : BE745123
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date d'emission : {jour(ref, annees=-4)}
Valable jusqu'au : {jour(ref, annees=6)}
Emetteur : DGSN
""",
        },
        {
            "fichier": "cin_02_expire_bientot.txt",
            "dossier": alaoui,
            "statut_attendu": "A_VERIFIER",
            "codes_attendus": ["CIN_EXPIRE_BIENTOT"],
            "description": "CIN valide mais expirant dans 20 jours (avertissement)",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : ALAOUI
Prenom : Fatima Zahra
Date de naissance : 02/09/1988
Numero CIN : A234567
Adresse : 45 avenue Mohammed V, Agdal, Rabat
Date d'emission : {jour(ref, annees=-10, jours=20)}
Valable jusqu'au : {jour(ref, jours=20)}
Emetteur : DGSN
""",
        },
        # ------------------------------------------------------------------
        # CIN - cas rejetes
        # ------------------------------------------------------------------
        {
            "fichier": "cin_03_expiree.txt",
            "dossier": tazi,
            "statut_attendu": "REJETE",
            "codes_attendus": ["CIN_EXPIREE"],
            "description": "CIN expiree depuis 8 mois",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : TAZI
Prenom : Karim
Date de naissance : 21/11/1979
Numero CIN : K456789
Adresse : 8 boulevard Pasteur, Tanger
Date d'emission : {jour(ref, mois=-8, annees=-10)}
Valable jusqu'au : {jour(ref, mois=-8)}
Emetteur : DGSN
""",
        },
        {
            "fichier": "cin_04_nom_divergent.txt",
            "dossier": benali,
            "statut_attendu": "REJETE",
            "codes_attendus": ["NOM_DIVERGENT"],
            "description": "CIN valide mais au nom d'une autre personne que le dossier",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : CHAKIR
Prenom : Mehdi
Date de naissance : 30/06/1992
Numero CIN : C112233
Adresse : 3 rue Al Massira, Marrakech
Date d'emission : {jour(ref, annees=-2)}
Valable jusqu'au : {jour(ref, annees=8)}
Emetteur : DGSN
""",
        },
        {
            "fichier": "cin_05_numero_invalide.txt",
            "dossier": elamrani,
            "statut_attendu": "REJETE",
            "codes_attendus": ["CIN_NUMERO_FORMAT_INVALIDE"],
            "description": "Numero de CIN hors format national (chiffres seuls)",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : EL AMRANI
Prenom : Salma
Date de naissance : 07/01/1997
Numero CIN : 1234
Adresse : 27 rue Oued Ziz, Hay Riad, Rabat
Date d'emission : {jour(ref, annees=-3)}
Valable jusqu'au : {jour(ref, annees=7)}
Emetteur : DGSN
""",
        },
        {
            "fichier": "cin_06_sans_validite.txt",
            "dossier": tazi,
            "statut_attendu": "REJETE",
            "codes_attendus": ["CIN_DATE_VALIDITE_ABSENTE"],
            "description": "CIN sans date de validite lisible",
            "contenu": f"""ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : TAZI
Prenom : Karim
Numero CIN : K456789
Adresse : 8 boulevard Pasteur, Tanger
Date d'emission : {jour(ref, annees=-5)}
Emetteur : DGSN
""",
        },
        {
            "fichier": "cin_07_emetteur_invalide.txt",
            "dossier": benali,
            "statut_attendu": "REJETE",
            "codes_attendus": ["EMETTEUR_NON_AUTORISE"],
            "description": "Piece d'identite emise par un organisme non habilite",
            "contenu": f"""CARTE D'IDENTITE PROFESSIONNELLE
SOCIETE ATLAS SECURITE PRIVEE

Nom : BENALI
Prenom : Youssef
Numero CIN : BE745123
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date d'emission : {jour(ref, mois=-6)}
Valable jusqu'au : {jour(ref, annees=2)}
Emetteur : Atlas Securite Privee SARL
""",
        },
        # ------------------------------------------------------------------
        # Justificatifs de domicile - cas conformes
        # ------------------------------------------------------------------
        {
            "fichier": "domicile_08_lydec_conforme.txt",
            "dossier": benali,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "Facture Lydec de moins de 3 mois, cas nominal",
            "contenu": f"""LYDEC
Lyonnaise des Eaux de Casablanca
FACTURE D'EAU ET D'ELECTRICITE

Numero de contrat : 4471203
Nom : BENALI Youssef
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Periode de consommation : du {jour(ref, mois=-2, jours=-15)} au {jour(ref, mois=-1, jours=-15)}
Date de facture : {jour(ref, mois=-1)}
Consommation electricite : 187 kWh
Consommation eau : 12 m3
Montant total : 428,50 MAD
Emetteur : LYDEC
""",
        },
        {
            "fichier": "domicile_09_redal_conforme.txt",
            "dossier": alaoui,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "Facture Redal recente, nom en ordre inverse (prenom puis nom)",
            "contenu": f"""REDAL
Distribution Eau et Electricite - Rabat Sale
QUITTANCE

Reference client : RB-889201
Nom : Fatima Zahra ALAOUI
Adresse : 45 avenue Mohammed V, Agdal, Rabat
Date de facture : {jour(ref, jours=-25)}
Montant : 312,00 MAD
Statut : Payee
Emetteur : REDAL
""",
        },
        {
            "fichier": "domicile_10_amendis_conforme.txt",
            "dossier": tazi,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "Facture Amendis a la limite haute de recevabilite (2 mois et demi)",
            "contenu": f"""AMENDIS TANGER
FACTURE D'ABONNEMENT

Client : TAZI Karim
Adresse : 8 boulevard Pasteur, Tanger
Numero de police : TNG-3345128
Date de facture : {jour(ref, mois=-2, jours=-15)}
Montant : 265,80 MAD
Emetteur : Amendis
""",
        },
        {
            "fichier": "domicile_11_onee_conforme.txt",
            "dossier": elamrani,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "Facture ONEE, emetteur ecrit en toutes lettres",
            "contenu": f"""OFFICE NATIONAL DE L'ELECTRICITE ET DE L'EAU POTABLE
Branche Electricite

Abonne : EL AMRANI Salma
Adresse : 27 rue Oued Ziz, Hay Riad, Rabat
Numero d'abonnement : 77120934
Date d'emission : {jour(ref, jours=-40)}
Index precedent : 4521
Index actuel : 4698
Montant : 198,20 MAD
Emetteur : Office National de l'Electricite et de l'Eau Potable
""",
        },
        {
            "fichier": "domicile_12_maroctelecom_conforme.txt",
            "dossier": benali,
            "statut_attendu": "VALIDE",
            "codes_attendus": [],
            "description": "Facture telecom recente, emetteur sous son sigle IAM",
            "contenu": f"""MAROC TELECOM (IAM)
FACTURE TELEPHONE FIXE ET INTERNET

Titulaire : BENALI Youssef
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Numero de ligne : 0522-45-88-12
Date de facture : {jour(ref, jours=-12)}
Forfait ADSL 20 Mega : 249,00 MAD
Montant total TTC : 289,00 MAD
Emetteur : Itissalat Al-Maghrib
""",
        },
        # ------------------------------------------------------------------
        # Justificatifs de domicile - cas rejetes
        # ------------------------------------------------------------------
        {
            "fichier": "domicile_13_perime.txt",
            "dossier": alaoui,
            "statut_attendu": "REJETE",
            "codes_attendus": ["JUSTIFICATIF_PERIME"],
            "description": "Facture de 5 mois, au-dela du seuil de 3 mois",
            "contenu": f"""REDAL
QUITTANCE D'EAU

Reference client : RB-889201
Nom : ALAOUI Fatima Zahra
Adresse : 45 avenue Mohammed V, Agdal, Rabat
Date de facture : {jour(ref, mois=-5)}
Montant : 287,40 MAD
Emetteur : REDAL
""",
        },
        {
            "fichier": "domicile_14_limite_3mois.txt",
            "dossier": tazi,
            "statut_attendu": "REJETE",
            "codes_attendus": ["JUSTIFICATIF_PERIME"],
            "description": "Cas limite : facture d'exactement 3 mois et 1 jour",
            "contenu": f"""AMENDIS TANGER
FACTURE D'EAU

Client : TAZI Karim
Adresse : 8 boulevard Pasteur, Tanger
Date de facture : {jour(ref, mois=-3, jours=-1)}
Montant : 210,00 MAD
Emetteur : Amendis
""",
        },
        {
            "fichier": "domicile_15_nom_divergent.txt",
            "dossier": benali,
            "statut_attendu": "REJETE",
            "codes_attendus": ["NOM_DIVERGENT"],
            "description": "Facture recente mais au nom d'un tiers (colocataire, proprietaire)",
            "contenu": f"""LYDEC
FACTURE D'EAU ET D'ELECTRICITE

Numero de contrat : 4471203
Nom : IDRISSI Hamid
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date de facture : {jour(ref, jours=-18)}
Montant total : 402,10 MAD
Emetteur : LYDEC
""",
        },
        {
            "fichier": "domicile_16_emetteur_non_autorise.txt",
            "dossier": elamrani,
            "statut_attendu": "REJETE",
            "codes_attendus": ["EMETTEUR_NON_AUTORISE"],
            "description": "Facture recente d'un organisme hors liste blanche",
            "contenu": f"""STREAMFLIX MAROC
FACTURE D'ABONNEMENT MENSUEL

Client : EL AMRANI Salma
Adresse : 27 rue Oued Ziz, Hay Riad, Rabat
Date de facture : {jour(ref, jours=-10)}
Abonnement Premium : 99,00 MAD
Emetteur : Streamflix Maroc SARL
""",
        },
        {
            "fichier": "domicile_17_date_future.txt",
            "dossier": benali,
            "statut_attendu": "REJETE",
            "codes_attendus": ["DATE_EMISSION_FUTURE"],
            "description": "Date d'emission posterieure au jour d'examen (document suspect)",
            "contenu": f"""LYDEC
FACTURE D'EAU ET D'ELECTRICITE

Numero de contrat : 4471203
Nom : BENALI Youssef
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date de facture : {jour(ref, mois=2)}
Montant total : 415,00 MAD
Emetteur : LYDEC
""",
        },
        {
            "fichier": "domicile_18_sans_adresse.txt",
            "dossier": alaoui,
            "statut_attendu": "REJETE",
            "codes_attendus": ["ADRESSE_ABSENTE"],
            "description": "Attestation recente mais sans adresse exploitable",
            "contenu": f"""REDAL
ATTESTATION DE RESIDENCE

Nous soussignes REDAL attestons que la personne designee ci-dessous
est titulaire d'un contrat d'abonnement actif.

Nom : ALAOUI Fatima Zahra
Reference : RB-889201
Date d'emission : {jour(ref, jours=-15)}
Emetteur : REDAL
""",
        },
        # ------------------------------------------------------------------
        # Cas limites et pieges
        # ------------------------------------------------------------------
        {
            "fichier": "divers_19_type_inconnu.txt",
            "dossier": tazi,
            "statut_attendu": "REJETE",
            "codes_attendus": ["DOC_TYPE_INCONNU"],
            "description": "Bulletin de paie : ni CIN ni justificatif de domicile",
            "contenu": f"""SOCIETE MAGHREB INDUSTRIES SA
BULLETIN DE PAIE

Salarie : TAZI Karim
Matricule : MI-2291
Periode : {jour(ref, mois=-1)[3:]}
Salaire brut : 12 400,00 MAD
Cotisations CNSS : 1 116,00 MAD
Salaire net : 10 284,00 MAD
Date d'edition : {jour(ref, jours=-5)}
""",
        },
        {
            "fichier": "domicile_20_nom_translitteration.txt",
            "dossier": benali,
            "statut_attendu": "A_VERIFIER",
            "codes_attendus": ["NOM_APPROXIMATIF"],
            "description": "Variante de translitteration du prenom (Youssuf / Youssef)",
            "contenu": f"""INWI
FACTURE MOBILE

Titulaire : BENALI Youssuf
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Numero : 0661-23-45-67
Date de facture : {jour(ref, jours=-8)}
Forfait : 149,00 MAD
Emetteur : inwi
""",
        },
    ]


def ecrire(cas: list[dict], reference: date) -> None:
    DOSSIER_DOCUMENTS.mkdir(parents=True, exist_ok=True)

    # On repart d'un dossier propre : sinon un ancien fichier renomme resterait
    # et fausserait les mesures du script d'evaluation.
    for ancien in DOSSIER_DOCUMENTS.glob("*.txt"):
        ancien.unlink()

    index = []
    for element in cas:
        chemin = DOSSIER_DOCUMENTS / element["fichier"]
        chemin.write_text(element["contenu"], encoding="utf-8")
        index.append(
            {
                "fichier": element["fichier"],
                "dossier": element["dossier"],
                "statut_attendu": element["statut_attendu"],
                "codes_attendus": element["codes_attendus"],
                "description": element["description"],
            }
        )

    FICHIER_CAS.write_text(
        json.dumps(
            {
                "date_reference": reference.isoformat(),
                "nombre_cas": len(index),
                "avertissement": (
                    "Donnees entierement fictives, generees pour un projet pedagogique. "
                    "Noms, adresses et numeros sont inventes."
                ),
                "cas": index,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main() -> None:
    analyseur = argparse.ArgumentParser(description="Genere le jeu de donnees fictives KYC.")
    analyseur.add_argument(
        "--date",
        help="Date de reference au format AAAA-MM-JJ (defaut : aujourd'hui).",
    )
    arguments = analyseur.parse_args()

    reference = date.fromisoformat(arguments.date) if arguments.date else date.today()
    cas = construire_cas(reference)
    ecrire(cas, reference)

    attendus: dict[str, int] = {}
    for element in cas:
        attendus[element["statut_attendu"]] = attendus.get(element["statut_attendu"], 0) + 1

    print(f"{len(cas)} documents generes dans {DOSSIER_DOCUMENTS}")
    print(f"Date de reference : {reference:%d/%m/%Y}")
    print("Repartition attendue :")
    for statut, nombre in sorted(attendus.items()):
        print(f"  {statut:<12} {nombre}")
    print(f"\nIndex des cas : {FICHIER_CAS}")


if __name__ == "__main__":
    main()
