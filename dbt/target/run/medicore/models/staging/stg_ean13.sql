-- back compat for old kwarg name
  
  begin;
    
        
            
                
                
            
                
                
            
                
                
            
        
    

    

    merge into MEDICORE.STAGING.stg_ean13 as DBT_INTERNAL_DEST
        using MEDICORE.STAGING.stg_ean13__dbt_tmp as DBT_INTERNAL_SOURCE
        on (
                    DBT_INTERNAL_SOURCE.PHA_ID = DBT_INTERNAL_DEST.PHA_ID
                ) and (
                    DBT_INTERNAL_SOURCE.EAN_13 = DBT_INTERNAL_DEST.EAN_13
                ) and (
                    DBT_INTERNAL_SOURCE.PRD_ID = DBT_INTERNAL_DEST.PRD_ID
                )

    
    when matched then update set
        "PHA_ID" = DBT_INTERNAL_SOURCE."PHA_ID","EAN_13" = DBT_INTERNAL_SOURCE."EAN_13","PRD_ID" = DBT_INTERNAL_SOURCE."PRD_ID","LOADED_AT" = DBT_INTERNAL_SOURCE."LOADED_AT"
    

    when not matched then insert
        ("PHA_ID", "EAN_13", "PRD_ID", "LOADED_AT")
    values
        ("PHA_ID", "EAN_13", "PRD_ID", "LOADED_AT")

;
    commit;