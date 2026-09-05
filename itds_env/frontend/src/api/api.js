import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || `http://${window.location.hostname}:5001`;

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000  // 120s global timeout (increased from 60s) for heavy AI analysis
});
// Allow sending/receiving HttpOnly cookies (refresh token)
api.defaults.withCredentials = true;

// Client metadata helper - OPTIMIZED for speed
// Geolocation is collected asynchronously in background without blocking
const getClientMetadata = async () => {
  // Return immediately with core metadata (fast path)
  const metadata = {
    client_ip: null,  // Will be populated if available
    user_agent: navigator.userAgent,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    platform: navigator.platform,
    language: navigator.language,
    ram_gb: navigator.deviceMemory || null,
    cpu_cores: navigator.hardwareConcurrency || null,
    hardware_id: btoa(`${navigator.platform}-${navigator.deviceMemory || ''}-${navigator.hardwareConcurrency || ''}`.slice(0, 100)),
    device_model: `${navigator.platform} (${navigator.userAgentData?.brands?.map(b => b.brand).join(', ') || 'Unknown'})`,
    location: null,
    screen: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
    connection_type: navigator.connection?.effectiveType || 'unknown'
  };
  const ipPromise = (async () => {
    try {
      const ipResponse = await Promise.race([
        fetch('https://api.ipify.org?format=json', { method: 'GET' }).then((r) => r.json()),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000)),
      ]);
      metadata.client_ip = ipResponse.ip;
      return;
    } catch {
      // Try fallback service
    }

    try {
      const altResponse = await Promise.race([
        fetch('https://icanhazip.com/', { method: 'GET' }).then((r) => r.text()),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1500)),
      ]);
      metadata.client_ip = altResponse.trim();
    } catch {
      // Leave null if unavailable
    }
  })();

  const geoPromise = (async () => {
    if (!navigator.geolocation) return;
    try {
      const pos = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 3000,
          maximumAge: 30000,
        });
      });
      if (pos?.coords) {
        metadata.location = {
          latitude: Number(pos.coords.latitude.toFixed(6)),
          longitude: Number(pos.coords.longitude.toFixed(6)),
          accuracy_m: Math.round(pos.coords.accuracy || 0),
          captured_at: new Date().toISOString(),
        };
      }
    } catch {
      // Permission denied or timeout; fallback stays null
    }
  })();

  await Promise.allSettled([ipPromise, geoPromise]);

  return metadata;
};

// Request interceptor - Add token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Set content-type only for body-based requests; avoid GET preflight issues.
    const method = (config.method || 'get').toLowerCase();
    const hasBodyMethod = ['post', 'put', 'patch', 'delete'].includes(method);
    if (hasBodyMethod) {
      if (config.data instanceof FormData) {
        delete config.headers['Content-Type'];
      } else {
        config.headers['Content-Type'] = 'application/json';
      }
    } else {
      delete config.headers['Content-Type'];
    }

    return config;
  },
  (error) => Promise.reject(error)
);


// Response interceptor - Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest?._retry) {
      originalRequest._retry = true;
      // Try to refresh using cookie-based refresh token
      return api.post('/api/auth/refresh').then((resp) => {
        const newAccess = resp.data?.access_token;
        if (newAccess) {
          localStorage.setItem('token', newAccess);
          originalRequest.headers['Authorization'] = `Bearer ${newAccess}`;
          return api(originalRequest);
        }
        // If refresh didn't return a token, fall through to logout
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(error);
      }).catch(() => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(error);
      });
    }
    return Promise.reject(error);
  }
);

// ============================================
// Auth API
// ============================================

