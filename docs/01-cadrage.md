# Cadrage du projet — Semaine 1

## 1. Le besoin

À l'ouverture d'un compte bancaire, un analyste conformité vérifie manuellement
chaque pièce justificative. Le contrôle est répétitif, purement factuel, et
consomme un temps disproportionné par rapport à sa difficulté intellectuelle.

Il porte sur cinq questions, toujours les mêmes :

1. Le document est-il du type attendu ?
2. Le nom qui y figure est-il celui du dossier ?
3. Le document est-il encore valide (CIN non expirée, justificatif de moins de 3 mois) ?
4. L'organisme émetteur est-il habilité ?
5. Les données sont-elles au bon format (numéro de CIN, dates, adresse) ?

## 2. Objectif

Automatiser ces cinq contrôles et produire un rapport motivé, de sorte que
l'analyste ne traite plus que les cas signalés.

**Ce que l'agent fait :** lire un document texte, en extraire les informations,
appliquer les règles, rendre une décision motivée et traçable.

**Ce que l'agent ne fait pas :** décider seul du sort d'un dossier. Un rejet
automatique reste une proposition de rejet soumise à un analyste. C'est une
position de principe : la décision d'ouvrir ou de refuser un compte engage la
banque, pas l'outil.

## 3. Périmètre

### Dans le périmètre

| Élément | Choix |
|---|---|
| Types de documents | CIN marocaine, justificatif de domicile |
| Format d'entrée | Texte brut (`.txt`) |
| Contexte réglementaire | Maroc — émetteurs, format de CIN, villes |
| Sortie | Statut + motifs + trace des contrôles (texte, Markdown, JSON) |
| Moteur | LLM local (Ollama), avec repli sans modèle |

### Hors périmètre, et pourquoi

| Exclusion | Raison |
|---|---|
| OCR (scans, photos) | Ajoute une source d'erreur qui masquerait la qualité du raisonnement de l'agent. À traiter comme un module amont distinct. |
| Détection de falsification | Relève de l'analyse d'image et de la vérification auprès des organismes émetteurs, pas de la lecture de texte. |
| Recoupement entre plusieurs pièces | Suppose une notion de dossier multi-documents. Extension naturelle, mais qui double le périmètre. |
| Passeport, permis, acte de naissance | Chaque type ajoute ses propres règles. Mieux vaut deux types traités correctement que six approximativement. |

## 4. Les trois statuts

Un système à deux états (validé / rejeté) force une décision binaire là où
l'information est parfois insuffisante. D'où un troisième statut :

| Statut | Signification | Suite du traitement |
|---|---|---|
| **VALIDÉ** | Tous les contrôles passent | Dossier poursuit son cours |
| **REJETÉ** | Au moins une anomalie bloquante | Pièce à redemander au client |
| **À VÉRIFIER** | Uniquement des avertissements | Revue par un analyste |

Exemples d'avertissements : CIN expirant dans trois semaines, nom proche mais non
identique (translittération), adresse dont la ville n'est pas reconnue.

Sans ce troisième état, chacun de ces cas devrait être arbitrairement classé
validé (risque) ou rejeté (friction client injustifiée).

## 5. Les règles retenues

Toutes centralisées dans `src/config.py`.

### Seuils

| Paramètre | Valeur | Justification |
|---|---|---|
| Ancienneté maximale d'un justificatif | 3 mois | Pratique standard KYC |
| Alerte avant expiration d'une CIN | 30 jours | Évite d'ouvrir un compte sur une pièce bientôt caduque |
| Score minimal de correspondance du nom | 0,85 | Calibré pour accepter les variantes de translittération et refuser une personne différente |

### Point technique : « moins de 3 mois » n'est pas « moins de 90 jours »

La règle est calendaire. Selon les mois traversés, une fenêtre de 3 mois mesure
entre 89 et 92 jours. Deux cas réels du jeu de test le montrent :

- un justificatif de **90 jours** est **refusé** (émis le 31/01, examiné le 01/05) ;
- un justificatif de **91 jours** est **accepté** (émis le 01/05, examiné le 31/07).

Un seuil écrit `timedelta(days=90)` trancherait exactement l'inverse. Le calcul
utilise `relativedelta`, qui donne la lecture juridiquement correcte. C'est vérifié
par le test `test_calcul_en_mois_calendaires_et_non_en_jours`.

