"""Vérifie que les cartes Metabase correspondent aux SQL documentés dans Dashboards.md."""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = sys.argv[1]
BASE = 'http://localhost:3000/api'


def api_get(path):
    """GET sur l'API Metabase."""
    req = urllib.request.Request(f'{BASE}/{path}', headers={'X-Metabase-Session': TOKEN})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_post(path, data):
    """POST sur l'API Metabase."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='POST',
        headers={'X-Metabase-Session': TOKEN, 'Content-Type': 'application/json; charset=utf-8'}
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


issues = []

for did in range(2, 18):
    d = api_get(f'dashboard/{did}')
    dname = d['name']
    print(f'\n=== {dname} ===')

    for dc in d.get('dashcards', []):
        card = dc.get('card', {})
        cid = card.get('id')
        if not cid:
            continue
        cname = card.get('name', '?')

        # Get full card to check query type and source table
        full = api_get(f'card/{cid}')
        stage = full['dataset_query']['stages'][0]
        card_type = stage.get('lib/type', '')

        if 'native' in card_type:
            sql = stage.get('native', '').strip()
            # Check table referenced
            table = 'SQL natif'
            if 'MART_KPI_MARGE_PAR_PRODUIT' in sql:
                table = 'MART_KPI_MARGE_PAR_PRODUIT'
            elif 'MART_KPI_MARGE_PAR_UNIVERS' in sql:
                table = 'MART_KPI_MARGE_PAR_UNIVERS'
            elif 'MART_KPI_RUPTURES_PAR_PRODUIT' in sql:
                table = 'MART_KPI_RUPTURES_PAR_PRODUIT'
            elif 'MART_KPI_ECOULEMENT_PAR_FOURNISSEUR' in sql:
                table = 'MART_KPI_ECOULEMENT_PAR_FOURNISSEUR'
            elif 'MART_KPI_VENTES_PAR_PRODUIT' in sql:
                table = 'MART_KPI_VENTES_PAR_PRODUIT'
            elif 'MART_KPI_GENERIQUE_MARGE' in sql:
                table = 'MART_KPI_GENERIQUE_MARGE'
            elif 'FACT_TRESORERIE' in sql:
                table = 'FACT_TRESORERIE'
            elif 'FACT_VENTES' in sql:
                table = 'FACT_VENTES'
            elif 'MART_KPI_TRESORERIE' in sql:
                table = 'MART_KPI_TRESORERIE'
            elif 'MART_KPI_MARGE' in sql:
                table = 'MART_KPI_MARGE'
            else:
                table = 'SQL natif (autre)'

            # Test query
            try:
                result = api_post(f'card/{cid}/query', {})
                err = result.get('error')
                rows = result.get('data', {}).get('rows', [])
                status = f'ERROR: {err[:60]}' if err else f'{len(rows)} rows'
            except Exception as e:
                status = f'EXCEPTION: {str(e)[:60]}'
                err = str(e)

            if err:
                issues.append(('QUERY_ERROR', dname, cname, cid, status))

            print(f'  [{cid}] {cname}')
            print(f'       Type: SQL natif | Table: {table} | {status}')

        else:
            # MBQL card - get source table
            src_table = stage.get('source-table')
            agg = stage.get('aggregation', [])
            agg_types = [a[0] for a in agg] if agg else ['no agg']

            # Resolve table name
            try:
                tbl = api_get(f'table/{src_table}')
                table_name = tbl.get('name', f'table_{src_table}')
            except Exception:
                table_name = f'table_{src_table}'

            # Test query
            try:
                result = api_post(f'card/{cid}/query', {})
                err = result.get('error')
                rows = result.get('data', {}).get('rows', [])
                status = f'ERROR: {err[:60]}' if err else f'{len(rows)} rows'
            except Exception as e:
                status = f'EXCEPTION: {str(e)[:60]}'
                err = str(e)

            if err:
                issues.append(('QUERY_ERROR', dname, cname, cid, status))

            print(f'  [{cid}] {cname}')
            print(f'       Type: MBQL | Table: {table_name} | Agg: {agg_types} | {status}')

# Summary
print(f'\n{"="*60}')
print(f'RÉSUMÉ : {len(issues)} erreurs')
print(f'{"="*60}')
for i in issues:
    print(f'  {i[1]} > {i[2]} (id={i[3]}): {i[4]}')

if not issues:
    print('  Toutes les cartes retournent des données sans erreur.')
