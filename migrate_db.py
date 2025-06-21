#!/usr/bin/env python3
"""
Database migration script for Swarm Multi-Agent System
Handles migration from SQLite to PostgreSQL for production deployment
"""

import os
import sys
import sqlite3
import psycopg2
import json
from datetime import datetime
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config import config

class DatabaseMigrator:
    """Handles database migration from SQLite to PostgreSQL"""
    
    def __init__(self, sqlite_path: str, postgres_url: str):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        
    def connect_sqlite(self):
        """Connect to SQLite database"""
        return sqlite3.connect(self.sqlite_path)
    
    def connect_postgres(self):
        """Connect to PostgreSQL database"""
        return psycopg2.connect(self.postgres_url)
    
    def export_sqlite_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Export all data from SQLite database"""
        data = {}
        
        try:
            conn = self.connect_sqlite()
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                if table.startswith('sqlite_'):
                    continue  # Skip SQLite system tables
                
                print(f"Exporting table: {table}")
                cursor.execute(f"SELECT * FROM {table}")
                
                # Get column names
                columns = [description[0] for description in cursor.description]
                
                # Get all rows
                rows = cursor.fetchall()
                
                # Convert to list of dictionaries
                table_data = []
                for row in rows:
                    row_dict = {}
                    for i, value in enumerate(row):
                        row_dict[columns[i]] = value
                    table_data.append(row_dict)
                
                data[table] = table_data
                print(f"Exported {len(table_data)} rows from {table}")
            
            conn.close()
            return data
            
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
            return {}
        except Exception as e:
            print(f"Error exporting SQLite data: {e}")
            return {}
    
    def create_postgres_tables(self):
        """Create tables in PostgreSQL database"""
        try:
            conn = self.connect_postgres()
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    agent_id VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    response TEXT,
                    model_used VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                );
            """)
            
            # Create agent_memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id SERIAL PRIMARY KEY,
                    agent_id VARCHAR(50) NOT NULL,
                    memory_key VARCHAR(255) NOT NULL,
                    memory_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_id, memory_key)
                );
            """)
            
            # Create file_operations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_operations (
                    id SERIAL PRIMARY KEY,
                    agent_id VARCHAR(50) NOT NULL,
                    operation VARCHAR(50) NOT NULL,
                    file_path TEXT NOT NULL,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                );
            """)
            
            # Create email_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_logs (
                    id SERIAL PRIMARY KEY,
                    agent_id VARCHAR(50) NOT NULL,
                    message_id VARCHAR(255),
                    recipient VARCHAR(255) NOT NULL,
                    subject TEXT,
                    status VARCHAR(50) DEFAULT 'sent',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered_at TIMESTAMP,
                    metadata JSONB
                );
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_agent_id ON conversations(agent_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_memory_agent_id ON agent_memory(agent_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_agent_id ON file_operations(agent_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_logs_agent_id ON email_logs(agent_id);")
            
            conn.commit()
            conn.close()
            print("PostgreSQL tables created successfully")
            
        except psycopg2.Error as e:
            print(f"PostgreSQL error: {e}")
        except Exception as e:
            print(f"Error creating PostgreSQL tables: {e}")
    
    def import_postgres_data(self, data: Dict[str, List[Dict[str, Any]]]):
        """Import data into PostgreSQL database"""
        try:
            conn = self.connect_postgres()
            cursor = conn.cursor()
            
            for table_name, table_data in data.items():
                if not table_data:
                    continue
                
                print(f"Importing {len(table_data)} rows into {table_name}")
                
                # Get column names from first row
                columns = list(table_data[0].keys())
                
                # Create INSERT statement
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join(columns)
                insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                
                # Prepare data for insertion
                rows_to_insert = []
                for row in table_data:
                    row_values = []
                    for col in columns:
                        value = row[col]
                        # Handle JSON fields
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value)
                        row_values.append(value)
                    rows_to_insert.append(tuple(row_values))
                
                # Insert data in batches
                batch_size = 100
                for i in range(0, len(rows_to_insert), batch_size):
                    batch = rows_to_insert[i:i + batch_size]
                    try:
                        cursor.executemany(insert_sql, batch)
                        conn.commit()
                    except psycopg2.Error as e:
                        print(f"Error inserting batch for {table_name}: {e}")
                        conn.rollback()
                
                print(f"Successfully imported {table_name}")
            
            conn.close()
            print("Data import completed")
            
        except psycopg2.Error as e:
            print(f"PostgreSQL error during import: {e}")
        except Exception as e:
            print(f"Error importing data: {e}")
    
    def migrate(self):
        """Perform complete migration"""
        print("Starting database migration...")
        print(f"Source: {self.sqlite_path}")
        print(f"Target: {self.postgres_url}")
        
        # Step 1: Create PostgreSQL tables
        print("\n1. Creating PostgreSQL tables...")
        self.create_postgres_tables()
        
        # Step 2: Export SQLite data
        print("\n2. Exporting SQLite data...")
        data = self.export_sqlite_data()
        
        if not data:
            print("No data to migrate")
            return
        
        # Step 3: Import data to PostgreSQL
        print("\n3. Importing data to PostgreSQL...")
        self.import_postgres_data(data)
        
        print("\nMigration completed successfully!")

def main():
    """Main migration function"""
    # Default paths
    sqlite_path = os.path.join(os.path.dirname(__file__), 'src', 'database', 'app.db')
    
    # Get PostgreSQL URL from environment or config
    postgres_url = os.getenv('DATABASE_URL') or config.database_url
    
    if not postgres_url or postgres_url.startswith('sqlite'):
        print("Error: PostgreSQL DATABASE_URL not configured")
        print("Please set the DATABASE_URL environment variable")
        sys.exit(1)
    
    if not os.path.exists(sqlite_path):
        print(f"SQLite database not found at: {sqlite_path}")
        print("Creating empty migration (no existing data to migrate)")
        migrator = DatabaseMigrator(sqlite_path, postgres_url)
        migrator.create_postgres_tables()
        return
    
    # Perform migration
    migrator = DatabaseMigrator(sqlite_path, postgres_url)
    migrator.migrate()

if __name__ == "__main__":
    main()

