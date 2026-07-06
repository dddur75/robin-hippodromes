# -*- coding: utf-8 -*-
"""Client des flux JSON publics turfinfo (non officiels — décision D4).

Conditions actées par le conseil : usage strictement privé et non commercial,
rate limiting poli, aucun stockage brut, arrêt propre si la source casse.
Le client essaie plusieurs combinaisons host/version connues de la communauté
et se fige sur la première qui répond.
"""
import json
import time
import random
import datetime as dt

import requests

BASES_CANDIDATES = [
    "https://offline.turfinfo.api.pmu.fr/rest/client/1",
    "https://online.turfinfo.api.pmu.fr/rest/client/1",
    "https://offline.turfinfo.api.pmu.fr/rest/client/61",
    "https://online.turfinfo.api.pmu.fr/rest/client/61",
]

HEADERS = {
    "User-Agent": "RobinHippodromes/8.0 (pilote de recherche prive, non commercial)",
    "Accept": "application/json",
}

PAUSE_S = 0.8  # politesse entre requêtes


class SourceIndisponible(Exception):
    pass


class PmuClient:
    def __init__(self, base_url=None, timeout=20):
        self.base = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._derniere_requete = 0.0

    # ------------------------------------------------------------------ util
    def _attendre(self):
        ecart = time.time() - self._derniere_requete
        if ecart < PAUSE_S:
            time.sleep(PAUSE_S - ecart + random.uniform(0, 0.2))
        self._derniere_requete = time.time()

    def _get(self, path):
        """GET avec 3 tentatives. Retourne le JSON ou None (404 / vide)."""
        if self.base is None and not self.choisir_base():
            raise SourceIndisponible("aucun host turfinfo ne répond")
        url = self.base + path
        for tentative in range(3):
            self._attendre()
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 404:
                    return None
                if r.status_code == 204 or not r.content:
                    return None
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, json.JSONDecodeError):
                if tentative == 2:
                    return None
                time.sleep(2 * (tentative + 1))
        return None

    def choisir_base(self):
        """Teste les hosts candidats sur le programme d'hier ; fige le premier OK."""
        hier = (dt.date.today() - dt.timedelta(days=1)).strftime("%d%m%Y")
        for base in BASES_CANDIDATES:
            try:
                self._attendre()
                r = self.session.get(f"{base}/programme/{hier}", timeout=self.timeout)
                if r.status_code == 200 and "programme" in r.text[:2000]:
                    self.base = base
                    return True
            except requests.RequestException:
                continue
        return False

    # ------------------------------------------------------------- endpoints
    @staticmethod
    def fmt_date(d):
        return d.strftime("%d%m%Y")

    def programme(self, d):
        return self._get(f"/programme/{self.fmt_date(d)}")

    def participants(self, d, r, c):
        return self._get(f"/programme/{self.fmt_date(d)}/R{r}/C{c}/participants")

    def course_detail(self, d, r, c):
        return self._get(f"/programme/{self.fmt_date(d)}/R{r}/C{c}")

    def rapports_definitifs(self, d, r, c):
        j = self._get(f"/programme/{self.fmt_date(d)}/R{r}/C{c}/rapports-definitifs")
        if j is None:
            j = self._get(
                f"/programme/{self.fmt_date(d)}/R{r}/C{c}/rapports-definitifs"
                "?specialisation=INTERNET")
        return j


# ------------------------------------------------------------ parseurs bruts
def iter_courses(programme_json):
    """Itère (reunion_dict, course_dict) sur un JSON de programme, défensivement."""
    if not programme_json:
        return
    prog = programme_json.get("programme", programme_json)
    for reunion in prog.get("reunions", []) or []:
        for course in reunion.get("courses", []) or []:
            yield reunion, course


def pays_reunion(reunion):
    p = reunion.get("pays") or {}
    return (p.get("code") or p.get("codeIso") or reunion.get("codePays") or "").upper()


def hippodrome_reunion(reunion):
    h = reunion.get("hippodrome") or {}
    return (h.get("libelleCourt") or h.get("libelleLong")
            or h.get("code") or "INCONNU").strip().upper()


def num_reunion(reunion, course):
    return course.get("numReunion") or reunion.get("numOfficiel") \
        or reunion.get("numExterne")


def num_course(course):
    return course.get("numOrdre") or course.get("numExterne") or course.get("numCourse")


def discipline_course(course):
    return (course.get("discipline") or course.get("specialite") or "").upper()


def heure_depart(course, tzinfo):
    """Datetime de départ (aware) à partir du champ heureDepart (epoch ms le plus souvent)."""
    h = course.get("heureDepart")
    if h is None:
        return None
    try:
        h = float(h)
        if h > 1e11:      # epoch millisecondes
            h /= 1000.0
        return dt.datetime.fromtimestamp(h, tz=tzinfo)
    except (TypeError, ValueError, OSError):
        return None


def ordre_arrivee(course_json):
    """Liste des numéros gagnants (>=2 si dead-heat), ou None si arrivée absente."""
    if not course_json:
        return None
    for cle in ("ordreArrivee", "arriveeDefinitive", "arrivee"):
        v = course_json.get(cle)
        if v:
            premiers = v[0] if isinstance(v[0], list) else [v[0]]
            nums = []
            for x in premiers:
                try:
                    nums.append(int(x))
                except (TypeError, ValueError):
                    pass
            return nums or None
    return None


def liste_participants(participants_json):
    if not participants_json:
        return []
    return participants_json.get("participants", []) or []


def rapport_direct(participant_raw):
    """Rapport probable / final e-SG du partant, ou None."""
    d = participant_raw.get("dernierRapportDirect") or {}
    r = d.get("rapport")
    try:
        r = float(r)
        return r if r > 1.0 else None
    except (TypeError, ValueError):
        return None


def dividende_gagnant(rapports_json, numero):
    """Dividende officiel Simple Gagnant pour 1 unité, pour `numero`. None si introuvable."""
    if not rapports_json:
        return None
    if isinstance(rapports_json, dict):
        rapports_json = (rapports_json.get("rapports")
                         or rapports_json.get("rapportsDefinitifs") or [])
    for pari in rapports_json or []:
        t = (pari.get("typePari") or pari.get("type") or "").upper()
        if "SIMPLE_GAGNANT" not in t:
            continue
        for r in pari.get("rapports", []) or []:
            combi = r.get("combinaison")
            nums = combi if isinstance(combi, list) else [combi]
            nums = [int(x) for x in nums if str(x).strip().isdigit()]
            if numero in nums:
                for cle in ("dividendePourUnEuro", "dividendeUnite",
                            "dividende", "rapport"):
                    v = r.get(cle)
                    if v is None:
                        continue
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                    # certains flux expriment le dividende en centimes
                    if cle != "rapport" and v > 200:
                        v /= 100.0
                    if v > 1.0:
                        return v
    return None
