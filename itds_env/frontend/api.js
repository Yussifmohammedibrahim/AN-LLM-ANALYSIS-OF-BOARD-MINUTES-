import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL ; (window.location.hostname === 'localhost' ? 'http://localhost:5000' : '');

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000  // 30s global timeout for file processing
});

// Request interceptor - Add token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    if (!(config.data instanceof FormData)) {
      config.headers['Content-Type'] = 'application/json';
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
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// ============================================
// Auth API
// ============================================

export const authAPI = {
  login: (credentials) => api.post('/api/auth/login', credentials),
  logout: () => api.post('/api/auth/logout'),
  getCurrentUser: () => api.get('/api/auth/me'),
  changePassword: (data) => api.post('/api/auth/change-password', data),
  getUsers: () => api.get('/api/admin/users'),
  updateUser: (userId, data) => api.put(`/api/admin/users/${userId}`, data),
  deleteUser: (userId) => api.delete(`/api/admin/users/${userId}`),
  forgotPassword: (email) => api.post('/api/auth/forgot-password', { email }),
  resetPassword: (token, newPassword) => api.post('/api/auth/reset-password', { token, newPassword }),
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
  getTrends: (theme) => api.get(`/api/trends?theme=${encodeURIComponent(theme)}`),
  getSummary: (year) => api.get(`/api/summary?year=${year}`),
  search: (query) => api.get(`/api/search?q=${encodeURIComponent(query)}`),
  getAuditLogs: (limit = 100) => api.get(`/api/audit?limit=${limit}`),
  getMeetings: (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    return api.get(`/api/meetings?${queryString}`);
  },
  getMeeting: (meetingId) => api.get(`/api/meetings/${meetingId}`),
  getSegments: (meetingId) => api.get(`/api/meetings/${meetingId}/segments`)
};

// ============================================
// AI & New APIs
// ============================================

export const aiAPI = {
  summarize: (meetingId) => api.post('/api/ai/summarize', { meeting_id: meetingId }),
  qa: (question) => api.post('/api/ai/qa', { question }),
  analyzeSentiment: (meetingId) => api.post('/api/ai/analyze-sentiment', { meeting_id: meetingId }),
  getSentiment: (meetingId) => {
    const url = meetingId ? `/api/ai/sentiment?meeting_id=${meetingId}` : '/api/ai/sentiment';
    return api.get(url);
  },
  extractActionItems: (meetingId) => api.post('/api/ai/extract-action-items', { meeting_id: meetingId }),
  getActionItems: (meetingId) => {
    const url = meetingId ? `/api/ai/action-items?meeting_id=${meetingId}` : '/api/ai/action-items';
    return api.get(url);
  },
  extractKeywords: (meetingId) => api.post('/api/ai/extract-keywords', { meeting_id: meetingId }),
  getKeywords: (meetingId) => {
    const url = meetingId ? `/api/ai/keywords?meeting_id=${meetingId}` : '/api/ai/keywords';
    return api.get(url);
  },
  classifyDocument: (meetingId) => api.post('/api/ai/classify-document', { meeting_id: meetingId }),
  getClassifications: (meetingId) => {
    const url = meetingId ? `/api/ai/document-classifications?meeting_id=${meetingId}` : '/api/ai/document-classifications';
    return api.get(url);
  },
  getNER: (meetingId) => {
    const url = meetingId ? `/api/ai/ner?meeting_id=${meetingId}` : '/api/ai/ner';
    return api.get(url);
  },
  anonymize: (text) => api.post('/api/ai/anonymize', { text }),
  simplifyText: (text) => api.post('/api/ai/simplify', { text }),
  getThemeTrends: () => api.get('/api/ai/theme-trends'),
  getDashboard: (filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    return api.get(`/api/dashboard${params ? '?' + params : ''}`);
  },
  getRealtimeDashboard: () => api.get('/api/dashboard/realtime'),
  extractTopics: (meetingId) => api.post('/api/ai/extract-topics', { meeting_id: meetingId }),
  findSimilar: (text, topK = 5) => api.post('/api/ai/similar', { text, top_k: topK }),
  transcribeLive: (transcript) => api.post('/api/ai/transcribe', { transcript }),
  analyzeSpeech: (text) => api.post('/api/ai/analyze-speech', { text }, { timeout: 30000 })
};

// ============================================
// Upload API
// ============================================

export const uploadAPI = {
  uploadFile: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/upload', formData, {
      timeout: 120000,
      onUploadProgress: (progressEvent) => {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        if (onProgress) onProgress(percentCompleted);
      }
    });
  },
  uploadFiles: (files, onProgress) => {
    const formData = new FormData();
    files.forEach((file, index) => formData.append(`files[${index}]`, file));
    return api.post('/api/upload/multiple', formData, {
      timeout: 300000,
      onUploadProgress: (progressEvent) => {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        if (onProgress) onProgress(percentCompleted);
      }
    });
  },
  getUploadStatus: (uploadId) => api.get(`/api/upload/status/${uploadId}`),
  cancelUpload: (uploadId) => api.post(`/api/upload/cancel/${uploadId}`)
};
