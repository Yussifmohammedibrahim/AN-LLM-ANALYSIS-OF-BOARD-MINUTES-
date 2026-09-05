# ITDS Profile Dropdown Enhancement TODO
Status: [Ready] - Created by BLACKBOXAI

## Steps

### 1. [ ] Backend: Add profile_image column
   - Create migration script add_profile_image_column.py
   - Run ALTER TABLE Users ADD COLUMN profile_image TEXT DEFAULT NULL

### 2. [ ] Backend: New endpoint /api/user/upload-profile-image
   - JWT protected POST in app.py
   - Save to itds_env/uploads/profile_images/
   - Update Users.profile_image = filename
   - Return 200 + new user data

### 3. [ ] Backend: Update /api/auth/me to include profile_image
   - SELECT *, profile_image FROM Users

### 4. [ ] Frontend: Update AuthContext.js
   - updateProfile for image upload (FormData)
   - User object: add profile_image

### 5. [ ] Frontend: Navigation.js dropdown
   - Avatar: <img src={user.profile_image || initialAvatar} />
   - Show username (bold), email (small)

### 6. [ ] Frontend: Settings.js add upload
   - File input, preview, upload button
   - Call updateProfile FormData

### 7. [ ] Test & Complete
   - Upload image → dropdown shows
   - Fallback initials if no image
   - All existing features intact

**Ready to proceed - confirm plan?**

