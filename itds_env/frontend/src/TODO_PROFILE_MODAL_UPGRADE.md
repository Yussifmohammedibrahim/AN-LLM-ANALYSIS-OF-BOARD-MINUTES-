# Profile Upload Modal Upgrade TODO

## Status: In Progress

- [x] 1. Add uploadProgress state and update progress-fill width in ProfileUploadModal.js
- [x] 2. Enhance handleUpload: Add simulated/real progress callback, post-upload user update (cache-bust, localStorage via onUpload)
- [x] 3. Update button classes to btn-upload/btn-cancel
- [x] 4. Enhance App.css: modalPop keyframe, avatar-preview gradient/shadow, upload-box scale(1.02), btn-upload gradient/hover, progress transition, added side margins
- [x] 5. Test drag/drop, preview, progress, upload, image refresh in Navigation

- [ ] 6. Backend: Confirm /api/user/upload-profile-image supports onProgress (if not, simulate)
- [ ] 7. Complete: Update this TODO, attempt_completion

**Notes:** Premium UI already solid; focus on progress + polish.

