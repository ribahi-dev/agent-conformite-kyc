# Agent IA d'analyse de conformité (KYC)

Agent qui lit une pièce justificative (CIN, justificatif de domicile) et rend un
rapport de conformité motivé : **VALIDÉ**, **REJETÉ** ou **À VÉRIFIER**, avec le
détail de chaque contrôle effectué.

> Projet pédagogique. Toutes les données sont fictives. Cet agent ne remplace pas
> la validation d'un analyste conformité.

---

## Le choix d'architecture central

**Le modèle de langage lit. Les règles Python décident.**

```
document texte
      │
      ▼
┌─────────────────┐   probabiliste
│  LLM : extraire │   « que dit ce document ? »
└─────────────────┘   → nom, dates, émetteur, numéro
      │
      ▼
┌─────────────────┐   déterministe
│  normalisation  │   « 18/08/2026 » → date(2026, 8, 18)
└─────────────────┘
      │
      ▼
┌─────────────────┐   déterministe
│ règles métier   │   « moins de 3 mois ? émetteur habilité ? »
└─────────────────┘
      │
      ▼
rapport : statut + motifs + trace des contrôles
```

Le LLM ne décide **jamais** de la conformité. Pourquoi c'est le bon choix pour un
sujet bancaire :

| | LLM qui décide | Règles qui décident |
|---|---|---|
| Reproductibilité | La même pièce peut être jugée différemment | Même entrée → même décision, toujours |
| Auditabilité | « le modèle a estimé que… » | « règle des 3 mois, `src/config.py:16` » |
| Modification d'un seuil | Réécrire et retester un prompt | Changer une constante |
| Défense en soutenance | Difficile | Chaque rejet se rattache à une règle nommée |

C'est la réponse à la question qui viendra en soutenance : *« comment garantissez-vous
que votre agent ne se trompe pas ? »*

---

## Installation

**Prérequis : Python 3.10 ou plus récent.** Le projet utilise la syntaxe
`str | None` dans des annotations que Pydantic évalue à l'exécution ; sur Python
3.9 ou antérieur, l'import de `src/models.py` échoue.

```bash
python -m pip install -r requirements.txt
```

Puis vérifier que tout est en place :

```bash
python verifier_installation.py
```

Ce script contrôle la version de Python, les dépendances, le jeu de données, le
moteur d'extraction, le pipeline et les tests — et indique la commande à lancer
pour chaque problème détecté.

### Installer sur une autre machine

