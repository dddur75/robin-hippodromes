# INSTALLATION — 3 étapes, ~10 minutes, puis plus rien

Tu as déjà fait tout ça pour Robin Miroir hier : c'est exactement la même
mécanique. Après l'étape 3, ton rôle est terminé — définitivement.

---

## Étape 1 — Le dépôt et les fichiers (4 min)

1. Sur github.com : **New repository** → nom `robin-hippodromes` →
   **Public** → *Create repository*.
2. **Add file → Upload files** : glisse-dépose **tout le contenu** du
   dossier dézippé (pas le dossier lui-même, son contenu). Commit.
3. **Vérification importante** : ouvre l'onglet **Actions**. Si tu vois
   « Robin des Hippodromes V8 », le dossier caché `.github` est bien passé →
   saute au point 4. Sinon (cas fréquent, les dossiers commençant par un
   point sont invisibles sur certains systèmes) :
   - **Add file → Create new file** ;
   - dans le champ du nom, tape exactement :
     `.github/workflows/robin.yml` (les `/` créent les dossiers) ;
   - ouvre le fichier `COPIE_WORKFLOW_robin.yml.txt` (à la racine du dépôt),
     copie tout son contenu, colle-le, **Commit**.

## Étape 2 — Les 2 clés Telegram (3 min)

Tu peux **réutiliser le bot de Robin Miroir** (même token, même chat id) :
les messages des deux Robin arriveront dans la même conversation, préfixés
par leur nom. Sinon, crée un bot neuf via @BotFather (commande `/newbot`).

Dans le dépôt : **Settings → Secrets and variables → Actions →
New repository secret**, deux fois :

| Nom du secret | Valeur |
|---|---|
| `TELEGRAM_TOKEN` | le token du bot |
| `TELEGRAM_CHAT_ID` | l'identifiant de ta conversation |

## Étape 3 — Le lancement (3 min)

1. **Settings → Pages** → Source : *Deploy from a branch* → Branch :
   `main`, dossier `/docs` → **Save**. (C'est ton dashboard.)
2. Onglet **Actions** → si demandé, clique *« I understand my workflows,
   enable them »* → workflow **Robin des Hippodromes V8** →
   **Run workflow** → laisse `initialisation` → **Run workflow**.

---

## Ce qui se passe ensuite (sans toi)

1. **Validation de la source** (le veto du Jour 1) : Robin teste les flux
   et t'envoie **GO ✅ ou NO-GO ❌** sur Telegram. En cas de NO-GO, rien
   n'est construit, le projet s'arrête là proprement.
2. **Constitution des bases** : 6 mois d'historique (chevaux, drivers,
   entraîneurs, hippodromes). Compte 1 à 3 h ; si c'est long, le système
   se relance tout seul. Message Telegram quand c'est fini.
3. **Le pilote démarre le lendemain matin** : gel des probabilités vers
   9 h, verrouillage des cotes l'après-midi, bilan vers 23 h 45.
   Deux messages Telegram par jour, jamais plus.
4. Dashboard : `https://TON-PSEUDO.github.io/robin-hippodromes/`
   (l'adresse exacte s'affiche dans Settings → Pages, compte ~5 min après
   le premier lancement).

## Et si quelque chose casse ?

Rien à surveiller : si la source devient muette, Robin te prévient et se
suspend tout seul au bout de 7 jours. Le verdict tombe automatiquement à
J+90 ou 200 sélections. Ton unique rôle d'ici là : lire deux messages par
jour, si tu en as envie.
