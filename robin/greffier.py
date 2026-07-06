# -*- coding: utf-8 -*-
"""Greffier — mémoire du système.

Deux natures de fichiers, deux règles :
  - le JOURNAL (sélections, mesures) est append-only : on n'écrase jamais,
    une correction crée une ligne `correction_de` (règle R8 de V7.1) ;
  - les BASES (chevaux, drivers, entraîneurs, hippodromes) sont un état
    agrégé, reconstruit depuis les résultats, réécrit à chaque mise à jour.
"""
import csv
import json
import hashlib
import datetime as dt
from zoneinfo import ZoneInfo

from .config import (BASES, JOURNAL, DATA, ETAT_PATH, TZ, PROTOCOLE, ROOT)

TZINFO = ZoneInfo(TZ)


def maintenant():
    return dt.datetime.now(TZINFO)


def horodatage():
    return maintenant().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------- état
ETAT_DEFAUT = {
    "statut": "NON_INITIALISE",   # NON_INITIALISE | INITIALISATION | ACTIF |
                                  # SUSPENDU_SOURCE | MORT_NO_SIGNAL | NO_GO_SOURCE
    "date_debut_pilote": None,
    "n_selections": 0,
    "jours_panne": 0,
    "audit_j30_fait": False,
    "backfill": {"derniere_date": None, "terminee": False},
    "calibration": {"temperature": None, "artefact": None},
    "verdict": None,
}


def charger_etat():
    if ETAT_PATH.exists():
        with open(ETAT_PATH, encoding="utf-8") as f:
            etat = json.load(f)
        for k, v in ETAT_DEFAUT.items():
            etat.setdefault(k, v)
        return etat
    return dict(ETAT_DEFAUT)


def sauver_etat(etat):
    ETAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ETAT_PATH, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=2)


def jour_pilote(etat):
    if not etat.get("date_debut_pilote"):
        return 0
    debut = dt.date.fromisoformat(etat["date_debut_pilote"])
    return (maintenant().date() - debut).days + 1


def hash_protocole():
    """SHA-256 du protocole gelé (affiché au dashboard, preuve d'immutabilité)."""
    p = ROOT / "PROTOCOLE.md"
    if not p.exists():
        return "PROTOCOLE_ABSENT"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# ---------------------------------------------------------------- fichiers
def _lire_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _ecrire_csv(path, lignes, champs):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        w.writeheader()
        for l in lignes:
            w.writerow({k: l.get(k, "") for k in champs})


