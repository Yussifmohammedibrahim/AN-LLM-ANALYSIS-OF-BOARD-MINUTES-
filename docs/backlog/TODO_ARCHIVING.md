# Secure Login Activity Archiving & Retrieval - IMPLEMENTATION TODO

## [x] 1. Backend Schema & Migration ✅
- [x] Create `add_archiving.py` migration script
- [x] Update `itds_env/app/models.py`: Add `archived_at TIMESTAMP NULL` to AuditLogs CREATE TABLE
- [x] Add indexes: `idx_auditlogs_archived_at`, `idx_auditlogs_archived_user`
- [x] Run migration: `python add_archiving.py`

## [x] 2. Backend API Enhancements (itds_env/app/app.py) ✅
- [x] Enhance `/api/activity/logs`: Support `?archived=true/false/all&start_date&end_date&user_id&status&device_type&location`
- [x] Add `/api/admin/archive-logs` (POST {days}), audit action
- [x] Add `/api/admin/restore-logs` (POST {log_ids})
- [x] Add `/api/admin/audit-trail` (GET)

## [x] 3. Admin Routes (itds_env/app/admin.py) ✅
- [x] Add routes: `/api/admin/archive-logs`, `/api/admin/restore-logs`, `/api/admin/audit-trail`
- [x] RBAC: admin-only, JWT required

## [x] 4. Frontend Updates ✅
- [x] `itds_env/frontend/src/api/api.js`: Extend `getActivityLogs({archived, startDate, endDate, userId, status, deviceType, location})`
- [x] `itds_env/frontend/src/components/ActivityLogins.js`: Tabs (Active/Archived/All), advanced filters, Archive/Restore buttons, Run Auto-Archive

## [ ] 2. Backend API Enhancements (itds_env/app/app.py)
- [ ] Enhance `/api/activity/logs`: Support `?archived=true/false/all&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&user_id=&status=&device_type=&location=`
- [ ] Add `/api/admin/archive-logs` (POST {days:90}): Archive old logs, audit action
- [ ] Add `/api/admin/restore-logs` (POST {log_ids:[]}): Restore selected
- [ ] Add `/api/admin/audit-trail` (GET): Archive/restore actions from AuditLogs

## [ ] 3. Admin Routes (itds_env/app/admin.py)
- [ ] Add routes: `/api/admin/archive-logs`, `/api/admin/restore-logs`, `/api/admin/audit-trail`
- [ ] RBAC: admin-only, JWT required

## [ ] 4. Frontend Updates
- [ ] `itds_env/frontend/src/api/api.js`: Extend `getActivityLogs({archived, startDate, endDate, userId, status, deviceType, location})`
- [ ] `itds_env/frontend/src/components/ActivityLogins.js`: Tabs (Active/Archived/All), advanced filters, Archive/Restore buttons, Run Auto-Archive

## [ ] 5. Testing & Validation
- [ ] Backend: Test endpoints with curl/Postman (admin token)
- [ ] Frontend: npm start, test UI filters/tabs/export
- [ ] E2E: Login/logout → Archive → Filter archived → Restore → Check audit trail
- [ ] Add test_archiving.py

## [ ] 6. Completion
- [ ] attempt_completion with demo command: `python run.py` (backend) + `cd itds_env/frontend && npm start` (frontend)
