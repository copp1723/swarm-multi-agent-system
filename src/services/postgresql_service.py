"""
PostgreSQL Configuration and Connection Helper
Handles PostgreSQL-specific setup, connection pooling, and optimization
"""

import os
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


class PostgreSQLManager:
    """Manages PostgreSQL connections and configuration"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.parsed_url = urlparse(database_url)
        self.connection_params = self._parse_connection_params()
        
    def _parse_connection_params(self) -> Dict[str, Any]:
        """Parse database URL into connection parameters"""
        return {
            'host': self.parsed_url.hostname,
            'port': self.parsed_url.port or 5432,
            'database': self.parsed_url.path.lstrip('/'),
            'username': self.parsed_url.username,
            'password': self.parsed_url.password,
        }
    
    def test_connection(self) -> bool:
        """Test PostgreSQL connection"""
        try:
            conn = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params['port'],
                database=self.connection_params['database'],
                user=self.connection_params['username'],
                password=self.connection_params['password']
            )
            conn.close()
            logger.info("✅ PostgreSQL connection successful")
            return True
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}")
            return False
    
    def create_database_if_not_exists(self, database_name: str) -> bool:
        """Create database if it doesn't exist"""
        try:
            # Connect to postgres database to create new database
            conn = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params['port'],
                database='postgres',  # Connect to default postgres database
                user=self.connection_params['username'],
                password=self.connection_params['password']
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
                (database_name,)
            )
            
            if cursor.fetchone():
                logger.info(f"📊 Database '{database_name}' already exists")
            else:
                # Create database
                cursor.execute(f'CREATE DATABASE "{database_name}"')
                logger.info(f"✅ Created database '{database_name}'")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create database: {e}")
            return False
    
    def get_optimized_engine_config(self) -> Dict[str, Any]:
        """Get optimized SQLAlchemy engine configuration for PostgreSQL"""
        return {
            'poolclass': QueuePool,
            'pool_size': 20,
            'max_overflow': 30,
            'pool_timeout': 30,
            'pool_recycle': 3600,  # 1 hour
            'pool_pre_ping': True,
            'echo': False,
            'connect_args': {
                'connect_timeout': 10,
                'application_name': 'swarm_multi_agent_system',
                'options': '-c timezone=UTC'
            }
        }
    
    def create_optimized_engine(self):
        """Create optimized SQLAlchemy engine for PostgreSQL"""
        config = self.get_optimized_engine_config()
        return create_engine(self.database_url, **config)
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get PostgreSQL database information"""
        try:
            engine = self.create_optimized_engine()
            
            with engine.connect() as conn:
                # Get PostgreSQL version
                version_result = conn.execute(text("SELECT version()"))
                version = version_result.scalar()
                
                # Get database size
                size_result = conn.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """))
                size = size_result.scalar()
                
                # Get connection count
                conn_result = conn.execute(text("""
                    SELECT count(*) FROM pg_stat_activity 
                    WHERE datname = current_database()
                """))
                connections = conn_result.scalar()
                
                # Get table count
                table_result = conn.execute(text("""
                    SELECT count(*) FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """))
                tables = table_result.scalar()
                
                return {
                    'version': version,
                    'size': size,
                    'active_connections': connections,
                    'table_count': tables,
                    'database_name': self.connection_params['database'],
                    'host': self.connection_params['host'],
                    'port': self.connection_params['port']
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get database info: {e}")
            return {}
    
    def optimize_database(self) -> bool:
        """Apply PostgreSQL optimizations"""
        try:
            engine = self.create_optimized_engine()
            
            with engine.connect() as conn:
                # Enable some PostgreSQL optimizations
                optimizations = [
                    "SET shared_preload_libraries = 'pg_stat_statements'",
                    "SET log_statement = 'all'",
                    "SET log_min_duration_statement = 1000",  # Log slow queries
                ]
                
                for optimization in optimizations:
                    try:
                        conn.execute(text(optimization))
                        logger.info(f"✅ Applied: {optimization}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not apply optimization: {optimization} - {e}")
                
                conn.commit()
                
            logger.info("✅ Database optimizations applied")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to optimize database: {e}")
            return False
    
    def create_indexes(self) -> bool:
        """Create performance indexes"""
        try:
            engine = self.create_optimized_engine()
            
            with engine.connect() as conn:
                indexes = [
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_username ON \"user\" (username)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_email ON \"user\" (email)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_active ON \"user\" (is_active)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_created ON \"user\" (created_at)",
                ]
                
                for index_sql in indexes:
                    try:
                        conn.execute(text(index_sql))
                        logger.info(f"✅ Created index: {index_sql.split('idx_')[1].split(' ')[0]}")
                    except Exception as e:
                        logger.warning(f"⚠️ Index creation failed: {e}")
                
                conn.commit()
                
            logger.info("✅ Performance indexes created")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create indexes: {e}")
            return False


def setup_postgresql(database_url: str) -> bool:
    """Complete PostgreSQL setup and optimization"""
    logger.info("🐘 Setting up PostgreSQL...")
    
    pg_manager = PostgreSQLManager(database_url)
    
    # Test connection
    if not pg_manager.test_connection():
        return False
    
    # Create database if needed
    db_name = pg_manager.connection_params['database']
    if not pg_manager.create_database_if_not_exists(db_name):
        return False
    
    # Get database info
    db_info = pg_manager.get_database_info()
    if db_info:
        logger.info("📊 PostgreSQL Database Info:")
        logger.info(f"   Version: {db_info.get('version', 'Unknown')}")
        logger.info(f"   Size: {db_info.get('size', 'Unknown')}")
        logger.info(f"   Tables: {db_info.get('table_count', 0)}")
        logger.info(f"   Connections: {db_info.get('active_connections', 0)}")
    
    # Apply optimizations
    pg_manager.optimize_database()
    
    # Create indexes
    pg_manager.create_indexes()
    
    logger.info("✅ PostgreSQL setup completed")
    return True


def get_postgresql_health() -> Dict[str, Any]:
    """Get PostgreSQL health status"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url or not database_url.startswith('postgresql'):
        return {'status': 'not_postgresql', 'healthy': False}
    
    try:
        pg_manager = PostgreSQLManager(database_url)
        
        # Test connection
        connection_ok = pg_manager.test_connection()
        
        # Get database info
        db_info = pg_manager.get_database_info()
        
        return {
            'status': 'healthy' if connection_ok else 'unhealthy',
            'healthy': connection_ok,
            'connection_params': {
                'host': pg_manager.connection_params['host'],
                'port': pg_manager.connection_params['port'],
                'database': pg_manager.connection_params['database']
            },
            'database_info': db_info
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'healthy': False,
            'error': str(e)
        }

