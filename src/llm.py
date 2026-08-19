"""
Couche d'acces au LLM.

L'agent ne connait qu'une interface, `ClientLLM`. Changer de moteur (Ollama en
local, une API distante, ou le mode simule) n'impose aucune modification du reste
du code. C'est ce qui permet de developper et de tester tout le pipeline sans
dependre d'un modele installe.

Trois implementations :
  - ClientOllama    : modele local via l'API HTTP d'Ollama (http://localhost:11434)
  - ClientSimule    : extraction par expressions regulieres, aucun LLM requis
  - ClientDefaillant: simule une panne du moteur, pour tester la robustesse
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import requests

OLLAMA_URL_DEFAUT = "http://localhost:11434"
MODELE_DEFAUT = "llama3.2"


class ErreurLLM(RuntimeError):
    """Le moteur est injoignable ou a renvoye une reponse inexploitable."""


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class ClientLLM(ABC):
    """Contrat commun a tous les moteurs."""

    nom: str = "abstrait"

    @abstractmethod
    def generer(self, prompt: str, system: str = "") -> str:
        """Renvoie la reponse textuelle du moteur."""

    def disponible(self) -> bool:
        """Indique si le moteur est joignable. Utilise par l'interface graphique."""
        return True


# ---------------------------------------------------------------------------
# Ollama (modele local)
# ---------------------------------------------------------------------------

class ClientOllama(ClientLLM):
    """Appelle un modele servi localement par Ollama.

    `format="json"` contraint le modele a produire du JSON syntaxiquement valide,
    ce qui elimine la principale source d'echec de parsing.
    `temperature=0` rend la sortie deterministe : deux passages sur le meme
    document donnent le meme resultat, condition necessaire a un audit.
    """

    def __init__(
        self,
        modele: str = MODELE_DEFAUT,
        url: str = OLLAMA_URL_DEFAUT,
        timeout: int = 120,
    ) -> None:
        self.modele = modele
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.nom = f"ollama:{modele}"

    def disponible(self) -> bool:
        try:
            reponse = requests.get(f"{self.url}/api/tags", timeout=3)
            return reponse.status_code == 200
        except requests.RequestException:
            return False

    def modeles_installes(self) -> list[str]:
        try:
            reponse = requests.get(f"{self.url}/api/tags", timeout=5)
            reponse.raise_for_status()
            return [m["name"] for m in reponse.json().get("models", [])]
        except (requests.RequestException, KeyError, ValueError):
            return []

    def generer(self, prompt: str, system: str = "") -> str:
        charge: dict[str, object] = {
            "model": self.modele,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 800},
        }
        if system:
            charge["system"] = system

        try:
            reponse = requests.post(
                f"{self.url}/api/generate", json=charge, timeout=self.timeout
            )
            reponse.raise_for_status()
        except requests.Timeout as exc:
            raise ErreurLLM(
                f"Le modele '{self.modele}' n'a pas repondu en {self.timeout}s."
            ) from exc
        except requests.ConnectionError as exc:
            raise ErreurLLM(
                f"Ollama injoignable sur {self.url}. Verifie qu'il est demarre."
            ) from exc
        except requests.HTTPError as exc:
            detail = ""
            if exc.response is not None and exc.response.status_code == 404:
                detail = (
                    f" Le modele '{self.modele}' n'est pas installe "
                    f"(lance : ollama pull {self.modele})."
                )
            raise ErreurLLM(f"Ollama a renvoye une erreur HTTP.{detail}") from exc

        try:
            return reponse.json()["response"]
        except (ValueError, KeyError) as exc:
            raise ErreurLLM("Reponse d'Ollama inexploitable.") from exc


# ---------------------------------------------------------------------------
# Mode simule (aucun LLM requis)
# ---------------------------------------------------------------------------

