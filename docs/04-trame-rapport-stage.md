# Trame du rapport et préparation de la soutenance — Semaine 4

## 1. Prendre en main le projet

À lire avant toute chose si vous n'avez pas écrit ce code. Vous serez interrogé
dessus : les questions de soutenance ne portent jamais sur ce que le code fait,
mais sur **pourquoi il le fait ainsi**.

### Ordre de lecture conseillé

| Étape | Fichier | Ce qu'il faut en retenir |
|---|---|---|
| 1 | `README.md` | Le schéma du pipeline et le tableau « LLM décide / règles décident » |
| 2 | `src/config.py` | Toutes les valeurs métier sont ici, nulle part ailleurs |
| 3 | `src/regles.py` | Le cœur. Lire `controler_anciennete_justificatif` et `valider` en entier |
| 4 | `src/prompts.py` | La consigne qui interdit au modèle de juger |
| 5 | `src/agent.py` | L'enchaînement des trois étapes et le traitement des pannes |
| 6 | `tests/test_regles.py` | Chaque test énonce une règle en une phrase |

### Vérifier que tout fonctionne

```bash
python -m pip install -r requirements.txt
```

```bash
python generer_donnees.py
```

```bash
python -m pytest -q
```

```bash
python evaluer.py --moteur simule
```

```bash
python -m streamlit run app.py
```

### Les cinq phrases à savoir dire sans hésiter

1. « Le LLM lit le document, il ne décide jamais de la conformité. »
2. « La décision est prise par des règles Python, donc elle est reproductible et
   chaque rejet se rattache à une règle nommée. »
3. « Un échec technique produit un rejet, jamais une validation : en conformité,
   l'absence de preuve ne vaut pas preuve de conformité. »
4. « Les trois mois se calculent en mois calendaires, pas en 90 jours — la fenêtre
   réelle varie de 89 à 92 jours selon les mois. »
5. « Sur 20 cas, zéro faux positif : aucun document non conforme n'a été accepté. »

---

## 2. Plan du rapport

Volume indicatif : 25 à 35 pages hors annexes.

### Introduction (2 p.)

- Contexte : le KYC à l'ouverture de compte, son poids opérationnel
- Le problème : contrôle manuel, répétitif, purement factuel
- L'objectif et le périmètre en une phrase chacun
- Annonce du plan

### Chapitre 1 — Les agents IA (5-6 p.)

- Définition : percevoir, raisonner, agir
- Les six composants : perception, modèle, mémoire, outils, planification, boucle
- **La distinction essentielle** : agent autonome vs workflow déterministe
- Positionnement du projet : workflow déterministe, et pourquoi c'est le bon choix
  quand le chemin est réglementé

> Source : [03-architecture.md](03-architecture.md), sections 1 et 2.

### Chapitre 2 — Benchmark et choix techniques (5-6 p.)

- Les trois décisions : framework, moteur LLM, sortie structurée
- Tableau comparatif des frameworks avec les critères d'évaluation
- Justification de l'agent maison — et ce que ce choix coûte
- Justification d'Ollama local : la confidentialité des pièces d'identité
- Configuration `temperature=0` et `format="json"`, et pourquoi

> Source : [02-benchmark-outils.md](02-benchmark-outils.md).
> Ne pas omettre la colonne « pourquoi écarté » : un benchmark sans arbitrage
> explicite est une liste, pas un benchmark.

### Chapitre 3 — Cadrage et données (4-5 p.)

- Les cinq contrôles réglementaires
- Les trois statuts et la nécessité du troisième
- Le jeu de 20 documents, sa composition, les cas limites choisis
- **Pourquoi un générateur et non des fichiers figés**

> Source : [01-cadrage.md](01-cadrage.md).

### Chapitre 4 — Conception et réalisation (8-10 p.)

Le chapitre le plus important. Structure suggérée :

1. Le pipeline en trois étapes, avec le schéma
2. La séparation lecture / décision : le code naïf écarté, puis le code retenu
3. Les modèles de données, un par étape
4. Les règles, avec deux exemples détaillés :
   - l'ancienneté des 3 mois (le calcul calendaire)
   - la correspondance des noms (le score de similarité et sa justification)
5. Sévérité des anomalies et déduction du statut
6. La dégradation : le tableau des défaillances
7. L'interface Streamlit

### Chapitre 5 — Tests et résultats (4-5 p.)

- La stratégie : 115 tests, dates figées, moteur simulé
- Le tableau des résultats mesurés
- **L'analyse des deux échecs** — c'est ici que se joue la qualité du rapport
- La comparaison regex / LLM
- Les limites assumées

### Conclusion (2 p.)

- Ce qui a été livré, mesuré
- Ce que vous avez appris — techniquement et sur la méthode
- Les extensions identifiées : OCR, recoupement multi-documents, journalisation

### Annexes

- Extraits de code commentés : `controler_anciennete_justificatif`, `valider`
- Un rapport de conformité complet en Markdown (bouton d'export dans l'interface)
- Le prompt d'extraction intégral
- La sortie de `python evaluer.py`
- Captures d'écran de l'interface : un cas validé, un cas rejeté

---

## 3. Les figures à produire

| Figure | Où la trouver |
|---|---|
| Le pipeline en trois étapes | `README.md`, à redessiner proprement |
| Tableau « LLM décide / règles décident » | `README.md` |
| Répartition du jeu de données | `01-cadrage.md`, section 7 |
| Résultats de l'évaluation | Sortie de `python evaluer.py` |
| Interface, cas validé | Capture d'écran |
| Interface, cas rejeté avec motif | Capture d'écran |
| Trace des contrôles | Sortie de `python main.py` |

Une figure vaut mieux qu'un paragraphe pour le pipeline et pour les résultats.

---

## 4. Préparation de la soutenance

