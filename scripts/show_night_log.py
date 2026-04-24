"""Extrait les phases nocturnes des logs Docker."""
import subprocess

result = subprocess.run(
    ['docker', 'logs', '--since', '14h', 'medicore_elt_batch'],
    capture_output=True, timeout=30,
)

output = (result.stdout or b'') + (result.stderr or b'')
text = output.decode('utf-8', errors='replace')

keywords = [
    'Mode nuit:', 'ref-reload', 'post-reload', 'pipeline-maintenance',
    'RESUME BULK', 'RAPPORT GLOBAL', 'Finished running', 'Phase freshness',
    'CDC pre-reload', 'Audit purge', 'Backup Metabase',
    'PIPELINE MAINTENANCE', 'Phase dbt', 'Phase ref',
]

for line in text.split('\n'):
    if any(k in line for k in keywords):
        print(line.strip()[:130])
