-- back compat for old kwarg name
  
  begin;
    
        
            
                
                
            
                
                
            
                
                
            
                
                
            
        
    

    

    merge into MEDICORE.STAGING.stg_manqhistory as DBT_INTERNAL_DEST
        using MEDICORE.STAGING.stg_manqhistory__dbt_tmp as DBT_INTERNAL_SOURCE
        on (
                    DBT_INTERNAL_SOURCE.PHA_ID = DBT_INTERNAL_DEST.PHA_ID
                ) and (
                    DBT_INTERNAL_SOURCE.MNQ_DATE = DBT_INTERNAL_DEST.MNQ_DATE
                ) and (
                    DBT_INTERNAL_SOURCE.PRD_ID = DBT_INTERNAL_DEST.PRD_ID
                ) and (
                    DBT_INTERNAL_SOURCE.FAC_ID = DBT_INTERNAL_DEST.FAC_ID
                )

    
    when matched then update set
        "PHA_ID" = DBT_INTERNAL_SOURCE."PHA_ID","MNQ_DATE" = DBT_INTERNAL_SOURCE."MNQ_DATE","PRD_ID" = DBT_INTERNAL_SOURCE."PRD_ID","FAC_ID" = DBT_INTERNAL_SOURCE."FAC_ID","EN_LIGNES" = DBT_INTERNAL_SOURCE."EN_LIGNES","EN_BOITES" = DBT_INTERNAL_SOURCE."EN_BOITES","EN_CLIENTS" = DBT_INTERNAL_SOURCE."EN_CLIENTS","LOADED_AT" = DBT_INTERNAL_SOURCE."LOADED_AT"
    

    when not matched then insert
        ("PHA_ID", "MNQ_DATE", "PRD_ID", "FAC_ID", "EN_LIGNES", "EN_BOITES", "EN_CLIENTS", "LOADED_AT")
    values
        ("PHA_ID", "MNQ_DATE", "PRD_ID", "FAC_ID", "EN_LIGNES", "EN_BOITES", "EN_CLIENTS", "LOADED_AT")

;
    commit;