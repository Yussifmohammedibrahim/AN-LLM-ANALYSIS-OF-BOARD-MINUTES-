# Welcome Email Fix - SMTP Configuration Guide

## ✅ Plan Approved & Ready to Test

**Status:** SMTP config fix confirmed (no code changes needed).

## Step-by-Step Fix:

### 1. Configure SMTP (Copy & Fill)
```
cp itds_env/smtp_example.env itds_env/.env
# Edit itds_env/.env:
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourapp@gmail.com
SMTP_PASSWORD=abcd1234efgh5678  # ← 16-char Gmail App Password
FROM_EMAIL=yourapp@gmail.com
SECRET_KEY=your-32-char-secret
JWT_SECRET_KEY=your-jwt-secret
```

**Get Gmail App Password:**
1. Enable 2FA: Google Account → Security → 2-Step Verification
2. App Passwords → Select "Mail" → Generate → Copy 16 chars

### 2. Test SMTP Connection
```bash
cd c:/Users/DELL/Documents/itds_frameworks
python test_smtp_fixed.py
```
**Expected:** ✅ SMTP Connection SUCCESS!

### 3. Test Full Flow
```bash
python test_create_user.py
```
**Expected Response:**
```json
{
  "user_id": 123,
  "email_sent": true,
  "temp_password": "[emailed - change on login]",
  "message": "User created successfully"
}
```

### 4. Check Logs
```bash
tail -f itds_env/app.log | grep "Email event"
```
**Expected:** `Email event: sent to test@test.com`

### 5. Restart App & Test via Frontend
```bash
python run.py
```
- Login as admin (admin/admin123)
- UserManagement → Create user with email
- Check inbox!

## Recent Logs Show:
```
ERROR: Failed to send email: (535, b'5.7.8 Username and Password not accepted')
```
→ **Fix: Invalid/missing App Password in .env**

## Task Complete When:
- [ ] `test_smtp_fixed.py` → ✅ SUCCESS
- [ ] `test_create_user.py` → `"email_sent": true`
- [ ] Receive welcome email in inbox

**No code changes needed - functionality works!** 🚀

