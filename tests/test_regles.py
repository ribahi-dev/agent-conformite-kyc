"""
Tests des regles de conformite.

Toutes les dates sont figees via DATE_EXAMEN. Un test qui dependrait de la date
du jour passerait aujourd'hui et echouerait dans trois mois, sans qu'une seule
ligne de code ait change : c'est precisement l'erreur que ces regles doivent
eviter en production, autant ne pas la commettre dans les tests.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.models import DocumentNormalise, DossierClient, StatutConformite, TypeDocument
from src.regles import (
    controler_adresse,
    controler_anciennete_justificatif,
    controler_emetteur,
    controler_nom,
    controler_numero_cin,
    controler_validite_cin,
    score_correspondance_nom,
    valider,
)

DATE_EXAMEN = date(2026, 8, 18)

DOSSIER = DossierClient(
    dossier_id="D-TEST-001",
    nom="BENALI",
    prenom="Youssef",
    adresse_declaree="12 rue Ibn Sina, Maarif, Casablanca",
)


def cin(**remplacements) -> DocumentNormalise:
    """CIN conforme par defaut ; chaque test ne modifie que le champ qu'il eprouve."""
    valeurs = {
        "type_document": TypeDocument.CIN,
        "nom_titulaire": "BENALI",
        "prenom_titulaire": "Youssef",
        "numero_cin": "BE745123",
        "date_emission": date(2022, 8, 18),
        "date_validite": date(2032, 8, 18),
        "emetteur": "DGSN",
        "emetteur_canonique": "DGSN",
        "adresse": "12 rue Ibn Sina, Maarif, Casablanca",
        "confiance": 1.0,
    }
    valeurs.update(remplacements)
    return DocumentNormalise(**valeurs)


def domicile(**remplacements) -> DocumentNormalise:
    """Justificatif de domicile conforme par defaut."""
    valeurs = {
        "type_document": TypeDocument.JUSTIFICATIF_DOMICILE,
        "nom_titulaire": "BENALI",
        "prenom_titulaire": "Youssef",
        "date_emission": date(2026, 7, 20),
        "emetteur": "LYDEC",
        "emetteur_canonique": "LYDEC",
        "adresse": "12 rue Ibn Sina, Maarif, Casablanca",
        "confiance": 1.0,
    }
    valeurs.update(remplacements)
    return DocumentNormalise(**valeurs)


# ---------------------------------------------------------------------------
# Anciennete du justificatif : la regle des 3 mois
# ---------------------------------------------------------------------------

class TestAncienneteJustificatif:
    @pytest.mark.parametrize(
        "date_emission, doit_passer",
        [
            (date(2026, 8, 18), True),   # emis le jour meme
            (date(2026, 8, 1), True),    # 17 jours
            (date(2026, 5, 19), True),   # 2 mois et 30 jours, dans les clous
            (date(2026, 5, 18), True),   # exactement 3 mois : accepte (borne incluse)
            (date(2026, 5, 17), False),  # 3 mois et 1 jour : refuse
            (date(2026, 2, 1), False),   # 6 mois et demi
        ],
    )
    def test_seuil_trois_mois(self, date_emission: date, doit_passer: bool) -> None:
        controle, anomalies = controler_anciennete_justificatif(
            domicile(date_emission=date_emission), DATE_EXAMEN
        )
        assert controle.reussi is doit_passer
        if doit_passer:
            assert anomalies == []
        else:
            assert [a.code for a in anomalies] == ["JUSTIFICATIF_PERIME"]

    def test_date_future_rejetee(self) -> None:
        """Une facture datee dans le futur signale une piece falsifiee."""
        _, anomalies = controler_anciennete_justificatif(
            domicile(date_emission=date(2026, 10, 1)), DATE_EXAMEN
        )
        assert [a.code for a in anomalies] == ["DATE_EMISSION_FUTURE"]

    def test_date_absente_rejetee(self) -> None:
        _, anomalies = controler_anciennete_justificatif(
            domicile(date_emission=None), DATE_EXAMEN
        )
        assert [a.code for a in anomalies] == ["DATE_EMISSION_ABSENTE"]

    def test_calcul_en_mois_calendaires_et_non_en_jours(self) -> None:
        """La fenetre de 3 mois ne fait pas toujours 90 jours.

        Sa longueur reelle depend des mois traverses (89 a 92 jours selon que
        fevrier y figure ou non). Ces deux cas le prouvent : celui de 90 jours
        est refuse, celui de 91 jours est accepte. Un seuil ecrit "90 jours"
        trancherait exactement l'inverse.

        "Moins de 3 mois" est une notion calendaire, pas un compte de jours :
        c'est relativedelta qui donne la lecture juridiquement correcte.
        """
        # Emission le 31/01, examen le 01/05 : 90 jours d'ecart.
        # Limite = 01/05 moins 3 mois = 01/02. Le 31/01 est anterieur -> refuse.
        controle_90j, anomalies = controler_anciennete_justificatif(
            domicile(date_emission=date(2026, 1, 31)), date(2026, 5, 1)
        )
        assert (date(2026, 5, 1) - date(2026, 1, 31)).days == 90
        assert controle_90j.reussi is False
        assert anomalies[0].code == "JUSTIFICATIF_PERIME"

        # Emission le 01/05, examen le 31/07 : 91 jours d'ecart, soit plus.
        # Limite = 31/07 moins 3 mois = 30/04. Le 01/05 est posterieur -> accepte.
        controle_91j, _ = controler_anciennete_justificatif(
            domicile(date_emission=date(2026, 5, 1)), date(2026, 7, 31)
        )
        assert (date(2026, 7, 31) - date(2026, 5, 1)).days == 91
        assert controle_91j.reussi is True


