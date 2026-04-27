#!/bin/bash
# ==============================================================================
# Audit pré-nuit MediCore — vérifie toutes les protections critiques avant
# le batch nocturne pour éviter les incidents type 26/04 (sleep figé 9h).
#
# Vérifications + auto-correction :
#   1. Power Windows (STANDBYIDLE / HIBERNATEIDLE = 0 sur secteur)
#   2. Windows Update (heures actives 20h-08h + NoAutoRebootWithLoggedOnUsers)
#   3. WSL2 (.wslconfig vmIdleTimeout=-1)
#   4. Conteneurs Docker (tous running + healthy)
#   5. Pipeline batch_loop (safe_sleep actif, process sleep court)
#   6. Cohérence ENV=prod
#   7. Flags /tmp résiduels (peuvent bloquer le pre-night healthcheck)
#
# Usage :
#   ./scripts/pre_night_audit.sh           # audit lecture seule
#   ./scripts/pre_night_audit.sh --fix     # audit + auto-correction
#
# Mode --fix :
#   - Corrections automatiques (sans admin) : flags /tmp, conteneurs Docker
#     arretes, restart conteneur si sleep fige, ajout vmIdleTimeout dans
#     .wslconfig.
#   - Corrections necessitant admin Windows (registry, powercfg) : un script
#     PowerShell est genere dans /tmp/pre_night_admin_fix.ps1 et la commande
#     d elevation UAC est affichee.
#
# Sortie : verdict GO / GO avec warnings / NO-GO + exit code (0 si OK).
#
# Documentation complète : docs/17_pre_night_audit.md
# ==============================================================================

set -uo pipefail
export MSYS_NO_PATHCONV=1

FIX_MODE="${1:-check}"
FAIL_COUNT=0
WARN_COUNT=0
APPLIED_FIXES=()
ADMIN_FIX_SCRIPT="/tmp/pre_night_admin_fix.ps1"
ADMIN_FIXES_NEEDED=0
WSL_NEEDS_SHUTDOWN=0

print_check() {
    local status="$1" label="$2" detail="$3"
    case "$status" in
        OK)   printf "  [OK]   %-38s %s\n" "$label" "$detail" ;;
        WARN) printf "  [WARN] %-38s %s\n" "$label" "$detail"; WARN_COUNT=$((WARN_COUNT + 1)) ;;
        FAIL) printf "  [FAIL] %-38s %s\n" "$label" "$detail"; FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
        FIX)  printf "  [FIX]  %-38s %s\n" "$label" "$detail"; APPLIED_FIXES+=("$label : $detail") ;;
    esac
}

ps_query() {
    powershell.exe -NoProfile -Command "$1" 2>/dev/null | tr -d '\r' | head -1
}

# Ajoute une commande PowerShell admin au script de correction
admin_fix_add() {
    local description="$1"
    local cmd="$2"
    if [ "$ADMIN_FIXES_NEEDED" -eq 0 ]; then
        # Premiere fois : initialiser le script PS
        cat > "$ADMIN_FIX_SCRIPT" <<'PSHEAD'
# Script auto-genere par pre_night_audit.sh --fix
# Corrections necessitant les droits administrateur Windows.
# Lance ce fichier en PowerShell elevee (clic droit > Executer en admin).

Write-Host "Application des corrections admin pre-nuit MediCore..." -ForegroundColor Cyan
Write-Host ""
PSHEAD
    fi
    ADMIN_FIXES_NEEDED=$((ADMIN_FIXES_NEEDED + 1))
    cat >> "$ADMIN_FIX_SCRIPT" <<EOF

Write-Host "[$ADMIN_FIXES_NEEDED] $description" -ForegroundColor Yellow
$cmd
EOF
}

echo "========================================================================="
echo "  Audit pre-nuit MediCore - $(date '+%Y-%m-%d %H:%M:%S %Z')"
if [ "$FIX_MODE" = "--fix" ]; then
    echo "  Mode : --fix (auto-correction activee)"
fi
echo "========================================================================="

