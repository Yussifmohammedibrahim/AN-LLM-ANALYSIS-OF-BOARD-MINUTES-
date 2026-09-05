# Backend Crash Fix - SQLite Timestamp Error
Status: 🔄 In Progress

**Cause:** SQLite `convert_timestamp` fails on malformed TIMESTAMP fields (no space separator).

## Steps:
- [x] 1. Inspect/clean Users table timestamps (locked_until fixed)
- [x] 2. Fix `execute_safe_query` in app.py (catch InterfaceError + ValueError, basic fallback)

- [ ] 3. Test /api/auth/me & /api/admin/users (no 500s)
- [ ] 4. Restart app: `python run.py`
- [ ] 5. Frontend test: login → dashboard → admin
- [ ] 6. ✅ COMPLETE - Archive this TODO
