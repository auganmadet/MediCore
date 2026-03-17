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

**`http://192.168.1.30:3000`**

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

Les variables SMTP sont dans `docker-compose.yml` et `.env` :

```bash
# .env
MB_EMAIL_SMTP_HOST=smtp.office365.com
MB_EMAIL_SMTP_PORT=587
MB_EMAIL_SMTP_SECURITY=tls
MB_EMAIL_SMTP_USERNAME=metabase@mediprix.fr
MB_EMAIL_SMTP_PASSWORD=votre_mot_de_passe_smtp
MB_EMAIL_FROM_ADDRESS=metabase@mediprix.fr
MB_EMAIL_FROM_NAME=MediCore BI
MB_SITE_URL=http://192.168.1.30:3000
```

> `MB_SITE_URL` est utilisé par Metabase pour générer les liens dans les emails.
> Adapter le serveur SMTP selon votre fournisseur (Office 365, Gmail, SMTP interne).

Après modification, redémarrer Metabase :

```bash
docker compose restart metabase
```

### Première connexion — sans SMTP (fallback)

Si le SMTP n'est pas configuré, le script affiche les informations à communiquer manuellement :

```
Bonjour [Prénom],

Ton compte Metabase MediCore est créé. Voici tes accès :

  URL       : http://192.168.1.30:3000
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

  ┌─────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Situation                   │ Action                                                       │
  ├─────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Même réseau local           │ `http://192.168.1.30:3000` — aucune config supplémentaire    │
  ├─────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ VPN d'entreprise            │ S'assurer que le VPN route vers le réseau 192.168.1.0/24     │
  ├─────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Accès externe (internet)    │ Non recommandé sans HTTPS. Mettre en place un reverse proxy  │
  │                             │ (Nginx/Traefik) avec certificat SSL + nom DNS                │
  ├─────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Pare-feu Windows            │ Ouvrir le port 3000 en entrant (TCP) si bloqué               │
  └─────────────────────────────┴──────────────────────────────────────────────────────────────┘

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
  │ à http://192.168.1.30:3000           │ port 3000 ouvert 3) Docker en cours d'exécution          │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ "Connection refused" depuis un       │ Vérifier que le bind est `0.0.0.0:3000:3000` dans        │
  │ autre poste                          │ `docker-compose.yml` (pas `127.0.0.1`)                   │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────┘
