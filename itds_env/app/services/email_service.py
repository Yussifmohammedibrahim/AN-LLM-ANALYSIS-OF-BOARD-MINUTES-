"""
Email and Notification Service
Handles email rendering, SMTP delivery, and web push notifications.
"""
import logging
import os
import re
import json
import smtplib
import ssl
import importlib
import html as html_utils
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from ..models import execute_safe_query

# Resolve Web Push dependencies
try:
    _pywebpush_module = importlib.import_module('pywebpush')
    webpush = getattr(_pywebpush_module, 'webpush', None)
    WebPushException = getattr(_pywebpush_module, 'WebPushException', Exception)
except Exception:
    webpush = None
    WebPushException = Exception

def _get_vapid_config():
    public_key = (os.getenv('VAPID_PUBLIC_KEY') or '').strip()
    private_key = (os.getenv('VAPID_PRIVATE_KEY') or '').strip()
    subject = (os.getenv('VAPID_SUBJECT') or 'mailto:admin@itds.local').strip()
    return {
        'public_key': public_key,
        'private_key': private_key,
        'subject': subject,
        'configured': bool(public_key and private_key),
    }

def _send_web_push(subscription_info, payload):
    vapid = _get_vapid_config()
    if not vapid['configured']:
        return {'ok': False, 'error': 'VAPID keys not configured'}
    if webpush is None:
        return {'ok': False, 'error': 'pywebpush dependency is not installed'}

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=vapid['private_key'],
            vapid_claims={'sub': vapid['subject']},
            ttl=120,
        )
        return {'ok': True}
    except WebPushException as exc:
        logging.warning(f"Web push delivery failed: {exc}")
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:
        logging.warning(f"Unexpected web push error: {exc}")
        return {'ok': False, 'error': str(exc)}


# Constants
BASE_EMAIL_TEMPLATE = """
<html>
<head><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Type" content="text/html;charset=UTF-8"></head>
<body style="margin:0;padding:0;background:#e8eef9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <!-- Outer wrapper -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#e8eef9;padding:36px 16px;">
    <tr><td align="center">
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:580px;">
        <!-- Top accent bar -->
        <tr><td style="background:linear-gradient(90deg,#1e3a8a 0%,#2563eb 50%,#3b82f6 100%);height:4px;border-radius:4px 4px 0 0;"></td></tr>
        <!-- Card -->
        <tr><td style="background:#ffffff;border:1px solid #cbd5e1;border-top:none;border-radius:0 0 14px 14px;box-shadow:0 10px 30px -6px rgba(30,58,138,0.14);overflow:hidden;">
          <!-- Header -->
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <tr><td style="background:linear-gradient(135deg,#1e3a8a 0%,#1d4ed8 55%,#2563eb 100%);padding:32px 36px 28px;">
              <!-- Logo row -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="vertical-align:middle;padding-right:14px;">
                    <div style="width:42px;height:42px;background:rgba(255,255,255,0.15);border:2px solid rgba(255,255,255,0.3);border-radius:10px;text-align:center;line-height:42px;font-size:18px;font-weight:800;color:#ffffff;letter-spacing:-0.03em;">BM</div>
                  </td>
                  <td style="vertical-align:middle;">
                    <div style="font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:#93c5fd;font-weight:700;margin-bottom:3px;">Board Minutes Analyser</div>
                    <div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">Board Minutes</div>
                  </td>
                </tr>
              </table>
            </td></tr>
          </table>
          <!-- Body -->
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <tr><td style="padding:36px 36px 8px;">
              <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#374151;">Hello <strong style="color:#2563eb;font-weight:700;border-bottom:1.5px solid #bfdbfe;padding-bottom:1px;">{username}</strong>,</p>
              <p style="margin:16px 0 0;font-size:15px;line-height:1.75;color:#4b5563;">{message}</p>
              {button_section}
              <p style="font-size:13px;color:#6b7280;margin-top:20px;line-height:1.6;">{extra_note}</p>
            </td></tr>
          </table>
          <!-- Divider -->
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <tr><td style="padding:0 36px;"><div style="border-top:1px solid #e2e8f0;"></div></td></tr>
          </table>
          <!-- Footer -->
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <tr><td style="padding:20px 36px 28px;background:#f8faff;border-radius:0 0 14px 14px;">
              <p style="margin:0 0 4px;font-size:12px;color:#6b7280;line-height:1.7;">Need help? Contact your administrator or IT support team.</p>
              <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6;">This is an automated notification &mdash; please do not reply to this email.<br/>&copy; Board Minutes Analyser &bull; All rights reserved.</p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

def generate_button(link, text):
    safe_link = html_utils.escape(str(link or ''), quote=True)
    safe_text = html_utils.escape(str(text or 'Open'))
    return f'''
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px 0 20px;">
        <tr>
            <td style="border-radius:8px;background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 100%);box-shadow:0 4px 16px rgba(29,78,216,0.38);">
                <a href="{safe_link}" style="display:inline-block;padding:13px 32px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:0.02em;border-radius:8px;">{safe_text}</a>
            </td>
        </tr>
    </table>
    '''

def _html_to_text(value):
    if not value:
        return ''
    text = re.sub(r'(?i)<br\s*/?>', '\n', str(value))
    text = re.sub(r'(?i)</p>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    return html_utils.unescape(text).strip()

def render_email_template(username, title, intro, body_html='', action_html='', note_html='', action_text='', action_url=None, action_label=None):
    safe_username = html_utils.escape(str(username or 'User'))
    safe_title = html_utils.escape(str(title or 'Account Notification'))
    safe_intro = html_utils.escape(str(intro or ''))

    # CTA block: prefer explicit `action_html`, otherwise build from `action_url` and `action_label`
    if action_html:
        action_block = action_html
    elif action_url:
        action_block = generate_button(action_url, action_label or 'View full report')
    else:
        action_block = ''

    body_block = body_html or ''
    note_block = note_html or ''

    html_content = f"""
