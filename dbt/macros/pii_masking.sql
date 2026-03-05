{#
  Macro de masquage PII par hash MD5 tronqué.
  Produit une valeur pseudonymisée déterministe : PREFIX_xxxx

  Args:
    column_name: nom de la colonne à masquer
    prefix: préfixe lisible (ex: 'PHARM', 'USER', 'FOU', 'ADDR')
    hash_length: longueur du hash tronqué (défaut: 4)

  Exemple:
    {{ pii_mask('PHA_NOM', 'PHARM') }}  →  'PHARM_' || LEFT(MD5(CAST(PHA_NOM AS VARCHAR)), 4)
#}

{% macro pii_mask(column_name, prefix, hash_length=4) %}
'{{ prefix }}_' || LEFT(MD5(CAST({{ column_name }} AS VARCHAR)), {{ hash_length }})
{% endmacro %}
