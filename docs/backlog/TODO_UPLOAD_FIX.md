# Upload 500 Error Fix Plan
Status: [In Progress] 

## Phase 1: Verify & Install Dependencies ✅
- [x] Check/install required packages: PyPDF2, python-docx, pytesseract, Pillow
- [x] Test extract_text() with sample files

## Phase 2: Verify Database Schema
- [ ] Check if Meetings and Segments tables exist
- [ ] Create if missing via migration script

## Phase 3: Add Error Handling & Logging
- [ ] Enhance upload route with specific error messages
- [ ] Add try-catch around extract_text()
- [ ] Log file details on upload failure

## Phase 4: Frontend Improvements
- [ ] Add file preview & detailed error display
- [ ] Retry mechanism for 500 errors

## Commands to Run:
```
cd itds_env
pip install PyPDF2 python-docx pytesseract pillow
# Test with sample files
python test_upload.py
```

