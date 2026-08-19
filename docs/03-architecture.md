# Architecture — composants d'un agent IA appliqués au projet

## 1. Les composants d'un agent IA

La littérature décrit un agent comme un système qui perçoit un environnement,
raisonne, et agit pour atteindre un objectif. Six composants reviennent :

| Composant | Rôle |
|---|---|
| **Perception** | Recevoir l'information de l'environnement |
| **Modèle** | Le LLM — comprendre, raisonner, formuler |
| **Mémoire** | Conserver l'information entre les étapes ou les sessions |
| **Outils** | Agir sur le monde (API, base de données, fichiers) |
| **Planification** | Décomposer un objectif en étapes |
| **Boucle de contrôle** | Enchaîner perception → décision → action jusqu'à l'objectif |

## 2. Ce que ce projet utilise réellement

Point à énoncer clairement plutôt que de laisser le jury le découvrir :

| Composant | Présent | Mise en œuvre |
|---|---|---|
| Perception | Oui | Lecture d'un document texte (`agent.analyser`) |
| Modèle | Oui | LLM local via Ollama, pour l'extraction seulement |
| Mémoire | **Non** | Chaque document est traité indépendamment — voulu |
| Outils | Partiellement | Un seul « outil » : le moteur d'extraction |
| Planification | **Non** | Les étapes sont fixées à l'avance, pas décidées par le modèle |
| Boucle de contrôle | Simplifiée | Chaîne linéaire à trois étapes, sans cycle |

**Ce projet est donc un agent à workflow déterministe, pas un agent autonome.**

### Pourquoi c'est le bon choix, et non une limitation

Un agent autonome décide lui-même de sa prochaine action. C'est puissant quand le
chemin vers l'objectif est inconnu — recherche documentaire, débogage, exploration.

Ici, le chemin est parfaitement connu : lire les champs, vérifier cinq règles,
conclure. Laisser un modèle décider de l'ordre ou de la nécessité des contrôles
introduirait la possibilité qu'un contrôle soit **omis**. Dans un contexte de
conformité bancaire, c'est inacceptable : un contrôle réglementaire n'est pas
facultatif.

La formulation à retenir pour la soutenance : *« l'autonomie n'est pas une qualité
en soi ; elle se justifie quand le chemin est inconnu. Ici il est connu et
réglementé, donc il est codé. »*

## 3. Le pipeline

```
                    ┌──────────────────────────────┐
   document.txt ───►│  1. EXTRACTION               │
                    │     src/extraction.py        │
                    │     ┌──────────────────┐     │
                    │     │  LLM (Ollama)    │     │  ← probabiliste
                    │     └──────────────────┘     │
                    │  « que dit ce document ? »   │
                    └──────────────┬───────────────┘
                                   │  ExtractionBrute
                                   │  (tout en chaînes)
                                   ▼
                    ┌──────────────────────────────┐
                    │  2. NORMALISATION            │
                    │     src/extraction.py        │  ← déterministe
                    │  « 18/08/2026 » → date(...)  │
                    │  « lydec sa »   → LYDEC      │
                    └──────────────┬───────────────┘
                                   │  DocumentNormalise
                                   │  (types Python)
                                   ▼
                    ┌──────────────────────────────┐
                    │  3. RÈGLES MÉTIER            │
                    │     src/regles.py            │  ← déterministe
                    │  « moins de 3 mois ? »       │
                    │  « émetteur habilité ? »     │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                          RapportConformite
                    statut + motifs + trace
```

Une seule étape est probabiliste. Les deux suivantes sont du code Python ordinaire,
testable et reproductible.

## 4. La séparation lecture / décision

C'est le choix structurant du projet.

### Ce qu'on ne fait pas

```python
# Approche naïve — écartée
reponse = llm.generer("Ce justificatif de domicile est-il conforme ? " + document)
# → "Oui, ce document semble conforme car la date est récente..."
```

Quatre problèmes :

1. **Non reproductible** — une reformulation du prompt change la réponse.
2. **Inauditable** — impossible de citer la règle appliquée.
3. **Non paramétrable** — passer le seuil de 3 à 6 mois exige de réécrire et
   retester un prompt.
4. **Faux plausibles** — un modèle peut affirmer qu'une date de mai est « récente »
   en août avec la même assurance que pour une date d'août.

### Ce qu'on fait

```python
# Étape 1 — le LLM lit, sans juger
brut = extraire(document, client)        # → {"date_emission": "10/01/2026", ...}

# Étape 2 — Python convertit
doc = normaliser(brut)                  # → date(2026, 1, 10)

# Étape 3 — Python décide
limite = date_examen - relativedelta(months=3)
if doc.date_emission < limite:
    anomalie("JUSTIFICATIF_PERIME", BLOQUANT)
```

Le rejet devient citable : *« règle des 3 mois, `src/regles.py`, seuil défini dans
`src/config.py` ligne 16 »*.

### Ce que le prompt interdit explicitement

`src/prompts.py` contient cette consigne système :

> Ta seule tâche est de LIRE un document et d'en extraire les informations
> demandées. Tu ne juges jamais la validité, la conformité ou la recevabilité du
> document. Tu ne complètes jamais une information absente.

La dernière phrase compte autant que les autres : un modèle à qui l'on demande une
date d'émission absente a tendance à en inventer une plausible. La consigne `null`
et la vérification côté Python (`_texte_ou_none` traite `"N/A"`, `"inconnu"`, `"-"`
comme des absences) ferment cette porte.

