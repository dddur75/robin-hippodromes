# -*- coding: utf-8 -*-
"""Auditeur — le juge du soir.

Récupère arrivées et rapports définitifs, paie les sélections papier au
dividende officiel (règle du mutuel), écrit les mesures, met à jour les
4 bases, calcule les métriques cumulées, suit le témoin naïf, applique
le critère de mort (décision D9) et reconstruit le dashboard.
"""
import json
import datetime as dt

from .config import PROTOCOLE, DOCS
from . import pmu_client as pc
from . import greffier as g
from .arbitre import p_marche_normalisee


# ------------------------------------------------------------- course close
def cloturer_course(client, date_course, race, verrou):
    """Retourne (gagnants, p_final, statuts_np, dividendes) ou None si arrivée absente."""
    detail = client.course_detail(date_course, race["r"], race["c"])
    gagnants = pc.ordre_arrivee(detail)
    if not gagnants:
        return None
    pj = client.participants(date_course, race["r"], race["c"])
    partants = pc.liste_participants(pj)
    finals, nps = {}, set()
    for p in partants:
        num = p.get("numPmu")
        if num is None:
            continue
        num = int(num)
        if (p.get("statut") or "").upper().startswith("NON_"):
            nps.add(num)
            continue
        r = pc.rapport_direct(p)
        if r:
            finals[num] = {"rapport": r, "non_partant": False}
    p_final = p_marche_normalisee(finals)
    rj = client.rapports_definitifs(date_course, race["r"], race["c"])
    dividendes = {}
    for num in gagnants:
        div = pc.dividende_gagnant(rj, num)
        if div is None and num in finals:      # repli honnête, tracé en commentaire
            div = finals[num]["rapport"]
        if div:
            dividendes[num] = div
    return {"gagnants": gagnants, "p_final": p_final,
            "rapports_finals": {n: d["rapport"] for n, d in finals.items()},
            "non_partants": nps, "dividendes": dividendes}


# ------------------------------------------------------------------ mesures
def ecrire_mesures(date_course, race, verrou, cloture):
    """Une ligne par partant (course mesurée) — la matière première du Brier."""
    p_verrou = {}
    verrouillee = 0
    if verrou and verrou.get("verrouillee"):
        p_verrou = p_marche_normalisee(verrou["rapports"])
        verrouillee = 1
    nps = cloture["non_partants"]
    # renormalisation des probas Robin sur les partants effectifs
    probs = {int(n): p.get("prob_robin") for n, p in race["partants"].items()
             if int(n) not in nps and p.get("prob_robin") is not None}
    z = sum(probs.values())
    for num_s, partant in race["partants"].items():
        num = int(num_s)
        if num in nps or num not in probs or z <= 0:
            continue
        rv = None
        if verrou:
            d = verrou["rapports"].get(str(num)) or verrou["rapports"].get(num) or {}
            rv = d.get("rapport")
        g.ajouter_mesure(date_course, {
            "race_id": race["race_id"], "date": date_course.isoformat(),
            "hippodrome": race["hippodrome"], "numero": num,
            "cheval": partant.get("nom", ""),
            "prob_robin": round(probs[num] / z, 5),
            "p_marche_verrou": round(p_verrou.get(num, 0), 5) if p_verrou else "",
            "p_marche_final": round(cloture["p_final"].get(num, 0), 5)
            if cloture["p_final"] else "",
            "resultat": 1 if num in cloture["gagnants"] else 0,
            "rapport_verrou": rv or "",
            "rapport_final": cloture["rapports_finals"].get(num, ""),
            "verrouillee": verrouillee,
        })


def payer_selection(sel, race, cloture):
    """PnL papier de la sélection, payé au dividende officiel (D7)."""
    mise = PROTOCOLE["mise_flat"]
    num = sel["numero"]
    if num in cloture["non_partants"]:
        return {"resultat": "", "rapport_definitif": "", "pnl": 0.0,
                "statut": "NON_PARTANT", "commentaire": "mise remboursée"}
    if num in cloture["gagnants"]:
        div = cloture["dividendes"].get(num)
        commentaire = ""
        if div is None:
            div = cloture["rapports_finals"].get(num, sel["rapport_verrou"])
            commentaire = "dividende officiel indisponible, payé au dernier direct"
        return {"resultat": 1, "rapport_definitif": round(div, 2),
                "pnl": round(mise * (div - 1), 2), "statut": "GAGNEE",
                "commentaire": commentaire}
    return {"resultat": 0,
            "rapport_definitif": cloture["rapports_finals"].get(num, ""),
            "pnl": -mise, "statut": "PERDUE", "commentaire": ""}


