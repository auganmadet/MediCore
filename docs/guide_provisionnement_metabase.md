# Guide de provisionnement des utilisateurs Metabase

## Objectif

Gérer les comptes utilisateurs Metabase de manière centralisée via un fichier CSV et un script idempotent. Chaque utilisateur est associé à un service qui détermine ses droits d'accès.

---

## Prérequis

- Metabase en cours d'exécution (`http://localhost:3000`)
- Un **session token** administrateur (voir [Obtenir un token](#obtenir-un-session-token))
- Python 3.10+ (aucune dépendance externe)

---

## Fichiers concernés

  ┌──────────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Fichier                                  │ Rôle                                                     │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `config/metabase_users.csv`              │ Liste des utilisateurs à provisionner                    │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `scripts/provision_metabase_users.py`    │ Script de provisionnement (idempotent)                   │
  └──────────────────────────────────────────┴──────────────────────────────────────────────────────────┘

---

## 1. Éditer le fichier CSV

Ouvrir `config/metabase_users.csv` dans Excel ou un éditeur de texte.

### Format

```csv
email,prenom,nom,service,actif
simon.laporte@mediprix.fr,Simon,Laporte,IT,oui
lucie.ritzenthaler@mediprix.fr,Lucie,Ritzenthaler,Communication,oui
```

### Colonnes

  ┌───────────┬────────────────────────────────────────────────────────────────────────────┐
  │ Colonne   │ Description                                                                │
  ├───────────┼────────────────────────────────────────────────────────────────────────────┤
  │ email     │ Adresse email (identifiant unique du compte Metabase)                      │
  ├───────────┼────────────────────────────────────────────────────────────────────────────┤
  │ prenom    │ Prénom affiché dans Metabase                                               │
  ├───────────┼────────────────────────────────────────────────────────────────────────────┤
  │ nom       │ Nom affiché dans Metabase                                                  │
  ├───────────┼────────────────────────────────────────────────────────────────────────────┤
  │ service   │ Nom du service (crée un groupe Metabase + sous-collections)                │
  ├───────────┼────────────────────────────────────────────────────────────────────────────┤
  │ actif     │ `oui` = compte actif, `non` = compte désactivé                             │
  └───────────┴────────────────────────────────────────────────────────────────────────────┘

### Règles

- Les lignes commençant par `#` sont ignorées (commentaires)
- Les lignes vides sont ignorées
- Le champ `service` est libre : chaque valeur distincte crée un groupe et des sous-collections
- Le champ `actif` accepte : `oui`, `true`, `1`, `yes` (actif) ou toute autre valeur (inactif)

---

## 2. Obtenir un session token

Depuis l'interface Metabase : se connecter en tant qu'administrateur, puis ouvrir la console du navigateur (F12) et exécuter :

```javascript
// Le token est dans le localStorage
console.log(JSON.parse(localStorage.getItem('metabase.CURRENT_USER')))
```

Ou via l'API :

```bash
curl -X POST http://localhost:3000/api/session \
  -H "Content-Type: application/json" \
  -d '{"username":"admin@mediprix.fr","password":"votre_mot_de_passe"}'
```

Le token est dans la réponse : `{"id":"abc-123-def-456"}`.

---

## 3. Lancer le provisionnement

```bash
python scripts/provision_metabase_users.py "<session_token>"
```

### Exemple de sortie

```
============================================================
Provisionnement utilisateurs Metabase
============================================================

4 utilisateur(s) dans le CSV :
  Simon Laporte (simon.laporte@mediprix.fr) — IT [actif]
  Richard Deguilhem (richard.deguilhem@mediprix.fr) — IT [actif]
  Alexandre Hermitant (alexandre.hermitant@mediprix.fr) — IT [actif]
  Lucie Ritzenthaler (lucie.ritzenthaler@mediprix.fr) — Communication [actif]

--- Structure des collections ---
    Créé : Direction Générale/Cards/IT/
    Créé : Direction Générale/Dashboards/IT/
    Créé : Direction Générale/Cards/Communication/
    Créé : Direction Générale/Dashboards/Communication/
    ...

--- Provisionnement des comptes ---
  CRÉÉ : Simon Laporte (simon.laporte@mediprix.fr) — IT
         Mot de passe temporaire : Medicore2026!
  CRÉÉ : Richard Deguilhem (richard.deguilhem@mediprix.fr) — IT
         Mot de passe temporaire : Medicore2026!
  ...

============================================================
RÉSUMÉ
============================================================
  Créés : 4
  Services : IT, Communication
```

---

## 4. Comportement idempotent

Le script peut être relancé autant de fois que nécessaire sans effet de bord.

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Situation                           │ Comportement du script                                   │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Nouvel email dans le CSV            │ Crée le compte + groupe + collections + permissions      │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Email déjà existant dans Metabase   │ Aucune action (affiche "EXISTE")                         │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `actif=non` sur un compte existant  │ Désactive le compte (l'utilisateur ne peut plus se       │
  │                                     │ connecter mais ses cartes/dashboards sont conservés)     │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `actif=oui` sur un compte désactivé │ Réactive le compte                                       │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Nouveau service dans le CSV         │ Crée le groupe + les sous-collections dans chaque        │
  │                                     │ Cards/ et Dashboards/                                    │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Service déjà existant               │ Réutilise le groupe et les collections existantes        │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Cartes/dashboards orphelins         │ Déplacés automatiquement dans Admin/                     │
  └─────────────────────────────────────┴──────────────────────────────────────────────────────────┘

---

## 5. Gouvernance des collections

### Structure résultante

```
MediCore BI/                              view pour tous
├── Achats & Stock/                       view pour tous
│   ├── Cards/                            view pour tous
│   │   ├── Admin/                        view — cartes administrateur (protégées)
│   │   ├── IT/                           curate pour le groupe IT
│   │   └── Communication/                curate pour le groupe Communication
│   └── Dashboards/                       view pour tous
│       ├── Admin/                        view — dashboards administrateur (protégés)
│       ├── IT/                           curate pour le groupe IT
│       └── Communication/                curate pour le groupe Communication
├── Direction Générale/
│   └── ... (même structure)
├── Ventes & Performance/
│   └── ... (même structure)
├── Qualité & Pilotage/
│   └── ... (même structure)
└── Détail opérationnel/
    └── ... (même structure)
```

### Droits par service

  ┌──────────────────────────────────────┬─────────┬─────────────────────────────────────────────┐
  │ Ressource                            │ Droit   │ Détail                                      │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Dashboards/cartes Admin              │ view    │ Voir, filtrer, exporter                     │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Dashboards/cartes d'autres services  │ view    │ Voir, filtrer, exporter                     │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Cards/<Mon service>/                 │ curate  │ Créer, modifier, supprimer ses cartes       │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Dashboards/<Mon service>/            │ curate  │ Créer, modifier, supprimer ses dashboards   │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Données Snowflake (MARTS)            │ lecture │ Toutes les tables, query-builder uniquement │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ SQL natif                            │ bloqué  │ Sécurité : pas d'accès SQL direct           │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Administration Metabase              │ bloqué  │ Réservé à l'administrateur                  │
  └──────────────────────────────────────┴─────────┴─────────────────────────────────────────────┘

---

## 6. Cas d'usage courants

### Ajouter un nouvel utilisateur

1. Ajouter une ligne dans `config/metabase_users.csv`
2. Lancer `python scripts/provision_metabase_users.py "<token>"`
3. Communiquer à l'utilisateur les informations de connexion (voir §7)

### Désactiver un utilisateur (départ, changement de poste)

1. Mettre `actif` à `non` dans le CSV (ne pas supprimer la ligne pour la traçabilité)
2. Relancer le script

### Ajouter un nouveau service

1. Ajouter un utilisateur avec un nouveau nom de service dans le CSV
2. Relancer le script — les sous-collections sont créées automatiquement

### Changer un utilisateur de service

1. Désactiver l'ancien compte (`actif=non`)
2. Créer une nouvelle ligne avec le nouveau service (`actif=oui`)
3. Relancer le script
4. L'utilisateur conserve son historique dans l'ancien service (lecture seule)

---

## 7. Connexion utilisateur

### URL d'accès

Metabase est accessible sur le réseau local à l'adresse :

**`http://192.168.0.37:3000`**

> Cette URL est valable pour tous les postes connectés au même réseau local.
> Si l'IP du serveur change, mettre à jour cette documentation.
> Le port 3000 est exposé sur toutes les interfaces (`0.0.0.0`) dans `docker-compose.yml`.

### Première connexion — avec SMTP (recommandé)

Si le SMTP est configuré dans `docker-compose.yml`, l'utilisateur reçoit **automatiquement** un email d'invitation de Metabase à la création de son compte :

1. L'utilisateur reçoit un email de `MediCore BI <metabase@mediprix.fr>`
2. Il clique sur le lien "Configurer mon compte"
3. Il définit son propre mot de passe
4. Il arrive directement sur les dashboards MediCore BI

> Aucune action manuelle requise — le script déclenche l'envoi automatiquement.

### Configuration SMTP

Metabase a besoin d'un serveur SMTP pour envoyer les emails d'invitation et de réinitialisation de mot de passe.

#### Étape 1 — Choisir le fournisseur SMTP

  ┌────────────────────┬──────────────────────┬──────┬──────────┬──────────────────────────────────┐
  │ Fournisseur        │ Serveur SMTP         │ Port │ Sécurité │ Mot de passe                     │
  ├────────────────────┼──────────────────────┼──────┼──────────┼──────────────────────────────────┤
  │ Google Workspace   │ smtp.gmail.com       │ 587  │ tls      │ Mot de passe d'application       │
  ├────────────────────┼──────────────────────┼──────┼──────────┼──────────────────────────────────┤
  │ Office 365         │ smtp.office365.com   │ 587  │ tls      │ Mot de passe du compte           │
  ├────────────────────┼──────────────────────┼──────┼──────────┼──────────────────────────────────┤
  │ Gmail personnel    │ smtp.gmail.com       │ 587  │ tls      │ Mot de passe d'application       │
  └────────────────────┴──────────────────────┴──────┴──────────┴──────────────────────────────────┘

> **Mediprix utilise Google Workspace** — le serveur SMTP est `smtp.gmail.com`, pas `smtp.office365.com`.

#### Étape 2 — Créer un mot de passe d'application Google

Google bloque les connexions SMTP avec le mot de passe du compte (même complexe). Il faut un **mot de passe d'application** dédié.

**Prérequis** : activer la validation en 2 étapes sur le compte Google.

1. Se connecter à `https://myaccount.google.com` avec le compte SMTP (ex: `metabase@mediprix.fr`)
2. **Sécurité** → **Validation en deux étapes** → Activer (si pas déjà fait)
3. Aller sur `https://myaccount.google.com/apppasswords`
4. Saisir un nom (ex: "Metabase") → **Créer**
5. Google affiche un mot de passe de 16 caractères (ex: `abcd efgh ijkl mnop`)
6. Copier ce mot de passe **sans les espaces** (ex: `abcdefghijklmnop`)

> Si "Mots de passe d'application" n'apparaît pas :
> - Vérifier que la validation en 2 étapes est bien activée
> - Pour les comptes Google Workspace : demander à l'admin d'activer l'option
>   dans `admin.google.com` → **Sécurité** → **Paramètres de base**

#### Étape 3 — Configurer dans `.env`

```bash
# .env — Section SMTP
MB_EMAIL_SMTP_HOST=smtp.gmail.com
MB_EMAIL_SMTP_PORT=587
MB_EMAIL_SMTP_SECURITY=tls
MB_EMAIL_SMTP_USERNAME=metabase@mediprix.fr
MB_EMAIL_SMTP_PASSWORD=abcdefghijklmnop
MB_EMAIL_FROM_ADDRESS=metabase@mediprix.fr
MB_EMAIL_FROM_NAME=MediCore BI
MB_SITE_URL=http://192.168.0.37:3000
```

> **Important** : `MB_EMAIL_SMTP_PASSWORD` est le mot de passe d'application (16 caractères),
> **pas** le mot de passe du compte Google.

#### Étape 4 — Appliquer la configuration dans Metabase

Les variables `.env` ne sont lues que par Docker au démarrage. Metabase v0.58 stocke
ses settings SMTP dans sa base PostgreSQL. Il faut donc les configurer **via l'API** :

```bash
# Obtenir un token admin
TOKEN=$(python -c "
import urllib.request, json
data = json.dumps({'username':'admin@mediprix.fr','password':'xxx'}).encode()
req = urllib.request.Request('http://localhost:3000/api/session', data=data, headers={'Content-Type':'application/json'})
print(json.loads(urllib.request.urlopen(req).read())['id'])
")

# Configurer chaque setting SMTP
for KEY in email-smtp-host email-smtp-port email-smtp-security email-smtp-username email-smtp-password email-from-address email-from-name site-url; do
  VALUE=$(python -c "
import os
mapping = {
  'email-smtp-host': os.getenv('MB_EMAIL_SMTP_HOST','smtp.gmail.com'),
  'email-smtp-port': 587,
  'email-smtp-security': 'tls',
  'email-smtp-username': os.getenv('MB_EMAIL_SMTP_USERNAME',''),
  'email-smtp-password': os.getenv('MB_EMAIL_SMTP_PASSWORD',''),
  'email-from-address': os.getenv('MB_EMAIL_FROM_ADDRESS',''),
  'email-from-name': os.getenv('MB_EMAIL_FROM_NAME','MediCore BI'),
  'site-url': os.getenv('MB_SITE_URL','http://192.168.0.37:3000'),
}
import json; print(json.dumps(mapping['$KEY']))
  ")
  curl -s -X PUT "http://localhost:3000/api/setting/$KEY" \
    -H "X-Metabase-Session: $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"value\": $VALUE}"
done
```

Ou plus simplement, utiliser l'interface Metabase :
**Admin** (⚙️) → **Paramètres** → **Email** → Remplir les champs → **Envoyer un email de test**

#### Étape 5 — Tester

Via l'API :

```bash
curl -X POST http://localhost:3000/api/email/test \
  -H "X-Metabase-Session: $TOKEN" \
  -H "Content-Type: application/json" -d '{}'
```

Résultat attendu : `{"ok": true}` et un email de test reçu sur le compte admin.

#### Dépannage SMTP

  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Erreur                               │ Solution                                                 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `535 5.7.3 Authentication            │ Mot de passe incorrect ou pas un mot de passe            │
  │ unsuccessful`                        │ d'application. Regénérer via myaccount.google.com        │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `535-5.7.8 Username and Password     │ Même cause — Google exige un mot de passe d'application  │
  │ not accepted`                        │ (16 caractères), pas le mot de passe du compte           │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `Couldn't connect to host, port:     │ Problème IPv6 dans le conteneur Docker. Utiliser l'IP    │
  │ ...; timeout -1`                     │ directe dans email-smtp-host (ex: 40.99.220.50)          │
  │                                      │ ou configurer Java pour préférer IPv4                    │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ `email-configured?: False`           │ Les settings ne sont pas dans la base Metabase.          │
  │                                      │ Configurer via l'API Settings ou l'interface Admin       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Email envoyé mais pas reçu           │ Vérifier les spams. Vérifier que `email-from-address`    │
  │                                      │ correspond au compte SMTP (anti-spoofing)                │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────┘

### Première connexion — sans SMTP (fallback)

Si le SMTP n'est pas configuré, le script affiche les informations à communiquer manuellement :

```
Bonjour [Prénom],

Ton compte Metabase MediCore est créé. Voici tes accès :

  URL       : http://192.168.0.37:3000
  Email     : [son email]
  Mot de passe temporaire : Medicore2026!

À ta première connexion, change ton mot de passe :
  1. Connecte-toi avec les identifiants ci-dessus
  2. Clique sur l'icône en bas à gauche (ton initiale)
  3. Clique sur "Paramètres du compte"
  4. Dans la section "Mot de passe", saisis l'ancien puis le nouveau
  5. Clique sur "Enregistrer"

Tes dashboards sont dans la collection "MediCore BI".
Pour créer tes propres cartes et dashboards, utilise les dossiers
de ton service (ex: Cards/IT/, Dashboards/IT/).
```

### Accès réseau

  ┌─────────────────────────────┬─────────────────────────────────────────────────────────────────┐
  │ Situation                   │ Action                                                          │
  ├─────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Même réseau local           │ `http://192.168.0.37:3000` — aucune config supplémentaire       │
  ├─────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ VPN d'entreprise            │ S'assurer que le VPN route vers le réseau 192.168.1.0/24        │
  ├─────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Accès externe (internet)    │ Non recommandé sans HTTPS. Mettre en place un reverse proxy     │
  │                             │ (Nginx/Traefik) avec certificat SSL + nom DNS                   │
  ├─────────────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ Pare-feu Windows            │ Ouvrir le port 3000 en entrant (TCP) — voir commande ci-dessous │
  └─────────────────────────────┴─────────────────────────────────────────────────────────────────┘

**Ouvrir le port 3000 dans le pare-feu Windows** (à exécuter une seule fois, en administrateur sur la machine hébergeant Docker) :

```cmd
netsh advfirewall firewall add rule name="Metabase" dir=in action=allow protocol=TCP localport=3000
```

> Sans cette règle, les autres postes du réseau ne peuvent pas accéder à Metabase
> même si Docker expose le port sur `0.0.0.0:3000`.

**IP fixe (recommandé)** : l'URL `http://192.168.0.37:3000` dépend d'une IP attribuée par DHCP — elle peut changer. Demander à l'admin réseau de réserver l'IP dans le routeur :

  ┌──────────────────┬──────────────────────────────────────────┐
  │ Paramètre        │ Valeur                                   │
  ├──────────────────┼──────────────────────────────────────────┤
  │ Machine          │ DESKTOP-FKLPKRA                          │
  ├──────────────────┼──────────────────────────────────────────┤
  │ Adresse MAC      │ 9C-97-1B-08-19-20 (Wi-Fi)                │
  ├──────────────────┼──────────────────────────────────────────┤
  │ IP à réserver    │ 192.168.0.37                             │
  └──────────────────┴──────────────────────────────────────────┘

> Le hostname (`http://DESKTOP-FKLPKRA:3000`) ne fonctionne pas sur le réseau Mediprix
> car la résolution de nom NetBIOS/mDNS est désactivée. Utiliser l'IP fixe (demande auprès de l'Admin Sys).

---

## 8. Dépannage

  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Problème                             │ Solution                                                 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ "Session token expired"              │ Obtenir un nouveau token (voir §2)                       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ "Email already exists"               │ Normal : le script détecte et affiche "EXISTE"           │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ L'utilisateur ne voit pas les        │ Vérifier que son service est correct dans le CSV         │
  │ dashboards                           │ et relancer le script                                    │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ L'utilisateur ne peut pas créer      │ Il doit créer dans `Cards/<Son service>/` ou             │
  │ de carte                             │ `Dashboards/<Son service>/`, pas dans Admin/             │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Erreur "Permission denied"           │ Vérifier que le token utilisé est celui d'un admin       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ L'utilisateur ne peut pas accéder    │ Vérifier : 1) même réseau local 2) pare-feu Windows      │
  │ à http://192.168.0.37:3000           │ port 3000 ouvert 3) Docker en cours d'exécution          │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ "Connection refused" depuis un       │ Vérifier que le bind est `0.0.0.0:3000:3000` dans        │
  │ autre poste                          │ `docker-compose.yml` (pas `127.0.0.1`)                   │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────┘