# --- Section 1 : Power Windows ----------------------------------------------
echo ""
echo "--- Power Windows (anti-veille / anti-hibernation) ---"

STANDBY_AC=$(ps_query "(powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String 'courant alternatif').ToString()")
if echo "$STANDBY_AC" | grep -q "0x00000000"; then
    print_check OK "Veille systeme AC" "STANDBYIDLE = 0 (jamais)"
else
    print_check FAIL "Veille systeme AC" "STANDBYIDLE actif (la machine peut dormir)"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Desactiver veille systeme sur secteur" "powercfg /change standby-timeout-ac 0"
    fi
fi

HIBER_AC=$(ps_query "(powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE | Select-String 'courant alternatif').ToString()")
if echo "$HIBER_AC" | grep -q "0x00000000"; then
    print_check OK "Hibernation AC" "HIBERNATEIDLE = 0 (jamais)"
else
    print_check FAIL "Hibernation AC" "HIBERNATEIDLE actif"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Desactiver hibernation sur secteur" "powercfg /change hibernate-timeout-ac 0"
    fi
fi

# --- Section 2 : Windows Update ---------------------------------------------
echo ""
echo "--- Windows Update (anti-reboot intempestif) ---"

ACTIVE_START=$(ps_query "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings' -Name ActiveHoursStart -ErrorAction SilentlyContinue).ActiveHoursStart")
ACTIVE_END=$(ps_query "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings' -Name ActiveHoursEnd -ErrorAction SilentlyContinue).ActiveHoursEnd")
SMART_STATE=$(ps_query "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings' -Name SmartActiveHoursState -ErrorAction SilentlyContinue).SmartActiveHoursState")
NO_REBOOT=$(ps_query "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU' -Name NoAutoRebootWithLoggedOnUsers -ErrorAction SilentlyContinue).NoAutoRebootWithLoggedOnUsers")

# Heures actives attendues : 20h -> 08h (couvre la nuit batch 21h-07h)
if [ "$ACTIVE_START" = "20" ] && [ "$ACTIVE_END" = "8" ]; then
    print_check OK "Heures actives" "20h -> 8h (couvre nuit batch)"
elif [ -n "$ACTIVE_START" ] && [ -n "$ACTIVE_END" ]; then
    print_check WARN "Heures actives" "${ACTIVE_START}h -> ${ACTIVE_END}h (attendu 20h-8h)"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Heures actives Windows Update : 20h-8h" "reg add \"HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings\" /v ActiveHoursStart /t REG_DWORD /d 20 /f; reg add \"HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings\" /v ActiveHoursEnd /t REG_DWORD /d 8 /f"
    fi
else
    print_check FAIL "Heures actives" "non definies (Windows libre de redemarrer)"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Heures actives Windows Update : 20h-8h" "reg add \"HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings\" /v ActiveHoursStart /t REG_DWORD /d 20 /f; reg add \"HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings\" /v ActiveHoursEnd /t REG_DWORD /d 8 /f"
    fi
fi

if [ "$SMART_STATE" = "0" ]; then
    print_check OK "SmartActiveHoursState" "0 (config manuelle verrouillee)"
else
    print_check WARN "SmartActiveHoursState" "$SMART_STATE (Windows ajuste auto)"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Verrouiller SmartActiveHoursState a 0" "reg add \"HKLM\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings\" /v SmartActiveHoursState /t REG_DWORD /d 0 /f"
    fi
fi

if [ "$NO_REBOOT" = "1" ]; then
    print_check OK "NoAutoRebootWithLoggedOnUsers" "1 (jamais de reboot auto si connecte)"
else
    print_check FAIL "NoAutoRebootWithLoggedOnUsers" "absent (reboot Windows Update possible)"
    if [ "$FIX_MODE" = "--fix" ]; then
        admin_fix_add "Bloquer reboot auto si utilisateur connecte" "reg add \"HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU\" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f"
    fi
fi

# --- Section 3 : WSL2 -------------------------------------------------------
echo ""
echo "--- WSL2 (.wslconfig anti-gel timer) ---"

