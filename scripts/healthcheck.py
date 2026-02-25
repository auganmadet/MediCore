#!/usr/bin/env python3
import sys
import subprocess
import os
import snowflake.connector

def test_snowflake():
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            warehouse='MEDIcore_WH'
        )
        conn.close()
        return True
    except:
        return False

sys.exit(0 if test_snowflake() else 1)    
