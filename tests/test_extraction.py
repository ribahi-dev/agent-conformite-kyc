"""
Tests de l'extraction et de la normalisation.

Ces tests couvrent la frontiere la plus fragile du projet : ce qui sort d'un LLM
est du texte libre, et tout ce qui suit suppose des types propres. Chaque cas
ci-dessous correspond a une sortie reellement rencontree avec un modele local.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.extraction import (
    _extraire_json,
    _parser_date,
    _texte_ou_none,
    canoniser_emetteur,
    extraire,
    normaliser,
    supprimer_accents,
)
from src.llm import ClientSimule, ErreurLLM
from src.models import ExtractionBrute, TypeDocument


# ---------------------------------------------------------------------------
# Robustesse du parsing JSON
# ---------------------------------------------------------------------------

class TestExtractionJSON:
    def test_json_pur(self) -> None:
        assert _extraire_json('{"nom_titulaire": "BENALI"}') == {"nom_titulaire": "BENALI"}

    def test_json_entoure_de_texte(self) -> None:
        """Les modeles locaux preferent souvent annoncer leur reponse."""
        reponse = 'Voici le resultat :\n{"nom_titulaire": "BENALI"}\nJ\'espere que cela convient.'
        assert _extraire_json(reponse) == {"nom_titulaire": "BENALI"}

    def test_json_dans_des_balises_de_code(self) -> None:
        reponse = '```json\n{"nom_titulaire": "BENALI"}\n```'
        assert _extraire_json(reponse) == {"nom_titulaire": "BENALI"}

    def test_objets_imbriques(self) -> None:
        """Le comptage des accolades doit rendre l'objet complet, pas s'arreter au premier '}'."""
        reponse = '{"a": {"b": 1}, "c": 2}'
        assert _extraire_json(reponse) == {"a": {"b": 1}, "c": 2}

    def test_json_invalide_renvoie_none(self) -> None:
        assert _extraire_json("desole, je ne peux pas lire ce document") is None

    def test_tableau_json_refuse(self) -> None:
        """Un tableau n'est pas la structure attendue : on refuse plutot que d'improviser."""
        assert _extraire_json('[{"nom": "x"}]') is None


# ---------------------------------------------------------------------------
# Valeurs vides deguisees
# ---------------------------------------------------------------------------

class TestValeursVides:
    @pytest.mark.parametrize(
        "valeur", [None, "", "   ", "null", "NULL", "None", "N/A", "n/a", "-", "inconnu"]
    )
    def test_variantes_de_vide(self, valeur) -> None:
        """Un modele ecrit "N/A" la ou le schema demandait null : c'est un champ absent."""
        assert _texte_ou_none(valeur) is None

    def test_valeur_reelle_conservee(self) -> None:
        assert _texte_ou_none("  BENALI  ") == "BENALI"


# ---------------------------------------------------------------------------
# Parsing des dates
# ---------------------------------------------------------------------------

class TestParsingDates:
    @pytest.mark.parametrize(
        "texte, attendu",
        [
            ("18/08/2026", date(2026, 8, 18)),
            ("18-08-2026", date(2026, 8, 18)),
            ("18.08.2026", date(2026, 8, 18)),
            ("2026-08-18", date(2026, 8, 18)),
        ],
    )
    def test_formats_courants(self, texte: str, attendu: date) -> None:
        assert _parser_date(texte) == attendu

    def test_jour_en_premier(self) -> None:
        """03/04/2026 se lit 3 avril au Maroc comme en France, jamais 4 mars.

        Une inversion ici fausserait silencieusement tous les calculs
        d'anciennete : c'est le bug le plus couteux que ce module puisse avoir.
        """
        assert _parser_date("03/04/2026") == date(2026, 4, 3)

    def test_date_illisible(self) -> None:
        assert _parser_date("le mois dernier") is None

    def test_date_vide(self) -> None:
        assert _parser_date("") is None


# ---------------------------------------------------------------------------
# Canonisation des emetteurs
# ---------------------------------------------------------------------------

