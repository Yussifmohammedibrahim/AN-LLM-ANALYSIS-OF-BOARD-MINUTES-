"""Automated checks for temporary-password login and forced password change."""

import os
import sys
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

from werkzeug.security import generate_password_hash

from app.admin import generate_temporary_password
from app.app import app

app_module = importlib.import_module('app.app')
admin_module = importlib.import_module('app.admin')


def test_temporary_password_includes_uppercase():
    for _ in range(20):
        password = generate_temporary_password(12)
        assert len(password) == 12
        assert any(char.isupper() for char in password), password


def test_temp_password_login_and_forced_change_flow():
    state = {
        'user_id': 4242,
        'username': 'firsttimeuser',
        'password_hash': generate_password_hash('TempPass1'),
        'role': 'viewer',
        'must_change_password': 1,
        'is_deleted': 0,
        'email': 'firsttime@example.com',
    }

    def fake_execute_safe_query(query, params=(), fetch=True):
        normalized_query = ' '.join(str(query).split()).lower()

        if normalized_query.startswith('select * from users where username ='):
            username = params[0]
            if username == state['username']:
                return [state.copy()]
            return []

        if normalized_query.startswith('update users set last_login ='):
            state['last_login'] = params[0]
            return 1

        if normalized_query.startswith('select password_hash from users where user_id ='):
            return [{'password_hash': state['password_hash']}] if str(params[0]) == str(state['user_id']) else []

        if normalized_query.startswith('update users set password_hash = ?, must_change_password = 0 where user_id ='):
            if str(params[1]) == str(state['user_id']):
                state['password_hash'] = params[0]
                state['must_change_password'] = 0
                return 1
            return 0

        if normalized_query.startswith('select email, username from users where user_id ='):
            if str(params[0]) == str(state['user_id']):
                return [{'email': state['email'], 'username': state['username']}]
            return []

        if 'insert into auditlogs' in normalized_query:
            return 1

        raise AssertionError(f'Unexpected query: {query}')

    original_execute_safe_query = app_module.execute_safe_query
    original_log_auth_activity = app_module.log_auth_activity
    original_send_password_changed_email = app_module.send_password_changed_email

    app_module.execute_safe_query = fake_execute_safe_query
    app_module.log_auth_activity = lambda *args, **kwargs: None
    app_module.send_password_changed_email = lambda *args, **kwargs: True

    try:
        client = app.test_client()

        login_response = client.post(
            '/api/auth/login',
            json={'username': state['username'], 'password': 'TempPass1'},
        )
        assert login_response.status_code == 200
        login_data = login_response.get_json()
        assert login_data['must_change_password'] is True
        assert login_data['access_token']

        change_response = client.post(
            '/api/auth/change-password',
            headers={'Authorization': f"Bearer {login_data['access_token']}"},
            json={'current_password': 'TempPass1', 'new_password': 'NewPass1!'},
        )
        assert change_response.status_code == 200
        assert state['must_change_password'] == 0

        relogin_response = client.post(
            '/api/auth/login',
            json={'username': state['username'], 'password': 'NewPass1!'},
        )
        assert relogin_response.status_code == 200
        relogin_data = relogin_response.get_json()
        assert relogin_data['must_change_password'] is False
    finally:
        app_module.execute_safe_query = original_execute_safe_query
        app_module.log_auth_activity = original_log_auth_activity
        app_module.send_password_changed_email = original_send_password_changed_email


def test_admin_create_user_route_returns_uppercase_temp_password():
    state = {
        'actor_id': 1,
        'actor_username': 'admin',
        'actor_role': 'admin',
        'created_user_id': 9001,
    }

    def fake_execute_safe_query(query, params=(), fetch=True):
        normalized_query = ' '.join(str(query).split()).lower()

        if normalized_query.startswith('select user_id, username, role, is_deleted from users where user_id ='):
            if str(params[0]) == str(state['actor_id']):
                return [{
                    'user_id': state['actor_id'],
                    'username': state['actor_username'],
                    'role': state['actor_role'],
                    'is_deleted': 0,
                }]
            return []

        if 'select user_id, username, email, is_deleted from users where username =' in normalized_query:
            return []

        if 'select user_id, username, email, is_deleted from users where email =' in normalized_query:
            return []

        if normalized_query.startswith('insert into users'):
            return state['created_user_id']

        if 'insert into auditlogs' in normalized_query:
            return 1

        raise AssertionError(f'Unexpected query: {query}')

    original_execute_safe_query = app_module.execute_safe_query
    original_send_welcome_email = app_module.send_welcome_email
    original_log_action = admin_module.log_action

    app_module.execute_safe_query = fake_execute_safe_query
    app_module.send_welcome_email = lambda *args, **kwargs: False
    admin_module.log_action = lambda *args, **kwargs: None

    try:
        with app.app_context():
            from flask_jwt_extended import create_access_token

            token = create_access_token(identity='1')
            client = app.test_client()
            response = client.post(
                '/api/admin/users',
                headers={'Authorization': f'Bearer {token}'},
                json={
                    'username': 'tempuser1',
                    'email': 'tempuser1@example.com',
                    'full_name': 'Temp User',
                    'contact_number': '123456',
                    'role': 'viewer',
                },
            )

        assert response.status_code == 201, response.get_json()
        payload = response.get_json()
        temp_password = payload['temp_password']
        assert any(char.isupper() for char in temp_password), temp_password
    finally:
        app_module.execute_safe_query = original_execute_safe_query
        app_module.send_welcome_email = original_send_welcome_email
        admin_module.log_action = original_log_action


if __name__ == '__main__':
    test_temporary_password_includes_uppercase()
    test_temp_password_login_and_forced_change_flow()
    test_admin_create_user_route_returns_uppercase_temp_password()
    print('Temporary-password login flow tests passed.')