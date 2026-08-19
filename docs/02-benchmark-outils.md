# Benchmark des outils — Semaine 1

## 1. Ce qu'il fallait choisir

Trois décisions distinctes, souvent confondues :

1. **Le framework d'agent** — qui orchestre les étapes
2. **Le moteur LLM** — qui lit le document
3. **La méthode de sortie structurée** — comment obtenir des données exploitables

## 2. Frameworks d'agents

### Critères d'évaluation

| Critère | Pourquoi il compte ici |
|---|---|
| Contrôle sur le prompt | La séparation « lire / décider » exige de maîtriser exactement ce qui est envoyé |
| Déterminisme | Une décision de conformité doit être reproductible |
| Auditabilité | Chaque rejet doit être rattachable à une règle citable |
| Poids des dépendances | Un projet de stage doit être installable et compréhensible par un tiers |
| Courbe d'apprentissage | Le temps passé à apprendre le framework est pris sur le temps métier |
| Adéquation au besoin | Un seul appel LLM, pas d'orchestration multi-étapes |

### Comparaison

| Outil | Points forts | Pourquoi écarté ici |
|---|---|---|
| **LangChain** | Écosystème très large, nombreuses intégrations, abondamment documenté | Le prompt réellement envoyé est reconstruit par des couches d'abstraction. Difficile de répondre précisément à « qu'avez-vous demandé au modèle ? ». Dépendances lourdes pour un besoin d'un seul appel. |
| **LangGraph** | Excellent pour les workflows à états et les cycles | Notre pipeline est linéaire : extraction → normalisation → règles. Une machine à états pour trois étapes séquentielles ajoute un concept sans résoudre de problème. |
| **LlamaIndex** | Référence pour l'indexation et la recherche documentaire (RAG) | Conçu pour interroger un corpus. Nous analysons un document unique fourni en entrée : la brique centrale de l'outil ne sert pas. |
| **CrewAI** | Agents multiples avec rôles, délégation entre agents | Suppose plusieurs agents qui collaborent. Un seul rôle ici : lire. La délégation introduirait du non-déterminisme dans une chaîne qui doit en être exempte. |
| **Haystack** | Pipelines de traitement documentaire bien structurés | Orienté recherche et question-réponse. Même inadéquation que LlamaIndex. |
| **Pydantic AI / Instructor** | Sortie structurée validée par Pydantic, très proche du besoin | Sérieusement envisagé. Écarté au profit du contrat `ClientLLM` maison, plus explicite pédagogiquement : le mécanisme d'extraction et de validation JSON reste visible dans le code, ce qui est précisément ce qu'il faut savoir expliquer en soutenance. |
| **Agent maison** (retenu) | Contrôle total, aucune magie, 4 dépendances, lisible intégralement | Aucune fonctionnalité offerte gratuitement : tout ce qui existe a dû être écrit. |

### Décision : agent maison

**Justification.** Un framework d'agents résout des problèmes que ce projet n'a
pas : choix dynamique d'outils, mémoire conversationnelle, boucles de raisonnement,
délégation. Notre besoin est un pipeline linéaire à trois étapes dont une seule
appelle un LLM.

L'adopter aurait coûté deux fois : le temps d'apprentissage, et l'opacité. Or le
livrable doit être **expliqué en soutenance**, ligne par ligne. Un code de 1 200
lignes entièrement lisible se défend mieux qu'un code de 300 lignes dont l'essentiel
se passe dans une dépendance.

**Ce que la décision coûte.** Le repli sur un autre moteur, la journalisation, la
gestion des erreurs et le parsing JSON robuste ont dû être écrits à la main —
environ 250 lignes que LangChain aurait fournies.

**Quand la décision inverse serait la bonne.** Si le périmètre s'étendait à
plusieurs documents recoupés, à une recherche dans une base réglementaire (RAG), ou
à un enchaînement d'outils, réécrire cette orchestration à la main deviendrait une
erreur. LangGraph serait alors le bon choix.

## 3. Moteurs LLM

### Critères

