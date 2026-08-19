"""
Interface en ligne de commande de l'agent de conformite.

Exemples :
    # Un document, contre un dossier client donne
    python main.py data/documents/cin_01_conforme.txt --nom BENALI --prenom Youssef

    # Sortie JSON, pour archivage ou chainage avec un autre outil
    python main.py data/documents/cin_03_expiree.txt --nom TAZI --prenom Karim --format json

    # Tout le jeu de donnees, avec synthese
    python main.py --lot

    # Forcer un moteur precis
    python main.py --lot --moteur ollama --modele llama3.2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.agent import AgentConformite
from src.llm import ErreurLLM, charger_client
from src.models import DossierClient
from src.rapport import (
    formater_json,
    formater_markdown,
    formater_synthese,
    formater_texte,
)

RACINE = Path(__file__).parent
FICHIER_CAS = RACINE / "data" / "cas_de_test.json"

FORMATEURS = {
    "texte": formater_texte,
    "json": formater_json,
    "markdown": formater_markdown,
}


def analyser_un(arguments: argparse.Namespace, agent: AgentConformite) -> int:
    chemin = Path(arguments.document)
    if not chemin.exists():
        print(f"Fichier introuvable : {chemin}", file=sys.stderr)
        return 2

    if not arguments.nom:
        print(
            "Le nom du client est requis pour verifier la correspondance (--nom).",
            file=sys.stderr,
        )
        return 2

    dossier = DossierClient(
        dossier_id=arguments.dossier_id,
        nom=arguments.nom,
        prenom=arguments.prenom or "",
    )

    rapport = agent.analyser_fichier(chemin, dossier, date_reference=arguments.date)
    print(FORMATEURS[arguments.format](rapport))

    # Code de sortie exploitable par un script appelant : 0 valide, 1 rejete.
    return 0 if rapport.statut.value == "VALIDE" else 1


def analyser_lot(arguments: argparse.Namespace, agent: AgentConformite) -> int:
    if not FICHIER_CAS.exists():
        print(
            f"Jeu de donnees absent ({FICHIER_CAS}). Lance d'abord : python generer_donnees.py",
            file=sys.stderr,
        )
        return 2

    donnees = json.loads(FICHIER_CAS.read_text(encoding="utf-8"))
    date_reference = arguments.date or date.fromisoformat(donnees["date_reference"])

    documents = []
    for cas in donnees["cas"]:
        chemin = RACINE / "data" / "documents" / cas["fichier"]
        if not chemin.exists():
            print(f"Document manquant, ignore : {cas['fichier']}", file=sys.stderr)
            continue
        documents.append(
            (cas["fichier"], chemin.read_text(encoding="utf-8"), DossierClient(**cas["dossier"]))
        )

    rapports = agent.analyser_lot(documents, date_reference=date_reference)

    if arguments.format == "json":
        from src.rapport import exporter_json_lot

        print(exporter_json_lot(rapports))
        return 0

    for rapport in rapports:
        print(FORMATEURS[arguments.format](rapport))
        print()

    print(formater_synthese(rapports))
    return 0


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Agent d'analyse de conformite KYC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    analyseur.add_argument("document", nargs="?", help="Chemin du document a analyser.")
    analyseur.add_argument("--nom", help="Nom de famille figurant au dossier client.")
    analyseur.add_argument("--prenom", help="Prenom figurant au dossier client.")
    analyseur.add_argument("--dossier-id", default="D-MANUEL", help="Identifiant du dossier.")
    analyseur.add_argument(
        "--lot", action="store_true", help="Analyse tout le jeu de donnees de data/documents."
    )
    analyseur.add_argument(
        "--moteur",
        default="auto",
        choices=["auto", "ollama", "simule", "defaillant"],
        help="Moteur d'extraction (defaut : auto).",
    )
    analyseur.add_argument("--modele", default="llama3.2", help="Modele Ollama a utiliser.")
    analyseur.add_argument(
        "--format",
        default="texte",
        choices=list(FORMATEURS),
        help="Format de sortie du rapport.",
    )
    analyseur.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Date d'examen du dossier (AAAA-MM-JJ). Defaut : aujourd'hui.",
    )
    arguments = analyseur.parse_args()

    if not arguments.lot and not arguments.document:
        analyseur.print_help()
        return 2

    try:
        client = charger_client(arguments.moteur, arguments.modele)
    except ErreurLLM as erreur:
        print(f"Moteur indisponible : {erreur}", file=sys.stderr)
        return 3

    agent = AgentConformite(client=client)
    print(f"Moteur : {client.nom}\n", file=sys.stderr)

    return analyser_lot(arguments, agent) if arguments.lot else analyser_un(arguments, agent)


if __name__ == "__main__":
    raise SystemExit(main())
