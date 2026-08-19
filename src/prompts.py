"""
Prompts d'extraction.

Regle de conception : le prompt ne demande JAMAIS au LLM de juger la conformite.
Il lui demande uniquement de lire et de restituer ce qui est ecrit. Toute
question du type "ce document est-il valide ?" est traitee par src/regles.py.

Pourquoi : un LLM interroge sur la validite produit une reponse plausible mais
non reproductible, impossible a auditer et sensible a la formulation. Une regle
Python sur une date produit toujours le meme resultat et se justifie devant un
controleur.
"""

from __future__ import annotations

SYSTEM_EXTRACTION = """Tu es un assistant d'extraction documentaire pour un service bancaire marocain.

Ta seule tache est de LIRE un document et d'en extraire les informations demandees.
Tu ne juges jamais la validite, la conformite ou la recevabilite du document.
Tu ne completes jamais une information absente : si un champ n'apparait pas dans
le texte, tu renvoies null pour ce champ.

Tu reponds exclusivement par un objet JSON, sans texte avant ni apres, sans
balises de code."""


TEMPLATE_EXTRACTION = """Extrais les informations du document ci-dessous.

Renvoie un JSON avec exactement ces cles :

{{
  "type_document": "CIN" | "JUSTIFICATIF_DOMICILE" | "INCONNU",
  "nom_titulaire": string | null,
  "prenom_titulaire": string | null,
  "numero_cin": string | null,
  "date_emission": string | null,
  "date_validite": string | null,
  "emetteur": string | null,
  "adresse": string | null,
  "confiance": number entre 0 et 1
}}

Consignes de lecture :
- "type_document" : "CIN" pour une carte d'identite nationale, "JUSTIFICATIF_DOMICILE"
  pour une facture d'eau, d'electricite, de telephone ou une attestation de residence,
  "INCONNU" sinon.
- "nom_titulaire" : le nom de famille seul. "prenom_titulaire" : le prenom seul.
  Sur une CIN marocaine le nom est souvent en majuscules et le prenom en dessous.
- "numero_cin" : uniquement pour une CIN, tel qu'ecrit (ex : "BE745123").
- "date_emission" : la date a laquelle le document a ete etabli ou la facture emise.
  Recopie-la telle qu'elle apparait, sans reformater.
- "date_validite" : uniquement pour une CIN, la date d'expiration ("valable jusqu'au").
  null pour un justificatif de domicile.
- "emetteur" : l'organisme qui a etabli le document (DGSN, Lydec, Redal, Amendis,
  ONEE, Maroc Telecom, Orange, Inwi...).
- "adresse" : l'adresse complete figurant sur le document.
- "confiance" : 1.0 si le document est clair et complet, valeur plus basse s'il est
  partiel, ambigu ou difficile a interpreter.

Si une information est absente, mets null. N'invente rien.

DOCUMENT :
---
{texte_document}
---

JSON :"""


def construire_prompt_extraction(texte_document: str) -> str:
    """Assemble le prompt final envoye au LLM."""
    return TEMPLATE_EXTRACTION.format(texte_document=texte_document.strip())