WSL_CONFIG_BASH=$(echo "$USERPROFILE" | sed 's|\\|/|g' | sed 's|^C:|/c|')/.wslconfig
if [ -f "$WSL_CONFIG_BASH" ]; then
    # Verif 1 : section [wsl2] presente
    if grep -q "^\[wsl2\]" "$WSL_CONFIG_BASH"; then
        print_check OK ".wslconfig section [wsl2]" "presente"
    else
        print_check WARN ".wslconfig section [wsl2]" "absente"
        if [ "$FIX_MODE" = "--fix" ]; then
            printf "\n[wsl2]\n" >> "$WSL_CONFIG_BASH"
            print_check FIX ".wslconfig section [wsl2]" "ajoutee"
            WSL_NEEDS_SHUTDOWN=1
        fi
    fi

    # Verif 2 : networkingMode=NAT
    if grep -q "^networkingMode=NAT" "$WSL_CONFIG_BASH"; then
        print_check OK ".wslconfig networkingMode" "NAT (compat Docker Desktop)"
    else
        print_check WARN ".wslconfig networkingMode" "non defini ou autre valeur (attendu : NAT)"
        if [ "$FIX_MODE" = "--fix" ]; then
            if grep -q "^\[wsl2\]" "$WSL_CONFIG_BASH"; then
                sed -i '/^\[wsl2\]/a networkingMode=NAT' "$WSL_CONFIG_BASH"
            else
                printf "\n[wsl2]\nnetworkingMode=NAT\n" >> "$WSL_CONFIG_BASH"
            fi
            print_check FIX ".wslconfig networkingMode" "NAT ajoute"
            WSL_NEEDS_SHUTDOWN=1
        fi
    fi

    # Verif 3 : vmIdleTimeout=-1
    if grep -q "vmIdleTimeout=-1" "$WSL_CONFIG_BASH"; then
        print_check OK ".wslconfig vmIdleTimeout" "-1 (pas d hibernation idle WSL)"
    else
        print_check WARN ".wslconfig vmIdleTimeout" "non defini (defaut 60s = WSL peut geler)"
        if [ "$FIX_MODE" = "--fix" ]; then
            if grep -q "^\[wsl2\]" "$WSL_CONFIG_BASH"; then
                sed -i '/^\[wsl2\]/a vmIdleTimeout=-1' "$WSL_CONFIG_BASH"
            else
                printf "\n[wsl2]\nvmIdleTimeout=-1\n" >> "$WSL_CONFIG_BASH"
            fi
            print_check FIX ".wslconfig vmIdleTimeout" "-1 ajoute"
            WSL_NEEDS_SHUTDOWN=1
        fi
    fi
else
    print_check WARN ".wslconfig" "fichier absent"
    if [ "$FIX_MODE" = "--fix" ]; then
        printf "[wsl2]\nnetworkingMode=NAT\nvmIdleTimeout=-1\n" > "$WSL_CONFIG_BASH"
        print_check FIX ".wslconfig" "cree avec 3 lignes"
        WSL_NEEDS_SHUTDOWN=1
    fi
fi

# --- Section 4 : Conteneurs Docker ------------------------------------------
echo ""
echo "--- Conteneurs Docker ---"

EXPECTED=("medicore_elt_batch" "kafka" "kafka_connect" "mysql_cdc" "metabase" "metabase_db" "kafdrop" "zookeeper" "dbt_docs")
DOCKER_NEEDS_UP=0
for c in "${EXPECTED[@]}"; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "absent")
    HEALTH=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "")
    if [ "$STATUS" = "running" ]; then
        if [ "$HEALTH" = "healthy" ] || [ -z "$HEALTH" ] || [ "$HEALTH" = "<nil>" ]; then
            print_check OK "$c" "running"
        elif [ "$HEALTH" = "unhealthy" ]; then
            print_check WARN "$c" "running mais unhealthy"
        else
            print_check OK "$c" "running ($HEALTH)"
        fi
    else
        print_check FAIL "$c" "$STATUS"
        DOCKER_NEEDS_UP=1
    fi
done