export const authAPI = {
  // Login with real metadata
  login: async (credentials) => {
    const metadata = await getClientMetadata();
    const providedMeta = (credentials && typeof credentials.client_metadata === 'object') ? credentials.client_metadata : {};
    const mergedMetadata = {
      ...metadata,
      ...providedMeta,
      client_ip: providedMeta.client_ip || metadata.client_ip,
      location: providedMeta.location || metadata.location,
    };
    return api.post('/api/auth/login', { ...credentials, client_metadata: mergedMetadata });
  },

  
  // Logout with real metadata
  logout: async (payload = {}) => {
    const metadata = await getClientMetadata();
    const providedMeta = (payload && typeof payload.client_metadata === 'object') ? payload.client_metadata : {};
    const mergedMetadata = {
      ...metadata,
      ...providedMeta,
      client_ip: providedMeta.client_ip || metadata.client_ip,
      location: providedMeta.location || metadata.location,
    };
    return api.post('/api/auth/logout', { ...payload, client_metadata: mergedMetadata });
  },

  
  // Get current user
  getCurrentUser: () => api.get('/api/auth/me'),
  // Refresh access token (server sets rotated refresh cookie)
  refresh: () => api.post('/api/auth/refresh'),
  
  // Change password
  changePassword: (data) => api.post('/api/auth/change-password', data),
  
  // Get all users (admin)
  getUsers: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/admin/users${query ? `?${query}` : ''}`);
  },
  
  // Update user
  updateUser: (userId, data) => api.put(`/api/admin/users/${userId}`, data),
  
  // Delete user (admin)
  deleteUser: (userId, data = {}) => api.delete(`/api/admin/users/${userId}`, { data }),

  // Restore soft-deleted user
  restoreUser: (userId) => api.post(`/api/admin/users/${userId}/restore`),

  // Permanently delete user
  purgeUser: (userId) => api.delete(`/api/admin/users/${userId}/purge`),
  
  // Request password reset
  forgotPassword: (email) => api.post('/api/auth/forgot-password', { email }),
  
  // Reset password with token
  resetPassword: (token, newPassword) => api.post('/api/auth/reset-password', { token, newPassword }),
  
  // Upload profile image - FIXED: No manual Content-Type header
  uploadProfileImage: (file) => {
    const formData = new FormData();
    formData.append('image', file);
    return api.post('/api/user/upload-profile-image', formData);
  }
};

// ============================================
// Data API
// ============================================

export const dataAPI = {
  // Get trends for a theme
  getTrends: (theme) => api.get(`/api/trends?theme=${encodeURIComponent(theme)}`),
  
  // Get summary for a year
  getSummary: (year) => api.get(`/api/summary?year=${year}`),
  
  // Search meeting minutes
  search: (query) => api.get(`/api/search?q=${encodeURIComponent(query)}`),
  
  // Get audit logs (admin)
  getAuditLogs: (limit = 100) => api.get(`/api/audit?limit=${limit}`),

  // Get activity logs with archiving/retrieval filters (admin)
  getActivityLogs: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/activity/logs?${query}`);
  },
  
  // Get meetings
  getMeetings: (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    return api.get(`/api/meetings?${queryString}`);
  },
  
  // Get single meeting
  getMeeting: (meetingId) => api.get(`/api/meetings/${meetingId}`),
  
  // Get meeting segments
  getSegments: (meetingId) => api.get(`/api/meetings/${meetingId}/segments`)
};

// ============================================
// AI & New APIs
// ============================================

