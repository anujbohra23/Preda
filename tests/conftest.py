import os
import pytest

# Point to test DB before any app import
os.environ.setdefault(
    'DATABASE_URL',
    os.environ.get('DATABASE_URL', 'sqlite:///test_health.db')
)
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('UPLOAD_FOLDER', 'app/uploads')