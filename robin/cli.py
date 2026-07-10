# -*- coding: utf-8 -*-
"""CLI — point d'entrée unique de Robin des Hippodromes V8.

Commandes : validation · initialisation · matin · cotes · soir
Chaque commande est gardée par l'état du protocole : rien ne tourne
sans un GO de la validation, plus rien ne tourne après un verdict.

Correctif V8.0.1 (07/07/2026) : le job du soir est robuste aux retards
de cron GitHub (après minuit, il audite la journée de courses précédente).

Correctif V8.0.3 (10/07/2026) : le gel du matin devient immuable — si le
gel du jour existe déjà, la commande `matin` ne fait rien. On peut donc la
relancer sans risque (manuellement ou par les sessions de l'après-midi).

Correctif V8.0.2 (10/07/2026) : le job du soir devient auto-rattrapant
et idempotent. Chaque soir, il audite TOUTES les journées gelées non
encore auditées (4 jours en arrière maximum), dans l'ordre chronologique,
et pose un marqueur `audite_YYYYMMDD.json` par journée traitée. Relancer
la commande ne compte jamais deux fois la même course ni la même
sélection. Aucune règle de mesure n'est modifiée.
"""
import os
import sys
import json
import datetime as dt

import requests

from .config import PROTOCOLE
from .pmu_client import (PmuClient, SourceIndisponible, iter_courses,
                         pays_reunion, discipline_course, num_reunion,
                         num_course, liste_participants, rapport_direct,
                         ordre_arrivee)
from . import guetteur, arbitre, auditeur, backfill, messager
from . import greffier as g


# -------------------------------------------------------------- validation
def cmd_validation(silencieux=False):
    """Le veto du Jour 1 : quatre contrôles, verdict GO / NO-GO."""
    client = PmuClient()
    rapport = {"go": False, "controles": {}}
    if not client.choisir_base():
        rapport["controles"]["host"] = "AUCUN HOST NE RÉPOND"
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        return rapport
    rapport["controles"]["host"] = client.base

    hier = dt.date.today() - dt.timedelta(days=1)
    prog = client.programme(hier)
    course_test = None
    n_fr_attele = 0
    for reunion, course in iter_courses(prog):
        if pays_reunion(reunion) == "FRA" \
                and PROTOCOLE["discipline"] in discipline_course(course):
            n_fr_attele += 1
            if course_test is None:
                course_test = (num_reunion(reunion, course), num_course(course))
    rapport["controles"]["programme_hier"] = f"{n_fr_attele} courses trot FR" \
        if n_fr_attele else "AUCUNE COURSE TROT FR TROUVÉE"

    if course_test:
        r, c = int(course_test[0]), int(course_test[1])
        parts = liste_participants(client.participants(hier, r, c))
        avec_musique = sum(1 for p in parts if p.get("musique"))
        avec_rapport = sum(1 for p in parts if rapport_direct(p))
        rapport["controles"]["participants"] = (
            f"{len(parts)} partants, {avec_musique} musiques, "
            f"{avec_rapport} rapports directs")
        arrivee = ordre_arrivee(client.course_detail(hier, r, c))
        rapport["controles"]["arrivee"] = (f"gagnant(s) {arrivee}"
                                           if arrivee else "ARRIVÉE INTROUVABLE")
        rapport["participants_ok"] = len(parts) > 0 and avec_musique > 0
        rapport["arrivee_ok"] = bool(arrivee)
    else:
        rapport["participants_ok"] = rapport["arrivee_ok"] = False

    profond = dt.date.today() - dt.timedelta(days=PROTOCOLE["backfill_jours"])
    prog_ancien = client.programme(profond)
    rapport["controles"]["profondeur_historique"] = (
        f"programme de {profond} accessible" if prog_ancien
        else f"PROGRAMME DE {profond} INACCESSIBLE")

    rapport["go"] = bool(n_fr_attele and rapport.get("participants_ok")
                         and rapport.get("arrivee_ok") and prog_ancien)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    if not silencieux:
        if rapport["go"]:
            messager.info("Validation de la source : GO ✅\n"
                          + "\n".join(f"· {k} : {v}"
                                      for k, v in rapport["controles"].items()))
        else:
            messager.alerte("Validation de la source : NO-GO ❌\n"
                            + "\n".join(f"· {k} : {v}"
                                        for k, v in rapport["controles"].items())
                            + "\n\nRien n'a été construit. Le projet est "
                              "suspendu, conformément au veto du Jour 1.")
    return rapport