if [ "$DOCKER_NEEDS_UP" = "1" ] && [ "$FIX_MODE" = "--fix" ]; then
    echo "    Relance des conteneurs arretes..."
    if docker compose up -d 2>&1 | tail -3; then
        print_check FIX "docker compose up" "conteneur(s) relance(s)"
    fi
fi

# --- Section 5 : batch_loop ------------------------------------------------
echo ""
echo "--- Pipeline batch_loop (safe_sleep + ENV=prod) ---"

if grep -q "^safe_sleep()" scripts/batch_loop.sh 2>/dev/null; then
    print_check OK "safe_sleep defini dans le code" "fonction presente"
else
    print_check FAIL "safe_sleep defini dans le code" "absent (refactor manuel necessaire)"
fi

SAFE_COUNT=$(grep -c "safe_sleep " scripts/batch_loop.sh 2>/dev/null || echo "0")
if [ "$SAFE_COUNT" -ge "4" ]; then
    print_check OK "safe_sleep utilisations" "$SAFE_COUNT appels (attendu >= 4)"
else
    print_check WARN "safe_sleep utilisations" "$SAFE_COUNT appels (manque protections)"
fi

# Détection process sleep courant : doit être <= 60s pour confirmer safe_sleep actif
SLEEP_LINE=$(docker exec medicore_elt_batch sh -c "for p in /proc/[0-9]*; do cmd=\$(cat \$p/cmdline 2>/dev/null | tr '\\0' ' '); echo \"\$cmd\"; done | grep -E '^sleep [0-9]+'" 2>/dev/null | head -1 | tr -d '\r')
SLEEP_NEEDS_RESTART=0
if [ -n "$SLEEP_LINE" ]; then
    SLEEP_SEC=$(echo "$SLEEP_LINE" | awk '{print $2}')
    if [ "$SLEEP_SEC" -le "60" ]; then
        print_check OK "Process sleep en cours" "sleep ${SLEEP_SEC}s (safe_sleep actif)"
    else
        print_check FAIL "Process sleep en cours" "sleep ${SLEEP_SEC}s (LONG, risque de gel !)"
        SLEEP_NEEDS_RESTART=1
    fi
else
    print_check WARN "Process sleep en cours" "non detecte (cycle en cours peut-etre)"
fi

if [ "$SLEEP_NEEDS_RESTART" = "1" ] && [ "$FIX_MODE" = "--fix" ]; then
    echo "    Restart du conteneur batch pour purger le sleep fige..."
    if docker compose restart medicore-elt-batch 2>&1 | tail -2; then
        sleep 8
        print_check FIX "docker compose restart batch" "conteneur relance (safe_sleep actif au prochain cycle)"
    fi
fi

ENV_VAL=$(docker exec medicore_elt_batch printenv ENV 2>/dev/null | tr -d '\r')
if [ "$ENV_VAL" = "prod" ]; then
    print_check OK "ENV conteneur" "prod (dbt cible MEDICORE_PROD)"
else
    print_check FAIL "ENV conteneur" "$ENV_VAL (devrait etre prod, verifier .env + recreate)"
fi

# --- Section 6 : Flags /tmp résiduels ---------------------------------------
echo ""
echo "--- Flags /tmp (residuels du jour precedent) ---"

RESIDUAL=$(docker exec medicore_elt_batch sh -c "ls /tmp/ 2>/dev/null | grep -E '^(pre_night_done_today|pre_night_ok|night_cdc_done|ref_bulk_done_today|post_reload_dbt_done|mb_provision_done_today|dev_clone_done_today|extra_bulk_running)$'" 2>/dev/null | tr -d '\r')

if [ -z "$RESIDUAL" ]; then
    print_check OK "Flags /tmp" "aucun (propre)"
