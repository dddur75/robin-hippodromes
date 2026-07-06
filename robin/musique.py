# -*- coding: utf-8 -*-
"""Parseur de « musique » (historique de performances) pour le trot.

Exemples réels : "1a2a0a(25)Da3a", "Da5a1a1a", "0a0a(24)7a2m".
Convention de sortie, de la plus récente à la plus ancienne :
  1..9  -> place obtenue
  0     -> non placé (10e et au-delà)
  -1    -> incident : D (disqualifié), T (tombé), A (arrêté), R (rétrogradé)
"""
import re

_TOKEN = re.compile(r"(\d{1,2}|[DTAR])")

# Points de forme par place (1er fort, incident pénalisé)
_POINTS = {1: 1.0, 2: 0.75, 3: 0.60, 4: 0.45, 5: 0.35,
           6: 0.25, 7: 0.18, 8: 0.12, 9: 0.08, 0: 0.0, -1: -0.30}

# Pondération par récence (indice 0 = course la plus récente)
_RECENCE = [1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.25, 0.2]


def parser_musique(musique, n=8):
    """Retourne la liste des n dernières performances codées (récent -> ancien)."""
    if not musique:
        return []
    s = re.sub(r"\(\d+\)", " ", str(musique))  # retire les séparateurs d'année (25)
    out = []
    for m in _TOKEN.finditer(s):
        tok = m.group(1)
        if tok.isdigit():
            p = int(tok)
            out.append(p if 1 <= p <= 9 else 0)
        else:
            out.append(-1)
        if len(out) >= n:
            break
    return out


def score_forme(musique):
    """Score de forme dans [-0.3, 1.0], 0.35 par défaut si musique inconnue."""
    perfs = parser_musique(musique)
    if not perfs:
        return 0.35
    num, den = 0.0, 0.0
    for i, p in enumerate(perfs):
        w = _RECENCE[i] if i < len(_RECENCE) else 0.15
        num += w * _POINTS.get(p, 0.0)
        den += w
    return num / den if den else 0.35
