# -*- coding: utf-8 -*-
"""Messager — deux messages par jour, jamais plus (décision D10).

Aucune sollicitation intrajournalière : David ne parie pas, aucune
notification n'exige d'action. Vocabulaire V7.1 : observation, pilote,
NO_DATA — jamais de langage de tipster (règle R11).
"""
import os
import requests


def _envoyer(texte):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[messager] secrets Telegram absents — message non envoyé :")
        print(texte)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texte, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=20)
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"[messager] échec d'envoi : {e}")
        return False


def matin(n_courses, jour):
    _envoyer(
        f"🌅 <b>Robin des Hippodromes</b> — jour {jour} du pilote\n"
        f"Probabilités gelées sur <b>{n_courses}</b> course(s) de trot, "
        f"avant toute cote.\nProchaines nouvelles ce soir. Rien à faire.")


def soir(resume, url_dashboard=""):
    m = resume["metriques"]
    roi = f"{m['roi'] * 100:+.1f}".replace(".", ",")
    delta = f"{m['delta_brier']:+.4f}".replace(".", ",")
    derive = f"{m['derive_pp']:+.2f}".replace(".", ",")
    lignes = [
        "🌙 <b>Robin des Hippodromes</b> — bilan du jour "
        f"{resume['jour']}",
        f"Courses mesurées aujourd'hui : {resume['courses_jour']}"
        + (f" · NO_DATA : {resume['no_data']}" if resume.get("no_data") else ""),
    ]
    if resume["selections_jour"]:
        lignes.append("Sélections papier :")
        for s in resume["selections_jour"]:
            issue = {"GAGNEE": "✅", "PERDUE": "✖️", "NON_PARTANT": "↩️",
                     "NO_DATA": "∅"}.get(s["statut"], "…")
            lignes.append(f"  {issue} {s['cheval']} ({s['hippodrome']}) "
                          f"@ {s['rapport_verrou']} → "
                          f"{s['pnl']:+.0f} u".replace(".", ","))
    else:
        lignes.append("Aucune sélection papier (aucune value au verrouillage).")
    lignes += [
        f"Solde fictif : <b>{m['solde']:.0f} u</b> · ROI : {roi} %",
        f"Delta Brier : {delta} · Dérive : {derive} pp "
        f"· N = {m['n_selections']}",
    ]
    if url_dashboard:
        lignes.append(url_dashboard)
    _envoyer("\n".join(lignes))


def alerte(texte):
    _envoyer(f"⚠️ <b>Robin des Hippodromes</b>\n{texte}")


def info(texte):
    _envoyer(f"ℹ️ <b>Robin des Hippodromes</b>\n{texte}")
