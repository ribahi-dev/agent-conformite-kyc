"""
Mesure de la performance de l'agent sur le jeu de donnees etiquete.

Chaque cas de data/cas_de_test.json porte le statut attendu et les codes
d'anomalie attendus. Ce script confronte la sortie de l'agent a ces attentes et
produit trois indicateurs :

  - le taux de justesse sur le statut (VALIDE / REJETE / A_VERIFIER) ;
  - le taux de justesse sur le motif (le bon rejet, pour la bonne raison) ;
  - la repartition des erreurs, qui distingue les deux fautes n'ayant pas du
    tout le meme cout en conformite bancaire :
        * faux positif : un document non conforme accepte -> risque reglementaire
        * faux negatif : un document conforme rejete      -> friction client

Sans cette mesure, on ne peut pas affirmer que l'agent "fonctionne" ; on peut
seulement constater qu'il rend une reponse. C'est la difference entre une demo
et un livrable defendable.

Usage :
    python evaluer.py                      # moteur auto
    python evaluer.py --moteur simule      # baseline par expressions regulieres
    python evaluer.py --moteur ollama --modele llama3.2
    python evaluer.py --comparer           # simule et ollama cote a cote
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.agent import AgentConformite
from src.llm import ErreurLLM, charger_client
from src.models import DossierClient, RapportConformite

RACINE = Path(__file__).parent
FICHIER_CAS = RACINE / "data" / "cas_de_test.json"


class Resultat:
    """Comparaison entre ce qui etait attendu et ce que l'agent a produit."""

    def __init__(self, cas: dict, rapport: RapportConformite) -> None:
        self.fichier = cas["fichier"]
        self.description = cas["description"]
        self.statut_attendu = cas["statut_attendu"]
        self.codes_attendus = set(cas["codes_attendus"])
        self.statut_obtenu = rapport.statut.value
        self.codes_obtenus = {a.code for a in rapport.anomalies}
        self.rapport = rapport

    @property
    def statut_correct(self) -> bool:
        return self.statut_obtenu == self.statut_attendu

    @property
    def motif_correct(self) -> bool:
        """Le motif attendu doit figurer parmi les anomalies relevees.

        On n'exige pas l'egalite stricte : relever une anomalie supplementaire
        n'est pas une erreur tant que le motif principal est bien identifie.
        """
        if not self.codes_attendus:
            return not self.codes_obtenus
        return self.codes_attendus.issubset(self.codes_obtenus)

    @property
    def categorie_erreur(self) -> str | None:
        if self.statut_correct:
            return None
        if self.statut_attendu == "VALIDE":
            return "FAUX_NEGATIF"      # conforme, mais rejete par l'agent
        if self.statut_obtenu == "VALIDE":
            return "FAUX_POSITIF"      # non conforme, mais accepte par l'agent
        return "STATUT_DIVERGENT"      # rejet et a-verifier confondus


def charger_cas() -> tuple[list[dict], date]:
    if not FICHIER_CAS.exists():
        print(
            "Jeu de donnees absent. Lance d'abord : python generer_donnees.py",
            file=sys.stderr,
        )
        raise SystemExit(2)
    donnees = json.loads(FICHIER_CAS.read_text(encoding="utf-8"))
    return donnees["cas"], date.fromisoformat(donnees["date_reference"])


def evaluer(moteur: str, modele: str) -> tuple[list[Resultat], str]:
    cas_de_test, date_reference = charger_cas()

    try:
        client = charger_client(moteur, modele)
    except ErreurLLM as erreur:
        print(f"Moteur indisponible : {erreur}", file=sys.stderr)
        raise SystemExit(3)

    agent = AgentConformite(client=client)
    resultats: list[Resultat] = []

    for cas in cas_de_test:
        chemin = RACINE / "data" / "documents" / cas["fichier"]
        if not chemin.exists():
            print(f"Document manquant, ignore : {cas['fichier']}", file=sys.stderr)
            continue
        rapport = agent.analyser(
            chemin.read_text(encoding="utf-8"),
            DossierClient(**cas["dossier"]),
            date_reference=date_reference,
            nom_fichier=cas["fichier"],
        )
        resultats.append(Resultat(cas, rapport))

    return resultats, client.nom


