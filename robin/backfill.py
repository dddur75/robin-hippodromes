# -*- coding: utf-8 -*-
"""Backfill — 6 mois d'historique, en marche avant chronologique stricte.

Pour chaque journée passée : les features d'une course sont calculées avec
l'état des bases AVANT cette course, puis seulement les bases sont mises à
jour avec son résultat. Aucune fuite de futur. Le fichier walk-forward qui
en résulte sert à calibrer la température du softmax : c'est le premier
artefact E1 réel du projet (échelle de preuve V7.1).

Honnêteté actée par le conseil (annexe D11) : ce backfill ne permet AUCUN
backtest de ROI — l'historique des rapports probables d'avant-course
n'existe pas rétroactivement. Seule la calibration est testée ici.
"""
import csv
import json
import time
import hashlib
import datetime as dt

from .config import PROTOCOLE, ARTEFACTS, TEMPERATURE_DEFAUT
from . import pmu_client as pc
from . import guetteur
from .arbitre import scores_course, softmax, p_marche_normalisee
from .greffier import Bases, ajouter_ligne, horodatage

WF_PATH = ARTEFACTS / "walkforward.csv"
CHAMPS_WF = ["date", "race_id", "numero", "score", "resultat", "p_marche_final"]


def _jour(client, bases, date_course):
    """Traite une journée passée. Retourne (courses_ok, courses_no_data)."""
    gel = guetteur.matin(client, date_course)
    if gel is None:
        return 0, 0
    ok = nodata = 0
    for race in gel.values():
        detail = client.course_detail(date_course, race["r"], race["c"])
        gagnants = pc.ordre_arrivee(detail)
        pj = client.participants(date_course, race["r"], race["c"])
        partants_raw = pc.liste_participants(pj)
        if not gagnants or not partants_raw:
            nodata += 1
            continue
        nps = {int(p["numPmu"]) for p in partants_raw
               if p.get("numPmu")
               and (p.get("statut") or "").upper().startswith("NON_")}
        finals = {int(p["numPmu"]): {"rapport": pc.rapport_direct(p),
                                     "non_partant": False}
                  for p in partants_raw
                  if p.get("numPmu") and int(p["numPmu"]) not in nps
                  and pc.rapport_direct(p)}
        p_final = p_marche_normalisee(finals)
        partants = {n: p for n, p in race["partants"].items() if int(n) not in nps}
        if len(partants) < PROTOCOLE["partants_min"]:
            nodata += 1
            continue
        # features avec l'état des bases AVANT la course
        sc = scores_course(partants, bases, race["hippodrome"],
                           race.get("distance"), date_course)
        for num, s in sc.items():
            ajouter_ligne(WF_PATH, {
                "date": date_course.isoformat(), "race_id": race["race_id"],
                "numero": num, "score": round(s, 5),
                "resultat": 1 if num in gagnants else 0,
                "p_marche_final": round(p_final.get(int(num), 0), 5)
                if p_final else "",
            }, CHAMPS_WF)
        # ... puis seulement, mise à jour des bases
        bases.integrer_resultat(date_course, race["hippodrome"],
                                race.get("distance"),
                                list(partants.values()), gagnants)
        ok += 1
    bases.purger_rolling(date_course)
    return ok, nodata


def executer(client, etat, budget_minutes=240):
    """Backfill résumable. Retourne True si terminé."""
    debut_exec = time.time()
    bases = Bases()
    fin = dt.date.today() - dt.timedelta(days=1)
    depart = fin - dt.timedelta(days=PROTOCOLE["backfill_jours"])
    bf = etat["backfill"]
    if bf.get("derniere_date"):
        depart = dt.date.fromisoformat(bf["derniere_date"]) + dt.timedelta(days=1)
    date_course = depart
    total_ok = 0
    while date_course <= fin:
        ok, nodata = _jour(client, bases, date_course)
        total_ok += ok
        bf["derniere_date"] = date_course.isoformat()
        print(f"[backfill] {date_course} : {ok} courses, {nodata} NO_DATA")
        if date_course.day % 10 == 0:
            bases.sauver()
        if (time.time() - debut_exec) / 60 > budget_minutes:
            bases.sauver()
            print("[backfill] budget temps atteint — reprise au prochain run")
            return False
        date_course += dt.timedelta(days=1)
    bases.sauver()
    bf["terminee"] = True
    print(f"[backfill] terminé : {total_ok} courses intégrées au total (session)")
    return True


# ------------------------------------------------------------- calibration
def calibrer(etat):
    """Grid search de la température minimisant le Brier walk-forward.

    N'utilise que la seconde moitié chronologique du fichier (les bases y
    sont déjà étayées) pour éviter le bruit du démarrage à froid.
    """
    if not WF_PATH.exists():
        return None
    with open(WF_PATH, encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    if len(lignes) < 2000:
        print(f"[calibration] {len(lignes)} lignes — insuffisant, "
              f"température par défaut conservée")
        etat["calibration"]["temperature"] = TEMPERATURE_DEFAUT
        return None
    lignes = lignes[len(lignes) // 2:]
    courses = {}
    for l in lignes:
        try:
            courses.setdefault(l["race_id"], []).append(
                (float(l["score"]), int(l["resultat"]),
                 float(l["p_marche_final"]) if l["p_marche_final"] else None))
        except (KeyError, ValueError):
            continue

    def brier_modele(t):
        s = n = 0.0
        for runners in courses.values():
            probs = softmax([r[0] for r in runners], t)
            for p, (_, res, _) in zip(probs, runners):
                s += (p - res) ** 2
                n += 1
        return s / n if n else 9.9

    grille = [0.4 + 0.13 * i for i in range(25)]
    scores = [(brier_modele(t), t) for t in grille]
    meilleur_brier, meilleur_t = min(scores)

    s = n = 0.0
    for runners in courses.values():
        for _, res, pm in runners:
            if pm is not None:
                s += (pm - res) ** 2
                n += 1
    brier_marche = s / n if n else None

    artefact = {
        "type": "calibration_walkforward",
        "date_execution": horodatage(),
        "dataset_source": str(WF_PATH.name),
        "hash_fichier": hashlib.sha256(WF_PATH.read_bytes()).hexdigest(),
        "n_lignes": len(lignes), "n_courses": len(courses),
        "temperature_retenue": round(meilleur_t, 3),
        "brier_robin": round(meilleur_brier, 5),
        "brier_marche_final": round(brier_marche, 5) if brier_marche else None,
        "delta_brier": round(brier_marche - meilleur_brier, 5)
        if brier_marche else None,
        "limites": ("calibration descriptive sur walk-forward ; aucun backtest "
                    "de ROI possible (rapports probables historiques inexistants) ; "
                    "ne constitue ni un edge validé ni un feu vert de mise"),
    }
    chemin = ARTEFACTS / f"calibration_{dt.date.today().strftime('%Y%m%d')}.json"
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(artefact, f, ensure_ascii=False, indent=2)
    etat["calibration"] = {"temperature": round(meilleur_t, 3),
                           "artefact": chemin.name}
    print(f"[calibration] T={meilleur_t:.2f}, Brier Robin={meilleur_brier:.5f}, "
          f"Brier marché={brier_marche:.5f}" if brier_marche else "")
    return artefact
