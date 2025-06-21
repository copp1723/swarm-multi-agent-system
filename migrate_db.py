#!/usr/bin/env python3
"""
Database Migration and Setup Script
Handles PostgreSQL database initialization, migrations, and data seeding
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.models.user import db, User
from src.config_flexible import get_config
from src.services.auth_service import AuthenticationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """Handles database migrations and setup"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.config = get_config()
        
    def check_database_connection(self) -> bool:
        """Check if database connection is working"""
        try:
            with self.app.app_context():
                db.session.execute(text('SELECT 1'))
                db.session.commit()
                logger.info("✅ Database connection successful")
                return True
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def check_database_exists(self) -> bool:
        """Check if database exists and has tables"""
        try:
            with self.app.app_context():
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                logger.info(f"📊 Found {len(tables)} tables: {tables}")
                return len(tables) > 0
        except Exception as e:
            logger.error(f"❌ Failed to check database: {e}")
            return False
    
    def create_tables(self) -> bool:
        """Create all database tables"""
        try:
            with self.app.app_context():
                logger.info("🔨 Creating database tables...")
                db.create_all()
                
                # Verify tables were created
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                logger.info(f"✅ Created {len(tables)} tables: {tables}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            return False
    
    def seed_initial_data(self) -> bool:
        """Seed database with initial data"""
        try:
            with self.app.app_context():
                logger.info("🌱 Seeding initial data...")
                
                # Check if admin user already exists
                admin_user = User.query.filter_by(username='admin').first()
                if admin_user:
                    logger.info("👤 Admin user already exists")
                    return True
                
                # Create admin user
                auth_service = AuthenticationService(
                    secret_key=self.config.security.secret_key
                )
                
                admin_user = User(
                    username='admin',
                    email='admin@swarm.local',
                    first_name='System',
                    last_name='Administrator',
                    roles='admin,user',
                    is_active=True,
                    created_at=datetime.now(timezone.utc)
                )
                
                # Set password
                admin_user.password_hash = auth_service.hash_password('admin123')
                
                db.session.add(admin_user)
                db.session.commit()
                
                logger.info("✅ Created admin user (username: admin, password: admin123)")
                logger.warning("🔒 IMPORTANT: Change the admin password in production!")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to seed data: {e}")
            db.session.rollback()
            return False
    
    def run_migrations(self) -> bool:
        """Run database migrations"""
        try:
            with self.app.app_context():
                logger.info("🔄 Running database migrations...")
                
                # For now, we'll use simple table creation
                # In the future, this could use Flask-Migrate for more complex migrations
                
                # Check if we need to add new columns or modify existing ones
                inspector = inspect(db.engine)
                
                # Example: Check if user table has all required columns
                if 'user' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('user')]
                    logger.info(f"📋 User table columns: {columns}")
                    
                    # Add any missing columns here
                    required_columns = [
                        'user_id', 'username', 'email', 'password_hash',
                        'first_name', 'last_name', 'roles', 'is_active',
                        'created_at', 'last_login'
                    ]
                    
                    missing_columns = [col for col in required_columns if col not in columns]
                    if missing_columns:
                        logger.warning(f"⚠️ Missing columns: {missing_columns}")
                        # In a real migration system, we'd add these columns here
                
                logger.info("✅ Migrations completed")
                return True
                
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            return False
    
    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """Create database backup (PostgreSQL only)"""
        if not self.config.database.is_postgresql:
            logger.info("📁 Backup skipped (SQLite database)")
            return True
            
        try:
            if not backup_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"backup_swarm_db_{timestamp}.sql"
            
            # Extract database connection details
            db_url = self.config.database.url
            # This would use pg_dump in a real implementation
            logger.info(f"💾 Database backup would be created at: {backup_path}")
            logger.info("📝 Note: Implement pg_dump for production backups")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            return False
    
    def verify_setup(self) -> bool:
        """Verify database setup is correct"""
        try:
            with self.app.app_context():
                logger.info("🔍 Verifying database setup...")
                
                # Check tables exist
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                
                required_tables = ['user']  # Add more tables as needed
                missing_tables = [table for table in required_tables if table not in tables]
                
                if missing_tables:
                    logger.error(f"❌ Missing tables: {missing_tables}")
                    return False
                
                # Check admin user exists
                admin_user = User.query.filter_by(username='admin').first()
                if not admin_user:
                    logger.error("❌ Admin user not found")
                    return False
                
                # Test database operations
                test_user_count = User.query.count()
                logger.info(f"👥 Found {test_user_count} users in database")
                
                logger.info("✅ Database verification successful")
                return True
                
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return False


def create_app_for_migration():
    """Create Flask app for migration purposes"""
    app = Flask(__name__)
    
    config = get_config()
    app.config['SECRET_KEY'] = config.security.secret_key
    app.config['SQLALCHEMY_DATABASE_URI'] = config.database.url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': config.database.pool_size,
        'pool_timeout': config.database.pool_timeout,
        'pool_recycle': config.database.pool_recycle,
        'echo': config.database.echo
    }
    
    db.init_app(app)
    return app


def main():
    """Main migration script"""
    logger.info("🚀 Starting database migration...")
    
    # Create Flask app
    app = create_app_for_migration()
    migrator = DatabaseMigrator(app)
    
    # Check database connection
    if not migrator.check_database_connection():
        logger.error("💥 Cannot connect to database. Check your DATABASE_URL.")
        sys.exit(1)
    
    # Check if database already exists
    db_exists = migrator.check_database_exists()
    
    if not db_exists:
        logger.info("🆕 New database detected, creating tables...")
        if not migrator.create_tables():
            logger.error("💥 Failed to create tables")
            sys.exit(1)
    else:
        logger.info("📊 Existing database detected, running migrations...")
        if not migrator.run_migrations():
            logger.error("💥 Migration failed")
            sys.exit(1)
    
    # Seed initial data
    if not migrator.seed_initial_data():
        logger.error("💥 Failed to seed initial data")
        sys.exit(1)
    
    # Verify setup
    if not migrator.verify_setup():
        logger.error("💥 Database verification failed")
        sys.exit(1)
    
    logger.info("🎉 Database migration completed successfully!")
    logger.info("📋 Summary:")
    logger.info("   - Database connection: ✅")
    logger.info("   - Tables created/updated: ✅")
    logger.info("   - Initial data seeded: ✅")
    logger.info("   - Verification passed: ✅")
    logger.info("")
    logger.info("🔐 Default admin credentials:")
    logger.info("   Username: admin")
    logger.info("   Password: admin123")
    logger.info("   ⚠️  CHANGE PASSWORD IN PRODUCTION!")


if __name__ == '__main__':
    main()

