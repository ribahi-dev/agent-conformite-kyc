"""
Verification de l'installation sur une nouvelle machine.

A lancer en premier apres avoir copie le projet :

    python verifier_installation.py

Controle dans l'ordre : version de Python, dependances, jeu de donnees, moteur
d'extraction, pipeline complet. Chaque echec indique la commande qui le corrige.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).parent
PYTHON_MINIMAL = (3, 10)

# Nom du module a importer -> nom du paquet a installer (ils different parfois).
DEPENDANCES = {
    "pydantic": "pydantic",
    "requests": "requests",
    "dateutil": "python-dateutil",
    "streamlit": "streamlit",
    "pytest": "pytest",
}

succes: list[str] = []
echecs: list[tuple[str, str]] = []


def valider(nom: str, condition: bool, correction: str = "") -> bool:
    if condition:
        succes.append(nom)
        print(f"  OK   {nom}")
    else:
        echecs.append((nom, correction))
        print(f"  KO   {nom}")
        if correction:
            print(f"       -> {correction}")
    return condition


print("=" * 72)
print("VERIFICATION DE L'INSTALLATION")
print("=" * 72)


# ---------------------------------------------------------------------------
# 1. Version de Python
# ---------------------------------------------------------------------------

print("\n1. Version de Python")

version = sys.version_info
version_lisible = f"{version.major}.{version.minor}.{version.micro}"

# Le projet utilise la syntaxe `str | None` dans des annotations que Pydantic
# evalue a l'execution : cela impose Python 3.10 au minimum.
python_ok = valider(
    f"Python {version_lisible} (3.10 minimum requis)",
    version >= PYTHON_MINIMAL,
    "Installe Python 3.10 ou plus recent depuis python.org",
)

if not python_ok:
    print("\nInutile de poursuivre : les autres controles echoueraient tous.")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 2. Dependances
# ---------------------------------------------------------------------------

print("\n2. Dependances")

manquantes: list[str] = []
for module, paquet in DEPENDANCES.items():
    try:
        importlib.import_module(module)
        valider(paquet, True)
    except ImportError:
        manquantes.append(paquet)
        valider(paquet, False, f"python -m pip install {paquet}")

if manquantes:
    print("\n  Pour tout installer d'un coup :")
    print("    python -m pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# 3. Fichiers du projet
# ---------------------------------------------------------------------------

print("\n3. Fichiers du projet")

for chemin in ["src/regles.py", "src/agent.py", "src/config.py", "app.py", "main.py"]:
    valider(chemin, (RACINE / chemin).exists(), "Le dossier copie est incomplet")


# ---------------------------------------------------------------------------
# 4. Jeu de donnees
# ---------------------------------------------------------------------------

print("\n4. Jeu de donnees fictives")

fichier_cas = RACINE / "data" / "cas_de_test.json"
documents = list((RACINE / "data" / "documents").glob("*.txt"))

donnees_ok = valider(
    f"{len(documents)} documents dans data/documents/",
    len(documents) >= 20,
    "python generer_donnees.py",
)

if valider("data/cas_de_test.json present", fichier_cas.exists(), "python generer_donnees.py"):
    donnees = json.loads(fichier_cas.read_text(encoding="utf-8"))
    print(f"       date de reference du jeu : {donnees['date_reference']}")
    print(f"       {donnees['nombre_cas']} cas etiquetes")

    # Verifie que chaque cas declare pointe vers un fichier reellement present :
    # un document manquant faussserait silencieusement le taux de justesse.
    absents = [
        cas["fichier"]
        for cas in donnees["cas"]
        if not (RACINE / "data" / "documents" / cas["fichier"]).exists()
    ]
    valider(
        "tous les cas declares ont leur document",
        not absents,
        f"python generer_donnees.py  (manquants : {', '.join(absents[:3])})",
    )


# ---------------------------------------------------------------------------
# 5. Moteur d'extraction
# ---------------------------------------------------------------------------

print("\n5. Moteur d'extraction")

if not manquantes:
    sys.path.insert(0, str(RACINE))
    from src.llm import ClientOllama

    sonde = ClientOllama()
    if sonde.disponible():
        modeles = sonde.modeles_installes()
        valider("Ollama repond sur localhost:11434", True)
        print(f"       modeles installes : {', '.join(modeles) or 'aucun'}")
        valider(
            "au moins un modele installe",
            bool(modeles),
            "ollama pull llama3.2",
        )
    else:
        # Ce n'est pas un echec : le projet fonctionne sans Ollama.
        print("  --   Ollama non detecte")
        print("       Le mode simule (regex) sera utilise automatiquement.")
        print("       Pour installer un vrai LLM : ollama.com/download puis")
        print("       ollama pull llama3.2")


# ---------------------------------------------------------------------------
# 6. Pipeline complet
# ---------------------------------------------------------------------------

print("\n6. Pipeline complet")

if not manquantes and donnees_ok:
    from datetime import date

    from src.agent import AgentConformite
    from src.llm import ClientSimule
    from src.models import DossierClient, StatutConformite

    agent = AgentConformite(client=ClientSimule())

    document_test = RACINE / "data" / "documents" / "cin_01_conforme.txt"
    if document_test.exists():
        rapport = agent.analyser(
            document_test.read_text(encoding="utf-8"),
            DossierClient(dossier_id="D-VERIF", nom="BENALI", prenom="Youssef"),
            date_reference=date(2026, 8, 18),
        )
        valider(
            f"analyse d'une CIN conforme -> {rapport.statut.value}",
            rapport.statut is StatutConformite.VALIDE,
            "Le pipeline ne rend pas la decision attendue",
        )

    # Un document vide doit etre rejete : c'est l'exigence de securite centrale.
    rapport_vide = agent.analyser("", DossierClient(dossier_id="D", nom="X", prenom="Y"))
    valider(
        "un document vide est rejete (jamais valide)",
        rapport_vide.statut is StatutConformite.REJETE,
        "Regression grave : verifie src/agent.py",
    )


# ---------------------------------------------------------------------------
# 7. Tests
# ---------------------------------------------------------------------------

print("\n7. Suite de tests")

if "pytest" not in manquantes:
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        cwd=RACINE,
        capture_output=True,
        text=True,
    )
    derniere_ligne = [l for l in resultat.stdout.strip().splitlines() if l.strip()]
    resume = derniere_ligne[-1] if derniere_ligne else "aucune sortie"
    valider(f"pytest : {resume}", resultat.returncode == 0, "python -m pytest -q  (pour le detail)")


# ---------------------------------------------------------------------------
# Conclusion
# ---------------------------------------------------------------------------

print("\n" + "=" * 72)
if echecs:
    print(f"{len(echecs)} probleme(s) a corriger :")
    for nom, correction in echecs:
        print(f"  - {nom}")
        if correction:
            print(f"    {correction}")
    print("=" * 72)
    raise SystemExit(1)

print(f"Installation complete : {len(succes)} controles reussis.")
print("=" * 72)
print("\nProchaines etapes :")
print("  python main.py --lot                    analyse tout le jeu de donnees")
print("  python evaluer.py --moteur simule       mesure le taux de justesse")
print("  python -m streamlit run app.py          lance l'interface graphique")
