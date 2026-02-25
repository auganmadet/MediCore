"""
Module partagé de masquage PII - RGPD compliant
Utilisé par daily_cdc_batch.py (CDC) et bulk_load.py (bulk load initial)
--> n'est plus utilisé car le masking PII se fait désormais par les models dbt
"""

import hashlib
from typing import Dict

import pandas as pd


def mask_pii(event: Dict, table_name: str) -> Dict:
    """Masquage PII MediCore - RGPD compliant"""
    masked = event.copy()

    # RAW_ORDERS : Patients + Opérateur
    if 'ORDERS' in table_name.upper():
        # Opérateur pharmacie
        if 'ORD_OPERATEUR' in masked:
            masked['ORD_OPERATEUR'] = f"USER_{hashlib.md5(str(masked['ORD_OPERATEUR']).encode()).hexdigest()[:4].upper()}"

        # Âge patient → quartile anonyme (reste NUMBER pour compatibilité Parquet/Snowflake)
        if 'ORD_CLIENT_AGE_MONTHS' in masked and masked['ORD_CLIENT_AGE_MONTHS'] is not None:
            age_months = int(masked['ORD_CLIENT_AGE_MONTHS'])
            masked['ORD_CLIENT_AGE_MONTHS'] = (age_months // 36) * 36  # Par tranche 3 ans

        # Département → masqué
        if 'ORD_CLIENT_DEPARTEMENT' in masked:
            masked['ORD_CLIENT_DEPARTEMENT'] = f"DEP{str(masked['ORD_CLIENT_DEPARTEMENT'])[:2]}***"

    # RAW_PHARMACIE : Nom officine
    if 'PHARMACIE' in table_name.upper():
        if 'PHA_NOM' in masked:
            masked['PHA_NOM'] = f"PHARM_{hashlib.md5(str(masked['PHA_NOM']).encode()).hexdigest()[:4].upper()}"

    # RAW_PHARMACIES : Coordonnées sensibles
    if 'PHARMACIES' in table_name.upper():
        # ADELI pharmacien
        if 'adeli' in masked:
            masked['adeli'] = f"***{masked['adeli'][-4:]}"
        # Nom officine
        if 'name' in masked:
            masked['name'] = f"PHARM_{hashlib.md5(str(masked['name']).encode()).hexdigest()[:4].upper()}"
        # Téléphone
        if 'phone' in masked:
            phone = str(masked['phone']).replace(' ', '').replace('.', '')
            masked['phone'] = f"{phone[:2]}**{phone[-4:]}"
        # Code postal
        if 'postal_code' in masked:
            masked['postal_code'] = f"{masked['postal_code'][:2]}***"

    # RAW_MEDIPRIX_FACTURES
    if 'MEDIPRIX_FACTURES' in table_name.upper():
        if 'ORD_OPERATEUR' in masked:
            masked['ORD_OPERATEUR'] = f"USER_{hashlib.md5(str(masked['ORD_OPERATEUR']).encode()).hexdigest()[:4].upper()}"
        if 'PHA_NOM' in masked:
            masked['PHA_NOM'] = f"PHARM_{hashlib.md5(str(masked['PHA_NOM']).encode()).hexdigest()[:4].upper()}"

    # Fournisseurs B2B = public → NON masqué
    if 'FOURNISSEURS' in table_name.upper():
        pass

    return masked


def _md5_hash_series(series):
    """Hash MD5 via list comprehension (2-3x plus rapide que Series.apply sur strings)."""
    vals = series.astype(str).values
    return pd.Series(
        [hashlib.md5(v.encode()).hexdigest()[:4].upper() for v in vals],
        index=series.index
    )


def mask_pii_dataframe(df, table_name: str):
    """Masquage PII vectorisé sur DataFrame - même logique que mask_pii() mais sans iterrows()."""

    tn = table_name.upper()

    # RAW_ORDERS : Patients + Opérateur
    if 'ORDERS' in tn:
        if 'ORD_OPERATEUR' in df.columns:
            df['ORD_OPERATEUR'] = 'USER_' + _md5_hash_series(df['ORD_OPERATEUR'])
        if 'ORD_CLIENT_AGE_MONTHS' in df.columns:
            mask = df['ORD_CLIENT_AGE_MONTHS'].notna()
            df.loc[mask, 'ORD_CLIENT_AGE_MONTHS'] = (df.loc[mask, 'ORD_CLIENT_AGE_MONTHS'].astype(int) // 36) * 36
        if 'ORD_CLIENT_DEPARTEMENT' in df.columns:
            df['ORD_CLIENT_DEPARTEMENT'] = 'DEP' + df['ORD_CLIENT_DEPARTEMENT'].astype(str).str[:2] + '***'

    # RAW_PHARMACIE : Nom officine
    if 'PHARMACIE' in tn:
        if 'PHA_NOM' in df.columns:
            df['PHA_NOM'] = 'PHARM_' + _md5_hash_series(df['PHA_NOM'])

    # RAW_PHARMACIES : Coordonnées sensibles
    if 'PHARMACIES' in tn:
        if 'adeli' in df.columns:
            df['adeli'] = '***' + df['adeli'].astype(str).str[-4:]
        if 'name' in df.columns:
            df['name'] = 'PHARM_' + _md5_hash_series(df['name'])
        if 'phone' in df.columns:
            clean = df['phone'].astype(str).str.replace(' ', '', regex=False).str.replace('.', '', regex=False)
            df['phone'] = clean.str[:2] + '**' + clean.str[-4:]
        if 'postal_code' in df.columns:
            df['postal_code'] = df['postal_code'].astype(str).str[:2] + '***'

    # RAW_MEDIPRIX_FACTURES
    if 'MEDIPRIX_FACTURES' in tn:
        if 'ORD_OPERATEUR' in df.columns:
            df['ORD_OPERATEUR'] = 'USER_' + _md5_hash_series(df['ORD_OPERATEUR'])
        if 'PHA_NOM' in df.columns:
            df['PHA_NOM'] = 'PHARM_' + _md5_hash_series(df['PHA_NOM'])

    return df