export const aiAPI = {
  // Summarization
  summarize: (meetingId) => api.post('/api/ai/summarize', { meeting_id: meetingId }),

  // Question Answering
  qa: (question, history = []) => api.post('/api/ai/qa', { question, history }),

  // Sentiment Analysis
  analyzeSentiment: (meetingId) => api.post('/api/ai/sentiment', { meeting_id: meetingId }),
  getSentiment: (meetingId) => {
    const url = meetingId ? `/api/reports?type=sentiments&meeting_id=${meetingId}` : '/api/reports?type=sentiments';
    return api.get(url);
  },

  // Action Items
  extractActionItems: (meetingId) => api.post('/api/ai/action-items', { meeting_id: meetingId }),
  getActionItems: (meetingId) => {
    const params = new URLSearchParams({ type: 'action_items' });
    if (meetingId) params.set('meeting_id', meetingId);
    return api.get(`/api/reports?${params.toString()}`);
  },

  // Keywords
  extractKeywords: (meetingId) => api.post('/api/ai/keywords', { meeting_id: meetingId }),
  getKeywords: (meetingId) => {
    const params = new URLSearchParams({ type: 'keywords' });
    if (meetingId) params.set('meeting_id', meetingId);
    return api.get(`/api/reports?${params.toString()}`);
  },

  // Document Classification
  classifyDocument: (meetingId) => api.post('/api/ai/classify-document', { meeting_id: meetingId }),
  getClassifications: (meetingId) => {
    const url = meetingId ? `/api/ai/document-classifications?meeting_id=${meetingId}` : '/api/ai/document-classifications';
    return api.get(url);
  },

  // Named Entity Recognition
  getNER: (meetingId) => {
    const url = meetingId ? `/api/ai/ner?meeting_id=${meetingId}` : '/api/ai/ner';
    return api.get(url);
  },
  anonymize: (text) => api.post('/api/ai/anonymize', { text }),

  // Text Simplification
  simplifyText: (text) => api.post('/api/ai/simplify', { text }),

  // Theme Trends
  getThemeTrends: () => api.get('/api/ai/theme-trends'),
  getDynamicThemes: () => api.get('/api/ai/themes'),

  // Dashboard
  getDashboard: (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    return api.get(`/api/dashboard${params ? '?' + params : ''}`);
  },
  getRealtimeDashboard: () => api.get('/api/dashboard/realtime'),
  getRealtimeAnalytics: () => api.get('/api/dashboard/realtime'),
  getRealtimeStreamUrl: () => {
    const token = localStorage.getItem('token');
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    return `${API_BASE_URL}/api/dashboard/stream${query}`;
  },
  searchRealtimeAnalytics: (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    return api.get(`/api/analytics/search${params ? '?' + params : ''}`);
  },
  generateReport: (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const format = filters.format;
    const useBlob = format === 'csv' || format === 'pdf';
    return api.get(`/api/reports${params ? '?' + params : ''}`, useBlob ? { responseType: 'blob' } : undefined);
  },

  // Topic Modeling
  extractTopics: (meetingId) => api.post('/api/ai/extract-topics', { meeting_id: meetingId }),
  runBatchAnalysis: (payload = {}) => api.post('/api/ai/run-batch-analysis', payload),
  startBatchAnalysis: (payload = {}) => api.post('/api/ai/run-batch-analysis/start', payload),
  getBatchAnalysisStatus: (jobId) => api.get(`/api/ai/run-batch-analysis/status/${encodeURIComponent(jobId)}`),
  cancelBatchAnalysis: (jobId) => api.post(`/api/ai/run-batch-analysis/cancel/${encodeURIComponent(jobId)}`),

  // Similarity Search
  findSimilar: (text, topK = 5) => api.post('/api/ai/similar', { text, top_k: topK }),

  // Live Voice Analysis
  transcribeLive: (transcript) => api.post('/api/ai/transcribe', { transcript }),
  deleteTranscript: (transcriptId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.delete(`/api/ai/transcripts/${encodeURIComponent(transcriptId)}${query ? `?${query}` : ''}`);
  },
  deleteReportItem: (itemId) => api.delete(`/api/ai/report-item/${itemId}`),
  clearAllTranscripts: () => api.delete('/api/ai/transcripts'),
  hardDeleteAllMinutesAndRecordings: () => api.delete('/api/ai/transcripts?permanent=1&deleted_only=1&hard_delete=1'),
  restoreTranscript: (transcriptId) => api.post(`/api/ai/transcripts/${encodeURIComponent(transcriptId)}/restore`),
  getDeletedMeetings: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/ai/meetings/deleted${query ? `?${query}` : ''}`);
  },
  restoreDeletedMeetingMinute: (meetingId) => api.post(`/api/ai/meetings/${encodeURIComponent(meetingId)}/restore-minute`),
  clearTranscriptAnalysis: (transcriptId) => api.post(`/api/ai/transcripts/${encodeURIComponent(transcriptId)}/clear-analysis`),
  clearMeetingMinuteAndAnalysis: (meetingId) => api.post(`/api/ai/meetings/${encodeURIComponent(meetingId)}/clear-minute-analysis`),
  deleteSentimentRecord: (sentimentId) => api.delete(`/api/ai/sentiments/${encodeURIComponent(sentimentId)}`),
  deleteKeywordRecord: (keywordId) => api.delete(`/api/ai/keywords/${encodeURIComponent(keywordId)}`),
  clearAllTranscriptAnalysis: () => api.post('/api/ai/transcripts/clear-analysis'),
  getTranscripts: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/ai/transcripts${query ? `?${query}` : ''}`);
  },
  transcribeAudio: (file, options = {}) => {
    const formData = new FormData();
    formData.append('audio', file);
    if (options.mode) formData.append('mode', options.mode);
    return api.post('/api/ai/transcribe-audio', formData, {
      timeout: 300000,
      signal: options.signal,
    });
  },
  startTranscribeAudio: (file, options = {}) => {
    const formData = new FormData();
    formData.append('audio', file);
    if (options.mode) formData.append('mode', options.mode);
    return api.post('/api/ai/transcribe-audio/start', formData, { timeout: 120000 });
  },
  getTranscribeAudioStatus: (jobId) => api.get(`/api/ai/transcribe-audio/status/${encodeURIComponent(jobId)}`),
  cancelTranscribeAudioJob: (jobId) => api.post(`/api/ai/transcribe-audio/cancel/${encodeURIComponent(jobId)}`),
  analyzeSpeech: (text) => api.post('/api/ai/analyze-speech', { text }, { timeout: 120000 }),
  answerQuestion: (question, history = []) => api.post('/api/ai/answer-question', { question, history })
};




