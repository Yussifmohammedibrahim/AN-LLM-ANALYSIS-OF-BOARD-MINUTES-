# Fix Dashboard undefined.map() Error - Implementation Plan

Status: ✅ Step 1 Complete - safeMap created

## Analysis Summary
✅ All .map() calls found safe (useState([]), loading guards)
✅ AuthContext user=null guarded by ProtectedLayout loading spinner
✅ Dashboard.js already has safeChartData() fallbacks, mock data
✅ Navigation filteredNavItems always array from hardcoded navItems

## Likely Causes (task matches)
1. **API returns unexpected structure** (undefined/null data)
2. Chart.js datasets.data expects array (timing/race)
3. Initial render before fallback loads

## Fix Steps (0-disruption)

### 1. 🛡️ Add Global SafeMap Utility
`src/utils/safeMap.js`:
```js
export const safeMap = (arr, fn) => (Array.isArray(arr) ? arr.map(fn) : []);
```

### 2. 🔧 Defensive API Handling (all components)
Replace:
```js
setData(response.data)
```
With:
```js
setData(Array.isArray(response.data) ? response.data : [])
```

### 3. 📊 Chart.js Double Guard (Dashboard.js)
Already good, add data?.datasets?.map()

### 4. 🧪 Test Sequence
```
cd itds_env/frontend && npm start
cd ../.. && python run.py
Navigate /dashboard - check console
```

### 5. ✅ Completion
- [x] Create safeMap utils
- [ ] Audit/update 3 API components: UserManagement, Reports, Search
- [ ] Test dashboard load
- [ ] Remove this TODO, create TODO_FIXED.md

**Priority**: High - repeated console spam but no crash

**Risk**: None - defensive programming only

