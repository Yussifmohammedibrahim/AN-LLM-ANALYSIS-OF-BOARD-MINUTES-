# TODO: Fix Password Change Email Notification

## Status: [IN PROGRESS]

## Steps:
1. [x] Update test_change_password.py: Add email to test user creation
2. [x] Edit itds_env/app/app.py: Improve email sending function with better error handling
3. [x] Remove duplicate endpoint from itds_env/app/auth.py
4. [x] Fix validation error message consistency
5. [ ] Configure SMTP .env vars
6. [ ] Test: run server + test script, verify email sent/logged
7. [x] Update this TODO when done

## Testing Command:
```bash
python run.py  # in one terminal
python test_change_password.py  # in another
tail -f app.log | grep email
```