# ---------------------------------------------------------------------------
# Validite de la CIN
# ---------------------------------------------------------------------------

class TestValiditeCIN:
    def test_cin_valide(self) -> None:
        controle, anomalies = controler_validite_cin(cin(), DATE_EXAMEN)
        assert controle.reussi is True
        assert anomalies == []

    def test_cin_expiree(self) -> None:
        _, anomalies = controler_validite_cin(
            cin(date_validite=date(2025, 12, 31)), DATE_EXAMEN
        )
        assert [a.code for a in anomalies] == ["CIN_EXPIREE"]

    def test_cin_expirant_le_jour_meme_est_valide(self) -> None:
        """Une CIN reste opposable jusqu'a la fin de son dernier jour de validite."""
        controle, anomalies = controler_validite_cin(
            cin(date_validite=DATE_EXAMEN), DATE_EXAMEN
        )
        assert controle.reussi is True
        assert [a.code for a in anomalies] == ["CIN_EXPIRE_BIENTOT"]

    def test_alerte_expiration_proche(self) -> None:
        controle, anomalies = controler_validite_cin(
            cin(date_validite=date(2026, 9, 5)), DATE_EXAMEN
        )
        assert controle.reussi is True  # accepte...
        assert [a.code for a in anomalies] == ["CIN_EXPIRE_BIENTOT"]  # ...mais signale

    def test_date_validite_absente(self) -> None:
        _, anomalies = controler_validite_cin(cin(date_validite=None), DATE_EXAMEN)
        assert [a.code for a in anomalies] == ["CIN_DATE_VALIDITE_ABSENTE"]


# ---------------------------------------------------------------------------
# Format du numero de CIN
# ---------------------------------------------------------------------------

class TestNumeroCIN:
    @pytest.mark.parametrize("numero", ["BE745123", "A234567", "K45678", "AB123456"])
    def test_formats_valides(self, numero: str) -> None:
        controle, anomalies = controler_numero_cin(cin(numero_cin=numero))
        assert controle.reussi is True
        assert anomalies == []

    @pytest.mark.parametrize("numero", ["1234", "ABC123456", "BE7451", "745123", "BE-745-123!"])
    def test_formats_invalides(self, numero: str) -> None:
        controle, anomalies = controler_numero_cin(cin(numero_cin=numero))
        assert controle.reussi is False
        assert anomalies[0].code == "CIN_NUMERO_FORMAT_INVALIDE"

    def test_numero_absent(self) -> None:
        _, anomalies = controler_numero_cin(cin(numero_cin=None))
        assert [a.code for a in anomalies] == ["CIN_NUMERO_ABSENT"]


# ---------------------------------------------------------------------------
# Correspondance du nom
# ---------------------------------------------------------------------------

class TestCorrespondanceNom:
    @pytest.mark.parametrize(
        "nom_document",
        [
            "Youssef BENALI",
            "BENALI Youssef",       # ordre inverse
            "youssef benali",       # casse differente
            "BENALI, Youssef",      # ponctuation
            "Youssef Bénali",       # accent
        ],
    )
    def test_variantes_acceptees(self, nom_document: str) -> None:
        """Ordre, casse, ponctuation et accents ne doivent jamais causer un rejet."""
        assert score_correspondance_nom(nom_document, "Youssef BENALI") >= 0.99

    def test_translitteration_toleree_avec_avertissement(self) -> None:
        score = score_correspondance_nom("Youssuf BENALI", "Youssef BENALI")
        assert 0.85 <= score < 0.99

    def test_personne_differente_rejetee(self) -> None:
        assert score_correspondance_nom("Hamid IDRISSI", "Youssef BENALI") < 0.85

    def test_controle_nom_divergent(self) -> None:
        _, anomalies = controler_nom(
            cin(nom_titulaire="IDRISSI", prenom_titulaire="Hamid"), DOSSIER
        )
        assert [a.code for a in anomalies] == ["NOM_DIVERGENT"]

    def test_controle_nom_absent(self) -> None:
        _, anomalies = controler_nom(
            cin(nom_titulaire=None, prenom_titulaire=None), DOSSIER
        )
        assert [a.code for a in anomalies] == ["NOM_ABSENT"]


