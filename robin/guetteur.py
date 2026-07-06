# -*- coding: utf-8 -*-
"""Guetteur — l'œil du système (décision D2 : le capteur est la machine).

Deux modes :
  * matin : programme + partants, cotes SUPPRIMÉES à l'ingestion (liste blanche) ;
  * cotes : snapshots des rapports probables des courses proches du départ.
"""
import datetime as dt

from .config import PROTOCOLE
from . import pmu_client as pc
from .features import epurer_partant
from .greffier import TZINFO, horodatage


def courses_eligibles(client, date_course):
    """Courses trot attelé FR du jour, avec leurs métadonnées (sans cotes)."""
    prog = client.programme(date_course)
    if prog is None:
        return None                      # source muette -> l'appelant gère la panne
    courses = []
    for reunion, course in pc.iter_courses(prog):
        if pc.pays_reunion(reunion) != PROTOCOLE["pays"]:
            continue
        if PROTOCOLE["discipline"] not in pc.discipline_course(course):
            continue
        r, c = pc.num_reunion(reunion, course), pc.num_course(course)
        if not r or not c:
            continue
        depart = pc.heure_depart(course, TZINFO)
        courses.append({
            "r": int(r), "c": int(c),
            "race_id": f"{date_course.strftime('%Y%m%d')}-R{r}C{c}",
            "hippodrome": pc.hippodrome_reunion(reunion),
            "label": (course.get("libelleCourt") or course.get("libelle") or "")[:60],
            "heure_depart": depart.isoformat() if depart else None,
            "distance": course.get("distance"),
        })
    return courses


def matin(client, date_course):
    """Construit la structure du jour : partants épurés (aucune cote conservée)."""
    courses = courses_eligibles(client, date_course)
    if courses is None:
        return None
    gel = {}
    for co in courses:
        pj = client.participants(date_course, co["r"], co["c"])
        partants = pc.liste_participants(pj)
        declares = [p for p in partants
                    if not (p.get("statut") or "").upper().startswith("NON_")]
        if not (PROTOCOLE["partants_min"] <= len(declares)
                <= PROTOCOLE["partants_max"]):
            continue
        co = dict(co)
        # Épuration IMMÉDIATE : seuls les champs de la liste blanche survivent.
        co["partants"] = {int(p["numPmu"]): epurer_partant(p)
                          for p in partants if p.get("numPmu")}
        co["horodatage_programme"] = horodatage()
        gel[co["race_id"]] = co
    return gel


def snapshot_course(client, date_course, race):
    """Rapports probables e-SG actuels de la course. {numero: rapport} ou None."""
    pj = client.participants(date_course, race["r"], race["c"])
    partants = pc.liste_participants(pj)
    if not partants:
        return None
    rapports = {}
    for p in partants:
        num = p.get("numPmu")
        r = pc.rapport_direct(p)
        statut = (p.get("statut") or "").upper()
        if num is None:
            continue
        rapports[int(num)] = {
            "rapport": r,
            "non_partant": statut.startswith("NON_"),
        }
    return {"horodatage": horodatage(), "rapports": rapports}


def minutes_avant_depart(race, maintenant_dt):
    if not race.get("heure_depart"):
        return None
    depart = dt.datetime.fromisoformat(race["heure_depart"])
    return (depart - maintenant_dt).total_seconds() / 60.0
