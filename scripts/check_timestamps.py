"""Verifie les timestamps des tables RAW."""
import snowflake.connector, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / '.env')
conn = snowflake.connector.connect(account=os.getenv('SNOWFLAKE_ACCOUNT'),user=os.getenv('SNOWFLAKE_USER'),password=os.getenv('SNOWFLAKE_PASSWORD'),database='MEDICORE_PROD',warehouse='MEDICORE_WH',schema='RAW')
cur = conn.cursor()
for t in ['RAW_PHARMACIE','RAW_PRODUITS','RAW_FOURNISSEURS','RAW_DAYBYDAY','RAW_FACTURES','RAW_COMMANDES']:
    cur.execute(f'SELECT MAX(CDC_TIMESTAMP) FROM {t}')
    print(f'{t}: {cur.fetchone()[0]}')
cur.close()
conn.close()