# ---------------------------------------------------------------------------
# Emetteur
# ---------------------------------------------------------------------------

class TestEmetteur:
    def test_dgsn_accepte_pour_cin(self) -> None:
        controle, anomalies = controler_emetteur(cin())
        assert controle.reussi is True
        assert anomalies == []

    def test_lydec_refuse_pour_cin(self) -> None:
        """Une CIN ne peut etre emise que par la DGSN, meme par un organisme par
        ailleurs habilite pour les justificatifs de domicile."""
        _, anomalies = controler_emetteur(
            cin(emetteur="LYDEC", emetteur_canonique="LYDEC")
        )
        assert [a.code for a in anomalies] == ["EMETTEUR_NON_AUTORISE"]

    @pytest.mark.parametrize(
        "canonique", ["LYDEC", "REDAL", "AMENDIS", "ONEE", "MAROC TELECOM", "INWI"]
    )
    def test_emetteurs_domicile_acceptes(self, canonique: str) -> None:
        controle, _ = controler_emetteur(
            domicile(emetteur=canonique, emetteur_canonique=canonique)
        )
        assert controle.reussi is True

    def test_emetteur_hors_liste(self) -> None:
        _, anomalies = controler_emetteur(
            domicile(emetteur="Streamflix Maroc", emetteur_canonique=None)
        )
        assert [a.code for a in anomalies] == ["EMETTEUR_NON_AUTORISE"]

    def test_emetteur_absent(self) -> None:
        _, anomalies = controler_emetteur(domicile(emetteur=None, emetteur_canonique=None))
        assert [a.code for a in anomalies] == ["EMETTEUR_ABSENT"]


# ---------------------------------------------------------------------------
# Adresse
# ---------------------------------------------------------------------------

class TestAdresse:
    def test_adresse_avec_ville_connue(self) -> None:
        controle, anomalies = controler_adresse(domicile())
        assert controle.reussi is True
        assert anomalies == []

    def test_adresse_absente_bloque(self) -> None:
        _, anomalies = controler_adresse(domicile(adresse=None))
        assert [a.code for a in anomalies] == ["ADRESSE_ABSENTE"]

    def test_adresse_sans_ville_avertit_seulement(self) -> None:
        """Une ville non reconnue n'est pas une preuve de fraude : on alerte, on ne rejette pas."""
        _, anomalies = controler_adresse(domicile(adresse="Douar Ait Ourir, province rurale"))
        assert [a.code for a in anomalies] == ["ADRESSE_NON_PLAUSIBLE"]
        assert anomalies[0].severite.value == "AVERTISSEMENT"


# ---------------------------------------------------------------------------
# Decision globale
# ---------------------------------------------------------------------------

class TestDecision:
    def test_document_conforme_valide(self) -> None:
        statut, anomalies, controles = valider(cin(), DOSSIER, DATE_EXAMEN)
        assert statut is StatutConformite.VALIDE
        assert anomalies == []
        assert all(c.reussi for c in controles)

    def test_une_anomalie_bloquante_suffit_a_rejeter(self) -> None:
        statut, _, _ = valider(cin(date_validite=date(2020, 1, 1)), DOSSIER, DATE_EXAMEN)
        assert statut is StatutConformite.REJETE

    def test_avertissement_seul_donne_a_verifier(self) -> None:
        statut, anomalies, _ = valider(
            cin(date_validite=date(2026, 9, 1)), DOSSIER, DATE_EXAMEN
        )
        assert statut is StatutConformite.A_VERIFIER
        assert all(a.severite.value == "AVERTISSEMENT" for a in anomalies)

    def test_type_inconnu_court_circuite_les_controles(self) -> None:
        """Sur un type inconnu, on ne veut pas noyer le vrai motif sous des
        anomalies derivees (numero absent, date absente, emetteur absent...)."""
        statut, anomalies, _ = valider(
            DocumentNormalise(type_document=TypeDocument.INCONNU), DOSSIER, DATE_EXAMEN
        )
        assert statut is StatutConformite.REJETE
        assert [a.code for a in anomalies] == ["DOC_TYPE_INCONNU"]

    def test_tous_les_controles_sont_traces(self) -> None:
        """Le rapport doit prouver qu'un controle a eu lieu, pas le laisser deduire."""
        _, _, controles = valider(cin(), DOSSIER, DATE_EXAMEN)
        noms = {c.nom for c in controles}
        assert "Validite de la CIN" in noms
        assert "Correspondance du nom" in noms
        assert "Emetteur autorise" in noms
        assert "Numero de CIN" in noms

    def test_decision_reproductible(self) -> None:
        """Deux analyses du meme document donnent strictement la meme decision."""
        document = domicile(date_emission=date(2026, 5, 17))
        premiere = valider(document, DOSSIER, DATE_EXAMEN)
        seconde = valider(document, DOSSIER, DATE_EXAMEN)
        assert premiere[0] == seconde[0]
        assert [a.code for a in premiere[1]] == [a.code for a in seconde[1]]