def afficher(resultats: list[Resultat], nom_moteur: str) -> None:
    total = len(resultats)
    if not total:
        print("Aucun cas evalue.")
        return

    statuts_corrects = sum(1 for r in resultats if r.statut_correct)
    motifs_corrects = sum(1 for r in resultats if r.statut_correct and r.motif_correct)

    print()
    print("=" * 76)
    print(f"EVALUATION - moteur {nom_moteur} - {total} cas")
    print("=" * 76)
    print(
        f"Statut correct   : {statuts_corrects}/{total}  "
        f"({100 * statuts_corrects / total:.1f} %)"
    )
    print(
        f"Statut + motif   : {motifs_corrects}/{total}  "
        f"({100 * motifs_corrects / total:.1f} %)"
    )

    erreurs = [r for r in resultats if not r.statut_correct]
    faux_positifs = [r for r in erreurs if r.categorie_erreur == "FAUX_POSITIF"]
    faux_negatifs = [r for r in erreurs if r.categorie_erreur == "FAUX_NEGATIF"]
    divergents = [r for r in erreurs if r.categorie_erreur == "STATUT_DIVERGENT"]

    print()
    print("Repartition des erreurs :")
    print(f"  Faux positifs (non conforme accepte) : {len(faux_positifs)}   <- risque reglementaire")
    print(f"  Faux negatifs (conforme rejete)      : {len(faux_negatifs)}   <- friction client")
    print(f"  Statuts confondus                    : {len(divergents)}")

    motifs_manques = [r for r in resultats if r.statut_correct and not r.motif_correct]
    if motifs_manques:
        print()
        print("Bon statut mais motif attendu absent :")
        for resultat in motifs_manques:
            manquants = resultat.codes_attendus - resultat.codes_obtenus
            print(f"  {resultat.fichier}")
            print(f"    attendu : {', '.join(sorted(manquants))}")
            print(f"    obtenu  : {', '.join(sorted(resultat.codes_obtenus)) or 'aucun'}")

    if erreurs:
        print()
        print("-" * 76)
        print("CAS EN ECHEC")
        print("-" * 76)
        for resultat in erreurs:
            print(f"\n  {resultat.fichier}  [{resultat.categorie_erreur}]")
            print(f"    {resultat.description}")
            print(f"    attendu : {resultat.statut_attendu}")
            print(f"    obtenu  : {resultat.statut_obtenu}")
            codes = ", ".join(sorted(resultat.codes_obtenus)) or "aucune anomalie"
            print(f"    codes   : {codes}")

    duree = sum(r.rapport.duree_traitement_ms for r in resultats) / total
    print()
    print("-" * 76)
    print(f"Duree moyenne par document : {duree:.0f} ms")
    print("=" * 76)


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Evalue l'agent sur le jeu etiquete.")
    analyseur.add_argument("--moteur", default="auto", choices=["auto", "ollama", "simule"])
    analyseur.add_argument("--modele", default="llama3.2")
    analyseur.add_argument(
        "--comparer",
        action="store_true",
        help="Evalue successivement le mode simule et Ollama, pour comparaison.",
    )
    arguments = analyseur.parse_args()

    if arguments.comparer:
        for moteur in ("simule", "ollama"):
            try:
                resultats, nom = evaluer(moteur, arguments.modele)
                afficher(resultats, nom)
            except SystemExit:
                print(f"\nMoteur '{moteur}' indisponible, comparaison partielle.\n")
        return 0

    resultats, nom = evaluer(arguments.moteur, arguments.modele)
    afficher(resultats, nom)
    return 0 if all(r.statut_correct for r in resultats) else 1


if __name__ == "__main__":
    raise SystemExit(main())
