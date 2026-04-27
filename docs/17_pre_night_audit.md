# Audit pré-nuit système MediCore (`scripts/pre_night_audit.sh`)

## Table des matières

1. [Pourquoi ce script](#pourquoi-ce-script)
2. [Vue d'ensemble](#vue-densemble)
3. [Les 6 sections de vérification](#les-6-sections-de-vérification)
4. [Mode audit (lecture seule)](#mode-audit-lecture-seule)
5. [Mode `--fix` (auto-correction)](#mode---fix-auto-correction)
6. [Le prompt UAC unique](#le-prompt-uac-unique)
7. [Lecture de la sortie](#lecture-de-la-sortie)
8. [Cas d'usage typiques](#cas-dusage-typiques)
9. [Limitations](#limitations)
10. [Annexe A — Mapping vérifications ↔ commandes Windows manuelles](#annexe-a--mapping-vérifications--commandes-windows-manuelles)

---

## Pourquoi ce script

Le **2026-04-26**, le pipeline MediCore a perdu une nuit entière (ref_reload SKIP, dbt post-reload, pipeline_maintenance, dev auto-clone tous manqués) à cause d'un `sleep 600` du batch_loop qui s'est gelé pendant 9 heures sur Modern Standby Windows + WSL2.

L'incident a révélé qu'**aucune protection unique** ne suffit. La résilience exige **5 couches indépendantes** :

  ┌──────────────────────────────────────────┬──────────────────────────────────┐
  │ Couche                                   │ Risque mitigé                    │
  ├──────────────────────────────────────────┼──────────────────────────────────┤
  │ Power Windows (anti-veille / hibernation)│ Machine qui dort sur secteur     │
  ├──────────────────────────────────────────┼──────────────────────────────────┤
  │ Windows Update (heures actives)          │ Reboot intempestif pendant batch │
  ├──────────────────────────────────────────┼──────────────────────────────────┤
  │ WSL2 `.wslconfig`                        │ Hibernation idle de la VM Linux  │
  ├──────────────────────────────────────────┼──────────────────────────────────┤
  │ `safe_sleep` dans batch_loop.sh          │ Gel timer sleep si WSL hiberne   │
  ├──────────────────────────────────────────┼──────────────────────────────────┤
  │ Conteneurs Docker tous Up + ENV=prod     │ Pipeline correctement câblé      │
  └──────────────────────────────────────────┴──────────────────────────────────┘

Vérifier ces 5 couches manuellement = **8 commandes** à lancer dans 2 shells différents (PowerShell admin + Git Bash). C'est laborieux et oublier un check expose le pipeline. Le script `pre_night_audit.sh` automatise tout en **1 seule commande** avec verdict GO/NO-GO clair.

[↑ Retour au sommaire](#table-des-matières)

---

## Vue d'ensemble

  ┌─────────────────────────────────┬────────────────────────────────────────────┐
  │ Élément                         │ Valeur                                     │
  ├─────────────────────────────────┼────────────────────────────────────────────┤
  │ Fichier                         │ `scripts/pre_night_audit.sh`               │
  ├─────────────────────────────────┼────────────────────────────────────────────┤
  │ Langage                         │ Bash (Git Bash sur Windows)                │
  ├─────────────────────────────────┼────────────────────────────────────────────┤
  │ Prérequis                       │ Docker Desktop + WSL2 + PowerShell         │
  ├─────────────────────────────────┼────────────────────────────────────────────┤
  │ Durée d'exécution               │ ~10 secondes (audit) / ~90 s max (--fix)   │
  ├─────────────────────────────────┼────────────────────────────────────────────┤
  │ Quand le lancer                 │ Avant chaque nuit critique (~18h-20h FR)   │
  └─────────────────────────────────┴────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Les 6 sections de vérification

### Section 1 — Power Windows (anti-veille / anti-hibernation)

  ┌────────────────────┬──────────────────────────────────────────────────┐
  │ Check              │ Valeur attendue                                  │
  ├────────────────────┼──────────────────────────────────────────────────┤
  │ STANDBYIDLE AC     │ `0x00000000` (jamais de veille sur secteur)      │
  ├────────────────────┼──────────────────────────────────────────────────┤
  │ HIBERNATEIDLE AC   │ `0x00000000` (jamais d'hibernation sur secteur)  │
  └────────────────────┴──────────────────────────────────────────────────┘

Source de la mesure : `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE` et `HIBERNATEIDLE`.

### Section 2 — Windows Update (anti-reboot intempestif)

  ┌─────────────────────────────────┬───────────────────────────────────────────────┐
  │ Check                           │ Valeur attendue                               │
  ├─────────────────────────────────┼───────────────────────────────────────────────┤
  │ ActiveHoursStart                │ `20` (= 20h FR, début de la protection)       │
  ├─────────────────────────────────┼───────────────────────────────────────────────┤
  │ ActiveHoursEnd                  │ `8` (= 08h FR, fin de la protection)          │
  ├─────────────────────────────────┼───────────────────────────────────────────────┤
  │ SmartActiveHoursState           │ `0` (config manuelle verrouillée)             │
  ├─────────────────────────────────┼───────────────────────────────────────────────┤
  │ NoAutoRebootWithLoggedOnUsers   │ `1` (jamais de reboot auto si session active) │
  └─────────────────────────────────┴───────────────────────────────────────────────┘

La plage `20h-08h` couvre **toute la nuit batch (21h-07h)** avec 1h de marge avant et après. La journée (8h-20h) est protégée par `NoAutoRebootWithLoggedOnUsers=1` tant qu'une session utilisateur reste active.

Source : `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings` et `HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU`.

### Section 3 — WSL2 (`.wslconfig` anti-gel timer)

3 vérifications dans `~/.wslconfig` :

  ┌──────────────────────┬──────────────────────────────────────────────────┐
  │ Check                │ Valeur attendue                                  │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │ Section `[wsl2]`     │ Présente                                         │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │ `networkingMode=NAT` │ Présent (compat Docker Desktop)                  │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │ `vmIdleTimeout=-1`   │ Présent (pas d'hibernation idle WSL)             │
  └──────────────────────┴──────────────────────────────────────────────────┘

Note : `vmIdleTimeout=-1` ne suffit pas seul à empêcher Modern Standby de geler les timers. La vraie protection vient de `safe_sleep` (Section 5). `.wslconfig` est une protection complémentaire.

### Section 4 — Conteneurs Docker

Vérifie que **9 conteneurs** sont en état `running` :

  ┌─────────────────────────────┬────────────────────────────────────────────┐
  │ Conteneur                   │ Rôle                                       │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ medicore_elt_batch          │ Batch principal (CDC + dbt + pipeline)     │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ kafka                       │ Broker Kafka                               │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ kafka_connect               │ Debezium connector                         │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ mysql_cdc                   │ MySQL local pour tests CDC                 │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ metabase                    │ BI / dashboards                            │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ metabase_db                 │ PostgreSQL backend Metabase                │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ kafdrop                     │ UI inspection Kafka                        │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ zookeeper                   │ Coordination Kafka                         │
  ├─────────────────────────────┼────────────────────────────────────────────┤
  │ dbt_docs                    │ Catalog dbt (souvent unhealthy cosmétique) │
  └─────────────────────────────┴────────────────────────────────────────────┘

`dbt_docs` est typiquement signalé `unhealthy` à cause du healthcheck Docker qui interroge le port 8080 alors que le mapping externe est à 8082. C'est cosmétique et **n'affecte pas le pipeline**.

### Section 5 — Pipeline batch_loop (`safe_sleep` + ENV=prod)

  ┌──────────────────────────────┬────────────────────────────────────────────────┐
  │ Check                        │ Valeur attendue                                │
  ├──────────────────────────────┼────────────────────────────────────────────────┤
  │ Fonction `safe_sleep` définie│ Présente dans `scripts/batch_loop.sh:92`       │
  ├──────────────────────────────┼────────────────────────────────────────────────┤
  │ Utilisations de `safe_sleep` │ ≥ 4 appels (les 4 sleeps longs protégés)       │
  ├──────────────────────────────┼────────────────────────────────────────────────┤
  │ Process `sleep` en cours     │ ≤ 60 secondes (confirme `safe_sleep` actif)    │
  ├──────────────────────────────┼────────────────────────────────────────────────┤
  │ `ENV` dans le conteneur      │ `prod` (sinon dbt cible MEDICORE_DEV figé)     │
  └──────────────────────────────┴────────────────────────────────────────────────┘

Le check du process en cours est le **plus critique** : il valide que `safe_sleep` est bien actif **runtime**, pas seulement présent dans le code source. Si le résultat est `sleep 600` ou `sleep 3600`, c'est l'ancien code → restart du conteneur nécessaire.

### Section 6 — Flags `/tmp` résiduels

Vérifie qu'aucun flag du jour précédent n'est présent dans le conteneur :

```
pre_night_done_today, pre_night_ok, night_cdc_done,
ref_bulk_done_today, post_reload_dbt_done,
mb_provision_done_today, dev_clone_done_today, extra_bulk_running
```

Pourquoi : si `pre_night_done_today` reste de la veille, le pre-night healthcheck du soir sera **skippé** car la condition `! -f "$PRE_NIGHT_DONE_FLAG"` est fausse.

[↑ Retour au sommaire](#table-des-matières)

---

## Mode audit (lecture seule)

```bash
cd /c/Temp/MediCore && ./scripts/pre_night_audit.sh
```

  - Aucune action sur le système, aucun fichier modifié
  - Affiche le statut de chacun des 6 sections
  - Termine par un verdict clair
  - Code de retour `0` si OK, `> 0` si erreur(s) critique(s)

[↑ Retour au sommaire](#table-des-matières)

---

## Mode `--fix` (auto-correction)

```bash
./scripts/pre_night_audit.sh --fix
```

Le script applique automatiquement les corrections nécessaires.

### Corrections sans intervention

  ┌───────────────────────────────────────┬──────────────────────────────────────┐
  │ Problème détecté                      │ Action automatique                   │
  ├───────────────────────────────────────┼──────────────────────────────────────┤
  │ Flags `/tmp` résiduels                │ `rm -f` immédiat                     │
  ├───────────────────────────────────────┼──────────────────────────────────────┤
  │ Conteneur Docker arrêté               │ `docker compose up -d`               │
  ├───────────────────────────────────────┼──────────────────────────────────────┤
  │ Process `sleep` > 60s figé            │ `docker compose restart`             │
  ├───────────────────────────────────────┼──────────────────────────────────────┤
  │ `.wslconfig` absent ou incomplet      │ Création/édition du fichier          │
  └───────────────────────────────────────┴──────────────────────────────────────┘

### Corrections avec UAC unique

Pour les paramètres Windows qui exigent les droits administrateur (`HKLM\` et `powercfg`), le script génère `/tmp/pre_night_admin_fix.ps1` puis lance automatiquement `powershell.exe Start-Process -Verb RunAs -Wait` qui déclenche **un seul prompt UAC**.

  ┌───────────────────────────────────────────┬──────────────────────────────────┐
  │ Problème admin détecté                    │ Commande générée                 │
  ├───────────────────────────────────────────┼──────────────────────────────────┤
  │ STANDBYIDLE AC ≠ 0                        │ `powercfg /change standby-...`   │
  ├───────────────────────────────────────────┼──────────────────────────────────┤
  │ HIBERNATEIDLE AC ≠ 0                      │ `powercfg /change hibernate-...` │
  ├───────────────────────────────────────────┼──────────────────────────────────┤
  │ Heures actives ≠ 20h-08h                  │ `reg add ... ActiveHours*`       │
  ├───────────────────────────────────────────┼──────────────────────────────────┤
  │ SmartActiveHoursState ≠ 0                 │ `reg add ... SmartActive...`     │
  ├───────────────────────────────────────────┼──────────────────────────────────┤
  │ NoAutoRebootWithLoggedOnUsers ≠ 1         │ `reg add ... NoAutoReboot...`    │
  └───────────────────────────────────────────┴──────────────────────────────────┘

### Correction `wsl --shutdown` automatique

Si `.wslconfig` a été modifié dans la session, le script lance `wsl --shutdown` puis attend jusqu'à 90 s que Docker Desktop redémarre les conteneurs (qui ont `restart: unless-stopped`).

### Cas non auto-corrigeables

  ┌─────────────────────────────────┬─────────────────────────────────────────┐
  │ Problème                        │ Action manuelle requise                 │
  ├─────────────────────────────────┼─────────────────────────────────────────┤
  │ `safe_sleep` absent du code     │ Refactor manuel `scripts/batch_loop.sh` │
  ├─────────────────────────────────┼─────────────────────────────────────────┤
  │ `ENV` ≠ `prod`                  │ Modifier `.env` et faire                │
  │                                 │ `docker compose up -d --force-recreate` │
  └─────────────────────────────────┴─────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Le prompt UAC unique

Modifier les clés registre `HKLM\` ou exécuter `powercfg /change` exige toujours les droits administrateur Windows. **Aucune méthode** ne contourne ça (sauf désactiver UAC, déconseillé pour la sécurité).

Le script utilise `Start-Process powershell -Verb RunAs -Wait` qui :

  1. Affiche **un seul** prompt UAC (toutes les corrections sont groupées)
  2. Exécute le `.ps1` généré dans une console PowerShell élevée
  3. Attend la fin de l'exécution avant de reprendre le script bash
  4. Récupère le code de retour pour valider le succès

L'utilisateur clique **"Oui"** une fois sur la fenêtre UAC et toutes les corrections admin s'appliquent en cascade.

[↑ Retour au sommaire](#table-des-matières)

---

## Lecture de la sortie

  ┌──────────┬───────────────────────────────────────────────────────────┐
  │ Marqueur │ Signification                                             │
  ├──────────┼───────────────────────────────────────────────────────────┤
  │ `[OK]`   │ Aucune action nécessaire                                  │
  ├──────────┼───────────────────────────────────────────────────────────┤
  │ `[WARN]` │ À surveiller mais non bloquant                            │
  ├──────────┼───────────────────────────────────────────────────────────┤
  │ `[FAIL]` │ Critique, doit être corrigé avant la nuit                 │
  ├──────────┼───────────────────────────────────────────────────────────┤
  │ `[FIX]`  │ Correction appliquée automatiquement (mode `--fix`)       │
  └──────────┴───────────────────────────────────────────────────────────┘

Verdict final :

  - **GO** : tout est prêt pour la nuit, aucune action
  - **GO avec N warning(s)** : OK fonctionnellement, juste à surveiller
  - **NO-GO** : N erreur(s) critique(s) à corriger avant de laisser tourner

[↑ Retour au sommaire](#table-des-matières)

---

## Cas d'usage typiques

  ┌────────────────────────────────────────┬────────────────────────────────────┐
  │ Quand                                  │ Commande                           │
  ├────────────────────────────────────────┼────────────────────────────────────┤
  │ Routine quotidienne avant la nuit      │ `./scripts/pre_night_audit.sh`     │
  │ (idéalement vers 18h-20h FR)           │                                    │
  ├────────────────────────────────────────┼────────────────────────────────────┤
  │ Après un reboot Windows                │ `./scripts/pre_night_audit.sh --fix`│
  ├────────────────────────────────────────┼────────────────────────────────────┤
  │ Si la nuit a planté                    │ `./scripts/pre_night_audit.sh --fix`│
  ├────────────────────────────────────────┼────────────────────────────────────┤
  │ Après changement Windows / WSL / Docker│ `./scripts/pre_night_audit.sh`     │
  ├────────────────────────────────────────┼────────────────────────────────────┤
  │ Setup initial sur nouvelle machine     │ `./scripts/pre_night_audit.sh --fix`│
  └────────────────────────────────────────┴────────────────────────────────────┘

### Alias pratiques

À ajouter dans `~/.bashrc` Git Bash :

```bash
alias audit='cd /c/Temp/MediCore && ./scripts/pre_night_audit.sh'
alias audit-fix='cd /c/Temp/MediCore && ./scripts/pre_night_audit.sh --fix'
```

[↑ Retour au sommaire](#table-des-matières)

---

## Limitations

### Le prompt UAC est obligatoire

Modifier `HKLM\` ou `powercfg` exige les droits administrateur. Le script ne peut pas contourner cette protection Windows. **1 clic UAC est le minimum incompressible**.

### `wsl --shutdown` arrête les conteneurs Docker

Si `.wslconfig` doit être modifié, le `wsl --shutdown` automatique stoppe brièvement Docker Desktop. Les conteneurs avec `restart: unless-stopped` redémarrent automatiquement (~30-60 s). Le script attend jusqu'à 90 s.

Si tu lances le script en plein cycle CDC, le cycle sera interrompu. À éviter pendant les heures critiques.

### Détection du process `sleep` peut donner WARN

Si le check Docker tombe juste pendant l'exécution d'une phase (CDC, dbt, etc.), il n'y a pas de `sleep` en cours et le check retourne WARN au lieu de OK. C'est un faux négatif sans gravité.

### `dbt_docs unhealthy` warn cosmétique

Le healthcheck Docker de `dbt_docs` interroge le port 8080 (interne) alors que le mapping externe est sur 8082 (changé pour éviter conflit Windows iphlpsvc). Le warning est cosmétique et n'affecte pas le pipeline.

### Pas de check Snowflake

Le script ne vérifie pas la connectivité Snowflake. C'est le rôle de `scripts/pre_night_healthcheck.py` qui tourne automatiquement à 20h30 FR (Niveau 1, voir `docs/16_pipeline_maintenance.md`).

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe A — Mapping vérifications ↔ commandes Windows manuelles

Pour les utilisateurs qui préfèrent vérifier manuellement, voici les commandes équivalentes que le script regroupe :

  ┌────┬───────────────────────────────┬──────────────────────────────────────────┐
  │ #  │ Vérification                  │ Commande manuelle équivalente            │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  1 │ ActiveHoursStart              │ `reg query "HKLM\SOFTWARE\Microsoft\     │
  │    │                               │ WindowsUpdate\UX\Settings"               │
  │    │                               │ /v ActiveHoursStart`                     │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  2 │ ActiveHoursEnd                │ Idem `/v ActiveHoursEnd`                 │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  3 │ NoAutoRebootWithLoggedOnUsers │ `reg query "HKLM\SOFTWARE\Policies\      │
  │    │                               │ Microsoft\Windows\WindowsUpdate\AU"      │
  │    │                               │ /v NoAutoRebootWithLoggedOnUsers`        │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  4 │ STANDBYIDLE AC                │ `powercfg /query SCHEME_CURRENT          │
  │    │                               │ SUB_SLEEP STANDBYIDLE`                   │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  5 │ HIBERNATEIDLE AC              │ Idem `... HIBERNATEIDLE`                 │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  6 │ `.wslconfig`                  │ `cat "/c/Users/Augustin Madet/           │
  │    │                               │ .wslconfig"`                             │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  7 │ Conteneurs Docker             │ `docker ps --format                      │
  │    │                               │ "table {{.Names}}\t{{.Status}}"`         │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  8 │ Process `sleep` actuel        │ `docker exec medicore_elt_batch sh -c    │
  │    │                               │ "for p in /proc/[0-9]*; do               │
  │    │                               │ cmd=\$(cat \$p/cmdline ...); echo ...";  │
  │    │                               │ done | grep -E '^sleep [0-9]+'"`         │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │  9 │ ENV conteneur                 │ `docker exec medicore_elt_batch          │
  │    │                               │ printenv ENV`                            │
  ├────┼───────────────────────────────┼──────────────────────────────────────────┤
  │ 10 │ Flags `/tmp`                  │ `docker exec medicore_elt_batch          │
  │    │                               │ ls /tmp/ | grep -E "pre_night..."`       │
  └────┴───────────────────────────────┴──────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Liens connexes

- `docs/16_pipeline_maintenance.md` : architecture surveillance 4 niveaux (`pre_night_healthcheck.py` + `pipeline_maintenance.py`)
- `scripts/batch_loop.sh:92` : fonction `safe_sleep` (anti-gel WSL2)
- `scripts/kafka_status.sh` : vue lag + freshness Kafka (complémentaire)
- Memory `wsl_safe_sleep_fix.md` : analyse complète de l'incident 2026-04-26 et de la solution
