import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import LoadingSpinner from './LoadingSpinner';
import styles from './VoiceRecorder.module.css';
import { Radio, Square, Download, History, Pause, Play, Clock, Volume2, Copy, Trash2, Check, MoreVertical, RefreshCw, FileDown, Upload } from 'lucide-react';
import { aiAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useConfirm } from './ConfirmProvider';

const ACTIVE_AUDIO_JOB_KEY = 'voiceRecorderActiveAudioJob';

function VoiceRecorder() {
  const location = useLocation();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [finalTranscript, setFinalTranscript] = useState('');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [fullTranscript, setFullTranscript] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [recordingError, setRecordingError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const confirm = useConfirm();
  const [transcriptsHistory, setTranscriptsHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [actionMessage, setActionMessage] = useState('');
  const [animatedIndicator, setAnimatedIndicator] = useState(() => {
    const saved = localStorage.getItem('voiceRecorderAnimatedIndicator');
    if (saved === null) return true;
    return saved === 'true';
  });
  const [isCompactMode, setIsCompactMode] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [micDbLevel, setMicDbLevel] = useState(-60);
  const [cpuUsage, setCpuUsage] = useState(5);
  const [deletedItem, setDeletedItem] = useState(null);
  const [showDownloadOptions, setShowDownloadOptions] = useState(false);
  const [copiedHistoryId, setCopiedHistoryId] = useState(null);
  const [showHistoryOptions, setShowHistoryOptions] = useState(false);
  const [isUploadingAudio, setIsUploadingAudio] = useState(false);
  const [processingJob, setProcessingJob] = useState(null);
  const [lastUploadedFile, setLastUploadedFile] = useState(null);
  const [audioProcessingMode, setAudioProcessingMode] = useState(() => {
    const saved = localStorage.getItem('voiceRecorderAudioProcessingMode');
    return saved === 'full' ? 'full' : 'fast';
  });

  // Audio refs
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioUploadInputRef = useRef(null);
  const transcriptRef = useRef(null);
  const canvasRef = useRef(null);
  const analyserRef = useRef(null);
  const animationRef = useRef(null);
  const timerRef = useRef(null);
  const isPauseRef = useRef(false);
  const sessionIdRef = useRef(null);
  const directUploadAbortRef = useRef(null);
  const canceledAudioJobsRef = useRef(new Set());
  const applyUploadedAudioResultRef = useRef(null);
  const auditLogRef = useRef((() => {
    const logs = localStorage.getItem('voiceRecorderAuditLog');
    return logs ? JSON.parse(logs) : [];
  })());

  const appendAuditLog = (event) => {
    const nextLogs = [event, ...auditLogRef.current].slice(0, 50);
    auditLogRef.current = nextLogs;
    localStorage.setItem('voiceRecorderAuditLog', JSON.stringify(nextLogs));
  };

  // Migration cleanup: stop suppressing persisted transcript IDs so history displays server records.
  useEffect(() => {
    localStorage.removeItem('voiceRecorderHiddenPersistedIds');
  }, []);
  useEffect(() => {
    localStorage.setItem('voiceRecorderAnimatedIndicator', String(animatedIndicator));
  }, [animatedIndicator]);

  useEffect(() => {
    localStorage.setItem('voiceRecorderAudioProcessingMode', audioProcessingMode);
  }, [audioProcessingMode]);

  const clearActiveAudioJob = useCallback(() => {
    localStorage.removeItem(ACTIVE_AUDIO_JOB_KEY);
  }, []);

  const saveActiveAudioJob = useCallback((job) => {
    try {
      localStorage.setItem(ACTIVE_AUDIO_JOB_KEY, JSON.stringify(job));
    } catch {
      // Ignore storage quota/availability issues.
    }
  }, []);

  const pollAsyncAudioJob = useCallback(async ({ jobId, fileName = 'uploaded audio', audioMode = 'fast', startedAtMs = Date.now() }) => {
    const modeLabel = audioMode === 'full' ? 'Full mode' : 'Fast mode';
    const timeoutMs = 8 * 60 * 1000;

    while (Date.now() - startedAtMs < timeoutMs) {
      if (canceledAudioJobsRef.current.has(jobId)) {
        clearActiveAudioJob();
        return;
      }

      const statusResponse = await aiAPI.getTranscribeAudioStatus(jobId);
      const statusPayload = statusResponse?.data || statusResponse;
      const status = String(statusPayload?.status || '').toLowerCase();
      const progress = Number(statusPayload?.progress || 0);
      const message = String(statusPayload?.message || `${modeLabel}: processing audio...`);

      setActionMessage(`${message}${progress ? ` (${progress}%)` : ''}`);
      setProcessingJob((prev) => prev ? {
        ...prev,
        status,
        progress: progress || (status === 'completed' ? 100 : prev.progress),
        message,
        canCancel: !['completed', 'failed', 'canceled'].includes(status),
        canRetry: ['failed', 'canceled'].includes(status),
      } : null);

      if (status === 'completed') {
        const finalPayload = statusPayload?.result || statusPayload;
        if (typeof applyUploadedAudioResultRef.current === 'function') {
          await applyUploadedAudioResultRef.current(finalPayload, fileName);
        }
        notifySuccess('Audio uploaded, transcribed, and analyzed successfully.');
        setActionMessage('');
        setProcessingJob((prev) => prev ? {
          ...prev,
          status: 'completed',
          progress: 100,
          message: 'Completed',
          canCancel: false,
          canRetry: false,
        } : null);
        setIsAnalyzing(false);
        clearActiveAudioJob();
        return;
      }

      if (status === 'failed' || status === 'canceled') {
        clearActiveAudioJob();
        throw new Error(statusPayload?.error || statusPayload?.message || 'Audio processing failed');
      }

      await new Promise((resolve) => setTimeout(resolve, 1600));
    }

    clearActiveAudioJob();
    throw new Error('Audio processing timed out. Please try a shorter audio clip.');
  }, [clearActiveAudioJob]);

  useEffect(() => {
    let canceled = false;
    const raw = localStorage.getItem(ACTIVE_AUDIO_JOB_KEY);
    if (!raw || processingJob) return undefined;

    let saved;
    try {
      saved = JSON.parse(raw);
    } catch {
      clearActiveAudioJob();
      return undefined;
    }

    const jobId = String(saved?.jobId || '').trim();
    if (!jobId) {
      clearActiveAudioJob();
      return undefined;
    }

    const audioMode = saved?.audioMode === 'full' ? 'full' : 'fast';
    const fileName = saved?.fileName || 'uploaded audio';
    const startedAtMs = Number(saved?.startedAtMs || Date.now());

    setIsAnalyzing(true);
    setIsUploadingAudio(false);
    setProcessingJob({
      jobId,
      mode: 'async',
      audioMode,
      status: 'running',
      progress: Number(saved?.progress || 10),
      message: 'Resuming background processing...',
      canCancel: true,
      canRetry: false,
      fileName,
    });

    (async () => {
      try {
        await pollAsyncAudioJob({ jobId, fileName, audioMode, startedAtMs });
      } catch (err) {
        if (canceled) return;
        const errorMessage = err?.response?.data?.error || err?.message || 'Audio upload analysis failed';
        setRecordingError(errorMessage);
        notifyError(errorMessage);
        setActionMessage('');
        setProcessingJob((prev) => prev ? {
          ...prev,
          status: 'failed',
          message: errorMessage,
          canCancel: false,
          canRetry: true,
        } : null);
        setIsAnalyzing(false);
      }
    })();

    return () => {
      canceled = true;
    };
  }, [clearActiveAudioJob, pollAsyncAudioJob, processingJob]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (showDownloadOptions && !event.target.closest('.downloadDropdown')) {
        setShowDownloadOptions(false);
      }
      if (showHistoryOptions && !event.target.closest('.historyDropdown')) {
        setShowHistoryOptions(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showDownloadOptions, showHistoryOptions]);

  useEffect(() => {
    if (volumeLevel > 0) {
      const db = Math.max(-60, Math.min(0, 20 * Math.log10(Math.max(volumeLevel, 0.001))));
      setMicDbLevel(Number(db.toFixed(1)));
    } else {
      setMicDbLevel(-60);
    }
  }, [volumeLevel]);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [finalTranscript, liveTranscript]);

  useEffect(() => {
    const params = new URLSearchParams(location.search || '');
    const shouldOpenHistory = params.get('history') === '1' || params.get('history') === 'true';
    if (shouldOpenHistory) {
      setShowHistory(true);
    }
  }, [location.search]);

  const loadTranscriptsHistory = useCallback(async () => {
    try {
      // Use the shared API client so history loading targets the same backend as delete/clear actions.
      const response = await aiAPI.getTranscripts();
      const data = response?.data || response;
      if (!data || !Array.isArray(data.transcripts)) {
        throw new Error('Invalid transcripts payload');
      }

      const getHistoryKey = (entry) => {
        const transcriptId = String(entry?.transcript_id || '').trim();
        if (/^\d+$/.test(transcriptId)) return `db:${transcriptId}`;
        const sessionId = String(entry?.session_id || '').trim();
        if (sessionId) return `session:${sessionId}`;
        const createdAt = String(entry?.created_at || '').trim();
        if (createdAt) return `created:${createdAt}`;
        return '';
      };

      // Backend is source-of-truth when reachable.
      // Do not merge local cache here to prevent stale records from resurrecting.
      const merged = [...data.transcripts]
        .reduce((acc, entry) => {
          const key = getHistoryKey(entry);
          if (!key || acc.seen.has(key)) return acc;
          acc.seen.add(key);
          acc.rows.push(entry);
          return acc;
        }, { seen: new Set(), rows: [] })
        .rows
        .slice(0, 50);

      setTranscriptsHistory(merged);
      localStorage.setItem('voiceRecorderHistory', JSON.stringify(merged));
      return;
    } catch (err) {
      console.warn('Backend history not available; clearing stale local cache:', err.message);
      setTranscriptsHistory([]);
      localStorage.removeItem('voiceRecorderHistory');
    }
  }, []);

  useEffect(() => {
    loadTranscriptsHistory();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [loadTranscriptsHistory]);

  const startRecording = async () => {
    try {
      setRecordingError('');
      setFinalTranscript('');
      setLiveTranscript('');
      setFullTranscript('');
      setAnalysis(null);
      setRecordingTime(0);
      setVolumeLevel(0);

      // New recording session identifier for history merging
      sessionIdRef.current = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

      // Speech Recognition
      initSpeechRecognition();

      // Audio recording + visualization
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Web Audio API for visualization
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = audioContext.createAnalyser();
      const microphone = audioContext.createMediaStreamSource(stream);
      microphone.connect(analyser);
      analyser.fftSize = 256;
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      analyserRef.current = { analyser, dataArray, bufferLength };

      // Canvas animation
      const draw = () => {
        const { analyser, dataArray, bufferLength } = analyserRef.current;
        if (!analyser) return;

        analyser.getByteFrequencyData(dataArray);
        
        const canvas = canvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext('2d');
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          
          const barWidth = (canvas.width / bufferLength) * 2.5;
          let barHeight;
          let x = 0;

          for (let i = 0; i < bufferLength; i++) {
            barHeight = (dataArray[i] / 255) * canvas.height * 0.8;
            
            const r = barHeight + 100 * (i / bufferLength);
            const g = 250 * (i / bufferLength);
            const b = 50;
            
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillRect(x, canvas.height - barHeight / 2, barWidth, barHeight / 2);
            
            x += barWidth + 1;
          }
          
          // Volume level for meter
          const volume = dataArray.reduce((a, b) => a + b) / bufferLength / 255;
          setVolumeLevel(volume);

          // Real-time CPU simulation based on volume level
          const cpuValue = Math.round(Math.min(100, Math.max(5, 15 + (volume * 80) + Math.random() * 10)));
          setCpuUsage(cpuValue);
        }
        
        animationRef.current = requestAnimationFrame(draw);
      };
      draw();

      // MediaRecorder for audio download
      const mediaRecorder = new MediaRecorder(stream);
      const chunks = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        setAudioBlob(blob);
      };
      mediaRecorder.start(1000); // Timeslice for better perf
      mediaRecorderRef.current = mediaRecorder;

      // Timer
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

    } catch (err) {
      console.error('Recording start failed:', err);

      let userMessage = 'Microphone access denied. Please allow microphone usage in your browser settings.';

      if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        userMessage = 'No microphone found. Please connect a microphone and try again.';
      } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        userMessage = 'Microphone permission denied. Please grant access and retry.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        userMessage = 'Unable to access microphone. It may be in use by another application.';
      } else if (err.name === 'OverconstrainedError' || err.name === 'ConstraintNotSatisfiedError') {
        userMessage = 'No microphone combination matches the specified requirements.';
      } else if (err.message && err.message.toLowerCase().includes('permission')) {
        userMessage = 'Microphone permission denied. Please allow access and reload.';
      } else if (err.message && err.message.toLowerCase().includes('device')) {
        userMessage = 'Microphone not available. Check device connection and try again.';
      }

      setRecordingError(userMessage);
    }
  };

  const handleSpeechResult = (event) => {
    let interim = '';
    let final = '';

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final += result + ' ';
      } else {
        interim += result;
      }
    }

    setLiveTranscript(interim);
    if (final.trim()) {
      const newFinal = final.trim() + '. ';
      setFinalTranscript(prev => prev + newFinal);
      setFullTranscript(prev => prev + newFinal);
    }
  };

  const initSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setRecordingError('Speech recognition not supported in this browser');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsRecording(true);
      setRecordingError(''); // clear previous transient errors
    };

    recognition.onresult = handleSpeechResult;

    recognition.onerror = (event) => {
      console.warn('Speech error:', event.error);

      // "aborted" can happen when we explicitly call recognition.stop() (pause/stop flow)
      // or when browser cancels recognition internally. Don't show user noise for normal pause.
      if (event.error === 'aborted') {
        if (isPauseRef.current) {
          return;
        }
        setRecordingError('Speech recognition was aborted unexpectedly. Please try recording again.');
        setIsRecording(false);
        return;
      }

      // Handle common recoverable speech errors more gracefully
      if (['no-speech', 'audio-capture', 'network', 'not-allowed'].includes(event.error)) {
        const friendly = {
          'no-speech': 'No speech detected. Please speak clearly into your microphone.',
          'audio-capture': 'Microphone input not detected. Check your mic and try again.',
          'network': 'Network issue while recognizing speech. Check your connection.',
          'not-allowed': 'Microphone permission denied. Please allow access in browser settings.'
        }[event.error];
        setRecordingError(friendly || `Speech recognition error: ${event.error}`);
      } else {
        setRecordingError(`Speech recognition error: ${event.error}`);
      }

      // Stop recognition on error to prevent weird internal state.
      if (recognitionRef.current && recognitionRef.current.state !== 'inactive') {
        recognitionRef.current.stop();
      }
      setIsRecording(false);
    };

    recognition.onend = () => {
      // If user clicked pause/stop, do not finalize and avoid error display.
      if (isPauseRef.current) {
        return;
      }

      // onend also occurs when recognition service drops unexpectedly.
      finalizeRecognition();
    };

    recognition.start();
    recognitionRef.current = recognition;
  };

  const stopSpeechRecognition = () => {
    if (recognitionRef.current && recognitionRef.current.state !== 'inactive') {
      recognitionRef.current.stop();
    }
    recognitionRef.current = null;
  };

  const finalizeRecognition = (runAnalysis = true) => {
    setIsRecording(false);
    setIsPaused(false);
    setLiveTranscript('');
    if (runAnalysis && fullTranscript.trim()) {
      handleAnalyze();
    }
  };