### Déroulé de la démonstration (12-15 min)

| Temps | Contenu |
|---|---|
| 0-2 min | Le problème : contrôle manuel répétitif |
| 2-4 min | L'architecture : LLM lit, règles décident. **Insister ici** |
| 4-7 min | Démo : un document conforme, puis une CIN expirée, puis un nom divergent |
| 7-9 min | Le traitement par lot et le taux de justesse |
| 9-11 min | L'onglet « Règles appliquées » : modifier un seuil et remontrer l'effet |
| 11-13 min | Résultats mesurés et limites assumées |

Deux gestes qui portent :

1. **Faire varier la date d'examen** dans l'interface pour montrer un justificatif
   qui bascule de VALIDÉ à REJETÉ. La règle des 3 mois devient visible.
2. **Débrancher Ollama** en direct et remontrer une analyse : l'agent annonce le
   repli au lieu de faire semblant.

### Questions probables, et réponses

**« Que se passe-t-il si le LLM se trompe ? »**
> Il ne peut se tromper que sur la lecture, pas sur la décision. S'il lit mal une
> date, la règle s'applique à une mauvaise donnée — c'est pourquoi le rapport
> affiche les données extraites à côté de la décision : l'analyste voit sur quoi
> l'agent s'est fondé. Et une lecture peu sûre déclenche À VÉRIFIER, pas VALIDÉ.

**« Comment garantissez-vous la reproductibilité ? »**
> `temperature=0`, et surtout la décision prise par du code Python. Deux analyses du
> même document donnent la même décision : c'est vérifié par un test dédié.

**« Pourquoi ne pas avoir utilisé LangChain ? »**
> LangChain résout des problèmes que ce projet n'a pas : choix dynamique d'outils,
> mémoire, boucles de raisonnement. Notre pipeline est linéaire à trois étapes dont
> une seule appelle un LLM. Et le livrable devait être explicable intégralement —
> un code entièrement lisible se défend mieux qu'un code court dont l'essentiel se
> passe dans une dépendance. Si le périmètre s'étendait au RAG ou au recoupement
> multi-documents, LangGraph deviendrait le bon choix.

**« Votre agent est-il vraiment un agent ? »**
> C'est un agent à workflow déterministe, pas un agent autonome — et c'est délibéré.
> Un agent autonome pourrait omettre un contrôle. Un contrôle réglementaire n'est
> pas facultatif. L'autonomie se justifie quand le chemin est inconnu ; ici il est
> réglementé, donc codé.

**« Pourquoi 3 mois, et pourquoi pas en jours ? »**
> C'est la pratique standard KYC pour un justificatif de domicile. Le calcul est
> calendaire parce que la règle l'est : selon les mois traversés, trois mois valent
> entre 89 et 92 jours. Le jeu de test contient un cas à 90 jours qui est refusé et
> un cas à 91 jours qui est accepté — un seuil en jours trancherait l'inverse.

**« Que faites-vous d'un document falsifié ? »**
> Rien, et c'est une limite assumée. L'agent vérifie la cohérence des informations,
> pas l'authenticité du document. Une fausse facture bien rédigée passe les
> contrôles. Détecter une falsification demande de l'analyse d'image et une
> vérification auprès de l'émetteur — hors périmètre.

**« Pourquoi un mode sans LLM ? Ce n'est pas contradictoire avec le sujet ? »**
> Il remplit deux rôles. Il permet de tester tout le pipeline en une demi-seconde
> sans dépendre d'un modèle installé. Et il sert de référence de comparaison : c'est
> lui qui permet de chiffrer ce que le LLM apporte réellement, au lieu de le
> supposer. Ses deux échecs — un document qui écrit « Abonné » au lieu de « Nom »,
> un numéro mal formé déclaré absent — sont exactement ce qu'un LLM traite sans
> effort.

**« Combien de temps pour traiter un dossier réel ? »**
> 1 ms en mode regex. Avec llama3.2 en local, comptez quelques secondes par
> document, à mesurer avec `python evaluer.py --comparer`. À comparer aux minutes
> d'un contrôle manuel.

**« Et la protection des données personnelles ? »**
> C'est l'argument décisif du choix d'Ollama : le document ne quitte jamais la
> machine. Aucune pièce d'identité n'est transmise à un tiers. Le code est prêt pour
> une API distante, mais ce serait un arbitrage réglementaire, pas technique.

### À éviter

- Dire « l'IA analyse le document et décide » — c'est exactement l'inverse du choix
  d'architecture, et cela invite la question qui démonte le projet.
- Présenter les 95 % sans expliquer les 5 % restants. Les deux échecs analysés
  valent mieux qu'un taux brut.
- Masquer les limites. Les énoncer soi-même montre qu'on a cadré ; les subir en
  question montre qu'on a survolé.
- Improviser sur un fichier qu'on n'a pas lu. Mieux vaut « je ne l'ai pas retenu, je
  le retrouve dans `config.py` » qu'une réponse inventée.

---

## 5. Ce qu'il reste à faire pour aller plus loin

Par ordre de rapport valeur / effort :

| Extension | Effort | Apport |
|---|---|---|
| Mesurer avec Ollama et compléter le tableau comparatif | Faible | Le résultat le plus solide du rapport |
| Journaliser chaque analyse dans un fichier JSON horodaté | Faible | Piste d'audit complète, très bien vu en conformité |
| Recouper l'adresse de la CIN avec celle du justificatif | Moyen | Contrôle de cohérence inter-documents |
| Ajouter un type de document (passeport) | Moyen | Montre que l'architecture s'étend |
| OCR en amont (Tesseract) | Élevé | Traite des scans réels |
| Statistiques de rejet par motif sur un historique | Moyen | L'indicateur qu'un service conformité demandera |