### Émetteurs habilités

**CIN** : DGSN exclusivement.

**Justificatif de domicile** : Lydec, Redal, Amendis, ONEE, Maroc Telecom, Orange
Maroc, Inwi.

Chaque émetteur est déclaré avec ses variantes d'écriture rencontrées sur les
documents réels — « LYDEC », « lydec », « Lyonnaise des Eaux de Casablanca »
désignent le même organisme. Sans cette canonisation, une simple variation
typographique ferait rejeter un document parfaitement valide.

### Format du numéro de CIN

`^[A-Z]{1,2}\d{5,6}$` — 1 à 2 lettres suivies de 5 à 6 chiffres. Exemples :
`BE745123`, `A234567`.

Les espaces et tirets internes sont retirés avant contrôle : `BE 745 123` et
`BE745123` désignent le même numéro.

## 6. Choix de conception structurants

### Le LLM lit, les règles décident

Détaillé dans [03-architecture.md](03-architecture.md). Résumé : demander à un LLM
si un document est conforme produit une réponse plausible mais non reproductible et
inauditable. Lui demander de lire, puis décider en Python, produit une décision
identique à chaque passage et rattachable à une règle nommée.

### La date d'examen est un paramètre, jamais `date.today()`

Toutes les fonctions de règles reçoivent une `date_reference` explicite. Trois
bénéfices :

1. les tests ne dépendent pas de la date du jour et ne se périment pas ;
2. un dossier peut être rejoué tel qu'il aurait été traité à une date passée, ce
   qu'un contrôle *a posteriori* exige ;
3. l'interface permet de faire varier la date pour démontrer la règle des 3 mois
   en direct.

### Un échec technique produit un rejet, jamais une validation

Moteur injoignable, document vide, réponse aberrante du modèle : tous ces cas
aboutissent à REJETÉ avec le motif `DOC_ILLISIBLE`. En conformité, l'absence de
preuve ne vaut pas preuve de conformité. Un test balaie six entrées dégradées et
vérifie qu'aucune ne ressort VALIDÉ.

### Tous les contrôles sont tracés, pas seulement les échecs

Le rapport liste les contrôles réussis autant que les contrôles échoués. Un
auditeur doit pouvoir vérifier qu'un contrôle a bien été exécuté, et non le déduire
de son silence.

## 7. Le jeu de données fictives

20 documents dans `data/documents/`, chacun accompagné de son résultat attendu dans
`data/cas_de_test.json`.

| Catégorie | Nombre |
|---|---|
| CIN conformes | 2 |
| CIN non conformes | 5 |
| Justificatifs conformes | 5 |
| Justificatifs non conformes | 6 |
| Cas limites et pièges | 2 |

Répartition des attendus : 6 VALIDÉ, 12 REJETÉ, 2 À VÉRIFIER.

Cas limites inclus délibérément :

- un justificatif d'exactement 3 mois et 1 jour (frontière de la règle) ;
- une CIN expirant dans 20 jours (frontière de l'avertissement) ;
- un nom en ordre inversé (prénom avant nom) ;
- une variante de translittération (Youssuf / Youssef) ;
- une facture au nom d'un tiers, cas fréquent en pratique (colocataire, propriétaire) ;
- une date d'émission dans le futur, signature d'un document falsifié ;
- un bulletin de paie, pour vérifier le rejet des types non gérés.

**Le jeu est généré, pas écrit à la main.** `generer_donnees.py` calcule toutes les
dates par rapport à une date de référence. Un justificatif « de moins de 3 mois »
figé dans un fichier cesserait d'être valide trois mois plus tard : le jeu de test
deviendrait faux sans qu'une ligne de code ait changé.

Toutes les identités, adresses et références sont inventées.

## 8. Critères de réussite

| Critère | Cible | Atteint |
|---|---|---|
| Zéro faux positif (non conforme accepté) | 0 | 0 |
| Taux de justesse sur le statut | > 90 % | 95 % |
| Chaque rejet porte un motif explicite | 100 % | 100 % |
| Décision reproductible | 100 % | vérifié par test |
| Aucune défaillance ne produit VALIDÉ | 100 % | vérifié par test |
| Couverture par tests | — | 115 tests |
