"""
Module partagé de masquage PII - RGPD compliant
Utilisé par daily_cdc_batch.py (CDC) et bulk_load.py (bulk load initial)
"""

import hashlib
from typing import Dict


def mask_pii(event: Dict, table_name: str) -> Dict:
    """Masquage PII MediCore - RGPD compliant"""
    masked = event.copy()

    # RAW_ORDERS : Patients + Opérateur
    if 'ORDERS' in table_name.upper():
        # Opérateur pharmacie
        if 'ORD_OPERATEUR' in masked:
            masked['ORD_OPERATEUR'] = f"USER_{hashlib.md5(str(masked['ORD_OPERATEUR']).encode()).hexdigest()[:4].upper()}"

        # Âge patient → quartile anonyme
        if 'ORD_CLIENT_AGE_MONTHS' in masked and masked['ORD_CLIENT_AGE_MONTHS']:
            age_months = int(masked['ORD_CLIENT_AGE_MONTHS'])
            quartile = (age_months // 36) * 36  # Par tranche 3 ans
            masked['ORD_CLIENT_AGE_MONTHS'] = f"{quartile}-{quartile+35}m"

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
