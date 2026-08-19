"""
Tests du pipeline complet et de sa degradation.

L'exigence centrale verifiee ici : aucune defaillance technique ne doit produire
un "VALIDE". Un moteur en panne, un document vide ou une reponse aberrante
doivent tous aboutir a un rejet motive, jamais a une acceptation par defaut.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agent import AgentConformite
from src.llm import ClientDefaillant, ClientSimule
from src.models import DossierClient, StatutConformite, TypeDocument

DATE_EXAMEN = date(2026, 8, 18)

DOSSIER = DossierClient(
    dossier_id="D-TEST-001",
    nom="BENALI",
    prenom="Youssef",
    adresse_declaree="12 rue Ibn Sina, Maarif, Casablanca",
)

CIN_CONFORME = """ROYAUME DU MAROC
DIRECTION GENERALE DE LA SURETE NATIONALE
CARTE D'IDENTITE NATIONALE

Nom : BENALI
Prenom : Youssef
Numero CIN : BE745123
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date d'emission : 18/08/2022
Valable jusqu'au : 18/08/2032
Emetteur : DGSN
"""

FACTURE_PERIMEE = """LYDEC
FACTURE D'EAU ET D'ELECTRICITE

Nom : BENALI Youssef
Adresse : 12 rue Ibn Sina, Maarif, Casablanca
Date de facture : 10/01/2026
Montant total : 428,50 MAD
Emetteur : LYDEC
"""


@pytest.fixture
def agent() -> AgentConformite:
    """Agent branche sur le moteur simule : les tests ne dependent d'aucun modele installe."""
    return AgentConformite(client=ClientSimule())


# ---------------------------------------------------------------------------
# Cas nominaux
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_document_conforme(self, agent: AgentConformite) -> None:
        rapport = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.VALIDE
        assert rapport.type_document is TypeDocument.CIN
        assert rapport.anomalies == []
        assert rapport.motifs_rejet == []

    def test_document_non_conforme(self, agent: AgentConformite) -> None:
        rapport = agent.analyser(FACTURE_PERIMEE, DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.REJETE
        assert "JUSTIFICATIF_PERIME" in {a.code for a in rapport.anomalies}
        assert rapport.motifs_rejet  # le motif est expose, pas seulement le statut

    def test_rapport_horodate_et_trace(self, agent: AgentConformite) -> None:
        """Chaque rapport doit etre auditable : quand, avec quel moteur, en combien de temps."""
        rapport = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN, nom_fichier="cin.txt")
        assert rapport.nom_fichier == "cin.txt"
        assert rapport.moteur_llm == "simule:regex"
        assert rapport.horodatage is not None
        assert rapport.duree_traitement_ms >= 0
        assert len(rapport.controles) >= 5

    def test_decision_reproductible(self, agent: AgentConformite) -> None:
        """Deux passages sur le meme document rendent la meme decision."""
        premier = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN)
        second = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN)
        assert premier.statut == second.statut
        assert [a.code for a in premier.anomalies] == [a.code for a in second.anomalies]


# ---------------------------------------------------------------------------
# Degradation : rien ne doit passer en VALIDE par accident
# ---------------------------------------------------------------------------

class TestDegradation:
    def test_moteur_en_panne_rejette(self) -> None:
        """Un moteur injoignable produit un rejet motive, jamais une validation."""
        agent = AgentConformite(client=ClientDefaillant())
        rapport = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.REJETE
        assert rapport.anomalies[0].code == "DOC_ILLISIBLE"
        assert "indisponible" in rapport.anomalies[0].detail.lower()

    def test_document_vide_rejette(self, agent: AgentConformite) -> None:
        rapport = agent.analyser("", DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.REJETE
        assert rapport.anomalies[0].code == "DOC_ILLISIBLE"

    def test_document_blanc_rejette(self, agent: AgentConformite) -> None:
        rapport = agent.analyser("   \n\n  ", DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.REJETE

    def test_texte_hors_sujet_rejette(self, agent: AgentConformite) -> None:
        rapport = agent.analyser("Bonjour, comment allez-vous ?", DOSSIER, DATE_EXAMEN)
        assert rapport.statut is StatutConformite.REJETE
        assert rapport.type_document is TypeDocument.INCONNU

    def test_aucune_defaillance_ne_produit_valide(self, agent: AgentConformite) -> None:
        """Balayage des entrees degradees : aucune ne doit ressortir VALIDE."""
        entrees = [
            "",
            "   ",
            "azerty",
            "{}",
            "<html><body>404 Not Found</body></html>",
            "Nom : BENALI",  # fragment sans type ni date
        ]
        for entree in entrees:
            rapport = agent.analyser(entree, DOSSIER, DATE_EXAMEN)
            assert rapport.statut is not StatutConformite.VALIDE, f"entree acceptee : {entree!r}"


# ---------------------------------------------------------------------------
# Traitement par lot
# ---------------------------------------------------------------------------

class TestTraitementLot:
    def test_lot_complet(self, agent: AgentConformite) -> None:
        documents = [
            ("cin.txt", CIN_CONFORME, DOSSIER),
            ("facture.txt", FACTURE_PERIMEE, DOSSIER),
        ]
        rapports = agent.analyser_lot(documents, DATE_EXAMEN)
        assert len(rapports) == 2
        assert rapports[0].statut is StatutConformite.VALIDE
        assert rapports[1].statut is StatutConformite.REJETE

    def test_un_document_defaillant_n_interrompt_pas_le_lot(self, agent: AgentConformite) -> None:
        """Une file d'attente KYC ne doit pas s'arreter sur un document corrompu."""
        documents = [
            ("vide.txt", "", DOSSIER),
            ("cin.txt", CIN_CONFORME, DOSSIER),
        ]
        rapports = agent.analyser_lot(documents, DATE_EXAMEN)
        assert len(rapports) == 2
        assert rapports[0].statut is StatutConformite.REJETE
        assert rapports[1].statut is StatutConformite.VALIDE


# ---------------------------------------------------------------------------
# Serialisation du rapport
# ---------------------------------------------------------------------------

def test_rapport_serialisable_en_json(agent: AgentConformite) -> None:
    """Le rapport doit pouvoir etre archive tel quel : c'est la piste d'audit."""
    import json

    rapport = agent.analyser(CIN_CONFORME, DOSSIER, DATE_EXAMEN)
    donnees = json.loads(rapport.model_dump_json())
    assert donnees["statut"] == "VALIDE"
    assert donnees["dossier_id"] == "D-TEST-001"
    assert "controles" in donnees