Confidentialité (des pièces d'identité ne doivent pas sortir du réseau bancaire),
coût, qualité d'extraction en français, vitesse, reproductibilité.

| Moteur | Coût | Confidentialité | Qualité attendue | Remarque |
|---|---|---|---|---|
| **Ollama + llama3.2** (3 Md paramètres, ~2 Go) | Gratuit | Totale — rien ne sort de la machine | Correcte sur des documents structurés | **Retenu** : suffisant pour de l'extraction de champs |
| **Ollama + qwen2.5:7b** (~4,7 Go) | Gratuit | Totale | Meilleure sur le français et les documents peu structurés | Alternative si llama3.2 échoue sur des cas réels |
| **Ollama + mistral:7b** (~4,1 Go) | Gratuit | Totale | Bonne en français | Équivalent au précédent |
| **API Claude** | ~2-3 $ pour tout le projet | Données transmises à un tiers | Nettement supérieure | Écarté pour la confidentialité, mais le code y est prêt |
| **API OpenAI** | Similaire | Idem | Supérieure | Même raison |

### Décision : Ollama en local

**Justification.** L'argument décisif est la confidentialité. Un agent de
conformité traite des pièces d'identité ; les transmettre à une API externe est
un obstacle réglementaire réel, indépendamment du coût. Le fonctionnement local
lève cette objection avant qu'elle soit posée.

Le coût nul et l'absence de dépendance réseau sont des bénéfices secondaires.

**La contrainte assumée.** Un modèle de 3 milliards de paramètres extrait moins
fiablement qu'un modèle d'API. C'est acceptable ici parce que l'extraction est
la seule tâche confiée au LLM : les décisions, qui exigent la fiabilité, sont
prises par du code Python.

L'interface `ClientLLM` (`src/llm.py`) permet de basculer vers une API en écrivant
une classe d'une vingtaine de lignes, sans modifier le reste du projet.

### Configuration retenue

```python
{
    "format": "json",                              # sortie JSON syntaxiquement valide
    "options": {"temperature": 0, "num_predict": 800},
}
```

`temperature=0` rend la sortie déterministe — deux passages sur le même document
donnent le même résultat, condition nécessaire à un audit. `format="json"` élimine
la principale cause d'échec de parsing.

## 4. Sortie structurée

| Approche | Évaluation |
|---|---|
| Texte libre puis parsing par regex | Fragile : dépend de la formulation du modèle |
| Appel de fonction / tool calling | Efficace, mais support inégal selon les modèles locaux |
| **JSON contraint + validation Pydantic** (retenu) | `format="json"` côté Ollama, validation Pydantic côté Python |

**Décision : JSON + Pydantic**, avec un parsing volontairement tolérant
(`_extraire_json` dans `src/extraction.py`) qui gère les trois comportements
réellement observés avec des modèles locaux :

1. JSON pur — cas nominal ;
2. JSON précédé d'une phrase d'introduction ;
3. JSON entouré de balises de code Markdown.

Un compteur d'accolades isole le premier objet équilibré. Chacun de ces cas fait
l'objet d'un test dans `tests/test_extraction.py`.

Pydantic apporte en outre la conversion de types, les valeurs par défaut, et la
sérialisation JSON du rapport final — utile pour la piste d'audit.

## 5. Le moteur de repli, et ce qu'il apporte

Une quatrième option a été implémentée : `ClientSimule`, qui extrait les champs par
expressions régulières, sans aucun modèle.

Utilité première : développer et tester tout le pipeline sans dépendre d'un modèle
installé — les 115 tests s'exécutent en 0,5 seconde.

Utilité seconde, plus intéressante : il constitue la **référence de comparaison**
qui permet de chiffrer l'apport du LLM. Sur les 20 cas :

| | Statut correct | Statut + motif |
|---|---|---|
| Regex seul | 19/20 (95 %) | 18/20 (90 %) |
| Ollama | à mesurer avec `python evaluer.py --comparer` |

Les deux échecs du regex sont instructifs :

- un document qui écrit `Abonné :` au lieu de `Nom :` n'est pas lu — le regex ne
  connaît que les formulations prévues ;
- un numéro de CIN mal formé (`1234`) est déclaré *absent* plutôt que *invalide*,
  car il ne correspond à aucun motif de capture.

Ces deux cas sont exactement ce qu'un LLM traite sans effort. **C'est la
justification empirique de son emploi** : sans cette comparaison, le choix du LLM
resterait une préférence ; avec elle, c'est un résultat mesuré.

## 6. Synthèse

| Décision | Choix | Raison décisive |
|---|---|---|
| Framework | Agent maison | Le code doit être explicable intégralement en soutenance |
| Moteur LLM | Ollama local | Confidentialité des pièces d'identité |
| Modèle | llama3.2 | Suffisant pour de l'extraction ; qwen2.5:7b en repli |
| Sortie | JSON + Pydantic | Robustesse face aux sorties imparfaites des modèles locaux |
| Décision métier | Python, jamais le LLM | Reproductibilité et auditabilité |
| Dépendances | 4 (pydantic, requests, dateutil, streamlit) | Installable et lisible par un tiers |
