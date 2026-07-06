# -*- coding: utf-8 -*-
"""Extraction des features d'un partant, par liste blanche stricte.

Aucun champ de rapport ou de cote n'entre ici : la règle « probabilités
avant cotes » de V7.1 (R4) est appliquée par la structure du code, pas par
la discipline humaine. C'est la décision D3 du conseil.
"""
from .config import CHAMPS_AUTORISES, LISSAGE_K, LISSAGE_P0
from .musique import score_forme


def epurer_partant(raw):
    """Ne conserve que les champs de la liste blanche (cotes exclues par construction)."""
    return {k: raw.get(k) for k in CHAMPS_AUTORISES if k in raw}


def _taux_lisse(victoires, partants, k=LISSAGE_K, p0=LISSAGE_P0):
    v = float(victoires or 0)
    n = float(partants or 0)
    return (v + k * p0) / (n + k)


def _gains_carriere(p):
    g = p.get("gainsParticipant")
    if isinstance(g, dict):
        for cle in ("gainsCarriere", "gainsAnneeEnCours", "gainsVictoires"):
            if g.get(cle) is not None:
                try:
                    return float(g[cle])
                except (TypeError, ValueError):
                    pass
    try:
        return float(g)
    except (TypeError, ValueError):
        return 0.0


def _bonus_deferre(p):
    d = (p.get("deferre") or "").upper()
    if "ANTERIEURS_POSTERIEURS" in d:
        return 1.0          # déferré des 4 pieds
    if "POSTERIEURS" in d or "ANTERIEURS" in d:
        return 0.5
    return 0.0


def _fraicheur(jours):
    if jours is None:
        return 0.5
    if 10 <= jours <= 45:
        return 1.0
    if jours < 10:
        return 0.4
    if jours <= 90:
        return 0.6
    return 0.35


def _aptitude_distance(dist_course, dist_moyenne_cheval):
    if not dist_course or not dist_moyenne_cheval:
        return 0.5
    ecart = abs(float(dist_course) - float(dist_moyenne_cheval))
    return max(0.0, 1.0 - min(1.0, ecart / 600.0))


def features_partant(p, bases, hippodrome, distance_course, date_course):
    """Vecteur de features brut d'un partant épuré. `bases` = objet Bases du greffier."""
    nom = (p.get("nom") or "").strip().upper()
    driver = (p.get("driver") or "").strip().upper()
    entraineur = (p.get("entraineur") or "").strip().upper()

    cheval = bases.cheval(nom)
    jours = None
    dist_moy = None
    if cheval:
        jours = bases.jours_depuis(cheval, date_course)
        dist_moy = cheval.get("dist_moyenne")

    d_g, d_n = bases.driver_stats(driver)
    dh_g, dh_n = bases.driver_hippo_stats(driver, hippodrome)
    e_g, e_n = bases.entraineur_stats(entraineur)
    e30_g, e30_n = bases.forme30(entraineur, date_course)

    sr_driver = _taux_lisse(d_g, d_n)
    if dh_n >= 20:  # le taux local ne compte que s'il est étayé
        sr_driver = 0.6 * sr_driver + 0.4 * _taux_lisse(dh_g, dh_n)

    return {
        "forme": score_forme(p.get("musique")),
        "driver": sr_driver,
        "entraineur": _taux_lisse(e_g, e_n),
        "forme30_ent": _taux_lisse(e30_g, e30_n, k=8),
        "deferre": _bonus_deferre(p),
        "distance": _aptitude_distance(distance_course, dist_moy),
        "fraicheur": _fraicheur(jours),
        "gains": _gains_carriere(p),   # transformé en percentile intra-course ensuite
    }