1. **Copier le dossier** `agent-conformite-kyc/`, en excluant `__pycache__/` et
   `.pytest_cache/` (fichiers compilés, inutiles et liés à la machine d'origine).
2. Installer Python 3.10+ puis les dépendances (`pip install -r requirements.txt`).
3. **Régénérer le jeu de données** :

```bash
python generer_donnees.py
```

   Sans argument, les dates sont recalculées par rapport au jour courant. Les
   documents livrés ont été générés au 18/08/2026 : sur une machine utilisée
   plusieurs mois plus tard, les justificatifs « récents » seraient devenus
   périmés et la démonstration perdrait son sens.

   Pour reproduire exactement les résultats de ce README :

```bash
python generer_donnees.py --date 2026-08-18
```

4. Lancer `python verifier_installation.py` : tout doit être vert.

### Moteur d'extraction

Le projet fonctionne **sans aucun modèle installé** grâce à un moteur de repli par
expressions régulières (`--moteur simule`). Pour utiliser un vrai LLM en local :

1. Installer Ollama depuis [ollama.com/download](https://ollama.com/download)
2. Télécharger un modèle :

```bash
ollama pull llama3.2
```

L'agent détecte Ollama automatiquement. S'il ne répond pas, il bascule sur le mode
simulé en l'annonçant clairement — il ne fait jamais semblant.

> Modèles conseillés : `llama3.2` (2 Go, rapide) pour démarrer, `qwen2.5:7b`
> (4,7 Go) si l'extraction en français doit être plus fiable.

---

## Utilisation

### Générer le jeu de données fictives

```bash
python generer_donnees.py --date 2026-08-18
```

Écrit 20 documents dans `data/documents/` et leur résultat attendu dans
`data/cas_de_test.json`. Les dates sont calculées par rapport à la date de
référence : sans cela, un justificatif « de moins de 3 mois » cesserait d'être
valide trois mois plus tard et le jeu de test deviendrait faux tout seul.

### Analyser un document

```bash
python main.py data/documents/cin_01_conforme.txt --nom BENALI --prenom Youssef
```

```bash
python main.py data/documents/domicile_13_perime.txt --nom ALAOUI --prenom "Fatima Zahra" --format markdown
```

### Traiter tout le jeu de données

```bash
python main.py --lot
```

### Interface graphique

```bash
python -m streamlit run app.py
```

> `python -m streamlit` et non `streamlit` : sur cette machine, `streamlit.exe`
> n'est pas dans le PATH.

Trois onglets : analyse d'un document, traitement par lot avec taux de justesse,
et affichage des règles réellement appliquées (lues depuis `src/config.py`).

### Mesurer la performance

```bash
python evaluer.py --moteur simule
```

```bash
python evaluer.py --comparer
```

### Lancer les tests

```bash
python -m pytest -q
```

---

## Résultats mesurés

Sur les 20 cas de `data/cas_de_test.json`, avec le **moteur de repli par regex**
(aucun LLM) :

| Indicateur | Résultat |
|---|---|
| Statut correct | 19/20 — 95 % |
| Statut **et** motif corrects | 18/20 — 90 % |
| Faux positifs (non conforme accepté) | **0** |
| Faux négatifs (conforme rejeté) | 1 |
| Durée moyenne | 1 ms / document |
| Tests unitaires | 115 passent |

**Zéro faux positif** est l'indicateur qui compte en conformité : aucun document
non conforme n'a été accepté. Les deux erreurs vont dans le sens prudent.

### Les deux écarts, et ce qu'ils démontrent

Ils ne sont pas des bugs à corriger : ce sont les limites de l'approche par
expressions régulières, et donc la justification chiffrée de l'emploi d'un LLM.

1. **`domicile_11_onee_conforme.txt`** — le document écrit `Abonné :` au lieu de
   `Nom :`. Le regex ne trouve pas le titulaire et le document est rejeté à tort.
   Un LLM lit cette ligne sans difficulté.
2. **`cin_05_numero_invalide.txt`** — le numéro `1234` ne correspond à aucun motif
   de capture, donc le regex le déclare *absent* au lieu de *mal formé*. Bon statut
   (rejeté), mauvais motif.

Relancer `python evaluer.py --comparer` une fois Ollama installé produit le
tableau avant/après qui constitue le résultat le plus solide du rapport de stage.

---

## Structure

```
agent-conformite-kyc/
├── src/
│   ├── config.py       Seuils, émetteurs habilités, codes d'anomalie
│   ├── models.py       Modèles Pydantic des 3 étapes du pipeline
│   ├── llm.py          Ollama, moteur simulé, moteur défaillant
│   ├── prompts.py      Prompt d'extraction (jamais de jugement)
│   ├── extraction.py   Appel du LLM + normalisation des types
│   ├── regles.py       Les règles de conformité — le cœur métier
│   ├── agent.py        Orchestration des 3 étapes
│   └── rapport.py      Mise en forme texte / markdown / JSON
├── data/
│   ├── documents/      20 documents fictifs
│   └── cas_de_test.json  Résultat attendu de chaque cas
├── tests/              115 tests
├── docs/               Cadrage, benchmark, architecture, trame du rapport
├── app.py              Interface Streamlit
├── main.py             Ligne de commande
├── evaluer.py          Mesure du taux de justesse
├── generer_donnees.py  Générateur du jeu de données
└── verifier_installation.py  Contrôle de l'installation (à lancer en premier)
```

---

## Règles appliquées

Toutes définies dans `src/config.py`, modifiables sans toucher au code.

**Communs à tous les documents**
- Type reconnu (CIN ou justificatif de domicile)
- Nom correspondant au dossier client — tolère l'ordre, la casse, les accents et
  les variantes de translittération (Youssef / Youssuf) via un score de similarité
- Émetteur figurant dans la liste blanche
- Fiabilité de lecture suffisante

**CIN**
- Numéro au format national : 1 à 2 lettres + 5 à 6 chiffres
- Non expirée à la date d'examen ; avertissement si elle expire sous 30 jours
- Émise par la DGSN exclusivement

**Justificatif de domicile**
- Moins de 3 mois, calculés en **mois calendaires** et non en 90 jours fixes
  (la fenêtre réelle varie de 89 à 92 jours selon les mois traversés)
- Date d'émission non postérieure au jour d'examen
- Adresse présente, avec ville identifiable
- Émetteur parmi : Lydec, Redal, Amendis, ONEE, Maroc Telecom, Orange, Inwi

**Décision**

| Anomalies | Statut |
|---|---|
| Au moins une bloquante | REJETÉ |
| Uniquement des avertissements | À VÉRIFIER (revue humaine) |
| Aucune | VALIDÉ |

Un échec technique — moteur injoignable, document illisible — produit **REJETÉ**,
jamais VALIDÉ. En conformité, l'absence de preuve ne vaut pas preuve de conformité.
C'est vérifié par un test dédié qui balaie six entrées dégradées.

---

## Limites assumées

À énoncer soi-même en soutenance plutôt que de les subir en question :

- **Entrée texte uniquement.** Pas d'OCR : un scan ou une photo de CIN n'est pas
  traité. Ajouter Tesseract serait l'étape suivante.
- **Pas de détection de falsification.** L'agent vérifie la cohérence des
  informations, pas l'authenticité du document. Une fausse facture bien rédigée
  passe les contrôles.
- **Liste blanche d'émetteurs figée.** Un nouvel opérateur doit être ajouté à la
  main dans `src/config.py`.
- **Villes limitées aux principales villes marocaines.** Une adresse rurale lève un
  avertissement, jamais un rejet — choix délibéré pour ne pas pénaliser un client
  dont la commune n'est pas dans la liste.
- **Un document à la fois.** Le recoupement entre plusieurs pièces d'un même
  dossier (l'adresse de la CIN correspond-elle à celle de la facture ?) n'est pas
  implémenté.

---

## Documentation

| Fichier | Contenu |
|---|---|
| [docs/01-cadrage.md](docs/01-cadrage.md) | Périmètre, règles retenues, choix de conception |
| [docs/02-benchmark-outils.md](docs/02-benchmark-outils.md) | Comparaison des frameworks d'agents et justification |
| [docs/03-architecture.md](docs/03-architecture.md) | Composants d'un agent IA appliqués à ce projet |
| [docs/04-trame-rapport-stage.md](docs/04-trame-rapport-stage.md) | Plan du rapport et préparation de la soutenance |