## 5. Les modèles de données

Un modèle par étape, ce qui rend la frontière entre probabiliste et déterministe
visible dans le code lui-même.

| Modèle | Étape | Particularité |
|---|---|---|
| `ExtractionBrute` | Sortie du LLM | Tous les champs en `str \| None`. Aucun format imposé au modèle. |
| `DocumentNormalise` | Après conversion | Types Python. Porte `erreurs_normalisation`. |
| `RapportConformite` | Décision | Statut, anomalies, trace des contrôles, horodatage. |

### Pourquoi `erreurs_normalisation` existe

Une date présente mais illisible et une date absente ne sont pas la même situation :

- absente → le document est incomplet, le client doit fournir autre chose ;
- illisible → le document existe peut-être correctement mais la lecture a échoué,
  ce qui appelle une vérification humaine.

Ces deux cas produisent des codes d'anomalie distincts. Confondre les deux revient
à masquer un défaut de l'outil derrière un défaut du client.

## 6. Les anomalies : sévérité et codes

Chaque contrôle échoué produit une `Anomalie` portant un **code stable** et une
**sévérité**.

| Sévérité | Effet | Exemple |
|---|---|---|
| `BLOQUANT` | Entraîne le rejet | CIN expirée, nom divergent |
| `AVERTISSEMENT` | Impose une revue humaine | CIN expirant sous 30 jours, nom approximatif |

Les codes (`JUSTIFICATIF_PERIME`, `CIN_EXPIREE`, `NOM_DIVERGENT`…) sont déclarés
dans `src/config.py`. Leur stabilité permet de produire des statistiques de rejet
par motif — indicateur qu'un service conformité demandera immédiatement.

La décision se déduit mécaniquement, sans autre chemin possible :

```python
if any(a.severite is BLOQUANT for a in anomalies):   statut = REJETE
elif anomalies:                                       statut = A_VERIFIER
else:                                                 statut = VALIDE
```

## 7. La trace des contrôles

Le rapport liste **tous** les contrôles exécutés, réussis comme échoués :

```
CONTROLES EFFECTUES (6/7 reussis)
  OK  Type de document - CIN
  OK  Fiabilite de l'extraction - confiance 1.00
  OK  Format des donnees
  KO  Correspondance du nom - divergence (score 0.62)
  OK  Emetteur autorise - DGSN
  OK  Numero de CIN - BE745123
  OK  Validite de la CIN - valide jusqu'au 18/08/2032
```

Un auditeur doit pouvoir vérifier qu'un contrôle a eu lieu, et non déduire son
exécution de son silence. Un test (`test_tous_les_controles_sont_traces`) vérifie
que la trace est bien produite.

## 8. La dégradation

Exigence : **aucune défaillance technique ne doit produire un VALIDÉ.**

| Défaillance | Comportement |
|---|---|
| Ollama injoignable | `REJETE` / `DOC_ILLISIBLE` avec le message d'erreur |
| Modèle absent | `REJETE`, message indiquant `ollama pull <modèle>` |
| Délai dépassé | `REJETE`, durée mentionnée |
| Réponse sans JSON | `REJETE`, début de la réponse conservé pour diagnostic |
| Document vide | `REJETE` avant tout appel au modèle |
| Exception imprévue en lot | `REJETE` pour ce document, le lot continue |

Le repli vers le mode simulé n'a lieu qu'au **choix explicite** du moteur `auto`, et
il est annoncé dans le rapport (champ `moteur_llm`) et dans l'interface. L'agent ne
fait jamais silencieusement semblant d'avoir utilisé un LLM.

Vérifié par `test_aucune_defaillance_ne_produit_valide`, qui balaie six entrées
dégradées.

## 9. La couche d'abstraction du moteur

```python
class ClientLLM(ABC):
    @abstractmethod
    def generer(self, prompt: str, system: str = "") -> str: ...
    def disponible(self) -> bool: ...
```

Trois implémentations : `ClientOllama`, `ClientSimule` (regex, sans modèle),
`ClientDefaillant` (panne simulée, pour les tests).

Bénéfices concrets :

1. les tests tournent sans modèle installé, en 0,5 seconde ;
2. la panne est testable — on ne peut pas vérifier une dégradation qu'on ne sait pas
   provoquer ;
3. passer à une API distante coûte une classe d'une vingtaine de lignes, sans
   toucher au reste ;
4. le mode regex fournit la référence de comparaison qui chiffre l'apport du LLM.

## 10. Correspondance fichier / responsabilité

| Fichier | Responsabilité | Contient des règles ? |
|---|---|---|
| `src/config.py` | Seuils, listes blanches, codes | **Oui** — les paramètres |
| `src/models.py` | Structures de données | Non |
| `src/llm.py` | Accès aux moteurs | Non |
| `src/prompts.py` | Consignes d'extraction | Non |
| `src/extraction.py` | Appel LLM + normalisation | Non |
| `src/regles.py` | Contrôles de conformité | **Oui** — la logique |
| `src/agent.py` | Orchestration, erreurs, mesure | Non |
| `src/rapport.py` | Mise en forme | Non |
| `app.py` | Interface graphique | Non |

Les règles métier vivent dans exactement deux fichiers. Toute règle qui apparaîtrait
ailleurs — notamment dans `app.py` — serait un défaut de conception : l'interface et
le traitement par lot rendraient alors des décisions différentes sur un même
document.
