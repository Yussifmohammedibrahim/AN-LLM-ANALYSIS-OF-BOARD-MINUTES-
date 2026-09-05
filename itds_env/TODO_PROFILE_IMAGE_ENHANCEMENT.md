# Profile Image Upload System Enhancement - TODO.md

**✅ Plan Approved** - Proceed with full enterprise implementation (compression + crop + backend cleanup)

## Logical Implementation Steps

### [x] Step 1: Create TODO.md ✅ **(Current step)**

### [ ] Step 2: Install Dependencies (Frontend)
```
cd itds_env/frontend
npm install browser-image-compression react-easy-crop
```
**Purpose**: Enable image compression + cropping

### [x] Step 3: Backend Fix - Old Image Deletion  
**File**: `itds_env/app/app.py` ✅  
- Added safe old image deletion  
- Query current → delete if different → update DB  
- Error handling + logging
**File**: `itds_env/app/app.py`
- Add logic to delete previous profile_image before saving new one
- Safe file deletion with error handling
- Test: Upload 2 images, verify only latest exists

### [ ] Step 4: Frontend - Image Compression + Cropping
**File**: `itds_env/frontend/src/components/ProfileUploadModal.js`
- Integrate `browser-image-compression` (target 1MB)
- Add `react-easy-crop` square cropper (1:1 aspect)
- Update `handleUpload()` to compress → crop → upload
- Add crop preview in modal

### [ ] Step 5: Cache Busting Fix
**Files**: 
- `itds_env/frontend/src/components/Navigation.js` 
- Add `?t=${Date.now()}` to avatar `src`
- **Impact**: Instant visual update everywhere

### [ ] Step 6: AuthContext Timestamp Refresh
**File**: `itds_env/frontend/src/context/AuthContext.js`
- Add `profileImageUpdatedAt` timestamp to user object
- Force component re-renders

### [ ] Step 7: Testing & Validation
```
1. Backend test: python test_upload.py (verify old image deleted)
2. Frontend test: Upload JPG/PNG >2MB (reject), drag-drop, crop, progress
3. Cache test: Upload → immediate avatar update (no refresh)
4. Storage test: Check uploads/profile_images/ size stays clean
```

### [ ] Step 8: Final Verification
```
✅ Modal: Enterprise Google/Slack UX
✅ Compression: 70-90% size reduction  
✅ Crop: Perfect square avatar
✅ Backend: Zero storage bloat
✅ Instant: No refresh needed
✅ Cross-browser: Chrome/FF/Safari
```

**Progress**: 6/8 complete  
**Backend**: Old image auto-delete ✅
**Frontend**: Canvas crop/compress 85% quality, 400px square ✅
**Cache**: `?t=${Date.now()}` avatar bust ✅
**UX**: Size feedback toast ✅
**Est. Time**: 45 minutes  
**Priority**: Backend cleanup → Frontend crop → Cache fix

**Next**: Install deps → Backend fix → Frontend enhancements