// ============================================
// Upload API
// ============================================

export const uploadAPI = {
  // Upload file with optimizations
  uploadFile: (file, onProgress, extraFields = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(extraFields || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        formData.append(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
      }
    });
    
    return api.post('/api/upload', formData, {
      timeout: 90000,  // 90 seconds for faster file processing
      onUploadProgress: (progressEvent) => {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        if (onProgress) {
          onProgress(percentCompleted);
        }
      }
    });
  },
  
  // Upload multiple files with parallel processing optimization
  uploadFiles: (files, onProgress, extraFields = {}) => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    Object.entries(extraFields || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        formData.append(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
      }
    });
    
    return api.post('/api/upload/multiple', formData, {
      timeout: 180000,  // 3 minutes for multiple files (reduced from 5)
      onUploadProgress: (progressEvent) => {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        if (onProgress) {
          onProgress(percentCompleted);
        }
      }
    });
  },
  
  // Get upload status
  getUploadStatus: (uploadId) => api.get(`/api/upload/status/${uploadId}`),
  
  // Cancel upload
  cancelUpload: (uploadId) => api.post(`/api/upload/cancel/${uploadId}`)
};

// ============================================
// Export API
// ============================================

export const exportAPI = {
  // Export to CSV
  exportCSV: (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    return api.get(`/api/export/csv?${queryString}`, { responseType: 'blob' });
  },
  
  // Export to PDF
  exportPDF: (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    return api.get(`/api/export/pdf?${queryString}`, { responseType: 'blob' });
  },
  
  // Export to JSON
  exportJSON: (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    return api.get(`/api/export/json?${queryString}`, { responseType: 'blob' });
  }
};

// ============================================
// Admin API
// ============================================

