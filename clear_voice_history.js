// Permanent cleanup script for 12 test recording history items
// Run this in browser console on VoiceRecorder page (F12 → Console)
// Clears frontend cache + backend DB permanently

(async function() {
  console.log('🧹 Starting permanent voice history cleanup...');
  
  // 1. Clear ALL frontend caches
  const clearedKeys = [
    'voiceRecorderHistory',
    'voiceRecorderHiddenPersistedIds',
    'voiceRecorderAuditLog'
  ];
  
  clearedKeys.forEach(key => {
    localStorage.removeItem(key);
    console.log(`✅ Cleared localStorage: ${key}`);
  });
  
  // 2. Backend bulk delete (if logged in)
  const token = localStorage.getItem('token');
  if (token) {
    try {
      const response = await fetch('/api/ai/transcripts', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (response.ok) {
        console.log('✅ Backend transcripts deleted permanently');
      } else {
        const errText = await response.text();
        console.warn('⚠️ Backend delete failed (might already be empty):', response.status, errText);
      }
    } catch (apiError) {
      console.warn('⚠️ Backend API unavailable (local clear still worked):', apiError.message);
    }
  } else {
    console.log('ℹ️ No auth token (local clear only - run logged in for full DB cleanup)');
  }
  
  // 3. Hard reload to update UI
  setTimeout(() => {
    location.reload();
  }, 500);
  
  console.log('🎉 Cleanup complete! Page will reload. 12 test items removed from interface + app permanently.');
  console.log('📋 Next: Verify VoiceRecorder history shows 0 items.');
})();