# ---------------------------------------------------------- initialisation
def _self_dispatch():
    """Relance le workflow d'initialisation (backfill résumable, zéro gestion)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return False
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/"
            "robin.yml/dispatches",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            json={"ref": os.environ.get("GITHUB_REF_NAME", "main"),
                  "inputs": {"action": "initialisation"}},
            timeout=20)
        return r.status_code in (201, 204)
    except requests.RequestException:
        return False


def cmd_initialisation():
    etat = g.charger_etat()
    if etat["statut"] in ("ACTIF", "MORT_NO_SIGNAL", "TERMINE"):
        print(f"[init] statut {etat['statut']} — rien à initialiser")
        return
    if etat["statut"] != "INITIALISATION":
        rapport = cmd_validation()
        if not rapport["go"]:
            etat["statut"] = "NO_GO_SOURCE"
            g.sauver_etat(etat)
            return
        etat["statut"] = "INITIALISATION"
        g.sauver_etat(etat)

    client = PmuClient()
    if not client.choisir_base():
        messager.alerte("Initialisation : source injoignable, nouvel essai "
                        "au prochain lancement.")
        return
    budget = int(os.environ.get("BACKFILL_BUDGET_MIN", "240"))
    termine = backfill.executer(client, etat, budget_minutes=budget)
    g.sauver_etat(etat)
    if not termine:
        messager.info(f"Constitution des bases en cours "
                      f"(jusqu'au {etat['backfill']['derniere_date']}). "
                      f"Reprise automatique — rien à faire.")
        _self_dispatch()
        return

    artefact = backfill.calibrer(etat)
    demain = (g.maintenant().date() + dt.timedelta(days=1))
    etat["statut"] = "ACTIF"
    etat["date_debut_pilote"] = demain.isoformat()
    g.sauver_etat(etat)
    m = auditeur.metriques_cumulees()
    auditeur.ecrire_dashboard(etat, m, message="Initialisation terminée. "
                              "Le pilote démarre demain matin.")
    lignes = ["Initialisation terminée ✅",
              "Les 4 bases (chevaux, drivers, entraîneurs, hippodromes) "
              "sont constituées."]
    if artefact:
        lignes.append(
            f"Calibration walk-forward : Brier Robin "
            f"{artefact['brier_robin']} vs marché "
            f"{artefact['brier_marche_final']} "
            f"(delta {artefact['delta_brier']}). Mesure descriptive, "
            f"pas un edge validé.")
    lignes.append(f"Le pilote {PROTOCOLE['version']} démarre demain matin, "
                  f"à 0 €, protocole gelé. Rien à faire.")
    messager.info("\n".join(lignes))


# ------------------------------------------------------------------- matin
def _gate(etat, cmd):
    if etat["statut"] != "ACTIF":
        print(f"[{cmd}] statut {etat['statut']} — aucune action")
        return False
    return True


def cmd_matin():
    etat = g.charger_etat()
    if not _gate(etat, "matin"):
        return
    aujourd_hui = g.maintenant().date()
    if g.fichier_json_jour("gel", aujourd_hui).exists():
        print("[matin] gel déjà écrit pour aujourd'hui — aucune action "
              "(les probabilités gelées sont immuables)")
        return
    client = PmuClient()
    try:
        gel = guetteur.matin(client, aujourd_hui)
    except SourceIndisponible:
        gel = None
    if gel is None:
        etat["jours_panne"] += 1
        g.sauver_etat(etat)
        if etat["jours_panne"] >= PROTOCOLE["panne_jours_max"]:
            etat["statut"] = "SUSPENDU_SOURCE"
            g.sauver_etat(etat)
            messager.alerte(f"Source muette depuis {etat['jours_panne']} jours. "
                            "Pilote SUSPENDU proprement (décision D9). "
                            "Les données acquises sont conservées.")
        else:
            messager.alerte(f"NO_DATA ce matin (panne jour "
                            f"{etat['jours_panne']}/{PROTOCOLE['panne_jours_max']}). "
                            "Nouvel essai demain, rien à faire.")
        return
    etat["jours_panne"] = 0
    temperature = etat["calibration"].get("temperature")
    gel = arbitre.geler(gel, g.Bases(), temperature)
    g.sauver_json(g.fichier_json_jour("gel", aujourd_hui), gel)
    g.sauver_etat(etat)
    messager.matin(len(gel), g.jour_pilote(etat))


# ------------------------------------------------------------------- cotes
def cmd_cotes():
    etat = g.charger_etat()
    if not _gate(etat, "cotes"):
        return
    maintenant_dt = g.maintenant()
    aujourd_hui = maintenant_dt.date()
    gel = g.charger_json(g.fichier_json_jour("gel", aujourd_hui), None)
    if not gel:
        return
    verrous = g.charger_json(g.fichier_json_jour("verrous", aujourd_hui), {})
    selections = g.charger_json(g.fichier_json_jour("selections", aujourd_hui), [])
    client = None
    changement = False
    for rid, race in gel.items():
        mn = guetteur.minutes_avant_depart(race, maintenant_dt)
        if mn is None or mn <= 0:
            continue
        deja = verrous.get(rid, {})
        if deja.get("verrouillee"):
            continue
        if mn > PROTOCOLE["fenetre_snapshot_min"]:
            continue
        if client is None:
            client = PmuClient()
            if not client.choisir_base():
                return
        snap = guetteur.snapshot_course(client, aujourd_hui, race)
        if snap is None:
            continue
        verrous[rid] = snap
        changement = True
        if mn <= PROTOCOLE["fenetre_verrou_min"]:
            snap["verrouillee"] = True
            sel = arbitre.decider_selection(race, snap, len(selections))
            if sel:
                sel.update({"race_id": rid, "hippodrome": race["hippodrome"],
                            "course": race["label"],
                            "heure_depart": race["heure_depart"],
                            "horodatage_verrou": snap["horodatage"]})
                selections.append(sel)
    if changement:
        g.sauver_json(g.fichier_json_jour("verrous", aujourd_hui), verrous)
        g.sauver_json(g.fichier_json_jour("selections", aujourd_hui), selections)


# -------------------------------------------------------------------- soir
def _marqueur_audit(date_j):
    return g.JOURNAL / f"audite_{date_j.strftime('%Y%m%d')}.json"


def _journees_a_auditer(date_cible):
    """Journées gelées, non encore auditées, jusqu'à date_cible (4 max)."""
    dates = []
    for p in sorted(g.JOURNAL.glob("gel_*.json")):
        try:
            d = dt.datetime.strptime(p.stem.split("_")[1], "%Y%m%d").date()
        except (IndexError, ValueError):
            continue
        if d <= date_cible and not _marqueur_audit(d).exists():
            dates.append(d)
    return dates[-4:]