# --------------------------------------------------------------- métriques
def metriques_cumulees():
    """Relit tout le journal et recalcule les métriques (peu de lignes, exact)."""
    mesures = g.lire_toutes_mesures()
    selections = [s for s in g.lire_selections()
                  if s.get("statut") not in ("NON_PARTANT", "NO_DATA",
                                             "VERROUILLEE")]
    br_r, br_m, n_br = 0.0, 0.0, 0
    derive, n_der = 0.0, 0
    picks = {(s["race_id"], s["numero"]) for s in selections}
    temoin_pnl, temoin_mises = 0.0, 0.0
    par_course = {}
    courses_vues = set()
    for m in mesures:
        courses_vues.add(m["race_id"])
        try:
            pr = float(m["prob_robin"])
            res = int(m["resultat"])
        except (KeyError, ValueError):
            continue
        pf = m.get("p_marche_final")
        if pf not in ("", None):
            pf = float(pf)
            br_r += (pr - res) ** 2
            br_m += (pf - res) ** 2
            n_br += 1
        pv = m.get("p_marche_verrou")
        if (m["race_id"], m["numero"]) in picks and pv not in ("", None) \
                and pf not in ("", None):
            derive += (float(pf) - float(pv)) * 100.0
            n_der += 1
        if m.get("verrouillee") in (1, "1") and m.get("rapport_verrou") \
                not in ("", None):
            par_course.setdefault(m["race_id"], []).append(m)
    # témoin naïf : le favori au verrouillage, mêmes règles, payé au dernier direct
    for rid, lignes in par_course.items():
        fav = min(lignes, key=lambda l: float(l["rapport_verrou"]))
        temoin_mises += PROTOCOLE["mise_flat"]
        if int(fav["resultat"]) == 1 and fav.get("rapport_final") not in ("", None):
            temoin_pnl += PROTOCOLE["mise_flat"] * (float(fav["rapport_final"]) - 1)
        else:
            temoin_pnl -= PROTOCOLE["mise_flat"]
    pnl = sum(float(s["pnl"] or 0) for s in selections)
    mises = PROTOCOLE["mise_flat"] * len(selections)
    return {
        "n_courses_mesurees": len(courses_vues),
        "n_selections": len(selections),
        "solde": round(PROTOCOLE["bankroll_initiale"] + pnl, 1),
        "roi": round(pnl / mises, 4) if mises else 0.0,
        "delta_brier": round((br_m - br_r) / n_br, 5) if n_br else 0.0,
        "derive_pp": round(derive / n_der, 2) if n_der else 0.0,
        "temoin_roi": round(temoin_pnl / temoin_mises, 4) if temoin_mises else 0.0,
        "n_brier": n_br,
    }


# ---------------------------------------------------------- critère de mort
def appliquer_critere_de_mort(etat, metriques):
    """Décision D9 — le système porte sa propre condamnation."""
    jour = g.jour_pilote(etat)
    au_verdict = (metriques["n_selections"] >= PROTOCOLE["verdict_n_selections"]
                  or jour >= PROTOCOLE["verdict_jours"])
    if not au_verdict:
        return None
    if metriques["delta_brier"] <= PROTOCOLE["mort_delta_brier"]:
        etat["statut"], etat["verdict"] = "MORT_NO_SIGNAL", "NO_SIGNAL"
        return ("Verdict : NO_SIGNAL. Le modèle ne bat pas le marché en "
                "calibration (delta Brier <= 0). Pilote archivé. Aucune mise "
                "n'a jamais été en jeu.")
    if (metriques["roi"] <= PROTOCOLE["mort_roi"]
            and metriques["derive_pp"] < 0):
        etat["statut"], etat["verdict"] = "MORT_NO_SIGNAL", "NO_SIGNAL"
        return ("Verdict : NO_SIGNAL. ROI papier sous le seuil et dérive "
                "défavorable. Pilote archivé. Aucune mise n'a jamais été en jeu.")
    if metriques["derive_pp"] >= 0:
        etat["statut"], etat["verdict"] = "TERMINE", "RESEARCH_CANDIDATE"
        return ("Verdict : RESEARCH_CANDIDATE. Calibration meilleure que le "
                "marché et dérive favorable. La suite éventuelle est une V8.1 "
                "de recherche — pas une mise.")
    etat["statut"], etat["verdict"] = "TERMINE", "INDETERMINE"
    return ("Verdict : INDETERMINE. Signal partiel, insuffisant pour conclure. "
            "Aucune mise n'est justifiée par ce pilote.")


# --------------------------------------------------------------- dashboard
def ecrire_dashboard(etat, metriques, source_ok=True, message=""):
    selections = g.lire_selections()
    recentes = [s for s in selections if s.get("statut") != "VERROUILLEE"][-30:]
    data = {
        "maj": g.horodatage(),
        "statut": etat["statut"],
        "verdict": etat.get("verdict"),
        "jour_pilote": g.jour_pilote(etat),
        "hash_protocole": g.hash_protocole(),
        "source_ok": source_ok,
        "message": message,
        "protocole": {k: PROTOCOLE[k] for k in
                      ("version", "mode", "seuil_value", "mise_flat",
                       "max_selections_jour", "verdict_n_selections",
                       "verdict_jours")},
        **metriques,
        "selections_recentes": list(reversed(recentes)),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(DOCS / "data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data
