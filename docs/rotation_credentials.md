# Rotation des credentials — MediCore

## Objectif

Changer régulièrement les mots de passe et tokens des comptes de service
pour limiter la fenêtre d'exposition en cas de fuite (log accidentel,
ancien collaborateur, historique git).

**Fréquence recommandée : trimestrielle** (janvier, avril, juillet, octobre).

---

## 1. Inventaire des credentials

  ┌─────┬──────────────────────────┬───────────────────────────────────┬─────────────────────────────┐
  │ #   │ Credential               │ Utilisé par                       │ Stocké dans                 │
  ├─────┼──────────────────────────┼───────────────────────────────────┼─────────────────────────────┤
  │ 1   │ SNOWFLAKE_PASSWORD       │ bulk_load.py, daily_cdc_batch.py, │ .env + GitHub Secrets       │
  │     │                          │ audit.py, kafka_lag.py, dbt,      │                             │
  │     │                          │ healthcheck.py, batch_loop.sh     │                             │
  ├─────┼──────────────────────────┼───────────────────────────────────┼─────────────────────────────┤
  │ 2   │ MYSQL_PASSWORD           │ bulk_load.py (lecture MySQL RDS)  │ .env                        │
  ├─────┼──────────────────────────┼───────────────────────────────────┼─────────────────────────────┤
  │ 3   │ TEAMS_WEBHOOK_URL        │ batch_loop.sh (alertes Teams)     │ .env                        │
  ├─────┼──────────────────────────┼───────────────────────────────────┼─────────────────────────────┤
  │ 4   │ MB_EMAIL_SMTP_PASSWORD   │ Metabase (envoi emails)           │ .env + Admin UI Metabase    │
  │     │ (mot de passe app Gmail) │                                   │                             │
  ├─────┼──────────────────────────┼───────────────────────────────────┼─────────────────────────────┤
  │ 5   │ Metabase admin password  │ UI Metabase (compte admin)        │ PostgreSQL interne Metabase │
  └─────┴──────────────────────────┴───────────────────────────────────┴─────────────────────────────┘

---

## 2. Procédure de rotation par credential

### 2a. SNOWFLAKE_PASSWORD (priorité haute)

C'est le credential le plus critique : il donne accès à toutes les données
de production (RAW, STAGING, MARTS, AUDIT).

**Ordre des opérations** (éviter toute interruption) :

```
1. Générer un nouveau mot de passe (min 16 caractères, alphanumérique + spéciaux)
2. Changer le mot de passe dans Snowflake :
     ALTER USER AUGUSTIN SET PASSWORD = 'NouveauMotDePasse';
3. Mettre à jour .env sur le serveur :
     SNOWFLAKE_PASSWORD=NouveauMotDePasse
4. Redémarrer le conteneur :
     docker compose restart medicore_elt_batch
5. Vérifier que le healthcheck passe :
     docker exec medicore_elt_batch python scripts/healthcheck.py
6. Mettre à jour GitHub Secrets :
     Repo → Settings → Secrets → SNOWFLAKE_PASSWORD → Update
7. Déclencher un run CI pour vérifier :
     gh workflow run ci.yml
```