def ajouter_ligne(path, ligne, champs):
    """Append-only : jamais de réécriture du journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    neuf = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        if neuf:
            w.writeheader()
        w.writerow({k: ligne.get(k, "") for k in champs})


# ------------------------------------------------------------------- bases
CHAMPS_CHEVAUX = ["nom", "nb_courses", "nb_victoires", "gains_total",
                  "somme_distances", "derniere_date"]
CHAMPS_TAUX = ["nom", "partants", "victoires"]
CHAMPS_DH = ["nom", "hippodrome", "partants", "victoires"]
CHAMPS_HIPPO = ["nom", "pays", "courses_vues"]
CHAMPS_ROLLING = ["date", "type", "nom", "victoire"]


class Bases:
    """Les 4 bases demandées (décision D5), chargées en mémoire."""

    def __init__(self):
        self.chevaux = {l["nom"]: l for l in _lire_csv(BASES / "chevaux.csv")}
        self.drivers = {l["nom"]: l for l in _lire_csv(BASES / "drivers.csv")}
        self.drivers_hippo = {(l["nom"], l["hippodrome"]): l
                              for l in _lire_csv(BASES / "drivers_hippodromes.csv")}
        self.entraineurs = {l["nom"]: l for l in _lire_csv(BASES / "entraineurs.csv")}
        self.hippodromes = {l["nom"]: l for l in _lire_csv(BASES / "hippodromes.csv")}
        self.rolling = _lire_csv(BASES / "rolling_60j.csv")

    # -- lectures --------------------------------------------------------
    def cheval(self, nom):
        c = self.chevaux.get(nom)
        if not c:
            return None
        try:
            n = float(c.get("nb_courses") or 0)
            sd = float(c.get("somme_distances") or 0)
            c = dict(c)
            c["dist_moyenne"] = (sd / n) if n else None
        except (TypeError, ValueError):
            c = dict(c)
            c["dist_moyenne"] = None
        return c

    @staticmethod
    def jours_depuis(cheval, date_course):
        d = cheval.get("derniere_date")
        if not d:
            return None
        try:
            return (date_course - dt.date.fromisoformat(d)).days
        except ValueError:
            return None

    def _stats(self, table, nom):
        l = table.get(nom)
        if not l:
            return 0, 0
        try:
            return float(l.get("victoires") or 0), float(l.get("partants") or 0)
        except (TypeError, ValueError):
            return 0, 0

    def driver_stats(self, nom):
        return self._stats(self.drivers, nom)

    def entraineur_stats(self, nom):
        return self._stats(self.entraineurs, nom)

    def driver_hippo_stats(self, nom, hippodrome):
        l = self.drivers_hippo.get((nom, hippodrome))
        if not l:
            return 0, 0
        try:
            return float(l.get("victoires") or 0), float(l.get("partants") or 0)
        except (TypeError, ValueError):
            return 0, 0

    def forme30(self, entraineur, date_course):
        """(victoires, partants) de l'entraîneur sur 30 jours glissants."""
        g = n = 0
        limite = date_course - dt.timedelta(days=30)
        for l in self.rolling:
            if l.get("type") != "entraineur" or l.get("nom") != entraineur:
                continue
            try:
                d = dt.date.fromisoformat(l["date"])
            except (KeyError, ValueError):
                continue
            if limite <= d < date_course:
                n += 1
                g += int(l.get("victoire") or 0)
        return g, n

    # -- écritures -------------------------------------------------------
    def integrer_resultat(self, date_course, hippodrome, distance,
                          partants, gagnants):
        """Met à jour les 4 bases avec le résultat d'une course.

        `partants` : liste de dicts épurés {nom, driver, entraineur, ...}
        `gagnants` : liste de numéros gagnants.
        """
        d_iso = date_course.isoformat()
        h = self.hippodromes.setdefault(
            hippodrome, {"nom": hippodrome, "pays": "FRA", "courses_vues": 0})
        h["courses_vues"] = int(float(h.get("courses_vues") or 0)) + 1

        for p in partants:
            if (p.get("statut") or "").upper().startswith("NON_"):
                continue
            num = p.get("numPmu")
            gagne = 1 if num in gagnants else 0
            nom = (p.get("nom") or "").strip().upper()
            drv = (p.get("driver") or "").strip().upper()
            ent = (p.get("entraineur") or "").strip().upper()

            if nom:
                c = self.chevaux.setdefault(nom, {
                    "nom": nom, "nb_courses": 0, "nb_victoires": 0,
                    "gains_total": 0, "somme_distances": 0, "derniere_date": ""})
                c["nb_courses"] = int(float(c.get("nb_courses") or 0)) + 1
                c["nb_victoires"] = int(float(c.get("nb_victoires") or 0)) + gagne
                c["somme_distances"] = (float(c.get("somme_distances") or 0)
                                        + float(distance or 0))
                if not c.get("derniere_date") or c["derniere_date"] < d_iso:
                    c["derniere_date"] = d_iso

            for table, cle in ((self.drivers, drv), (self.entraineurs, ent)):
                if not cle:
                    continue
                l = table.setdefault(cle, {"nom": cle, "partants": 0, "victoires": 0})
                l["partants"] = int(float(l.get("partants") or 0)) + 1
                l["victoires"] = int(float(l.get("victoires") or 0)) + gagne

            if drv:
                k = (drv, hippodrome)
                l = self.drivers_hippo.setdefault(
                    k, {"nom": drv, "hippodrome": hippodrome,
                        "partants": 0, "victoires": 0})
                l["partants"] = int(float(l.get("partants") or 0)) + 1
                l["victoires"] = int(float(l.get("victoires") or 0)) + gagne

            if ent:
                self.rolling.append({"date": d_iso, "type": "entraineur",
                                     "nom": ent, "victoire": str(gagne)})

    def purger_rolling(self, aujourd_hui):
        limite = (aujourd_hui - dt.timedelta(days=60)).isoformat()
        self.rolling = [l for l in self.rolling if (l.get("date") or "") >= limite]

    def sauver(self):
        _ecrire_csv(BASES / "chevaux.csv", self.chevaux.values(), CHAMPS_CHEVAUX)
        _ecrire_csv(BASES / "drivers.csv", self.drivers.values(), CHAMPS_TAUX)
        _ecrire_csv(BASES / "drivers_hippodromes.csv",
                    self.drivers_hippo.values(), CHAMPS_DH)
        _ecrire_csv(BASES / "entraineurs.csv", self.entraineurs.values(), CHAMPS_TAUX)
        _ecrire_csv(BASES / "hippodromes.csv", self.hippodromes.values(), CHAMPS_HIPPO)
        _ecrire_csv(BASES / "rolling_60j.csv", self.rolling, CHAMPS_ROLLING)


# ----------------------------------------------------------------- journal
CHAMPS_SELECTIONS = [
    "date", "race_id", "hippodrome", "course", "heure_depart", "numero",
    "cheval", "prob_robin", "rapport_verrou", "horodatage_verrou",
    "rapport_definitif", "resultat", "pnl", "statut", "commentaire",
    "correction_de",
]

CHAMPS_MESURES = [
    "race_id", "date", "hippodrome", "numero", "cheval", "prob_robin",
    "p_marche_verrou", "p_marche_final", "resultat", "rapport_verrou",
    "rapport_final", "verrouillee",
]


def fichier_json_jour(prefixe, date_course):
    return JOURNAL / f"{prefixe}_{date_course.strftime('%Y%m%d')}.json"


def charger_json(path, defaut):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return defaut


def sauver_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def ajouter_selection(ligne):
    ajouter_ligne(JOURNAL / "selections.csv", ligne, CHAMPS_SELECTIONS)


def ajouter_mesure(date_course, ligne):
    path = JOURNAL / f"mesures_{date_course.strftime('%Y-%m')}.csv"
    ajouter_ligne(path, ligne, CHAMPS_MESURES)


def lire_toutes_mesures():
    lignes = []
    for path in sorted(JOURNAL.glob("mesures_*.csv")):
        lignes.extend(_lire_csv(path))
    return lignes


def lire_selections():
    return _lire_csv(JOURNAL / "selections.csv")
