from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class User(db.Model):
    """User model with authentication support"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    roles = db.Column(db.String(255), default='user')  # Comma-separated roles
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Optional profile fields
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    
    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary, optionally including sensitive data"""
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'roles': self.roles.split(',') if self.roles else ['user'],
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'first_name': self.first_name,
            'last_name': self.last_name
        }
        
        if include_sensitive:
            data['password_hash'] = self.password_hash
            
        return data
    
    def has_role(self, role: str) -> bool:
        """Check if user has specific role"""
        user_roles = self.roles.split(',') if self.roles else []
        return role in user_roles
    
    def add_role(self, role: str):
        """Add role to user"""
        user_roles = self.roles.split(',') if self.roles else []
        if role not in user_roles:
            user_roles.append(role)
            self.roles = ','.join(user_roles)
    
    def remove_role(self, role: str):
        """Remove role from user"""
        user_roles = self.roles.split(',') if self.roles else []
        if role in user_roles:
            user_roles.remove(role)
            self.roles = ','.join(user_roles) if user_roles else 'user'
    
    @property
    def full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        else:
            return self.username