export const adminAPI = {
  // Get all users (admin only - requires JWT with admin role)
  getUsers: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/admin/users${query ? `?${query}` : ''}`);
  },
  
  // Create new user (admin only)
  createUser: (userData) => api.post('/api/admin/users', userData),
  
  // Update user role (admin only)
  updateUser: (userId, data) => api.put(`/api/admin/users/${userId}`, data),
  
  // Delete user (admin only)
  deleteUser: (userId, data = {}) => api.delete(`/api/admin/users/${userId}`, { data }),

  // Restore soft-deleted user
  restoreUser: (userId) => api.post(`/api/admin/users/${userId}/restore`),

  // Permanently delete user
  purgeUser: (userId) => api.delete(`/api/admin/users/${userId}/purge`),

  // Super-admin only: permanently clear login/logout history
  purgeLoginHistory: (confirmationPhrase) => api.delete('/api/admin/purge-login-history', {
    data: { confirmation_phrase: confirmationPhrase }
  }),

  // System health metric (backend-calculated)
  getSystemHealth: () => api.get('/api/admin/system-health')
};

// ============================================
// Notification API
// ============================================

export const notificationsAPI = {
  getSummary: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/notifications/summary${query ? `?${query}` : ''}`);
  },
  getNotifications: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/notifications${query ? `?${query}` : ''}`);
  },
  markAsRead: (notificationId) => api.post(`/api/notifications/${notificationId}/read`),
  markAllAsRead: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.post(`/api/notifications/read-all${query ? `?${query}` : ''}`);
  },
  clearAll: (payload = {}) => api.post('/api/notifications/clear-all', payload),
  archiveNotification: (notificationId) => api.post(`/api/notifications/${notificationId}/archive`),
  restoreNotification: (notificationId) => api.post(`/api/notifications/${notificationId}/restore`),
  deleteNotification: (notificationId) => api.delete(`/api/notifications/${notificationId}`),
};

// ============================================
// Events API
// ============================================

export const eventsAPI = {
  listEvents: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/events${query ? `?${query}` : ''}`);
  },
  createEvent: (payload) => api.post('/api/events', payload),
  updateEvent: (eventId, payload) => api.put(`/api/events/${encodeURIComponent(eventId)}`, payload),
  deleteEvent: (eventId) => api.delete(`/api/events/${encodeURIComponent(eventId)}`),
  previewRecipients: (payload) => api.post('/api/events/preview-recipients', payload),
  sendEvent: (eventId) => api.post(`/api/events/${encodeURIComponent(eventId)}/send`),
  sendTestEmail: (eventId) => api.post(`/api/events/${encodeURIComponent(eventId)}/test-email`),
  downloadCalendar: (eventId) => api.get(`/api/events/${encodeURIComponent(eventId)}/calendar.ics`, { responseType: 'blob' }),
};

// ============================================
// Reports API
// ============================================

export const reportsAPI = {
  getExecutiveSummary: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/reports/executive-summary${query ? `?${query}` : ''}`);
  },
  getFormattedHtmlReport: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return api.get(`/api/reports/formatted-html${query ? `?${query}` : ''}`);
  },
  getPresentationTemplates: () => {
    return api.get('/api/reports/presentation/templates');
  },
  exportPresentation: (payload = {}) => {
    return api.post('/api/reports/presentation', payload, { responseType: 'blob' });
  },
  exportPresentationEnhanced: (payload = {}) => {
    return api.post('/api/reports/presentation/advanced', payload, { 
      responseType: 'blob',
      timeout: 120000  // 2 minute timeout for enhanced export
    });
  },
  scheduleReport: (payload = {}) => {
    return api.post('/api/reports/schedule', payload);
  },
  getScheduledReports: () => {
    return api.get('/api/reports/schedule');
  },
  updateScheduledReport: (id, payload = {}) => {
    return api.put(`/api/reports/schedule/${id}`, payload);
  },
  deleteScheduledReport: (id) => {
    return api.delete(`/api/reports/schedule/${id}`);
  },
  sendScheduledReportNow: (id) => {
    return api.post(`/api/reports/send-now/${id}`);
  },
  getSentimentTrends: (year) => {
    return api.get(`/api/reports/sentiment-trends/${year}`);
  },
  getGrowthAnalysis: (year) => {
    return api.get(`/api/reports/growth-analysis/${year}`);
  },
  getAnomalyDetails: (year) => {
    return api.get(`/api/reports/anomalies-detailed/${year}`);
  },
  getBranding: () => {
    return api.get('/api/reports/branding');
  },
  updateBranding: (payload = {}) => {
    return api.put('/api/reports/branding', payload);
  }
};

// Default export
export default api;

