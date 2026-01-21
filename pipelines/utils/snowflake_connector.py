import snowflake.connector
import os

class SnowflakeConnector:
    def __init__(self, schema='RAW'):
        self.conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            role='MEDIcore_DBT_EXECUTOR',
            database='MEDIcore',
            warehouse='MEDIcore_WH',
            schema=schema
        )
    
    def execute(self, query):
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()
    
    def insert_raw(self, table_name, data):
        cursor = self.conn.cursor()
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        values = list(data.values())
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor.execute(query, values)
        self.conn.commit()
