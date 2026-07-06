# -*- coding: utf-8 -*-
"""Robin des Hippodromes V8.0 — configuration du protocole gelé.

Toute modification de ce fichier après le lancement du pilote constitue
une V8.1 : datée, justifiée, jamais rétroactive (règle R13).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASES = DATA / "bases"
JOURNAL = DATA / "journal"
ARTEFACTS = DATA / "artefacts"
DOCS = ROOT / "docs"
ETAT_PATH = DATA / "etat.json"

TZ = "Europe/Paris"

PROTOCOLE = {
    "version": "V8.0",
    "mode": "PILOTE_0_EURO",           # aucune mise réelle, quel que soit le verdict
    "discipline": "ATTELE",             # trot attelé uniquement
    "pays": "FRA",                      # courses françaises
    "partants_min": 6,
    "partants_max": 16,
    "seuil_value": 1.20,                # prob_robin x rapport_verrou >= 1.20
    "rapport_min": 2.0,
    "rapport_max": 15.0,
    "mise_flat": 10.0,                  # unités fictives
    "bankroll_initiale": 1000.0,        # unités fictives
    "max_selections_jour": 5,
    "fenetre_verrou_min": 20,           # verrouillage au 1er snapshot <= 20 min du départ
    "fenetre_snapshot_min": 45,         # on snapshote les courses partant dans <= 45 min
    "verdict_n_selections": 200,        # verdict au premier atteint : N sélections...
    "verdict_jours": 90,                # ...ou J+90
    "audit_intermediaire_jours": 30,    # auto-audit J+30, sans conclusion
    "mort_delta_brier": 0.0,            # delta Brier <= 0 au verdict -> NO_SIGNAL
    "mort_roi": -0.20,                  # ROI <= -20 % ET dérive défavorable -> arrêt
    "panne_jours_max": 7,               # source muette 7 jours -> SUSPENDU_SOURCE
    "backfill_jours": 180,              # profondeur d'historique pour les 4 bases
}

# Poids du score transparent (décision D11 du conseil — pas de ML en V8.0).
# Chaque feature est standardisée (z-score) au sein de la course avant pondération.
POIDS = {
    "forme": 2.2,          # musique parsée, pondérée par récence
    "driver": 1.6,         # taux de réussite lissé (global + hippodrome)
    "entraineur": 1.2,     # taux de réussite lissé
    "forme30_ent": 0.8,    # forme entraîneur 30 jours glissants
    "deferre": 0.5,        # déferrage (D4 > DA/DP > ferré)
    "distance": 0.6,       # aptitude à la distance du jour
    "fraicheur": 0.4,      # jours depuis la dernière course
    "gains": 0.3,          # gains carrière, percentile intra-course
}

EPSILON_MELANGE = 0.06     # mélange uniforme anti-surconfiance : p = (1-e)*softmax + e/n
TEMPERATURE_DEFAUT = 1.4   # remplacée par la calibration sur le backfill (artefact E1)

LISSAGE_K = 20             # lissage de Laplace des taux de réussite
LISSAGE_P0 = 0.09          # taux de victoire moyen a priori (~1 partant sur 11)

# Liste blanche des champs participants autorisés en amont du gel.
# Aucun champ de rapport/cote n'y figure : l'intégrité "probas avant cotes"
# est structurelle, pas volontaire (décision D3).
CHAMPS_AUTORISES = {
    "numPmu", "nom", "driver", "entraineur", "musique", "age", "sexe",
    "deferre", "statut", "nombreCourses", "nombreVictoires",
    "gainsParticipant", "handicapDistance", "placeCorde",
}
