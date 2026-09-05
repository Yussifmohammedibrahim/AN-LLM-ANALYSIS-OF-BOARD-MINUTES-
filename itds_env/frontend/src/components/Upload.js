import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { uploadAPI, dataAPI } from '../api/api';
import { Upload as UploadIcon, FileText, X, CheckCircle, Loader2, FileArchive, RefreshCw, Image as ImageIcon } from 'lucide-react';
import { notifyError, notifySuccess, notifyWarning } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';

// Image preview component for uploaded image files
const ImagePreview = ({ file }) => {
  const [preview, setPreview] = useState(null);
  
  useEffect(() => {
    const isImage = /\.(jpg|jpeg|png|tiff|tif|webp)$/i.test(file.name);
    if (!isImage) return;
    
    const reader = new FileReader();
    reader.onload = (e) => {
      setPreview(e.target.result);
    };
    reader.readAsDataURL(file);
  }, [file]);

  if (!preview) return null;
  
  return (
    <img 
      src={preview} 
      alt={file.name}
      style={{
        width: '40px',
        height: '40px',
        borderRadius: '4px',
        objectFit: 'cover',
        border: '1px solid #d0dbe8'
      }}
      title={file.name}
    />
  );
};

// File icon component - shows different icons for different file types
const FileIcon = ({ file }) => {
  const isImage = /\.(jpg|jpeg|png|tiff|tif|webp)$/i.test(file.name);
  return isImage ? <ImageIcon size={20} /> : <FileText size={20} />;
};

