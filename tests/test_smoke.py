"""
Smoke tests — verify the app starts and core routes respond.
"""
import pytest
import os
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'development')


@pytest.fixture
def app():
    from app import create_app
    application = create_app('development')
    application.config['TESTING']  = True
    application.config['WTF_CSRF_ENABLED'] = False
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_landing_page(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'HealthAssist' in r.data


def test_login_page(client):
    r = client.get('/auth/login')
    assert r.status_code == 200
    assert b'Log In' in r.data or b'login' in r.data.lower()


def test_signup_page(client):
    r = client.get('/auth/signup')
    assert r.status_code == 200


def test_dashboard_redirects_when_logged_out(client):
    r = client.get('/sessions/')
    assert r.status_code == 302
    assert '/auth/login' in r.headers['Location']


def test_signup_and_login(client):
    # Sign up
    r = client.post('/auth/signup', data={
        'email':            'test@example.com',
        'password':         'TestPass123',
        'confirm_password': 'TestPass123',
    }, follow_redirects=True)
    assert r.status_code == 200

    # Log out
    client.get('/auth/logout')

    # Log in
    r = client.post('/auth/login', data={
        'email':    'test@example.com',
        'password': 'TestPass123',
    }, follow_redirects=True)
    assert r.status_code == 200


def test_settings_requires_login(client):
    r = client.get('/settings/')
    assert r.status_code == 302


def test_404_handled(client):
    r = client.get('/this-does-not-exist')
    assert r.status_code == 404