# PROTOCOLE ROBIN DES HIPPODROMES — V8.0 (GELÉ)

**Statut : gelé au lancement du pilote.** Toute modification après lancement
constitue une V8.1 : datée, justifiée, jamais rétroactive (règle R13 de V7.1,
reconduite). Le SHA-256 de ce fichier est affiché au pied du dashboard :
si le hash change, le protocole a changé.

## 1. Nature du pilote

Instrument de **mesure**, pas de pronostic. Zéro mise réelle, quel que soit
le verdict (règles R1 et R15 reconduites). L'objectif unique : établir si le
modèle Robin bat le marché mutuel — calibration (delta Brier), dérive au
verrouillage, ROI papier — et faire mieux que le témoin naïf « toujours le
favori ». Amendement du 5 juillet 2026 : Phil est retiré du projet.

## 2. Périmètre

| Paramètre | Valeur |
|---|---|
| Discipline | Trot **attelé**, courses **françaises** |
| Partants | 6 à 16 déclarés |
| Type de pari mesuré | Simple Gagnant uniquement (règle R9) |
| Collecte | toutes les courses éligibles du jour |

## 3. Modèle (décision D11 — score transparent, pas de ML en V8.0)

Features par partant, standardisées (z-score) au sein de la course :
forme musique (poids 2,2) · taux driver lissé, global + hippodrome (1,6) ·
taux entraîneur lissé (1,2) · forme entraîneur 30 j (0,8) · aptitude
distance (0,6) · déferrage (0,5) · fraîcheur (0,4) · gains carrière en
percentile intra-course (0,3). Probabilités : softmax(score / T) mélangé à
6 % d'uniforme. T est calibrée sur le walk-forward du backfill
(artefact E1 dans `data/artefacts/`). Lissage de Laplace k=20, p0=0,09.

## 4. Intégrité « probabilités avant cotes » (décision D3)

Le job du matin gèle `prob_robin` pour chaque partant **avant** tout accès
aux rapports. Nuance d'honnêteté : le flux participants contient
techniquement les cotes ; l'intégrité est donc **structurelle** — les
partants sont épurés à l'ingestion par liste blanche de champs
(`CHAMPS_AUTORISES` dans `robin/config.py`), aucun champ de rapport n'y
figure, et l'extracteur de features ne peut pas y accéder. Vérifiable dans
le code, verrouillé par le hash de ce protocole.

## 5. Verrouillage, sélection papier (décision D7 et D8)

- Snapshots des rapports e-SG toutes les 15 min pour les courses partant
  dans ≤ 45 min.
- **Verrouillage** = premier snapshot à ≤ 20 min du départ. Une seule
  granularité de slippage, pas d'exception.
- Sélection si `prob_robin × rapport_verrou ≥ 1,20`, rapport dans
  [2,0 ; 15,0], au plus 1 par course et 5 par jour, mise plate fictive de
  10 unités sur bankroll fictive de 1 000.
- **Paiement au rapport définitif officiel** (loi du mutuel). Non-partant :
  mise remboursée. Si le dividende officiel est indisponible : paiement au
  dernier rapport direct, tracé en commentaire.
- Témoin naïf : « toujours le favori au verrouillage », mêmes règles,
  payé au dernier rapport direct (approximation assumée d'un contrôle).

## 6. Métriques (hiérarchie fixe, décision D10)

1. **Delta Brier** (marché final − Robin, moyenné) : le juge scientifique.
2. **Dérive au verrouillage** (p finale − p verrou, sélections, en points
   de %) : le « CLV du turf ».
3. **ROI papier** au définitif : la conséquence, jamais le juge.
Dashboard : exactement 4 tuiles (solde, ROI, delta Brier, dérive) + journal.
Telegram : 2 messages par jour maximum, aucun ping intrajournalier.

## 7. Critère de mort (décision D9) — automatique

Au premier atteint de **N = 200 sélections** ou **J+90** :
- delta Brier ≤ 0 → verdict **NO_SIGNAL**, pilote archivé ;
- ROI ≤ −20 % **et** dérive défavorable → **NO_SIGNAL**, pilote archivé ;
- delta Brier > 0 et dérive ≥ 0 → **RESEARCH_CANDIDATE** (ouvre une V8.1
  de recherche, pas une mise) ;
- sinon → **INDETERMINE**.
Source muette 7 jours consécutifs → **SUSPENDU_SOURCE**, arrêt propre,
données conservées. Auto-audit factuel à J+30, sans conclusion.

## 8. Source de données (décision D4)

Flux JSON publics `turfinfo` (non officiels). Conditions actées : usage
strictement privé et non commercial, rate limiting ~0,8 s/requête, aucun
stockage brut, arrêt propre en cas de rupture. La validation du Jour 1
(commande `validation`) a droit de veto : sans GO, rien ne tourne.

## 9. Ce que ce pilote ne peut pas dire

- Aucun backtest de ROI n'est possible (l'historique des rapports probables
  d'avant-course n'existe pas) : le backfill ne teste que la calibration.
- Un verdict RESEARCH_CANDIDATE n'autorise **aucune mise réelle** : il
  autorise une V8.1 de recherche, avec son propre protocole.
- Le vocabulaire de tipster (« coup sûr », « méthode gagnante ») est
  proscrit dans le code, les messages et le dashboard (règle R11).