class ClientSimule(ClientLLM):
    """Extrait les champs par expressions regulieres, sans aucun modele.

    Ce n'est pas un LLM et cela n'en a pas les capacites : il ne fonctionne que
    sur des documents dont la structure est previsible. Il remplit deux roles :

      1. permettre de developper et de tester tout le pipeline avant d'installer
         un modele ;
      2. servir de reference de comparaison dans le rapport de stage, pour
         montrer ce que le LLM apporte reellement face a une approche purement
         reguliere (robustesse aux formulations inattendues).
    """

    nom = "simule:regex"

    MOTIFS: dict[str, list[str]] = {
        "nom_titulaire": [
            r"(?:^|\n)[ \t]*Nom(?:[ \t]+de[ \t]+famille)?[ \t]*[:\-][ \t]*(.+)",
            r"(?:^|\n)[ \t]*Titulaire[ \t]*[:\-][ \t]*(.+)",
            r"(?:^|\n)[ \t]*Client[ \t]*[:\-][ \t]*(.+)",
        ],
        "prenom_titulaire": [
            r"(?:^|\n)[ \t]*Pr[eé]nom[ \t]*[:\-][ \t]*(.+)",
        ],
        "numero_cin": [
            r"(?:N[°o]|Num[eé]ro)[ \t]*(?:de[ \t]*)?(?:CIN|carte)?[ \t]*[:\-]?[ \t]*([A-Z]{1,2}\d{5,6})\b",
            r"\bCIN[ \t]*[:\-]?[ \t]*([A-Z]{1,2}\d{5,6})\b",
        ],
        "date_emission": [
            r"(?:Date[ \t]+d[e’']?[ \t]*[eé]mission|[EÉ]mise?[ \t]+le|Date[ \t]+de[ \t]+facture|Date[ \t]+facture|Fait[ \t]+le|Date[ \t]+d[e’']?[ \t]*[eé]tablissement)[ \t]*[:\-]?[ \t]*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        ],
        "date_validite": [
            r"(?:Valable[ \t]+jusqu[’']?au|Date[ \t]+de[ \t]+validit[eé]|Expire[ \t]+le|Valide[ \t]+jusqu[’']?au)[ \t]*[:\-]?[ \t]*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
        ],
        "emetteur": [
            r"(?:^|\n)[ \t]*(?:[EÉ]metteur|Organisme|Fournisseur)[ \t]*[:\-][ \t]*(.+)",
        ],
        "adresse": [
            r"(?:^|\n)[ \t]*Adresse(?:[ \t]+de[ \t]+facturation)?[ \t]*[:\-][ \t]*(.+)",
        ],
    }

    # Marqueurs permettant de deviner le type de document.
    MARQUEURS_CIN = [
        "carte d'identit",
        "carte nationale",
        "carte d’identit",
        "dgsn",
        "surete nationale",
        "sûreté nationale",
    ]
    MARQUEURS_DOMICILE = [
        "facture",
        "quittance",
        "attestation de residence",
        "attestation de résidence",
        "consommation",
        "abonnement",
        "lydec",
        "redal",
        "amendis",
        "onee",
    ]

    def generer(self, prompt: str, system: str = "") -> str:
        texte = self._extraire_document(prompt)
        champs: dict[str, object] = {cle: None for cle in self.MOTIFS}

        for cle, motifs in self.MOTIFS.items():
            for motif in motifs:
                trouve = re.search(motif, texte, re.IGNORECASE | re.MULTILINE)
                if trouve:
                    champs[cle] = trouve.group(1).strip()
                    break

        type_document = self._deviner_type(texte)
        champs["type_document"] = type_document

        # Un justificatif de domicile n'a pas de date de validite : on evite qu'un
        # motif attrape par erreur une echeance de paiement.
        if type_document == "JUSTIFICATIF_DOMICILE":
            champs["date_validite"] = None

        if not champs.get("emetteur"):
            champs["emetteur"] = self._deviner_emetteur(texte)

        # La confiance chute avec le nombre de champs non trouves : c'est la
        # limite honnete d'une approche purement reguliere.
        attendus = self._champs_attendus(type_document)
        manquants = sum(1 for cle in attendus if not champs.get(cle))
        champs["confiance"] = round(max(0.0, 1.0 - 0.2 * manquants), 2)

        return json.dumps(champs, ensure_ascii=False)

    @staticmethod
    def _extraire_document(prompt: str) -> str:
        """Recupere le document encadre par les separateurs '---' du prompt."""
        blocs = prompt.split("---")
        return blocs[1] if len(blocs) >= 3 else prompt

    def _deviner_type(self, texte: str) -> str:
        minuscule = texte.lower()
        if any(m in minuscule for m in self.MARQUEURS_CIN):
            return "CIN"
        if any(m in minuscule for m in self.MARQUEURS_DOMICILE):
            return "JUSTIFICATIF_DOMICILE"
        return "INCONNU"

    @staticmethod
    def _deviner_emetteur(texte: str) -> str | None:
        from .config import EMETTEURS_JUSTIFICATIF_DOMICILE, VARIANTES_EMETTEUR_CIN

        minuscule = texte.lower()
        if any(variante in minuscule for variante in VARIANTES_EMETTEUR_CIN):
            return "DGSN"
        for canonique, variantes in EMETTEURS_JUSTIFICATIF_DOMICILE.items():
            if any(v in minuscule for v in variantes):
                return canonique
        return None

    @staticmethod
    def _champs_attendus(type_document: str) -> list[str]:
        if type_document == "CIN":
            return [
                "nom_titulaire",
                "prenom_titulaire",
                "numero_cin",
                "date_validite",
                "emetteur",
            ]
        if type_document == "JUSTIFICATIF_DOMICILE":
            return ["nom_titulaire", "date_emission", "emetteur", "adresse"]
        return ["nom_titulaire"]


# ---------------------------------------------------------------------------
# Moteur en panne (tests de robustesse)
# ---------------------------------------------------------------------------

class ClientDefaillant(ClientLLM):
    """Echoue systematiquement. Sert a verifier que l'agent degrade proprement."""

    nom = "defaillant"

    def __init__(self, message: str = "Moteur indisponible (simulation de panne).") -> None:
        self.message = message

    def disponible(self) -> bool:
        return False

    def generer(self, prompt: str, system: str = "") -> str:
        raise ErreurLLM(self.message)


# ---------------------------------------------------------------------------
# Fabrique
# ---------------------------------------------------------------------------

def charger_client(moteur: str = "auto", modele: str = MODELE_DEFAUT) -> ClientLLM:
    """Instancie le moteur demande.

    moteur = "auto"       : Ollama s'il repond, sinon repli sur le mode simule
             "ollama"     : Ollama, erreur s'il est injoignable
             "simule"     : extraction par regex
             "defaillant" : moteur en panne (tests)
    """
    moteur = moteur.lower()

    if moteur == "simule":
        return ClientSimule()
    if moteur == "defaillant":
        return ClientDefaillant()
    if moteur == "ollama":
        client = ClientOllama(modele=modele)
        if not client.disponible():
            raise ErreurLLM(
                f"Ollama injoignable sur {client.url}. "
                "Demarre-le, ou utilise --moteur simule."
            )
        return client
    if moteur == "auto":
        client_ollama = ClientOllama(modele=modele)
        return client_ollama if client_ollama.disponible() else ClientSimule()

    raise ValueError(
        f"Moteur inconnu : '{moteur}'. Attendu : auto, ollama, simule, defaillant."
    )
