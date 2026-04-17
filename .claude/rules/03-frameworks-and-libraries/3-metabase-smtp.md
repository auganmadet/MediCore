---
description: Configuration SMTP Metabase pour Google Workspace Mediprix. Gmail, mot de passe app, API Settings.
globs: "docker-compose.yml,scripts/metabase_*.py,scripts/provision_*.py"
---

- Mediprix utilise Google Workspace — le serveur SMTP est `smtp.gmail.com:587/tls`, PAS `smtp.office365.com`
- Authentification par **mot de passe d'application** Google (16 caractères), pas le mot de passe du compte
- Les variables `MB_EMAIL_*` dans `docker-compose.yml` sont lues uniquement au démarrage Docker
- Metabase v0.58 stocke ses settings SMTP dans sa base PostgreSQL interne — les env vars ne les écrasent pas après le premier lancement
- Configurer via l'API Settings (`PUT /api/setting/email-smtp-host`) ou l'Admin UI pour persister
- IPv6 peut causer des timeouts Java dans le conteneur Docker — utiliser l'IP directe ou forcer IPv4