else
    FLAG_COUNT=$(echo "$RESIDUAL" | wc -l | tr -d ' ')
    if [ "$FIX_MODE" = "--fix" ]; then
        FLAGS_PATHS=$(echo "$RESIDUAL" | awk '{print "/tmp/"$1}' | tr '\n' ' ')
        docker exec medicore_elt_batch sh -c "rm -f $FLAGS_PATHS" 2>/dev/null
        print_check FIX "Flags /tmp" "$FLAG_COUNT supprime(s)"
        echo "    Flags supprimes :"
        echo "$RESIDUAL" | sed 's/^/      - /'
    else
        print_check WARN "Flags /tmp" "$FLAG_COUNT residuel(s) detecte(s)"
        echo "    Flags presents :"
        echo "$RESIDUAL" | sed 's/^/      - /'
        echo "    Pour les supprimer : ./scripts/pre_night_audit.sh --fix"
    fi
fi

# --- Resume des fixes appliques --------------------------------------------
if [ "$FIX_MODE" = "--fix" ] && [ ${#APPLIED_FIXES[@]} -gt 0 ]; then
    echo ""
    echo "--- Corrections automatiques appliquees ---"
    for fix in "${APPLIED_FIXES[@]}"; do
        echo "  - $fix"
    done
fi

# --- Corrections admin Windows : auto-elevation via UAC ---------------------
if [ "$FIX_MODE" = "--fix" ] && [ "$ADMIN_FIXES_NEEDED" -gt 0 ]; then
    echo ""
    echo "--- Application des corrections admin Windows ($ADMIN_FIXES_NEEDED) ---"
    ADMIN_SCRIPT_WIN=$(cygpath -w "$ADMIN_FIX_SCRIPT" 2>/dev/null || echo "$ADMIN_FIX_SCRIPT")
    echo "  Lancement PowerShell elevee via UAC..."
    echo "  >>> Cliquer 'Oui' sur la fenetre UAC qui s'ouvre <<<"
    # -Wait : attendre que la fenetre PS admin se ferme avant de continuer
    # -Verb RunAs : declenche le prompt UAC
    # PassThru + ExitCode pour capturer le succes
    powershell.exe -NoProfile -Command "
        \$p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '$ADMIN_SCRIPT_WIN'
        exit \$p.ExitCode
    " 2>&1
    UAC_RC=$?
    if [ $UAC_RC -eq 0 ]; then
        print_check FIX "Admin Windows fixes" "$ADMIN_FIXES_NEEDED correction(s) appliquee(s) via UAC"
    else
        print_check WARN "Admin Windows fixes" "UAC refuse ou erreur (code $UAC_RC) — relancer ou appliquer manuellement"
        echo "    Script : $ADMIN_SCRIPT_WIN"
    fi
fi

# --- Application .wslconfig : wsl --shutdown automatique --------------------
if [ "$FIX_MODE" = "--fix" ] && [ "$WSL_NEEDS_SHUTDOWN" = "1" ]; then
    echo ""
    echo "--- Application .wslconfig : wsl --shutdown ---"
    echo "  Arret WSL pour appliquer .wslconfig (Docker va redemarrer)..."
    powershell.exe -NoProfile -Command "wsl --shutdown" 2>&1
    echo "  Attente redemarrage Docker (jusqu'a 90s max)..."
    # Attendre que Docker redemarre les conteneurs (restart: unless-stopped)
    for i in $(seq 1 18); do
        sleep 5
        if docker ps --filter "name=medicore_elt_batch" --filter "status=running" --format "{{.Names}}" 2>/dev/null | grep -q "medicore_elt_batch"; then
            print_check FIX "wsl --shutdown" "WSL redemarre, Docker remonte (apres ${i}x5s)"
            break
        fi
        if [ "$i" = "18" ]; then
            print_check WARN "wsl --shutdown" "Docker met plus de 90s a remonter, verifier manuellement"
        fi
    done
fi

# --- Verdict ---------------------------------------------------------------
echo ""
echo "========================================================================="
if [ "$FAIL_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
    echo "  VERDICT : GO - tout est pret pour le batch nocturne"
elif [ "$FAIL_COUNT" -eq 0 ]; then
    echo "  VERDICT : GO avec ${WARN_COUNT} warning(s) - revoir les warnings"
else
    echo "  VERDICT : NO-GO - ${FAIL_COUNT} erreur(s) critique(s) a corriger"
fi
echo "========================================================================="

exit $FAIL_COUNT