def _auditer_journee(client, bases, date_j):
    """Audite une journée gelée : clôtures, mesures, paiements, bases.

    Retourne (courses_ok, no_data, selections_soldees).
    """
    gel = g.charger_json(g.fichier_json_jour("gel", date_j), {})
    verrous = g.charger_json(g.fichier_json_jour("verrous", date_j), {})
    selections = g.charger_json(g.fichier_json_jour("selections", date_j), [])
    courses_jour = no_data = 0
    selections_soldees = []
    clotures_ok = set()
    for rid, race in gel.items():
        cloture = auditeur.cloturer_course(client, date_j, race,
                                           verrous.get(rid))
        if cloture is None:
            no_data += 1
            continue
        clotures_ok.add(rid)
        courses_jour += 1
        auditeur.ecrire_mesures(date_j, race, verrous.get(rid), cloture)
        partants_ok = [p for n, p in race["partants"].items()
                       if int(n) not in cloture["non_partants"]]
        bases.integrer_resultat(date_j, race["hippodrome"],
                                race.get("distance"), partants_ok,
                                cloture["gagnants"])
        for sel in [s for s in selections if s["race_id"] == rid]:
            solde = auditeur.payer_selection(sel, race, cloture)
            ligne = {
                "date": date_j.isoformat(), "race_id": rid,
                "hippodrome": sel["hippodrome"], "course": sel["course"],
                "heure_depart": sel["heure_depart"], "numero": sel["numero"],
                "cheval": sel["cheval"], "prob_robin": sel["prob_robin"],
                "rapport_verrou": sel["rapport_verrou"],
                "horodatage_verrou": sel["horodatage_verrou"],
                "correction_de": "", **solde,
            }
            g.ajouter_selection(ligne)
            selections_soldees.append(ligne)
    for sel in [s for s in selections if s["race_id"] not in clotures_ok]:
        ligne = {
            "date": date_j.isoformat(), "race_id": sel["race_id"],
            "hippodrome": sel["hippodrome"], "course": sel["course"],
            "heure_depart": sel["heure_depart"], "numero": sel["numero"],
            "cheval": sel["cheval"], "prob_robin": sel["prob_robin"],
            "rapport_verrou": sel["rapport_verrou"],
            "horodatage_verrou": sel["horodatage_verrou"],
            "resultat": "", "rapport_definitif": "", "pnl": 0.0,
            "statut": "NO_DATA",
            "commentaire": "arrivée introuvable — mesure annulée",
            "correction_de": "",
        }
        g.ajouter_selection(ligne)
        selections_soldees.append(ligne)
    g.sauver_json(_marqueur_audit(date_j), {
        "horodatage": g.horodatage(), "courses": courses_jour,
        "no_data": no_data, "selections": len(selections_soldees)})
    return courses_jour, no_data, selections_soldees