<html>
<head><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Type" content="text/html;charset=UTF-8"></head>
<body style="margin:0;padding:0;background:#e8eef9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <!-- Email preview text -->
    <div style="display:none;visibility:hidden;opacity:0;height:0;width:0;max-height:0;overflow:hidden;mso-hide:all;">{safe_title} &mdash; Board Minutes Analyser</div>
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#e8eef9;padding:36px 16px;">
        <tr><td align="center">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:580px;">
                <!-- Top accent bar -->
                <tr><td style="background:linear-gradient(90deg,#1e3a8a 0%,#2563eb 50%,#3b82f6 100%);height:4px;border-radius:4px 4px 0 0;"></td></tr>
                <!-- Card -->
                <tr><td style="background:#ffffff;border:1px solid #cbd5e1;border-top:none;border-radius:0 0 14px 14px;box-shadow:0 10px 30px -6px rgba(30,58,138,0.14);overflow:hidden;">
                    <!-- Header -->
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                        <tr><td style="background:linear-gradient(135deg,#1e3a8a 0%,#1d4ed8 55%,#2563eb 100%);padding:30px 36px 26px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                                <tr>
                                    <td style="vertical-align:middle;padding-right:14px;">
                                        <div style="width:44px;height:44px;background:rgba(255,255,255,0.15);border:2px solid rgba(255,255,255,0.28);border-radius:10px;text-align:center;line-height:44px;font-size:16px;font-weight:800;color:#ffffff;">BM</div>
                                    </td>
                                    <td style="vertical-align:middle;">
                                        <div style="font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:#93c5fd;font-weight:700;margin-bottom:3px;">Board Minutes Analyser</div>
                                        <div style="font-size:21px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;line-height:1.2;">{safe_title}</div>
                                    </td>
                                </tr>
                            </table>
                        </td></tr>
                    </table>
                    <!-- Body -->
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                        <tr><td style="padding:34px 36px 12px;">
                            <p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#374151;">Hello <strong style="color:#2563eb;font-weight:700;border-bottom:1.5px solid #bfdbfe;padding-bottom:1px;">{safe_username}</strong>,</p>
                            <p style="margin:16px 0 0;font-size:15px;line-height:1.75;color:#4b5563;">{safe_intro}</p>
                            {body_block}
                            {action_block}
                            {note_block}
                        </td></tr>
                    </table>
                    <!-- Divider -->
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                        <tr><td style="padding:4px 36px 0;"><div style="border-top:1px solid #e2e8f0;"></div></td></tr>
                    </table>
                    <!-- Footer -->
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                        <tr><td style="padding:20px 36px 28px;background:#f8faff;border-radius:0 0 14px 14px;">
                            <p style="margin:0 0 4px;font-size:12px;color:#6b7280;line-height:1.7;">Need help? Contact your administrator or IT support team.</p>
                            <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.7;">This is an automated notification &mdash; please do not reply to this email.<br/>&copy; Board Minutes Analyser &bull; All rights reserved.</p>
                        </td></tr>
                    </table>
                </td></tr>
            </table>
        </td></tr>
    </table>