const Upload = () => {
  const { t } = useLanguage();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({});
  const [uploadPhase, setUploadPhase] = useState({});
  const [dragOver, setDragOver] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  const uploadedDocuments = useMemo(() => {
    const rows = Array.isArray(documents) ? documents : [];
    return rows
      .filter((doc) => doc && Number(doc.meeting_id) > 0)
      .map((doc) => ({
        meeting_id: Number(doc.meeting_id),
        source_filename: String(doc.source_filename || '').trim(),
        meeting_date: doc.meeting_date || null,
        segments_count: Number(doc.segments_count || 0),
        summaries_count: Number(doc.summaries_count || 0),
      }))
      .sort((a, b) => b.meeting_id - a.meeting_id);
  }, [documents]);

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const waitForUploadCompletion = useCallback(async (uploadId, fileName) => {
    while (true) {
      const response = await uploadAPI.getUploadStatus(uploadId);
      const job = response?.data || {};
      const backendProgress = Number(job.progress ?? 0);
      const displayProgress = Math.min(100, 20 + Math.round((Math.max(0, Math.min(100, backendProgress)) * 80) / 100));

      if (job.status === 'failed') {
        setUploadProgress((prev) => ({
          ...prev,
          [fileName]: Math.min(99, Math.max(Number(prev[fileName] ?? 0), displayProgress)),
        }));
        setUploadPhase((prev) => ({
          ...prev,
          [fileName]: job.phase || 'failed',
        }));
        throw new Error(job.error || job.message || t('uploadExtractionFailed'));
      }

      setUploadProgress((prev) => ({
        ...prev,
        [fileName]: Math.max(Number(prev[fileName] ?? 0), displayProgress),
      }));
      setUploadPhase((prev) => ({
        ...prev,
        [fileName]: job.phase || job.status || 'extracting',
      }));

      if (job.status === 'completed') {
        return job;
      }

      await sleep(1000);
    }
  }, [t]);

  const loadUploadedDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    try {
      const response = await dataAPI.getMeetings({ limit: 100 });
      const payload = response?.data || {};
      setDocuments(Array.isArray(payload.meetings) ? payload.meetings : []);
    } catch (error) {
      console.error('Failed to load uploaded documents:', error);
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUploadedDocuments();
  }, [loadUploadedDocuments]);

  const handleFileSelect = useCallback((selectedFiles) => {
    const newFiles = Array.from(selectedFiles).filter(file => {
      // Validate file type
      const validTypes = [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
        'image/jpeg',
        'image/jpg',
        'image/png',
        'image/tiff',
        'image/x-tiff',
        'image/webp'
      ];
      const lowerName = String(file.name || '').toLowerCase();
      const validByExtension = /\.(pdf|docx|txt|jpg|jpeg|png|tif|tiff|webp)$/i.test(lowerName);
      
      if (!validTypes.includes(file.type) && !validByExtension) {
        notifyError(t('uploadInvalidFileType', { file: file.name }));
        return false;
      }
      
      // Validate file size (10MB max)
      if (file.size > 10 * 1024 * 1024) {
        notifyError(t('uploadFileTooLarge', { file: file.name }));
        return false;
      }
      
      return true;
    });

    setFiles(prev => {
      const merged = [...prev, ...newFiles];
      const seen = new Set();
      return merged.filter((file) => {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
    });
  }, [t]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  }, [handleFileSelect]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      notifyWarning(t('uploadSelectAtLeastOne'));
      return;
    }

    setUploading(true);
    const progress = {};

    // Initialize progress for all files
    files.forEach(file => {
      progress[file.name] = 0;
    });
    setUploadProgress({ ...progress });

    try {
      // Use Promise.allSettled for parallel uploads (faster than sequential)
      // Limit concurrency to 3 files at a time for optimal performance
      const uploadPromises = files.map((file, index) => {
        return new Promise((resolve) => {
          // Stagger uploads slightly to avoid overwhelming the server
          setTimeout(async () => {
            try {
              setUploadPhase((prev) => ({ ...prev, [file.name]: 'uploading' }));
              const uploadResponse = await uploadAPI.uploadFile(file, (percent) => {
                progress[file.name] = Math.min(20, Math.round(percent * 0.2));
                setUploadProgress({ ...progress });
                setUploadPhase((prev) => ({ ...prev, [file.name]: 'uploading' }));
              });

              const responseData = uploadResponse?.data || {};
              if (responseData.upload_id) {
                progress[file.name] = Math.max(progress[file.name] || 0, 20);
                setUploadProgress({ ...progress });
                setUploadPhase((prev) => ({ ...prev, [file.name]: 'extracting' }));

                const completedJob = await waitForUploadCompletion(responseData.upload_id, file.name);
                progress[file.name] = 100;
                setUploadProgress({ ...progress });
                setUploadPhase((prev) => ({ ...prev, [file.name]: 'completed' }));
                resolve({ success: true, file: file.name, meeting_id: completedJob.meeting_id });
                return;
              }

              progress[file.name] = 100;
              setUploadProgress({ ...progress });
              setUploadPhase((prev) => ({ ...prev, [file.name]: 'completed' }));
              resolve({ success: true, file: file.name, meeting_id: responseData.meeting_id });
            } catch (error) {
              console.error(`Upload failed for ${file.name}:`, error);
              setUploadPhase((prev) => ({ ...prev, [file.name]: 'failed' }));
              resolve({ success: false, file: file.name, error });
            }
          }, index * 200);  // 200ms stagger between uploads
        });
      });

      const results = await Promise.all(uploadPromises);
      const successCount = results.filter(r => r.success).length;
      const failCount = results.filter(r => !r.success).length;

      if (failCount > 0) {
        notifyWarning(t('uploadCompletedWithFailures', { success: successCount, failed: failCount }));
      } else {
        notifySuccess(t('uploadCompletedSuccess', { success: successCount }));
      }

      setFiles([]);
      setUploadProgress({});
      setUploadPhase({});
      await loadUploadedDocuments();
    } catch (error) {
      console.error('Upload error:', error);
      notifyError(t('uploadFailedGeneric'));
    } finally {
      setUploading(false);
    }
  };

  const handleClearAll = () => {
    if (uploading) return;
    setFiles([]);
    setUploadProgress({});
    setUploadPhase({});
  };

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1 className="page-title">{t('uploadTitle')}</h1>
        <p className="page-subtitle">{t('uploadSubtitle')}</p>
      </div>

      {/* Upload Zone */}
      <div className="upload-container">
        <div
          className={`upload-zone ${dragOver ? 'dragover' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => document.getElementById('file-input').click()}
          style={{ cursor: 'pointer' }}
        >
          <input
            id="file-input"
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.tif,.tiff,.webp"
            onChange={(e) => handleFileSelect(e.target.files)}
            style={{ display: 'none' }}
            disabled={uploading}
          />
          <div className="upload-icon">
            <UploadIcon size={48} />
          </div>
          <h3 className="upload-title">{t('uploadDropOrClick')}</h3>
          <p className="upload-subtitle">
            {t('uploadDocsForAI')}
          </p>
          <p className="upload-formats">
            Supported formats: PDF, Word (DOCX), Text (TXT), Images (JPG, JPEG, PNG, TIFF, WEBP)
            <br />
            {t('uploadMaxSize')}
          </p>
        </div>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{t('uploadFilesToUpload', { count: files.length })}</h3>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleClearAll}
              disabled={uploading}
            >
              {t('uploadClearAll')}
            </button>
          </div>
          <div className="card-body">
            <div className="upload-file-list">
              {files.map((file, index) => (
                <div key={index} className="upload-file-item">
                  <div className="upload-file-icon">
                    <ImagePreview file={file} />
                    {!(/\.(jpg|jpeg|png|tiff|tif|webp)$/i.test(file.name)) && <FileIcon file={file} />}
                  </div>
                  <div className="upload-file-info" style={{ flex: 1 }}>
                    <div className="upload-file-name">{file.name}</div>
                    <div className="upload-file-size">{formatFileSize(file.size)}</div>
                    {uploadProgress[file.name] !== undefined && (
                      <div className="upload-progress">
                        <div
                          className="upload-progress-bar"
                          style={{ width: `${uploadProgress[file.name]}%` }}
                        />
                      </div>
                    )}
                    <div className="text-xs text-secondary" style={{ marginTop: '0.35rem' }}>
                      {uploadPhase[file.name] === 'queued' && t('uploadPhaseQueued')}
                      {uploadPhase[file.name] === 'uploading' && t('uploadPhaseUploading')}
                      {uploadPhase[file.name] === 'extracting' && t('uploadPhaseExtracting')}
                      {uploadPhase[file.name] === 'saving' && t('uploadPhaseSaving')}
                      {uploadPhase[file.name] === 'completed' && t('uploadPhaseCompleted')}
                      {uploadPhase[file.name] === 'failed' && t('uploadPhaseFailed')}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {uploadProgress[file.name] === 100 ? (
                      <CheckCircle size={20} style={{ color: 'var(--success)' }} />
                    ) : uploadProgress[file.name] !== undefined ? (
                      <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                        {uploadProgress[file.name]}%
                      </span>
                    ) : null}
                    {!uploading && (
                      <button
                        className="btn btn-ghost btn-sm btn-icon"
                        onClick={() => removeFile(index)}
                      >
                        <X size={16} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

<div className="button-group" style={{ justifyContent: 'flex-end', marginTop: '1.5rem' }}>
              <button
                className="btn btn-ghost"
                onClick={handleClearAll}
                disabled={uploading}
              >
                {t('cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleUpload}
                disabled={uploading}
              >
                {uploading ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    {t('uploadUploading')}
                  </>
                ) : (
                  <>
                    <UploadIcon size={18} />
                    {t('uploadButtonCount', { count: files.length })}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Uploaded Documents */}
      <div className="card mt-4 upload-documents-card">
        <div className="card-header upload-documents-header">
          <div>
            <h3 className="card-title">{t('uploadUploadedDocs')}</h3>
            <p className="upload-documents-subtitle">{t('uploadUploadedDocsSubtitle')}</p>
          </div>
          <div className="upload-documents-toolbar">
            <span className="upload-documents-count">{t('uploadTotalDocs', { count: uploadedDocuments.length })}</span>
            <button className="btn btn-ghost btn-sm" onClick={loadUploadedDocuments} disabled={documentsLoading}>
              <RefreshCw size={16} className={documentsLoading ? 'animate-spin' : ''} />
              {t('uploadRefresh')}
            </button>
          </div>
        </div>
        <div className="card-body">
          {documentsLoading ? (
            <div className="loading" style={{ minHeight: '140px' }}><div className="spinner"></div></div>
          ) : uploadedDocuments.length === 0 ? (
            <div className="empty-state" style={{ padding: '1.5rem 0' }}>
              <FileArchive size={40} className="empty-icon" />
              <h3 className="empty-title">{t('uploadNoDocsYet')}</h3>
              <p>{t('uploadNoDocsHint')}</p>
            </div>
          ) : (
            <div className="table-container upload-documents-table-container">
              <table className="table upload-documents-table">
                <thead>
                  <tr>
                    <th>{t('uploadColDocument')}</th>
                    <th>{t('uploadColMeetingDate')}</th>
                    <th>{t('uploadColSegments')}</th>
                    <th>{t('uploadColSummaries')}</th>
                    <th>{t('uploadColStatus')}</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadedDocuments.map((doc) => {
                    const documentLabel = doc.source_filename || t('uploadDocumentNumber', { id: doc.meeting_id });
                    const isImage = /\.(jpg|jpeg|png|tiff|tif|webp)$/i.test(documentLabel);
                    const status = doc.summaries_count > 0
                      ? 'analyzed'
                      : doc.segments_count > 0
                        ? 'ready'
                        : 'uploaded';

                    const statusClass = status === 'analyzed'
                      ? 'status-analyzed'
                      : status === 'ready'
                        ? 'status-ready'
                        : 'status-uploaded';

                    const statusLabel = status === 'analyzed'
                      ? t('uploadStatusAnalyzed')
                      : status === 'ready'
                        ? t('uploadStatusReady')
                        : t('uploadStatusUploaded');

                    return (
                      <tr key={doc.meeting_id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            {isImage ? (
                              <ImageIcon size={16} style={{ color: '#5f78a8', flexShrink: 0 }} />
                            ) : (
                              <FileText size={16} style={{ color: '#5f78a8', flexShrink: 0 }} />
                            )}
                            <div className="font-semibold">{documentLabel}</div>
                          </div>
                          <div className="text-xs text-secondary">{t('uploadDocId', { id: doc.meeting_id })}</div>
                          {doc.metadata?.meetingTitle && (
                            <div className="text-xs text-secondary">Title: {doc.metadata.meetingTitle}</div>
                          )}
                        </td>
                        <td>{doc.meeting_date || t('reportsNA')}</td>
                        <td>{doc.segments_count}</td>
                        <td>{doc.summaries_count}</td>
                        <td><span className={`upload-doc-status ${statusClass}`}>{statusLabel}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Upload Guidelines */}
      <div className="card mt-4">
        <div className="card-header">
          <h3 className="card-title">{t('uploadGuidelines')}</h3>
        </div>
        <div className="card-body">
          <div className="grid grid-3">
            <div>
              <h4 style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{t('uploadSupportedFormatsTitle')}</h4>
              <ul style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', paddingLeft: '1.25rem' }}>
                <li>{t('uploadFormatPDF')}</li>
                <li>Word Document (DOCX)</li>
                <li>{t('uploadFormatText')}</li>
              </ul>
            </div>
            <div>
              <h4 style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{t('uploadSizeLimitTitle')}</h4>
              <ul style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', paddingLeft: '1.25rem' }}>
                <li>{t('uploadSizeMaximum')}</li>
                <li>{t('uploadSizeRecommended')}</li>
              </ul>
            </div>
            <div>
              <h4 style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{t('uploadAfterUploadTitle')}</h4>
              <ul style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', paddingLeft: '1.25rem' }}>
                <li>{t('uploadAfterAnalyze')}</li>
                <li>{t('uploadAfterExtractionTime')}</li>
                <li>{t('uploadAfterResultsInReports')}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default React.memo(Upload);