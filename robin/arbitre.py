# -*- coding: utf-8 -*-
"""Arbitre — le cerveau mesuré (décision D3).

Score transparent -> softmax calibré -> probabilités gelées AVANT toute cote
(le job du matin n'accède jamais aux rapports : voir features.py et guetteur.py).
La sélection value n'intervient que l'après-midi, sur le verrouillage marché.
"""
import math
import datetime as dt

from .config import POIDS, EPSILON_MELANGE, TEMPERATURE_DEFAUT, PROTOCOLE
from .features import features_partant
from .greffier import horodatage


# ------------------------------------------------------------------ maths
def _zscores(valeurs):
    n = len(valeurs)
    if n == 0:
        return []
    mu = sum(valeurs) / n
    var = sum((v - mu) ** 2 for v in valeurs) / n
    sigma = math.sqrt(var)
    if sigma < 1e-9:
        return [0.0] * n
    return [(v - mu) / sigma for v in valeurs]


def _percentiles(valeurs):
    n = len(valeurs)
    if n <= 1:
        return [0.5] * n
    ordre = sorted(range(n), key=lambda i: valeurs[i])
    pct = [0.0] * n
    for rang, i in enumerate(ordre):
        pct[i] = rang / (n - 1)
    return pct


def softmax(scores, temperature):
    t = max(float(temperature), 1e-3)
    m = max(scores)
    exps = [math.exp((s - m) / t) for s in scores]
    z = sum(exps)
    return [e / z for e in exps]


def scores_course(partants, bases, hippodrome, distance, date_course):
    """Scores pondérés par partant. `partants` = {numero: partant_épuré}."""
    nums = sorted(partants)
    feats = [features_partant(partants[n], bases, hippodrome, distance, date_course)
             for n in nums]
    # gains -> percentile intra-course (échelle-invariant)
    gains_pct = _percentiles([f["gains"] for f in feats])
    for f, g in zip(feats, gains_pct):
        f["gains"] = g
    scores = [0.0] * len(nums)
    for cle, poids in POIDS.items():
        z = _zscores([f[cle] for f in feats])
        for i, v in enumerate(z):
            scores[i] += poids * v
    return dict(zip(nums, scores))


def probas_course(partants, bases, hippodrome, distance, date_course,
                  temperature=None):
    t = temperature or TEMPERATURE_DEFAUT
    sc = scores_course(partants, bases, hippodrome, distance, date_course)
    nums = sorted(sc)
    probs = softmax([sc[n] for n in nums], t)
    n = len(nums)
    eps = EPSILON_MELANGE
    return {num: (1 - eps) * p + eps / n for num, p in zip(nums, probs)}


# --------------------------------------------------------------------- gel
def geler(gel, bases, temperature):
    """Ajoute prob_robin à chaque partant de chaque course, horodate le gel."""
    for race in gel.values():
        rid = race["race_id"]
        date_course = dt.date(int(rid[0:4]), int(rid[4:6]), int(rid[6:8]))
        probs = probas_course(race["partants"], bases, race["hippodrome"],
                              race.get("distance"), date_course, temperature)
        for num, p in probs.items():
            race["partants"][num]["prob_robin"] = round(p, 5)
        race["horodatage_gel"] = horodatage()
    return gel


# --------------------------------------------------------------- sélection
def p_marche_normalisee(rapports):
    """{numero: p} normalisée sur les partants avec rapport, NP exclus."""
    brutes = {}
    for num, d in rapports.items():
        if d.get("non_partant") or not d.get("rapport"):
            continue
        brutes[int(num)] = 1.0 / float(d["rapport"])
    z = sum(brutes.values())
    if z <= 0:
        return {}
    return {num: v / z for num, v in brutes.items()}


def decider_selection(race, verrou, nb_selections_jour):
    """Applique le filtre value sur le verrouillage. Retourne la sélection ou None.

    Règles gelées (PROTOCOLE) : value >= seuil, rapport dans la fenêtre,
    1 sélection max par course, plafond quotidien.
    """
    if nb_selections_jour >= PROTOCOLE["max_selections_jour"]:
        return None
    rapports = verrou["rapports"]
    meilleur = None
    for num_str, d in rapports.items():
        num = int(num_str)
        if d.get("non_partant") or not d.get("rapport"):
            continue
        r = float(d["rapport"])
        if not (PROTOCOLE["rapport_min"] <= r <= PROTOCOLE["rapport_max"]):
            continue
        partant = race["partants"].get(num) or race["partants"].get(str(num))
        if not partant or "prob_robin" not in partant:
            continue
        value = partant["prob_robin"] * r
        if value < PROTOCOLE["seuil_value"]:
            continue
        if meilleur is None or value > meilleur["value"]:
            meilleur = {
                "numero": num,
                "cheval": partant.get("nom", ""),
                "prob_robin": partant["prob_robin"],
                "rapport_verrou": r,
                "value": round(value, 3),
            }
    return meilleur