</body>
</html>
"""

    # Build plain-text fallback including CTA text if provided
    action_plain = action_text or (f"{action_label or 'View full report'}: {action_url}" if action_url else '')
    plain_text = "\n".join([
        f"ITDS Board Minutes - {title}",
        "",
        f"Hello {username or 'User'},",
        intro or '',
        _html_to_text(body_html),
        _html_to_text(action_plain),
        _html_to_text(note_html),
        "",
        "Need help? Contact your administrator or IT support team.",
        "This is an automated security message from ITDS Board Minutes."
    ]).strip()

    return html_content, plain_text

def send_email(to_email, subject, html_content, text_content=None, notification_event=None, attachments=None):
    try:
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = (os.getenv('SMTP_USERNAME') or '').strip()
        smtp_pass = (os.getenv('SMTP_PASSWORD') or '').replace(' ', '').strip()
        from_email = (os.getenv('FROM_EMAIL') or '').strip()

        if not all([smtp_server, smtp_port, smtp_user, smtp_pass, from_email]):
            logging.error("SMTP config incomplete - email not sent")
            return False

        recipients = [part.strip() for part in re.split(r'[;,]', str(to_email or '')) if part.strip()]
        if not recipients:
            logging.error("No valid recipient email addresses provided")
            return False

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = ', '.join(recipients)

        plain_text = text_content or _html_to_text(html_content)
        alt_part = MIMEMultipart('alternative')
        text_part = MIMEText(plain_text, 'plain', 'utf-8')
        html_part = MIMEText(html_content, 'html')
        alt_part.attach(text_part)
        alt_part.attach(html_part)
        msg.attach(alt_part)

        for attachment in attachments or []:
            filename = str(attachment.get('filename') or 'attachment.bin')
            content = attachment.get('content')
            mimetype = str(attachment.get('mimetype') or 'application/octet-stream')
            if content is None: continue
            if isinstance(content, str): payload_bytes = content.encode('utf-8')
            else: payload_bytes = bytes(content)
            main_type, sub_type = (mimetype.split('/', 1) + ['octet-stream'])[:2]
            part = MIMEBase(main_type, sub_type)
            part.set_payload(payload_bytes)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)

        def _send_via_smtp(use_ssl=False, target_port=None, timeout_sec=60):
            try:
                if use_ssl:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    smtp_client = smtplib.SMTP_SSL(smtp_server, target_port or 465, timeout=timeout_sec, context=ctx)
                else:
                    smtp_client = smtplib.SMTP(smtp_server, target_port or smtp_port, timeout=timeout_sec)
                    smtp_client.ehlo()
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    smtp_client.starttls(context=ctx)
                    smtp_client.ehlo()
                
                smtp_client.login(smtp_user, smtp_pass)
                smtp_client.sendmail(from_email, recipients, msg.as_string())
                smtp_client.quit()
            except smtplib.SMTPException as smtp_err:
                raise RuntimeError(f"SMTP error: {smtp_err}")
            except ssl.SSLError as ssl_err:
                raise RuntimeError(f"SSL error: {ssl_err}")
            except Exception as conn_err:
                raise RuntimeError(f"Connection error: {conn_err}")

        send_attempts = [(False, 587), (True, 465)] if smtp_port == 587 else [(True, 465)] if smtp_port == 465 else [(False, smtp_port), (True, 465)]
        
        last_error = None
        for use_ssl, target_port in send_attempts:
            try:
                _send_via_smtp(use_ssl=use_ssl, target_port=target_port, timeout_sec=60)
                last_error = None
                logging.info(f"Email sent successfully to {to_email}")
                break
            except Exception as e:
                last_error = e
                logging.warning(f"Send attempt failed ({use_ssl=}, {target_port=}): {e}")

        if last_error: raise last_error

        if isinstance(notification_event, dict):
            _log_notif(notification_event, to_email, subject, 'sent')
        return True
    except Exception as e:
        logging.error(f"Email send failed for {to_email}: {e}")
        if isinstance(notification_event, dict):
            _log_notif(notification_event, to_email, subject, 'failed', str(e))
        return False

def _log_notif(event, to_email, subject, status, error=None):
    try:
        _create_notification_event(
            user_id=event.get('user_id'),
            actor_user_id=event.get('actor_user_id'),
            actor_username=event.get('actor_username'),
            channel='email',
            direction=event.get('direction', 'received'),
            notification_type=event.get('notification_type', 'email'),
            title=event.get('title') or subject,
            body=event.get('body'),
            status=status,
            source=event.get('source', 'email'),
            reference_id=event.get('reference_id'),
            metadata=event.get('metadata'),
            recipient_email=to_email,
            sent_at=datetime.now(timezone.utc).isoformat() if status == 'sent' else None,
            failed_at=datetime.now(timezone.utc).isoformat() if status == 'failed' else None,
            error_message=error
        )
    except Exception as e:
        logging.warning(f"Failed to log notification: {e}")

def _create_notification_event(*, user_id, channel, title, body=None, status='sent', direction='received',
                                notification_type='general', source=None, actor_user_id=None,
                                actor_username=None, reference_id=None, metadata=None,
                                recipient_email=None, sent_at=None, delivered_at=None,
                                failed_at=None, error_message=None):
    payload = metadata
    if payload is not None and not isinstance(payload, str):
        try: payload = json.dumps(payload)
        except Exception: payload = str(payload)

    execute_safe_query(
        '''
        INSERT INTO NotificationEvents (
            user_id, actor_user_id, actor_username, channel, direction, notification_type,
            title, body, status, source, reference_id, is_read, read_at, is_deleted, deleted_at, is_archived, archived_at, metadata,
            created_at, sent_at, delivered_at, failed_at, error_message, recipient_email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, 0, NULL, 0, NULL, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            user_id, actor_user_id, actor_username, channel, direction, notification_type,
            title, body, status, source, reference_id, payload,
            datetime.now(timezone.utc).isoformat(), sent_at or datetime.now(timezone.utc).isoformat(),
            delivered_at, failed_at, error_message, recipient_email,
        ),
        fetch=False,
    )

def send_password_reset_confirmation(email, username, recipient_user_id=None):
    sent_at = datetime.now(timezone.utc).strftime('%d %b %Y at %H:%M UTC')
    html_content, text_content = render_email_template(
        username=username,
        title='Password Reset Successful',
        intro='Your account password has been reset successfully. You can now log in with your new password.',
        note_html=f'''
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:20px 0 4px;">
            <tr><td style="border-left:4px solid #f59e0b;background:#fffbeb;padding:14px 16px;border-radius:0 8px 8px 0;">
                <p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#92400e;">&#9888;&nbsp; Did not request this?</p>
                <p style="margin:0;font-size:13px;color:#b45309;line-height:1.6;">Contact support immediately and secure your account. This action was recorded on <strong>{sent_at}</strong>.</p>
            </td></tr>
        </table>'''
    )
    return send_email(email, 'Password Reset Successful - Board Minutes', html_content, text_content, 
                      notification_event={'user_id': recipient_user_id, 'notification_type': 'security', 'title': 'Password Reset Successful', 'source': 'password_reset_confirmation'})

def send_password_changed_email(email, username, recipient_user_id=None):
    sent_at = datetime.now(timezone.utc).strftime('%d %b %Y at %H:%M UTC')
    html_content, text_content = render_email_template(
        username=username,
        title='Password Changed',
        intro='Your account password was changed successfully.',
        note_html=f'''
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:20px 0 4px;">
            <tr><td style="border-left:4px solid #f59e0b;background:#fffbeb;padding:14px 16px;border-radius:0 8px 8px 0;">
                <p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#92400e;">&#128274;&nbsp; Security Notice</p>
                <p style="margin:0;font-size:13px;color:#b45309;line-height:1.6;">If this was not you, reset your password immediately and notify support. This change was recorded on <strong>{sent_at}</strong>.</p>
            </td></tr>
        </table>'''
    )
    return send_email(email, 'Password Changed - Board Minutes', html_content, text_content,
                      notification_event={'user_id': recipient_user_id, 'notification_type': 'security', 'title': 'Password Changed', 'source': 'password_changed_notification'})

def send_welcome_email(email, username, temp_password, recipient_user_id=None, actor_user_id=None, actor_username=None):
    safe_username = html_utils.escape(str(username or ''))
    safe_password = html_utils.escape(str(temp_password or ''))
    creds_box = f'''
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:20px 0;">
        <tr><td style="border-left:4px solid #2563eb;background:#eff6ff;padding:18px 20px;border-radius:0 10px 10px 0;">
            <p style="margin:0 0 4px;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#3b82f6;font-weight:700;">Your Login Credentials</p>
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-top:10px;">
                <tr>
                    <td style="padding:6px 0;font-size:13px;color:#6b7280;width:120px;">Username</td>
                    <td style="padding:6px 0;font-size:14px;font-weight:700;color:#1e3a8a;">{safe_username}</td>
                </tr>
                <tr>
                    <td style="padding:6px 0;font-size:13px;color:#6b7280;">Temp Password</td>
                    <td style="padding:6px 0;">
                        <span style="font-size:15px;font-weight:800;color:#1d4ed8;letter-spacing:0.06em;background:#dbeafe;padding:3px 10px;border-radius:5px;">{safe_password}</span>
                    </td>
                </tr>
            </table>
            <p style="margin:12px 0 0;font-size:12px;color:#6b7280;line-height:1.6;">Please change your password immediately after your first login.</p>
        </td></tr>
    </table>
    '''
    html_content, text_content = render_email_template(username=username, title='Welcome to Board Minutes Analyser', intro='Your account has been created successfully by an administrator. Use the credentials below to sign in.', body_html=creds_box)
    return send_email(email, 'Welcome to Board Minutes Analyser - Account Ready', html_content, text_content,
                      notification_event={'user_id': recipient_user_id, 'actor_user_id': actor_user_id, 'actor_username': actor_username, 'notification_type': 'account', 'title': 'Welcome to Board Minutes Analyser', 'source': 'welcome_email'})

def send_reset_email(email, username, token, recipient_user_id=None):
    frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    reset_link = f"{frontend_base_url}/reset-password/{token}"
    button = generate_button(reset_link, "Reset Password")
    html_content, text_content = render_email_template(username=username, title='Password Reset Request', intro='We received a request to reset your account password.', body_html=button)
    return send_email(email, 'Password Reset Request - Board Minutes', html_content, text_content,
                      notification_event={'user_id': recipient_user_id, 'notification_type': 'security', 'title': 'Password Reset Request', 'source': 'password_reset_request'})
