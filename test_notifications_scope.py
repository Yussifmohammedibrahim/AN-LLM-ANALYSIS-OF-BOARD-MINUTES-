import os
import sys
import unittest
import importlib
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_SRC_DIR = os.path.join(ROOT_DIR, 'itds_env')
if APP_SRC_DIR not in sys.path:
    sys.path.insert(0, APP_SRC_DIR)

backend_module = importlib.import_module('app.app')  # noqa: E402


class NotificationScopeAuthorizationTests(unittest.TestCase):
    def test_non_super_admin_cannot_request_all_scope(self):
        user_row = {'user_id': 21, 'role': 'admin', 'is_deleted': 0}
        scope = backend_module._resolve_notification_scope(user_row, requested_scope='all', default_scope='mine')
        self.assertIsNone(scope)

    def test_super_admin_can_request_all_scope(self):
        user_row = {'user_id': 1, 'role': 'super_admin', 'is_deleted': 0}
        scope = backend_module._resolve_notification_scope(user_row, requested_scope='all', default_scope='mine')
        self.assertEqual(scope, 'all')

    def test_invalid_scope_falls_back_to_default(self):
        user_row = {'user_id': 5, 'role': 'super_admin', 'is_deleted': 0}
        scope = backend_module._resolve_notification_scope(user_row, requested_scope='invalid-value', default_scope='mine')
        self.assertEqual(scope, 'mine')


class NotificationAuditLoggingTests(unittest.TestCase):
    @patch('app.app.log_archiving_activity')
    def test_super_admin_cross_user_action_is_audited(self, mock_log_archiving_activity):
        actor_row = {'user_id': 1, 'username': 'root', 'role': 'super_admin', 'is_deleted': 0}

        backend_module._log_super_admin_notification_action(
            actor_row,
            'notification_deleted',
            notification_id=77,
            target_user_id=42,
            extra_details={'reason': 'moderation'}
        )

        mock_log_archiving_activity.assert_called_once()
        args, kwargs = mock_log_archiving_activity.call_args
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], 'notification_deleted')
        self.assertEqual(args[2]['scope'], 'all')
        self.assertEqual(args[2]['notification_id'], 77)
        self.assertEqual(args[2]['target_user_id'], 42)
        self.assertEqual(args[2]['reason'], 'moderation')
        self.assertEqual(kwargs['actor_username'], 'root')
        self.assertEqual(kwargs['actor_role'], 'super_admin')

    @patch('app.app.log_archiving_activity')
    def test_super_admin_same_user_action_is_not_audited(self, mock_log_archiving_activity):
        actor_row = {'user_id': 1, 'username': 'root', 'role': 'super_admin', 'is_deleted': 0}

        backend_module._log_super_admin_notification_action(
            actor_row,
            'notification_marked_read',
            notification_id=88,
            target_user_id=1,
        )

        mock_log_archiving_activity.assert_not_called()

    @patch('app.app.log_archiving_activity')
    def test_non_super_admin_action_is_not_audited(self, mock_log_archiving_activity):
        actor_row = {'user_id': 2, 'username': 'admin', 'role': 'admin', 'is_deleted': 0}

        backend_module._log_super_admin_notification_action(
            actor_row,
            'notification_deleted',
            notification_id=99,
            target_user_id=42,
        )

        mock_log_archiving_activity.assert_not_called()


if __name__ == '__main__':
    unittest.main()
