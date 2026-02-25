-- Test d'unicité composite (PHA_ID, FOU_ID) sur RAW_FOURNISSEURS
-- Retourne les doublons s'il y en a (le test passe si 0 ligne retournée)
select
    PHA_ID,
    FOU_ID,
    count(*) as nb
from {{ source('mysql_raw', 'RAW_FOURNISSEURS') }}
group by PHA_ID, FOU_ID
having count(*) > 1
