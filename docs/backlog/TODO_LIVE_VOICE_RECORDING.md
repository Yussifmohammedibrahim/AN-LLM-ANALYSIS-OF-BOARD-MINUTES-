# Live Voice Recording Implementation TODO
Track progress here. Steps from approved plan:

## [x] 1. Database: Add Transcripts table (models.py)
- ✅ Extended schema non-disruptively
- No migration needed (IF NOT EXISTS)

## [x] 2. Backend: New AI endpoints (ai_routes.py)
- ✅ POST /api/ai/transcribe
- ✅ POST /api/ai/analyze-speech  
- ✅ Created ai/speech.py

## [x] 3. Frontend API: Extend aiAPI (api/api.js)
- ✅ transcribeLive()
- ✅ analyzeSpeech()

## [x] 4. UI: Add Voice section to Dashboard.js
- ✅ Recording button, live transcript, analysis results
- ✅ Icons: Mic/MicOff, visual feedback
- ✅ Error handling

## [ ] 5. Install dependencies
- Backend: transformers torch torchaudio (Whisper)
- Frontend: none

## [ ] 6. Test full flow
- Mic permission, live STT, backend analysis
- Error states

## [ ] 7. Polish & bonus
- Waveform animation
- Save to DB
- Download transcript

**Current step: 4/7 - UI complete. Ready for deps/test.**
