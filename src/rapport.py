"""
Mise en forme du rapport de conformite.

Trois sorties pour trois usages :
  - texte     : lecture en console, demonstration
  - markdown  : capture d'ecran et annexes du rapport de stage
  - json      : archivage et exploitation par un autre systeme (piste d'audit)

La logique de decision n'apparait nulle part ici : ce module ne fait que lire un
RapportConformite deja constitue.
"""

from __future__ import annotations

import json

from .models import RapportConformite, Severite, StatutConformite

SYMBOLES = {
    StatutConformite.VALIDE: "[VALIDE]",
    StatutConformite.REJETE: "[REJETE]",
    StatutConformite.A_VERIFIER: "[A VERIFIER]",
}


def formater_texte(rapport: RapportConformite, detaille: bool = True) -> str:
    """Rapport lisible en console."""
    lignes: list[str] = []
    largeur = 72

    lignes.append("=" * largeur)
    lignes.append(f"RAPPORT DE CONFORMITE - {SYMBOLES[rapport.statut]}")
    lignes.append("=" * largeur)
    lignes.append(f"Dossier      : {rapport.dossier_id}")
    if rapport.nom_fichier:
        lignes.append(f"Document     : {rapport.nom_fichier}")
    lignes.append(f"Type         : {rapport.type_document.value}")
    lignes.append(f"Analyse le   : {rapport.horodatage:%d/%m/%Y a %H:%M:%S}")
    lignes.append(f"Moteur       : {rapport.moteur_llm} ({rapport.duree_traitement_ms} ms)")
    lignes.append("")

    motifs = rapport.motifs_rejet
    if motifs:
        lignes.append(f"MOTIFS DE REJET ({len(motifs)})")
        lignes.append("-" * largeur)
        for numero, motif in enumerate(motifs, start=1):
            lignes.append(f"  {numero}. {motif}")
        lignes.append("")

    avertissements = rapport.avertissements
    if avertissements:
        lignes.append(f"AVERTISSEMENTS ({len(avertissements)})")
        lignes.append("-" * largeur)
        for numero, avertissement in enumerate(avertissements, start=1):
            lignes.append(f"  {numero}. {avertissement}")
        lignes.append("")

    if not motifs and not avertissements:
        lignes.append("Aucune anomalie detectee. Document conforme.")
        lignes.append("")

    if detaille and rapport.controles:
        lignes.append(
            f"CONTROLES EFFECTUES ({rapport.nb_controles_reussis}/{len(rapport.controles)} reussis)"
        )
        lignes.append("-" * largeur)
        for controle in rapport.controles:
            marque = "OK  " if controle.reussi else "KO  "
            detail = f" - {controle.detail}" if controle.detail else ""
            lignes.append(f"  {marque}{controle.nom}{detail}")
        lignes.append("")

    if detaille and rapport.document:
        doc = rapport.document
        lignes.append("DONNEES EXTRAITES")
        lignes.append("-" * largeur)
        champs = [
            ("Nom", doc.nom_complet),
            ("Numero CIN", doc.numero_cin),
            ("Date d'emission", f"{doc.date_emission:%d/%m/%Y}" if doc.date_emission else None),
            ("Date de validite", f"{doc.date_validite:%d/%m/%Y}" if doc.date_validite else None),
            ("Emetteur", doc.emetteur_canonique or doc.emetteur),
            ("Adresse", doc.adresse),
            ("Confiance", f"{doc.confiance:.2f}"),
        ]
        for etiquette, valeur in champs:
            if valeur:
                lignes.append(f"  {etiquette:<18}: {valeur}")
        lignes.append("")

    lignes.append("=" * largeur)
    return "\n".join(lignes)


def formater_markdown(rapport: RapportConformite) -> str:
    """Rapport en Markdown, destine aux annexes du rapport de stage."""
    lignes: list[str] = []

    lignes.append(f"## Rapport de conformite - {rapport.statut.value}")
    lignes.append("")
    lignes.append("| Champ | Valeur |")
    lignes.append("|---|---|")
    lignes.append(f"| Dossier | {rapport.dossier_id} |")
    lignes.append(f"| Document | {rapport.nom_fichier or '-'} |")
    lignes.append(f"| Type | {rapport.type_document.value} |")
    lignes.append(f"| Statut | **{rapport.statut.value}** |")
    lignes.append(f"| Analyse le | {rapport.horodatage:%d/%m/%Y %H:%M:%S} |")
    lignes.append(f"| Moteur | {rapport.moteur_llm} |")
    lignes.append(f"| Duree | {rapport.duree_traitement_ms} ms |")
    lignes.append("")

    if rapport.anomalies:
        lignes.append("### Anomalies")
        lignes.append("")
        lignes.append("| Severite | Code | Detail |")
        lignes.append("|---|---|---|")
        for anomalie in rapport.anomalies:
            detail = (anomalie.detail or anomalie.libelle).replace("|", "/")
            lignes.append(f"| {anomalie.severite.value} | `{anomalie.code}` | {detail} |")
        lignes.append("")
    else:
        lignes.append("Aucune anomalie detectee.")
        lignes.append("")

    if rapport.controles:
        lignes.append("### Controles effectues")
        lignes.append("")
        for controle in rapport.controles:
            marque = "x" if controle.reussi else " "
            detail = f" — {controle.detail}" if controle.detail else ""
            lignes.append(f"- [{marque}] {controle.nom}{detail}")
        lignes.append("")

    return "\n".join(lignes)


def formater_json(rapport: RapportConformite, indent: int = 2) -> str:
    """Rapport complet en JSON, pour archivage ou echange entre systemes."""
    return rapport.model_dump_json(indent=indent)


def formater_synthese(rapports: list[RapportConformite]) -> str:
    """Tableau de synthese d'un lot, avec repartition par motif de rejet."""
    if not rapports:
        return "Aucun document analyse."

    total = len(rapports)
    par_statut = {statut: 0 for statut in StatutConformite}
    for rapport in rapports:
        par_statut[rapport.statut] += 1

    lignes = ["", "=" * 72, f"SYNTHESE - {total} document(s) analyse(s)", "=" * 72]
    for statut, nombre in par_statut.items():
        if nombre:
            part = 100 * nombre / total
            lignes.append(f"  {SYMBOLES[statut]:<14} {nombre:>3} ({part:5.1f} %)")

    motifs: dict[str, int] = {}
    for rapport in rapports:
        for anomalie in rapport.anomalies:
            if anomalie.severite is Severite.BLOQUANT:
                motifs[anomalie.code] = motifs.get(anomalie.code, 0) + 1

    if motifs:
        lignes.append("")
        lignes.append("Motifs de rejet les plus frequents :")
        for code, nombre in sorted(motifs.items(), key=lambda item: -item[1]):
            lignes.append(f"  {nombre:>3}x  {code}")

    duree_moyenne = sum(r.duree_traitement_ms for r in rapports) / total
    lignes.append("")
    lignes.append(f"Duree moyenne de traitement : {duree_moyenne:.0f} ms")
    lignes.append("=" * 72)
    return "\n".join(lignes)


def exporter_json_lot(rapports: list[RapportConformite], indent: int = 2) -> str:
    """Serialise un lot complet, format attendu par un systeme d'archivage."""
    return json.dumps(
        [json.loads(r.model_dump_json()) for r in rapports],
        indent=indent,
        ensure_ascii=False,
    )
