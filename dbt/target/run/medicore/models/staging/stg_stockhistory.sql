-- back compat for old kwarg name
  
  begin;
    
        
            
                
                
            
                
                
            
                
                
            
        
    

    

    merge into MEDICORE.STAGING.stg_stockhistory as DBT_INTERNAL_DEST
        using MEDICORE.STAGING.stg_stockhistory__dbt_tmp as DBT_INTERNAL_SOURCE
        on (
                    DBT_INTERNAL_SOURCE.PHA_ID = DBT_INTERNAL_DEST.PHA_ID
                ) and (
                    DBT_INTERNAL_SOURCE.PRD_ID = DBT_INTERNAL_DEST.PRD_ID
                ) and (
                    DBT_INTERNAL_SOURCE.STH_DATE = DBT_INTERNAL_DEST.STH_DATE
                )

    
    when matched then update set
        "PHA_ID" = DBT_INTERNAL_SOURCE."PHA_ID","PRD_ID" = DBT_INTERNAL_SOURCE."PRD_ID","STH_DATE" = DBT_INTERNAL_SOURCE."STH_DATE","STH_STOCKDELTA" = DBT_INTERNAL_SOURCE."STH_STOCKDELTA","STH_STOCK" = DBT_INTERNAL_SOURCE."STH_STOCK","STH_PRIXTARIF" = DBT_INTERNAL_SOURCE."STH_PRIXTARIF","STH_PRIXPUBLIC" = DBT_INTERNAL_SOURCE."STH_PRIXPUBLIC","STH_PAMP" = DBT_INTERNAL_SOURCE."STH_PAMP","STH_PANET" = DBT_INTERNAL_SOURCE."STH_PANET","LOADED_AT" = DBT_INTERNAL_SOURCE."LOADED_AT"
    

    when not matched then insert
        ("PHA_ID", "PRD_ID", "STH_DATE", "STH_STOCKDELTA", "STH_STOCK", "STH_PRIXTARIF", "STH_PRIXPUBLIC", "STH_PAMP", "STH_PANET", "LOADED_AT")
    values
        ("PHA_ID", "PRD_ID", "STH_DATE", "STH_STOCKDELTA", "STH_STOCK", "STH_PRIXTARIF", "STH_PRIXPUBLIC", "STH_PAMP", "STH_PANET", "LOADED_AT")

;
    commit;