const togglePause = () => {
    const nextPaused = !isPaused;
    setIsPaused(nextPaused);

    if (nextPaused) { // pausing
      isPauseRef.current = true;
      if (timerRef.current) clearInterval(timerRef.current);
      if (recognitionRef.current && recognitionRef.current.stop) {
        recognitionRef.current.stop();
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.pause) {
        mediaRecorderRef.current.pause();
      }
    } else { // resuming
      isPauseRef.current = false;
      initSpeechRecognition();
      if (mediaRecorderRef.current && mediaRecorderRef.current.resume) {
        mediaRecorderRef.current.resume();
      }
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    }

    if (streamRef.current) {
      streamRef.current.getAudioTracks()[0].enabled = !nextPaused;
    }
  };

  const stopRecording = () => {
    isPauseRef.current = false;
    setIsPaused(false);

    // Stop speech recognition
    stopSpeechRecognition();

    // Stop media recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }

    // Stop stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }

    // Cleanup
    if (timerRef.current) clearInterval(timerRef.current);
    if (animationRef.current) cancelAnimationFrame(animationRef.current);

    finalizeRecognition();
  };

  const saveToHistory = (entry) => {
    setTranscriptsHistory((prev) => {
      let mergedEntry = entry;

      // If we have an open session, append to previous session item in history
      if (entry.session_id) {
        const existing = prev.find((item) => item.session_id === entry.session_id);
        if (existing) {
          mergedEntry = {
            ...existing,
            ...entry,
            transcript_text: `${existing.transcript_text.trim()} ${entry.transcript_text.trim()}`.trim(),
            updated_at: new Date().toISOString(),
          };
        }
      }

      const mergedTranscriptId = String(mergedEntry?.transcript_id || '');
      const mergedSessionId = String(mergedEntry?.session_id || '');
      const trimmedPrev = prev.filter((item) => {
        const itemTranscriptId = String(item?.transcript_id || '');
        const itemSessionId = String(item?.session_id || '');
        return itemTranscriptId !== mergedTranscriptId && itemSessionId !== mergedSessionId;
      });
      const next = [mergedEntry, ...trimmedPrev].slice(0, 50);

      localStorage.setItem('voiceRecorderHistory', JSON.stringify(next));
      return next;
    });
  };

  const handleAnalyze = async () => {
    if (!fullTranscript.trim()) return;
    setIsAnalyzing(true);
    setAnalysis(null);
    try {
      const response = await aiAPI.analyzeSpeech(fullTranscript);
      const result = response?.data || response;
      setAnalysis(result);

      const persistedTranscriptId = result?.transcript_id;
      const historyEntry = {
        session_id: sessionIdRef.current || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        // Use backend transcript ID when available to avoid duplicate local+server rows.
        transcript_id: persistedTranscriptId ? String(persistedTranscriptId) : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        created_at: new Date().toISOString(),
        transcript_text: fullTranscript,
        sentiment: result?.sentiment || 'NEUTRAL',
        summary: result?.summary || '',
        analysis: result,
      };
      saveToHistory(historyEntry);

      // Keep backend refresh as best-effort
      loadTranscriptsHistory();
    } catch (err) {
      const errorMessage = err?.response?.data?.details || err?.response?.data?.error || err.message || 'Unknown error';
      setRecordingError('Analysis failed: ' + errorMessage);
      setAnalysis(null);  // Clear stalled analysis state
    } finally {
      setIsAnalyzing(false);
    }
  };

  const applyUploadedAudioResult = useCallback(async (payload, fallbackName = 'Uploaded audio') => {
    const transcriptText = String(payload?.transcript || '').trim();
    if (transcriptText) {
      setFinalTranscript(transcriptText);
      setFullTranscript(transcriptText);
    }

    setAnalysis(payload);

    const persistedTranscriptId = payload?.transcript_id;
    const historyEntry = {
      session_id: sessionIdRef.current || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      transcript_id: persistedTranscriptId ? String(persistedTranscriptId) : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      created_at: new Date().toISOString(),
      transcript_text: transcriptText || fallbackName,
      sentiment: payload?.sentiment || 'NEUTRAL',
      summary: payload?.summary || '',
      analysis: payload,
    };
    saveToHistory(historyEntry);
    await loadTranscriptsHistory();
  }, [loadTranscriptsHistory]);

  useEffect(() => {
    applyUploadedAudioResultRef.current = applyUploadedAudioResult;
  }, [applyUploadedAudioResult]);

  const cancelProcessingJob = async () => {
    const current = processingJob;
    if (!current) return;

    if (current.mode === 'async' && current.jobId) {
      canceledAudioJobsRef.current.add(current.jobId);
      try {
        await aiAPI.cancelTranscribeAudioJob(current.jobId);
      } catch (err) {
        // Best effort: UI cancel still stops polling and ignores future updates.
      }
      setProcessingJob((prev) => prev ? {
        ...prev,
        status: 'canceled',
        message: 'Canceled by user',
        progress: 100,
        canCancel: false,
        canRetry: true,
      } : null);
      setActionMessage('Audio processing canceled.');
      setIsAnalyzing(false);
      setIsUploadingAudio(false);
      clearActiveAudioJob();
      return;
    }

    if (current.mode === 'direct' && directUploadAbortRef.current) {
      directUploadAbortRef.current.abort();
      directUploadAbortRef.current = null;
      setProcessingJob((prev) => prev ? {
        ...prev,
        status: 'canceled',
        message: 'Canceled by user',
        progress: 100,
        canCancel: false,
        canRetry: true,
      } : null);
      setActionMessage('Audio processing canceled.');
      setIsAnalyzing(false);
      setIsUploadingAudio(false);
      clearActiveAudioJob();
    }
  };

  const retryProcessingJob = () => {
    if (!lastUploadedFile) {
      notifyError('No recent audio file found for retry. Please upload again.');
      return;
    }
    beginAudioUpload(lastUploadedFile, null, audioProcessingMode);
  };

  const beginAudioUpload = async (selectedFile, inputTarget = null, mode = audioProcessingMode) => {
    const normalizedMode = mode === 'full' ? 'full' : 'fast';
    const modeLabel = normalizedMode === 'full' ? 'Full mode' : 'Fast mode';
    setLastUploadedFile(selectedFile);
    setIsUploadingAudio(true);
    setIsAnalyzing(true);
    setRecordingError('');
    setAnalysis(null);
    setProcessingJob({
      jobId: null,
      mode: 'async',
      audioMode: normalizedMode,
      status: 'uploading',
      progress: 5,
      message: `${modeLabel}: uploading audio...`,
      canCancel: true,
      canRetry: false,
      fileName: selectedFile.name,
    });

    try {
      try {
        setActionMessage('Uploading audio...');
        const startResponse = await aiAPI.startTranscribeAudio(selectedFile, { mode: normalizedMode });
        const startPayload = startResponse?.data || startResponse;
        const jobId = startPayload?.job_id;
        if (!jobId) {
          throw new Error('Audio processing job did not start.');
        }

        setProcessingJob({
          jobId,
          mode: 'async',
          audioMode: normalizedMode,
          status: 'queued',
          progress: 8,
          message: `${modeLabel}: processing in background...`,
          canCancel: true,
          canRetry: false,
          fileName: selectedFile.name,
        });
        saveActiveAudioJob({
          jobId,
          audioMode: normalizedMode,
          fileName: selectedFile.name,
          startedAtMs: Date.now(),
          progress: 8,
        });

        setActionMessage(`${modeLabel}: processing in background...`);
        notifySuccess('Upload accepted. Analysis is running in background.');
        setIsUploadingAudio(false);
        if (inputTarget) inputTarget.value = '';

        (async () => {
          try {
            await pollAsyncAudioJob({ jobId, fileName: selectedFile.name, audioMode: normalizedMode, startedAtMs: Date.now() });
          } catch (pollErr) {
            const errorMessage = pollErr?.response?.data?.error || pollErr?.message || 'Audio upload analysis failed';
            setRecordingError(errorMessage);
            notifyError(errorMessage);
            setActionMessage('');
            setProcessingJob((prev) => prev ? {
              ...prev,
              status: 'failed',
              message: errorMessage,
              canCancel: false,
              canRetry: true,
            } : null);
            setIsAnalyzing(false);
            clearActiveAudioJob();
          }
        })();
        return;
      } catch (asyncErr) {
        const statusCode = asyncErr?.response?.status;
        const errCode = asyncErr?.code;
        const message = String(asyncErr?.message || '');
        const shouldFallbackToDirect =
          statusCode === 404 ||
          statusCode === 405 ||
          errCode === 'ERR_NETWORK' ||
          message.toLowerCase().includes('network error');

        if (!shouldFallbackToDirect) {
          throw asyncErr;
        }

        const controller = new AbortController();
        directUploadAbortRef.current = controller;
        setProcessingJob({
          jobId: null,
          mode: 'direct',
          audioMode: normalizedMode,
          status: 'running',
          progress: 20,
          message: `${modeLabel}: processing in compatibility mode...`,
          canCancel: true,
          canRetry: false,
          fileName: selectedFile.name,
        });

        setActionMessage(`${modeLabel}: processing in background (compatibility mode)...`);
        notifySuccess('Upload accepted. Analysis is running in background.');
        setIsUploadingAudio(false);
        if (inputTarget) inputTarget.value = '';

        aiAPI.transcribeAudio(selectedFile, { signal: controller.signal, mode: normalizedMode })
          .then(async (directResponse) => {
            if (controller.signal.aborted) {
              return;
            }
            const finalPayload = directResponse?.data || directResponse;
            await applyUploadedAudioResult(finalPayload, selectedFile.name);
            notifySuccess('Audio uploaded, transcribed, and analyzed successfully.');
            setActionMessage('');
            setProcessingJob((prev) => prev ? {
              ...prev,
              status: 'completed',
              progress: 100,
              message: 'Completed',
              canCancel: false,
              canRetry: false,
            } : null);
            setIsAnalyzing(false);
            directUploadAbortRef.current = null;
            clearActiveAudioJob();
          })
          .catch((directErr) => {
            if (directErr?.name === 'CanceledError' || directErr?.code === 'ERR_CANCELED') {
              return;
            }
            const errorMessage = directErr?.response?.data?.error || directErr?.message || 'Audio upload analysis failed';
            setRecordingError(errorMessage);
            notifyError(errorMessage);
            setActionMessage('');
            setProcessingJob((prev) => prev ? {
              ...prev,
              status: 'failed',
              message: errorMessage,
              canCancel: false,
              canRetry: true,
            } : null);
            setIsAnalyzing(false);
            directUploadAbortRef.current = null;
            clearActiveAudioJob();
          });
        return;
      }
    } catch (err) {
      const errorMessage = err?.response?.data?.error || err?.message || 'Audio upload analysis failed';
      setRecordingError(errorMessage);
      notifyError(errorMessage);
      setIsAnalyzing(false);
      setIsUploadingAudio(false);
      setActionMessage('');
      setProcessingJob((prev) => prev ? {
        ...prev,
        status: 'failed',
        message: errorMessage,
        canCancel: false,
        canRetry: true,
      } : null);
      clearActiveAudioJob();
      if (inputTarget) inputTarget.value = '';
    }
  };

  const handleUploadedAudio = async (event) => {
    const selectedFile = event.target?.files?.[0];
    if (!selectedFile) return;

    const fileName = selectedFile.name.toLowerCase();
    const allowedExtensions = ['.wav', '.mp3', '.m4a', '.webm', '.mp4'];
    const isAllowed = allowedExtensions.some((ext) => fileName.endsWith(ext));
    if (!isAllowed) {
      notifyError('Please upload WAV, MP3, M4A, WEBM, or MP4 audio.');
      event.target.value = '';
      return;
    }

    if (selectedFile.size > 50 * 1024 * 1024) {
      notifyError('Audio file is too large. Please upload a WAV file under 50MB.');
      event.target.value = '';
      return;
    }
    await beginAudioUpload(selectedFile, event.target, audioProcessingMode);
  };

  const downloadTranscript = (format = 'txt') => {
    const content = format === 'json' 
      ? JSON.stringify({ transcript: fullTranscript, analysis, timestamp: new Date().toISOString() }, null, 2)
      : fullTranscript;
    const blob = new Blob([content], { type: format === 'txt' ? 'text/plain' : 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadAudio = () => {
    if (audioBlob) {
      const url = URL.createObjectURL(audioBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `recording-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.webm`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const copyHistoryTranscript = (item) => {
    if (navigator.clipboard && item.transcript_text) {
      navigator.clipboard.writeText(item.transcript_text)
        .then(() => {
          const id = item.transcript_id || item.session_id || item.created_at || Date.now();
          setCopiedHistoryId(id);
          setActionMessage('Copied to clipboard ✓');
          setTimeout(() => setCopiedHistoryId(null), 1600);
          setTimeout(() => setActionMessage(''), 1800);
        })
        .catch((error) => {
          console.error('Copy failed', error);
          setActionMessage('Copy failed, try again.');
          setTimeout(() => setActionMessage(''), 1800);
        });
    }
  };

  const downloadHistoryTranscript = (item) => {
    if (!item || !item.transcript_text) return;
    const content = `Transcript (recorded ${new Date(item.created_at).toLocaleString()}):\n\n${item.transcript_text}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `history-${item.transcript_id || item.session_id || Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const deleteHistoryItem = async (item) => {
    if (!item) return;
    const result = await confirm({
      title: 'Delete Recording',
      message: 'Are you sure you want to delete this recording?',
      actions: [{ label: 'Delete', value: 'delete', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'delete') return;

    const transcriptId = item.transcript_id;
    const sessionId = item.session_id;
    const isPersistedTranscript = /^\d+$/.test(String(transcriptId || ''));

    if (isPersistedTranscript) {
      try {
        await aiAPI.deleteTranscript(transcriptId);
      } catch (error) {
        const status = error?.response?.status;
        if (status === 404) {
          // Already gone (or stale ID in cache): continue and clear it locally.
          console.warn('Transcript already absent on server:', transcriptId);
        } else {
        console.error('Delete failed:', error);
        notifyError('Failed to delete recording from server. Please try again.');
        return;
        }
      }
    }

    setTranscriptsHistory((prev) => {
      const transcriptKey = String(transcriptId || '');
      const sessionKey = String(sessionId || '');
      const next = prev.filter((entry) => {
        const entryTranscriptKey = String(entry?.transcript_id || '');
        const entrySessionKey = String(entry?.session_id || '');
        return entryTranscriptKey !== transcriptKey && entrySessionKey !== sessionKey;
      });
      localStorage.setItem('voiceRecorderHistory', JSON.stringify(next));
      return next;
    });

    appendAuditLog({
      event: 'deleted',
      created_at: new Date().toISOString(),
      transcript_id: transcriptId,
      session_id: sessionId
    });

    const successMessage = isPersistedTranscript
      ? 'Moved to trash on the server.'
      : 'Recording deleted successfully.';

    // Only allow undo for local-only transcripts (session_id based).
    // Server-persisted transcripts (numeric IDs) are soft-deleted and can be restored by admins.
    if (!isPersistedTranscript) {
      setDeletedItem(item);
      setActionMessage('Recording deleted successfully. Undo?');
    } else {
      setDeletedItem(null);
      setActionMessage(successMessage);
    }

    notifySuccess(successMessage);

    // Refresh the transcript list from server after deletion to ensure UI stays in sync
    // and prevent any stale state issues that could show "No Results"
    setTimeout(async () => {
      try {
        await loadTranscriptsHistory();
      } catch (error) {
        console.error('Error refreshing transcripts after delete:', error);
      }
      setTimeout(() => setActionMessage(''), 1200);
    }, 400);
  };

  const undoDelete = () => {
    if (!deletedItem) return;
    // Safeguard: Prevent undo for server-persisted transcripts (numeric IDs).
    // These are handled by server-side soft delete and admin recovery.
    const isPersistedItem = /^\d+$/.test(String(deletedItem.transcript_id || ''));
    if (isPersistedItem) {
      notifyError('Server-persisted deletions cannot be undone.');
      return;
    }

    setTranscriptsHistory((prev) => {
      const next = [deletedItem, ...prev].slice(0, 50);
      localStorage.setItem('voiceRecorderHistory', JSON.stringify(next));
      return next;
    });
    setActionMessage('Delete undone successfully');
    setDeletedItem(null);
    setTimeout(() => setActionMessage(''), 2400);
  };

  const refreshHistory = async () => {
    setActionMessage('Refreshing history...');
    await loadTranscriptsHistory();
    setActionMessage('History synchronized');
    setTimeout(() => setActionMessage(''), 2000);
  };

  const clearAllHistory = async () => {
    if (!transcriptsHistory.length) {
      setActionMessage('No recordings to clear.');
      setTimeout(() => setActionMessage(''), 1800);
      return;
    }

    const result = await confirm({
      title: 'Clear History',
      message: 'Clear all recordings from this history list? Server-saved recordings will be moved to trash.',
      actions: [{ label: 'Clear All', value: 'clear', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'clear') return;

    const persistedIds = [...new Set(
      transcriptsHistory
        .map((item) => item?.transcript_id)
        .filter((id) => /^\d+$/.test(String(id || '')))
        .map((id) => String(id))
    )];

    let failedPersistedIds = new Set();

    if (persistedIds.length > 0) {
      setActionMessage('Clearing server recordings...');
      try {
        await aiAPI.clearAllTranscriptAnalysis();
        await aiAPI.clearAllTranscripts();
      } catch (bulkError) {
        // Fallback to per-item deletion for compatibility with older backend instances.
        for (const id of persistedIds) {
          try {
            await aiAPI.clearTranscriptAnalysis(id);
          } catch (analysisError) {
            const status = analysisError?.response?.status;
            if (status !== 404) {
              failedPersistedIds.add(id);
              continue;
            }
          }
          try {
            await aiAPI.deleteTranscript(id);
          } catch (error) {
            const status = error?.response?.status;
            // Treat already-missing rows as cleared to avoid false failures.
            if (status === 404) continue;
            failedPersistedIds.add(id);
          }
        }
      }

      // Verify what still exists on server to avoid false "cleared" states.
      try {
        const latestResponse = await aiAPI.getTranscripts();
        const latest = latestResponse?.data || latestResponse;
        const rows = Array.isArray(latest?.transcripts) ? latest.transcripts : [];
        const stillOnServer = new Set(
          rows
            .map((item) => String(item?.transcript_id || ''))
            .filter((id) => persistedIds.includes(id))
        );
        for (const id of stillOnServer) {
          failedPersistedIds.add(id);
        }
      } catch (verifyError) {
        // If we cannot verify server state, do not claim complete success.
        for (const id of persistedIds) {
          failedPersistedIds.add(id);
        }
      }
    }

    const remaining = transcriptsHistory.filter((item) => {
      const id = String(item?.transcript_id || '').trim();
      return !/^\d+$/.test(id);
    });

    setDeletedItem(null);
    setTranscriptsHistory(remaining);
    localStorage.setItem('voiceRecorderHistory', JSON.stringify(remaining));
    // Hard clear local cache keys used by this component.
    localStorage.removeItem('voiceRecorderHistory');
    localStorage.removeItem('voiceRecorderHiddenPersistedIds');

    if (failedPersistedIds.size > 0) {
      notifyError(`Cleared from this app. ${failedPersistedIds.size} item(s) could not be removed from server.`);
      setActionMessage('Recordings cleared from this application.');
    } else {
      notifySuccess('Moved all recordings to trash on the server.');
      setActionMessage('All recordings moved to trash.');
      // Confirm UI reflects server source-of-truth after bulk delete.
      await loadTranscriptsHistory();
    }

    setTimeout(() => setActionMessage(''), 2600);
  };

  const exportHistoryCSV = () => {
    if (!transcriptsHistory.length) return;
    const rows = transcriptsHistory.map(item => ({
      date: item.created_at,
      transcript: item.transcript_text,
      sentiment: item.sentiment || 'N/A',
      summary: item.summary || ''
    }));

    const header = ['date','transcript','sentiment','summary'];
    const csvContent = [header.join(','), ...rows.map(r => [
      JSON.stringify(r.date),
      JSON.stringify(r.transcript),
      JSON.stringify(r.sentiment),
      JSON.stringify(r.summary)
    ].join(','))].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `voiceRecorder_history_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const renderSentimentBadge = (sentiment) => {
    const className = `sentimentBadge sentiment${sentiment?.toLowerCase() || 'Neutral'}`;
    return (
      <div className={className}>
        {sentiment || 'Analyzing...'}
        {analysis?.confidence && <span>({analysis.confidence})</span>}
      </div>
    );
  };

  const filteredHistory = [...transcriptsHistory]
    .sort((a, b) => {
      const aTs = Date.parse(a?.updated_at || a?.created_at || 0) || 0;
      const bTs = Date.parse(b?.updated_at || b?.created_at || 0) || 0;
      return bTs - aTs;
    })
    .filter((item) => item.transcript_text.toLowerCase().includes(searchQuery.toLowerCase())
      || (item.summary || '').toLowerCase().includes(searchQuery.toLowerCase())
      || (item.sentiment || '').toLowerCase().includes(searchQuery.toLowerCase()));

  const showActionMessageToast = Boolean(actionMessage)
    && !(processingJob && /uploading|processing|analyzing/i.test(actionMessage));

  return (
    <div className={styles.voiceRecorderContainer}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <Volume2 size={26} /> Voice Recording Console
        </h1>
        <p className={styles.pageSubtitle}>
          Real-time transcription, waveform monitoring, and AI insights in one professional workspace
        </p>
      </div>

      {showActionMessageToast && (
        <div className={styles.toastSuccess} role="status" aria-live="polite">
          <span>{actionMessage}</span>
          {deletedItem && (
            <button className={styles.undoButton} onClick={undoDelete}>Undo</button>
          )}
        </div>
      )}

      {processingJob && (
        <div className={styles.processingBadge} role="status" aria-live="polite">
          <div className={styles.processingBadgeHeader}>
            <span className={styles.processingBadgeTitle}>
              Processing jobs {processingJob.audioMode ? <span className={styles.processingModeTag}>{processingJob.audioMode === 'full' ? 'Full' : 'Fast'}</span> : null}
            </span>
            <span className={styles.processingBadgePercent}>{Math.max(0, Math.min(100, Number(processingJob.progress || 0)))}%</span>
          </div>
          <div className={styles.processingBadgeMessage}>{processingJob.message || 'Processing audio...'}</div>
          <div className={styles.processingBarTrack}>
            <div
              className={styles.processingBarFill}
              style={{ width: `${Math.max(0, Math.min(100, Number(processingJob.progress || 0)))}%` }}
            />
          </div>
          <div className={styles.processingBadgeActions}>
            <button
              className={styles.secondaryBtn}
              onClick={cancelProcessingJob}
              disabled={!processingJob.canCancel}
              type="button"
            >
              Cancel
            </button>
            <button
              className={styles.primaryBtn}
              onClick={retryProcessingJob}
              disabled={!processingJob.canRetry}
              type="button"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>
            <Radio size={20} />
            Recording Controls
          </h2>
          <p className={styles.cardSubtitle}>
            Supports Chrome/Edge best. Grant microphone permission when prompted.
          </p>
        </div>

        <div className={`${styles.controlsGrid} card-body`}>
          <div className={styles.timerDisplay}>
            <Clock size={20} className="mr-2 inline" />
            {formatTime(recordingTime)}
          </div>

          <div className={styles.recordControls}>
            <button
              className={`${styles.primaryBtn} ${(isRecording && animatedIndicator) ? styles.recordingActive : ''} ${isRecording ? styles.dangerBtn : ''}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isAnalyzing || isUploadingAudio}
              aria-label={isRecording ? 'Stop recording' : 'Start recording'}
            >
              {isRecording ? <Square size={20} /> : <Radio size={20} />}
              <span>{isRecording ? 'Stop' : 'Record'}</span>
              {isRecording && <div className={styles.recordingIndicator} />}
            </button>

            <input
              ref={audioUploadInputRef}
              type="file"
              accept=".wav,.mp3,.m4a,.webm,.mp4,audio/wav,audio/mpeg,audio/mp4,audio/webm,video/mp4"
              style={{ display: 'none' }}
              onChange={handleUploadedAudio}
            />

            <button
              className={styles.secondaryBtn}
              onClick={() => audioUploadInputRef.current?.click()}
              disabled={isRecording || isAnalyzing || isUploadingAudio}
              aria-label="Upload audio"
              title={`Upload WAV, MP3, M4A, WEBM, or MP4 for transcription in ${audioProcessingMode === 'full' ? 'Full' : 'Fast'} mode`}
            >
              <Upload size={18} />
              <span>{isUploadingAudio ? 'Uploading...' : 'Upload Audio'}</span>
            </button>

            <div className={styles.modeToggleGroup} role="group" aria-label="Audio processing mode">
              <button
                type="button"
                className={`${styles.modeToggleButton} ${audioProcessingMode === 'fast' ? styles.modeToggleActive : ''}`}
                onClick={() => setAudioProcessingMode('fast')}
                disabled={isRecording || isUploadingAudio || isAnalyzing}
              >
                Fast mode {audioProcessingMode === 'fast' ? <span className={styles.modeRecommendedTag}>Recommended</span> : null}
              </button>
              <button
                type="button"
                className={`${styles.modeToggleButton} ${audioProcessingMode === 'full' ? styles.modeToggleActive : ''}`}
                onClick={() => setAudioProcessingMode('full')}
                disabled={isRecording || isUploadingAudio || isAnalyzing}
              >
                Full mode
              </button>
            </div>

            <div className={styles.modeHelperText}>
              Fast mode processes the first 60-90 seconds for quicker results. Full mode analyzes the entire audio for the most complete output.
            </div>

            {isRecording && (
              <button
                className={styles.secondaryBtn}
                onClick={togglePause}
                aria-label={isPaused ? 'Resume' : 'Pause'}
              >
                {isPaused ? <Play size={18} /> : <Pause size={18} />}
                <span>{isPaused ? 'Resume' : 'Pause'}</span>
              </button>
            )}
          </div>

          <div className={styles.volumeMeter}>
            <Volume2 size={16} />
            <div className={styles.volumeBar} style={{width: `${volumeLevel * 100}%`}} />
          </div>
          <div className={styles.accessibilityRow}>
            <label className={styles.switchLabel}>
              <input
                type="checkbox"
                checked={animatedIndicator}
                onChange={(e) => setAnimatedIndicator(e.target.checked)}
              />
              Animated live indicators
            </label>
            <label className={styles.switchLabel}>
              <input
                type="checkbox"
                checked={isCompactMode}
                onChange={(e) => setIsCompactMode(e.target.checked)}
              />
              Compact panel mode
            </label>
            <span className={styles.helpText}>Toggle compact interface mode for enterprise dashboards.</span>
          </div>
        </div>
      </div>

      {recordingError && (
        <div className={`${styles.alert} ${styles.alertDanger}`}>
          <span>❌</span>
          {recordingError}
          <button className={styles.btnClose} onClick={() => setRecordingError('')}>&times;</button>
        </div>
      )}

      {isRecording && !isCompactMode && (
        <div className={styles.visualizationContainer}>
          <div className={styles.waveformWrapper}>
            <div className={styles.waveformTitle}>Audio Waveform</div>
            <canvas 
              ref={canvasRef} 
              className={styles.waveformCanvas}
              width={800} 
              height={140}
              aria-label="Real-time audio waveform visualization"
            />
            <div className={styles.waveformStats}>
              <span>Real-time • {isPaused ? 'Paused' : 'Recording'}</span>
              <span>{micDbLevel.toFixed(1)} dB</span>
            </div>
          </div>
          
          <div className={styles.liveStatusBox}>
            <div className={styles.statusHeader}>
              <h4 className={styles.statusTitle}>Live Status</h4>
              <div className={`${styles.statusIndicator} ${isPaused ? styles.paused : styles.recording}`} />
            </div>
            
            <div className={styles.statusGrid}>
              <div className={styles.statusItem}>
                <div className={styles.statusLabel}>Recording State</div>
                <div className={styles.statusValue}>{isPaused ? 'Paused' : 'Recording'}</div>
              </div>
              
              <div className={styles.meterSection}>
                <div className={styles.meterLabel}>
                  <span className={styles.iconLabel}>Microphone</span>
                  <span className={styles.dbValue}>{micDbLevel.toFixed(1)} dB</span>
                </div>
                <div className={styles.levelMeter}>
                  <div className={styles.levelFill} style={{ width: `${Math.max(2, (micDbLevel + 60) / 0.6)}%` }} />
                </div>
              </div>
              
              <div className={styles.meterSection}>
                <div className={styles.meterLabel}>
                  <span className={styles.iconLabel}>CPU Usage</span>
                  <span className={styles.cpuValue}>{cpuUsage}%</span>
                </div>
                <div className={styles.levelMeter}>
                  <div className={styles.cpuFill} style={{ width: `${cpuUsage}%` }} />
                </div>
              </div>
            </div>
            
            <div className={styles.statusFooter}>
              <span className={styles.footerText}>Professional audio monitoring</span>
            </div>
          </div>
        </div>
      )}

      {(finalTranscript || liveTranscript) && (
        <div className={styles.transcriptContainer} ref={transcriptRef} role="log" aria-live="polite">
          <div className={styles.finalParagraph}>
            {finalTranscript.split(/(?<=[.!?])\s+/).map((p, i) => p.trim() && (
              <p key={i}>{p.trim()}</p>
            ))}
          </div>
          {liveTranscript && (
            <div className={styles.liveTranscript}>
              {liveTranscript}<span className={styles.cursorBlink}>|</span>
            </div>
          )}
        </div>
      )}

      {audioBlob && (
        <div className={styles.downloadSection}>
          <div className={`${styles.dropdownContainer} downloadDropdown`}>
            <button
              className={styles.primaryBtn}
              onClick={() => setShowDownloadOptions(!showDownloadOptions)}
              title="Download in different formats"
              aria-label="Download options"
            >
              <Download size={20} /> Download
            </button>
            {showDownloadOptions && (
              <div className={styles.dropdownMenu}>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    downloadAudio();
                    setShowDownloadOptions(false);
                  }}
                  title="Download as webm audio file"
                >
                  <Download size={16} /> Audio (.webm)
                </button>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    downloadTranscript('txt');
                    setShowDownloadOptions(false);
                  }}
                  title="Download as text file"
                >
                  <Download size={16} /> Text (.txt)
                </button>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    downloadTranscript('json');
                    setShowDownloadOptions(false);
                  }}
                  title="Download as JSON file"
                >
                  <Download size={16} /> JSON (.json)
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {analysis && !analysis.error && !isCompactMode && (
        <div className={styles.analysisResults}>
          <div className={styles.analysisCard}>
            <h4>Sentiment Analysis</h4>
            {renderSentimentBadge(analysis.sentiment)}
            {analysis.summary && <p>{analysis.summary}</p>}
          </div>
        </div>
      )}

      {isAnalyzing && !processingJob && <LoadingSpinner />}

      <div className={styles.historySection}>
        <div className={styles.historyHeaderRow}>
          <div className={`${styles.dropdownContainer} historyDropdown`} style={{ position: 'relative', flex: 1 }}>
            <button 
              className={`${styles.historyToggleBtn} ${showHistory ? styles.historyExpanded : ''}`}
              onClick={() => setShowHistory(!showHistory)}
              title="View recording history"
            >
              <History size={20} />
              <span>Recording History</span>
              <span className={styles.historyBadge}>{transcriptsHistory.length}</span>
              <span className={`${styles.chevron} ${showHistory ? styles.chevronUp : ''}`}>▼</span>
            </button>
          </div>
          
          <div className={`${styles.dropdownContainer} historyDropdown`} style={{ position: 'relative' }}>
            <button 
              className={styles.secondaryBtn}
              onClick={() => setShowHistoryOptions(!showHistoryOptions)}
              title="History options"
              aria-label="History options"
            >
              <MoreVertical size={20} />
            </button>
            
            {showHistoryOptions && (
              <div className={styles.dropdownMenu}>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    refreshHistory();
                    setShowHistoryOptions(false);
                  }}
                  title="Sync recordings across devices"
                >
                  <RefreshCw size={16} /> Multi-device Sync
                </button>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    exportHistoryCSV();
                    setShowHistoryOptions(false);
                  }}
                  title="Export all history to CSV"
                >
                  <FileDown size={16} /> Export CSV
                </button>
                <button
                  className={styles.dropdownItem}
                  onClick={() => {
                    clearAllHistory();
                    setShowHistoryOptions(false);
                  }}
                  title="Delete all recordings from this history"
                >
                  <Trash2 size={16} /> Move All to Trash
                </button>
              </div>
            )}
          </div>
        </div>

        {showHistory && (
          <div className={styles.historyDropdownContent}>
            <div className={styles.searchRow}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search transcripts, summary or sentiment..."
                className={styles.searchInput}
              />
            </div>
            
            <div className={styles.historyList}>
              {filteredHistory.length === 0 ? (
                <div className={styles.emptyState}>
                  <div className={styles.emptyStateIcon}>No Results</div>
                  <p>No recordings match that query.</p>
                </div>
              ) : (
                filteredHistory.map((item) => (
                  <div key={item.transcript_id || item.session_id || item.created_at} className={styles.historyItem}>
                    <div className={styles.historyItemTop}>
                      <div className={styles.historyItemMeta}>
                        <p className={styles.historyItemTitle}>{new Date(item.created_at).toLocaleString()}</p>
                        {(() => {
                          const sentimentValue = item.sentiment || item.analysis?.sentiment || 'NEUTRAL';
                          return (
                        <small className={styles.historyItemSentiment}>
                            {`Sentiment: ${sentimentValue}`}
                        </small>
                          );
                        })()}
                      </div>
                      <div className={styles.historyActions}>
                        <button onClick={() => copyHistoryTranscript(item)} title="Copy transcript to clipboard" aria-label="Copy transcript">
                        {(copiedHistoryId === (item.transcript_id || item.session_id || item.created_at)) ? <Check size={16} /> : <Copy size={16} />}
                        </button>
                        <button onClick={() => downloadHistoryTranscript(item)} title="Download transcript" aria-label="Download transcript">
                          <Download size={16} />
                        </button>
                        <button onClick={() => deleteHistoryItem(item)} title="Delete minute only" aria-label="Delete minute only">
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                    <p className={styles.historyItemText}>{item.transcript_text.slice(0, 120)}{item.transcript_text.length > 120 ? '...' : ''}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default VoiceRecorder;