**Fichiers impactés :**
- `.env` (serveur de production)
- GitHub Secrets (`SNOWFLAKE_PASSWORD`)
- Aucun fichier dans le code (le mot de passe n'est jamais en dur)

### 2b. MYSQL_PASSWORD

```
1. Changer le mot de passe dans MySQL RDS :
     ALTER USER 'medicore_reader'@'%' IDENTIFIED BY 'NouveauMotDePasse';
     FLUSH PRIVILEGES;
2. Mettre à jour .env :
     MYSQL_PASSWORD=NouveauMotDePasse
3. Redémarrer le conteneur :
     docker compose restart medicore_elt_batch
4. Vérifier la connexion :
     docker exec medicore_elt_batch python -c "
     import mysql.connector, os
     conn = mysql.connector.connect(
       host=os.getenv('MYSQL_HOST'), user=os.getenv('MYSQL_USER'),
       password=os.getenv('MYSQL_PASSWORD'), database='winstat')
     print('MySQL OK:', conn.is_connected())
     conn.close()"
```

**Fichiers impactés :** `.env` uniquement

### 2c. TEAMS_WEBHOOK_URL

```
1. Dans Microsoft Teams : supprimer l'ancien webhook du canal
2. Créer un nouveau webhook (canal → Connecteurs → Incoming Webhook)
3. Mettre à jour .env :
     TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/nouveau-url
4. Redémarrer le conteneur :
     docker compose restart medicore_elt_batch
5. Tester l'alerte :
     docker exec medicore_elt_batch bash -c "
     source /app/.env 2>/dev/null;
     curl -s -X POST \$TEAMS_WEBHOOK_URL \
       -H 'Content-Type: application/json' \
       -d '{\"text\": \"Test rotation webhook\"}'"
```

**Fichiers impactés :** `.env` uniquement

### 2d. MB_EMAIL_SMTP_PASSWORD (mot de passe app Gmail)

```
1. Google Workspace → Sécurité → Mots de passe d'application
2. Révoquer l'ancien mot de passe d'application
3. Créer un nouveau mot de passe d'application (16 caractères)
4. Mettre à jour dans Metabase :
   - Admin UI → Settings → Email → SMTP Password → nouveau mot de passe
   - OU via API : PUT /api/setting/email-smtp-password
5. Mettre à jour .env (pour le prochain docker compose up) :
     MB_EMAIL_SMTP_PASSWORD=NouveauMotDePasseApp
6. Envoyer un email de test depuis Metabase Admin → Email → Send test email
```

**Fichiers impactés :** `.env` + Admin UI Metabase

### 2e. Metabase admin password

```
1. Se connecter à Metabase (http://192.168.0.37:3000)
2. Profil admin → Mot de passe → Changer
3. Communiquer le nouveau mot de passe aux administrateurs IT
   (Simon, Richard, Alexandre)
```

**Fichiers impactés :** aucun (stocké dans PostgreSQL interne)

---

## 3. Checklist de rotation trimestrielle

```
[ ] 1. Planifier un créneau de maintenance (hors heures ouvrées, ex: 21h)
[ ] 2. Prévenir l'équipe IT (Simon, Richard, Alexandre)
[ ] 3. SNOWFLAKE_PASSWORD : ALTER USER + .env + GitHub Secrets + restart
[ ] 4. MYSQL_PASSWORD : ALTER USER + .env + restart
[ ] 5. TEAMS_WEBHOOK_URL : recréer webhook + .env + restart + test
[ ] 6. MB_EMAIL_SMTP_PASSWORD : révoquer + recréer + Metabase Admin + .env
[ ] 7. Metabase admin password : changer via UI + communiquer
[ ] 8. Vérifier le healthcheck conteneur
[ ] 9. Vérifier qu'un cycle batch complet passe (CDC + dbt + tests)
[ ] 10. Vérifier qu'un email Metabase s'envoie correctement
[ ] 11. Vérifier que la CI passe (GitHub Actions)
[ ] 12. Documenter la date de rotation dans ce fichier (section 4)
```

---

## 4. Historique des rotations

  ┌────────────┬──────────────────────────────────────┬──────────────────────┐
  │ Date       │ Credentials changés                  │ Effectué par         │
  ├────────────┼──────────────────────────────────────┼──────────────────────┤
  │ (aucune rotation effectuée à ce jour)             │                      │
  └────────────┴──────────────────────────────────────┴──────────────────────┘

---

## 5. Bonnes pratiques

- **Ne jamais commiter** de credentials dans le code (`.env` est dans `.gitignore`)
- **Mots de passe** : minimum 16 caractères, alphanumériques + spéciaux
- **Mot de passe app Gmail** : 16 caractères générés par Google (non modifiable)
- **Stockage temporaire** : utiliser un gestionnaire de mots de passe (Bitwarden, 1Password), jamais un fichier texte ou un message Slack
- **Accès limité** : seuls les administrateurs IT ont accès au `.env` de production
- **Alerte en cas de fuite** : si un credential est exposé (log, git, screenshot), effectuer une rotation immédiate sans attendre le trimestre
