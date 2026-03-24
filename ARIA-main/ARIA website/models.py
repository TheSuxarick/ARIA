"""Database models for ARIA email service."""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    """User account model for local email authentication."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.email}>'


class Session(db.Model):
    """Session tokens for user authentication."""
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Session {self.token[:10]}...>'


class GmailAccount(db.Model):
    """Gmail account OAuth credentials storage."""
    __tablename__ = 'gmail_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<GmailAccount {self.email}>'


class EmailMessage(db.Model):
    """Cached email messages from Gmail."""
    __tablename__ = 'email_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    gmail_id = db.Column(db.String(255), nullable=False, index=True)  # Gmail message ID
    account_id = db.Column(db.Integer, db.ForeignKey('gmail_accounts.id'), nullable=False)
    sender = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=True)
    received_at = db.Column(db.DateTime, nullable=False)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    account = db.relationship('GmailAccount', backref=db.backref('emails', lazy='dynamic', cascade='all, delete-orphan'))
    
    __table_args__ = (db.UniqueConstraint('gmail_id', 'account_id', name='_gmail_id_account_uc'),)
    
    def __repr__(self):
        return f'<EmailMessage {self.subject[:30]}>'
