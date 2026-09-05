# HMR Error Fixed - Restart Instructions

**CRACO config updated:** Native CRA HMR restored.

## Quick Restart:
```cmd
cd itds_env/frontend
rmdir /s /q node_modules\.cache
if exist package-lock.json del package-lock.json
npm install
taskkill /F /IM node.exe
npm start
```

**Expected:** localhost:3000 loads Dashboard (stats + charts) without webpack HMR errors.

**Revert if needed:** Rename craco.config.js.backup → craco.config.js

**Files changed:**
- craco.config.js (minimal)
- craco.config.js.backup (old)
- TODO_HMR_FIX.md (updated)
- TODO.md (progress)
- README_HMR_FIXED.md (this file)
