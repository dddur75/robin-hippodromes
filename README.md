# Robin des Hippodromes — V8

Pilote de **mesure** sur le trot attelé français, 100 % automatisé
(GitHub Actions), **0 € engagé**. Le système gèle chaque matin ses
probabilités avant toute cote, verrouille les rapports à 20 minutes du
départ, tient un journal papier au rapport définitif, et rend seul son
verdict à J+90 ou 200 sélections : NO_SIGNAL, INDETERMINE ou
RESEARCH_CANDIDATE.

Ce n'est **pas** un service de pronostics. C'est un instrument qui répond à
une question : *le modèle bat-il le marché mutuel, oui ou non ?* — et qui
s'arrête tout seul si la réponse est non.

- **Installation** : voir [INSTALL.md](INSTALL.md) (3 étapes, ~10 min).
- **Règles gelées** : voir [PROTOCOLE.md](PROTOCOLE.md) (hash affiché au
  dashboard).
- **Dashboard** : GitHub Pages, dossier `/docs` — 4 tuiles, journal,
  témoin naïf.

Architecture : 5 agents (Guetteur, Greffier, Arbitre, Auditeur, Messager)
orchestrés par un unique workflow. Source : flux JSON publics turfinfo
(non officiels), usage privé non commercial, rate limiting poli, veto de
validation au premier lancement.
