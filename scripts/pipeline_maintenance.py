"""Orchestrateur de maintenance post-exécution du pipeline MediCore.

Execute a 04h30 FR (02h30 UTC) par batch_loop.sh, APRES la nuit complete.
Audit de l'etat produit par les phases nocturnes (ref_reload + dbt post-reload).

4 phases (Phase 1 Healthcheck ex-H1/H7 est maintenant couverte par
pre_night_healthcheck.py a 20h30 FR, 30 min avant le mode nuit) :

- Phase 2 : CDC          lag Kafka, DLQ, doublons RAW CDC, offsets
                          (C4 Debezium state et N2 config deja verifies en pre-night)
- Phase 3 : Bulk Load    lock, tables vides, reconciliation MySQL/SF, timestamps
                          (B6 schema drift deja verifie en pre-night via N8)
- Phase 4 : dbt          modeles en erreur, tests, freshness, MARTS vides
                          (parse run_results.json genere par dbt post-reload)
- Phase 5 : Metabase     P1-P10, provisionnement pharmacies

Hook optionnel : cost_monitoring (insert AUDIT + alerte Teams si seuil cout).

Usage :
    python scripts/pipeline_maintenance.py                      # toutes les phases
    python scripts/pipeline_maintenance.py --dry-run             # simulation
    python scripts/pipeline_maintenance.py --phase cdc          # une seule phase
    python scripts/pipeline_maintenance.py --phase bulk
    python scripts/pipeline_maintenance.py --phase dbt
    python scripts/pipeline_maintenance.py --phase metabase
    python scripts/pipeline_maintenance.py --fix-safe            # fix surs (batch_loop)
    python scripts/pipeline_maintenance.py --fix                 # tous les fix (manuel)
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

# Phase 1 (Healthcheck) retiree : couverte par pre_night_healthcheck.py a 20h30 FR
# avant la nuit. Les sous-checks C4 (cdc) et B6 (bulk) restent dans leurs scripts
# respectifs comme "defense en profondeur" (cout ~1s chacun).
PHASES = {
    'cdc': {
        'name': 'Phase 2 - CDC',
        'script': 'cdc_maintenance.py',
        'critical': False,
        'description': 'Lag Kafka, DLQ, doublons, offsets',
    },
    'bulk': {
        'name': 'Phase 3 - Bulk Load',
        'script': 'bulk_maintenance.py',
        'critical': False,
        'description': 'Lock, tables vides, reconciliation MySQL/Snowflake, timestamps',
    },
    'dbt': {
        'name': 'Phase 4 - dbt',
        'script': 'dbt_maintenance.py',
        'critical': False,
        'description': 'Modeles en erreur, tests echoues, freshness, MARTS vides',
    },
    'metabase': {
        'name': 'Phase 5 - Metabase',
        'script': 'metabase_maintenance.py',
        'critical': False,
        'description': 'P1-P10, provisionnement pharmacies',
    },
}


def run_phase(phase_key, fix_level, dry_run):
    """Execute une phase de maintenance.

    Args:
        phase_key: cle de la phase (healthcheck, cdc, bulk, dbt, metabase)
        fix_level: 'none' (detection seule), 'safe' (fix surs), 'all' (tous les fix)
        dry_run: simulation sans modification
    """
    phase = PHASES[phase_key]
    script_path = SCRIPTS_DIR / phase['script']

    if not script_path.exists():
        return 'SKIP', f'Script {phase["script"]} non trouve'

    # --fix-safe et --fix passent maintenant --fix-safe a tous les scripts
    # car les garde-fous sont integres dans chaque script individuel.
    # --fix passe --fix (force sans garde-fous sur certaines operations).
    cmd = [PYTHON, str(script_path)]

    if phase_key == 'metabase':
        # metabase_maintenance.py est toujours safe
        pass
    elif fix_level == 'all':
        cmd.append('--fix')
    elif fix_level == 'safe':
        cmd.append('--fix-safe')

    if dry_run and phase_key not in ('healthcheck',):
        cmd.append('--dry-run')

    try:
        # Timeout par phase : cdc rapide, bulk/dbt/metabase lents
        phase_timeouts = {
            'cdc': 300,
            'bulk': 1800,
            'dbt': 1800,
            'metabase': 600,
        }
        timeout = phase_timeouts.get(phase_key, 600)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Afficher la sortie
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                print(f'  {line}')

        if result.returncode == 0:
            return 'OK', ''
        elif result.returncode == 1:
            return 'FAIL', 'Problemes critiques detectes'
        elif result.returncode == 2:
            return 'WARN', 'Problemes non critiques detectes'
        else:
            return 'FAIL', f'Exit code {result.returncode}'

    except subprocess.TimeoutExpired:
        return 'TIMEOUT', f'Timeout apres 300s'
    except Exception as e:
        return 'ERROR', str(e)[:100]


def run_cost_monitoring(dry_run):
    """Hook post-phases : cout Snowflake (insert AUDIT + alerte Teams si seuil).

    Execute apres toutes les phases (les couts bulk/dbt de la nuit sont
    desormais visibles). Non bloquant : un echec ici ne stoppe pas le rapport.
    """
    script_path = SCRIPTS_DIR / 'cost_monitoring.py'
    if not script_path.exists():
        return 'SKIP', 'cost_monitoring.py absent'

    cmd = [PYTHON, str(script_path)]
    if dry_run:
        cmd.append('--dry-run')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                print(f'  {line}')
        if result.returncode == 0:
            return 'OK', ''
        return 'WARN', f'Exit code {result.returncode}'
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', 'Timeout 60s'
    except Exception as e:  # pylint: disable=broad-except
        return 'ERROR', str(e)[:100]


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline maintenance post-execution (4 phases : CDC, Bulk, dbt, Metabase)')
    parser.add_argument('--phase', choices=list(PHASES.keys()),
                        help='Executer une seule phase')
    fix_group = parser.add_mutually_exclusive_group()
    fix_group.add_argument('--fix-safe', action='store_true',
                           help='Fix surs uniquement : C2, D3, P1-P10 (mode batch_loop)')
    fix_group.add_argument('--fix', action='store_true',
                           help='Tous les fix : y compris B4, B5, D1/D2 (mode manuel)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulation sans modification')
    args = parser.parse_args()

    # Determiner le niveau de fix
    if args.fix:
        fix_level = 'all'
    elif args.fix_safe:
        fix_level = 'safe'
    else:
        fix_level = 'none'

    mode_label = {
        'none': 'detection',
        'safe': 'fix-safe (C2, D3, P1-P10)',
        'all': 'fix-all (inclut B4, B5, D1/D2)',
    }

    start_time = datetime.now(timezone.utc)

    print('=' * 70)
    print(f'  PIPELINE MAINTENANCE -- {start_time.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    print(f'  Mode: {"dry-run" if args.dry_run else mode_label[fix_level]}')
    print('=' * 70)

    phases_to_run = [args.phase] if args.phase else list(PHASES.keys())
    report = {}

    for phase_key in phases_to_run:
        phase = PHASES[phase_key]
        print(f'\n{"=" * 70}')
        print(f'  {phase["name"]}')
        print(f'  {phase["description"]}')
        print(f'{"=" * 70}')

        status, msg = run_phase(phase_key, fix_level, args.dry_run)
        report[phase_key] = {'status': status, 'msg': msg}

        if status == 'OK':
            print(f'\n  >> {phase["name"]}: OK')
        else:
            print(f'\n  >> {phase["name"]}: {status} {msg}')

        # Si phase critique echoue, stop (aucune phase n'est critique actuellement,
        # Phase 1 Healthcheck etant desormais couverte par pre_night_healthcheck)
        if phase['critical'] and status in ('FAIL', 'TIMEOUT', 'ERROR'):
            print(f'\n  STOP: {phase["name"]} est critique — phases suivantes sautees')
            for remaining in phases_to_run[phases_to_run.index(phase_key) + 1:]:
                report[remaining] = {'status': 'SKIP', 'msg': 'Phase critique echouee'}
            break

        # Pause entre phases
        if phase_key != phases_to_run[-1]:
            time.sleep(2)

    # Hook final : cost_monitoring apres toutes les phases (cout nuit visible)
    if not args.phase:  # uniquement en mode full-run, pas sur une phase isolee
        print(f'\n{"=" * 70}')
        print(f'  Cost monitoring (hook post-phases)')
        print(f'{"=" * 70}')
        cost_status, cost_msg = run_cost_monitoring(args.dry_run)
        report['cost_monitoring'] = {'status': cost_status, 'msg': cost_msg}
        if cost_status == 'OK':
            print(f'  >> Cost monitoring: OK')
        else:
            print(f'  >> Cost monitoring: {cost_status} {cost_msg}')

    # Rapport final
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f'\n{"=" * 70}')
    print(f'  RAPPORT GLOBAL — {elapsed:.0f}s')
    print(f'{"=" * 70}')

    for phase_key, result in report.items():
        status = result['status']
        indicator = {'OK': 'OK', 'FAIL': 'FAIL', 'WARN': 'WARN',
                     'SKIP': 'SKIP', 'TIMEOUT': 'TIMEOUT', 'ERROR': 'ERROR'}
        label = PHASES[phase_key]['name'] if phase_key in PHASES else 'Hook - Cost monitoring'
        print(f'  {label:.<45} {indicator.get(status, status)}')

    # Cost monitoring n'est pas compte dans le decompte OK/FAIL (hook non bloquant)
    counted = {k: v for k, v in report.items() if k in PHASES}
    nb_ok = sum(1 for r in counted.values() if r['status'] == 'OK')
    nb_fail = sum(1 for r in counted.values() if r['status'] in ('FAIL', 'ERROR', 'TIMEOUT'))
    nb_warn = sum(1 for r in counted.values() if r['status'] == 'WARN')
    nb_skip = sum(1 for r in counted.values() if r['status'] == 'SKIP')

    print(f'\n  Total: {nb_ok} OK, {nb_fail} FAIL, {nb_warn} WARN, {nb_skip} SKIP')

    if nb_fail > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