class TestCanonisationEmetteur:
    @pytest.mark.parametrize(
        "ecriture, canonique",
        [
            ("LYDEC", "LYDEC"),
            ("lydec", "LYDEC"),
            ("Lyonnaise des Eaux de Casablanca", "LYDEC"),
            ("REDAL Veolia", "REDAL"),
            ("Amendis Tanger", "AMENDIS"),
            ("Office National de l'Electricite et de l'Eau Potable", "ONEE"),
            ("Itissalat Al-Maghrib", "MAROC TELECOM"),
            ("IAM", "MAROC TELECOM"),
            ("inwi", "INWI"),
            ("DGSN", "DGSN"),
            ("Direction Generale de la Surete Nationale", "DGSN"),
        ],
    )
    def test_variantes_ramenees_a_la_forme_canonique(self, ecriture: str, canonique: str) -> None:
        """Une variation d'ecriture ne doit jamais faire rejeter un document valide."""
        assert canoniser_emetteur(ecriture) == canonique

    def test_emetteur_avec_accents(self) -> None:
        assert canoniser_emetteur("Sûreté Nationale") == "DGSN"

    def test_emetteur_inconnu(self) -> None:
        assert canoniser_emetteur("Streamflix Maroc SARL") is None


# ---------------------------------------------------------------------------
# Suppression des accents
# ---------------------------------------------------------------------------

def test_suppression_accents() -> None:
    assert supprimer_accents("Bénali Youssef") == "Benali Youssef"
    assert supprimer_accents("Sûreté") == "Surete"
    assert supprimer_accents("EL AMRANI") == "EL AMRANI"


# ---------------------------------------------------------------------------
# Normalisation complete
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_champs_convertis(self) -> None:
        document = normaliser(
            ExtractionBrute(
                type_document="CIN",
                nom_titulaire="BENALI",
                prenom_titulaire="Youssef",
                numero_cin="be 745 123",
                date_validite="18/08/2032",
                emetteur="Direction Generale de la Surete Nationale",
            )
        )
        assert document.type_document is TypeDocument.CIN
        assert document.numero_cin == "BE745123"  # espaces retires, majuscules
        assert document.date_validite == date(2032, 8, 18)
        assert document.emetteur_canonique == "DGSN"
        assert document.erreurs_normalisation == []

    def test_date_illisible_est_tracee(self) -> None:
        """Un champ present mais illisible ne doit pas devenir un champ absent :
        les deux situations ont des motifs de rejet differents."""
        document = normaliser(
            ExtractionBrute(type_document="CIN", date_validite="prochainement")
        )
        assert document.date_validite is None
        assert len(document.erreurs_normalisation) == 1
        assert "date_validite" in document.erreurs_normalisation[0]

    def test_date_absente_ne_produit_pas_d_erreur(self) -> None:
        document = normaliser(ExtractionBrute(type_document="CIN", date_validite=None))
        assert document.date_validite is None
        assert document.erreurs_normalisation == []

    def test_civilite_retiree_du_nom(self) -> None:
        document = normaliser(ExtractionBrute(nom_titulaire="M. BENALI"))
        assert document.nom_titulaire == "BENALI"

    @pytest.mark.parametrize(
        "libelle, attendu",
        [
            ("CIN", TypeDocument.CIN),
            ("carte d'identite", TypeDocument.CIN),
            ("JUSTIFICATIF_DOMICILE", TypeDocument.JUSTIFICATIF_DOMICILE),
            ("facture", TypeDocument.JUSTIFICATIF_DOMICILE),
            ("attestation de residence", TypeDocument.JUSTIFICATIF_DOMICILE),
            ("bulletin de paie", TypeDocument.INCONNU),
            (None, TypeDocument.INCONNU),
        ],
    )
    def test_normalisation_du_type(self, libelle, attendu) -> None:
        assert normaliser(ExtractionBrute(type_document=libelle)).type_document is attendu


# ---------------------------------------------------------------------------
# Extraction de bout en bout avec le moteur simule
# ---------------------------------------------------------------------------

class TestExtractionBoutEnBout:
    def test_lecture_d_une_cin(self) -> None:
        texte = """ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : BENALI
Prenom : Youssef
Numero CIN : BE745123
Valable jusqu'au : 18/08/2032
Emetteur : DGSN
"""
        brut = extraire(texte, ClientSimule())
        assert brut.type_document == "CIN"
        assert brut.nom_titulaire == "BENALI"
        assert brut.numero_cin == "BE745123"

    def test_moteur_muet_leve_une_erreur(self) -> None:
        """Un moteur qui ne renvoie pas de JSON ne doit jamais aboutir a un document vide
        traite comme valide : l'agent doit recevoir une erreur explicite."""

        class ClientMuet(ClientSimule):
            def generer(self, prompt: str, system: str = "") -> str:
                return "Je ne peux pas traiter cette demande."

        with pytest.raises(ErreurLLM):
            extraire("un document", ClientMuet())