def cmd_soir():
    etat = g.charger_etat()
    if not _gate(etat, "soir"):
        return
    maintenant_dt = g.maintenant()
    date_cible = maintenant_dt.date()
    # Robustesse aux retards de cron GitHub : après minuit (heure de
    # Paris), la journée de courses à auditer est celle de la veille.
    if maintenant_dt.hour < 12:
        date_cible = date_cible - dt.timedelta(days=1)

    a_auditer = _journees_a_auditer(date_cible)
    if not a_auditer:
        if _marqueur_audit(date_cible).exists():
            print(f"[soir] journée {date_cible} déjà auditée — aucune action")
            return
        a_auditer = [date_cible]   # aucun gel : bilan honnête à 0 course

    client = PmuClient()
    source_ok = client.choisir_base()
    courses_jour = no_data = 0
    selections_soldees = []
    if source_ok:
        bases = g.Bases()
        for date_j in a_auditer:
            c, nd, sold = _auditer_journee(client, bases, date_j)
            courses_jour += c
            no_data += nd
            selections_soldees.extend(sold)
        bases.purger_rolling(date_cible)
        bases.sauver()
        etat["jours_panne"] = 0
        if len(a_auditer) > 1:
            anciennes = ", ".join(d.strftime("%d/%m")
                                  for d in a_auditer[:-1])
            messager.info(f"Rattrapage automatique : journée(s) {anciennes} "
                          f"auditée(s) en plus de celle du jour "
                          f"(cron en retard, aucune donnée perdue).")
    else:
        etat["jours_panne"] += 1
        if etat["jours_panne"] >= PROTOCOLE["panne_jours_max"]:
            etat["statut"] = "SUSPENDU_SOURCE"

    if etat.get("date_debut_pilote"):
        jour = (date_cible
                - dt.date.fromisoformat(etat["date_debut_pilote"])).days + 1
    else:
        jour = 0

    metriques = auditeur.metriques_cumulees()
    etat["n_selections"] = metriques["n_selections"]

    message_verdict = auditeur.appliquer_critere_de_mort(etat, metriques)

    if (jour >= PROTOCOLE["audit_intermediaire_jours"]
            and not etat.get("audit_j30_fait") and not message_verdict):
        etat["audit_j30_fait"] = True
        messager.info(
            f"Auto-audit J+30 (constat, sans conclusion) :\n"
            f"· courses mesurées : {metriques['n_courses_mesurees']}\n"
            f"· sélections papier : {metriques['n_selections']}\n"
            f"· delta Brier : {metriques['delta_brier']:+.4f}\n"
            f"· dérive : {metriques['derive_pp']:+.2f} pp\n"
            f"Le pilote continue jusqu'au verdict (J+"
            f"{PROTOCOLE['verdict_jours']} ou N="
            f"{PROTOCOLE['verdict_n_selections']}).")

    g.sauver_etat(etat)
    auditeur.ecrire_dashboard(etat, metriques, source_ok=source_ok,
                              message=message_verdict or "")
    messager.soir({
        "jour": jour, "courses_jour": courses_jour, "no_data": no_data,
        "selections_jour": selections_soldees, "metriques": metriques,
    })
    if message_verdict:
        messager.alerte(message_verdict)


# -------------------------------------------------------------------- main
COMMANDES = {
    "validation": cmd_validation,
    "initialisation": cmd_initialisation,
    "matin": cmd_matin,
    "cotes": cmd_cotes,
    "soir": cmd_soir,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDES:
        print("usage : python -m robin.cli "
              "[validation|initialisation|matin|cotes|soir]")
        sys.exit(2)
    COMMANDES[sys.argv[1]]()


if __name__ == "__main__":
    main()
