import React, { useState, useEffect, useCallback, useRef } from 'react';
import api, { authAPI } from '../api/api';
import { X, Loader2, Image as ImageIcon, Upload, AlertCircle, RotateCcw, Info } from 'lucide-react';
import Cropper from 'react-easy-crop';
import { notifyError, notifyInfo, notifySuccess } from '../utils/notify';

const ProfileUploadModal = ({ isOpen, onClose, onUpload }) => {
  // States
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);
  const [croppedImageBlob, setCroppedImageBlob] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [step, setStep] = useState('select'); // 'select' | 'crop' | 'confirm'
  const [validationError, setValidationError] = useState(null);
  const fileInputRef = useRef(null);
  const cropRef = useRef(null);
  const canvasRef = useRef(null);


  // Reset modal state
  const resetModal = useCallback(() => {
    setFile(null);
    setPreview(null);
    setCroppedAreaPixels(null);
    setCroppedImageBlob(null);
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setDragActive(false);
    setValidationError(null);
    setStep('select');
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // Cleanup on modal close
  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = 'auto';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      resetModal();
    }
  }, [isOpen, resetModal]);
  // Robust file validation
  const validateFile = useCallback((selectedFile) => {
    setValidationError(null);

    if (!selectedFile) return false;

    // Type validation - support common image formats
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!validTypes.includes(selectedFile.type)) {
      const msg = `File type not supported. Please use JPG, PNG, or WebP.`;
      setValidationError(msg);
      notifyError(msg);
      return false;
    }

    // Size limits
    const maxSizeMB = 5;
    const maxSizeBytes = maxSizeMB * 1024 * 1024;
    if (selectedFile.size > maxSizeBytes) {
      const sizeMB = (selectedFile.size / (1024 * 1024)).toFixed(2);
      const msg = `File too large: ${sizeMB}MB. Max: ${maxSizeMB}MB.`;
      setValidationError(msg);
      notifyError(msg);
      return false;
    }

    // Minimum size check (prevent uploading very tiny files)
    const minSizeKB = 50;
    const minSizeBytes = minSizeKB * 1024;
    if (selectedFile.size < minSizeBytes) {
      const msg = `File too small: ${(selectedFile.size / 1024).toFixed(0)}KB. Min: ${minSizeKB}KB.`;
      setValidationError(msg);
      notifyError(msg);
      return false;
    }

    // Store file metadata
    return true;
  }, []);

  // Generate cropped circular image
  const generateCroppedImage = useCallback(async (imageSrc, pixelCrop) => {
    const canvas = canvasRef.current;
    if (!canvas || !pixelCrop || !imageSrc) return;

    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onerror = () => {
      setValidationError('Failed to load image. File may be corrupted or unsupported.');
    };

    img.onload = async () => {
      try {
        canvas.width = pixelCrop.width;
        canvas.height = pixelCrop.height;

        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';

        // Draw cropped section
        ctx.drawImage(
          img,
          pixelCrop.x,
          pixelCrop.y,
          pixelCrop.width,
          pixelCrop.height,
          0,
          0,
          canvas.width,
          canvas.height
        );

        // Apply circular mask
        ctx.save();
        ctx.beginPath();
        ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2, 0, Math.PI * 2);
        ctx.clip();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(
          img,
          pixelCrop.x,
          pixelCrop.y,
          pixelCrop.width,
          pixelCrop.height,
          0,
          0,
          canvas.width,
          canvas.height
        );
        ctx.restore();

        canvas.toBlob((blob) => {
          if (blob) {
            setCroppedImageBlob(blob);
          }
        }, 'image/jpeg', 0.92);
      } catch (err) {
        setValidationError('Error processing image: ' + err.message);
      }
    };

    img.src = imageSrc;
  }, []);

  useEffect(() => {
    if (croppedAreaPixels && preview) {
      generateCroppedImage(preview, croppedAreaPixels);
    }
  }, [croppedAreaPixels, preview, generateCroppedImage]);

  // Drag and drop handlers
  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const selectedFile = e.dataTransfer.files[0];
      if (validateFile(selectedFile)) {
        setFile(selectedFile);
        setPreview(URL.createObjectURL(selectedFile));
        setValidationError(null);
        setCrop({ x: 0, y: 0 });
        setZoom(1);
        setStep('crop');
      }
    }
  }, [validateFile]);

  // File input change handler
  const handleFileChange = useCallback((e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile && validateFile(selectedFile)) {
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
      setValidationError(null);
      setStep('crop');
    }
  }, [validateFile]);

  // Compress image with error handling
  const compressImage = useCallback((inputFile) => {
    return new Promise((resolve, reject) => {
      try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const img = new Image();

        // Timeout protection
        const loadTimeout = setTimeout(() => {
          reject(new Error('Image load timeout - file may be corrupted'));
        }, 8000);

        img.onerror = () => {
          clearTimeout(loadTimeout);
          reject(new Error('Failed to load image'));
        };

        img.onload = () => {
          clearTimeout(loadTimeout);
          try {
            const targetSize = 480;
            const size = Math.min(img.width, img.height, targetSize);
            canvas.width = size;
            canvas.height = size;

            // Center crop
            ctx.drawImage(
              img,
              (img.width - size) / 2,
              (img.height - size) / 2,
              size,
              size,
              0,
              0,
              size,
              size
            );

            canvas.toBlob(
              (blob) => {
                if (!blob) {
                  reject(new Error('Compression failed - no output generated'));
                  return;
                }
                const compressedFile = new File([blob], 'profile.jpg', {
                  type: 'image/jpeg',
                  lastModified: Date.now(),
                });
                resolve(compressedFile);
              },
              'image/jpeg',
              0.88
            );
          } catch (err) {
            reject(new Error('Compression error: ' + err.message));
          }
        };

        img.src = URL.createObjectURL(inputFile);
      } catch (err) {
        reject(new Error('Unexpected compression error: ' + err.message));
      }
    });
  }, []);

  // Main upload handler
  const handleUpload = useCallback(async () => {
    if (!file) {
      setValidationError('No file selected');
      return;
    }

    if (!croppedImageBlob) {
      setValidationError('Please crop the image before uploading');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setValidationError(null);

    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => Math.min(prev + 10, 90));
    }, 150);

    try {
      // Compress image
      let compressedFile;
      try {
        compressedFile = await compressImage(croppedImageBlob);
      } catch (compressErr) {
        throw new Error('Image compression failed: ' + compressErr.message);
      }

      const originalSize = croppedImageBlob.size;
      const compressedSize = compressedFile.size;
      const ratio = ((1 - compressedSize / originalSize) * 100).toFixed(0);

      notifyInfo(
        `Compressed: ${(originalSize / 1024).toFixed(0)}KB → ${(compressedSize / 1024).toFixed(0)}KB (${ratio}% smaller)`
      );

      // Upload
      await authAPI.uploadProfileImage(compressedFile);
      setUploadProgress(100);

      clearInterval(progressInterval);
      notifySuccess('✓ Profile image updated successfully!');

      if (onUpload) onUpload();

      setTimeout(() => {
        onClose();
      }, 500);
    } catch (err) {
      clearInterval(progressInterval);

      // Network error
      if (!err.response) {
        const backendUrl =
          api?.defaults?.baseURL ||
          process.env.REACT_APP_API_URL ||
          `http://${window.location.hostname}:5001`;
        const msg = `Backend not responding at ${backendUrl}`;
        setValidationError(msg);
        notifyError(msg);
        console.error('Upload network error:', err.message);
        return;
      }

      // HTTP error
      const status = err.response?.status || 'Unknown';
      let errorData = err.response?.data;

      if (typeof errorData === 'string') {
        try {
          errorData = JSON.parse(errorData);
        } catch {
          errorData = { error: errorData };
        }
      }

      const errorMsg = errorData?.error || errorData?.message || 'Upload failed';
      const fullMessage = `Error ${status}: ${errorMsg}`;

      setValidationError(fullMessage);
      notifyError(fullMessage);

      console.error('Profile upload error:', { status, errorMsg, file: file?.name });
    } finally {
      setTimeout(() => {
        setUploading(false);
        setUploadProgress(0);
      }, 500);
    }
  }, [file, croppedImageBlob, compressImage, onUpload, onClose]);

  // Clear/reset handler
  const handleBack = useCallback(() => {
    setStep('select');
    setValidationError(null);
  }, []);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-container profile-modal-container profile-upload-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="modal-header profile-modal-header profile-upload-header"
        >
          <h3 className="modal-title">Update Profile Image</h3>
          <button
            className="profile-modal-close profile-upload-close"
            onClick={onClose}
            aria-label="Close"
            disabled={uploading}
            style={{ opacity: uploading ? 0.5 : 1 }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Progress bar */}
        {uploading && (
          <div className="profile-upload-progress-wrap">
            <div className="profile-upload-progress-track">
              <div
                className="profile-upload-progress-fill"
                style={{
                  width: `${uploadProgress}%`,
                }}
              />
            </div>
          </div>
        )}

        {/* Content */}
        <div className="profile-upload-body">
          {/* Step: Select */}
          {step === 'select' && (
            <>
              <label
                className={`upload-box ${dragActive ? 'drag-active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/jpg,image/png,image/webp"
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                />
                <div className="profile-upload-select-content">
                  <ImageIcon size={48} className="profile-upload-select-icon" />
                  <p className="profile-upload-drop-title">
                    {dragActive ? '↓ Drop your image here' : 'Click to browse or drag & drop'}
                  </p>
                  <small className="profile-upload-drop-subtitle">JPG • PNG • WebP — Max 5MB</small>
                </div>
              </label>

              {/* Info box */}
              <div className="profile-upload-info">
                <Info size={16} className="profile-upload-info-icon" />
                <span>Your profile image will be displayed as a circle. Please select a square image for best results.</span>
              </div>
            </>
          )}

          {/* Step: Crop */}
          {step === 'crop' && preview && (
            <>
              <div className="profile-upload-crop-wrap">
                <p className="profile-upload-crop-help">
                  Adjust your image: Drag to move • Scroll to zoom
                </p>
                <div className="profile-upload-crop-stage">
                  <Cropper
                    ref={cropRef}
                    image={preview}
                    crop={crop}
                    zoom={zoom}
                    aspect={1}
                    cropShape="round"
                    showGrid={true}
                    onCropChange={setCrop}
                    onZoomChange={setZoom}
                    onCropComplete={(_, croppedAreaPixels) => {
                      setCroppedAreaPixels(croppedAreaPixels);
                    }}
                  />
                </div>
              </div>

              {/* Zoom control */}
              <div className="profile-upload-zoom-wrap">
                <label className="profile-upload-zoom-label">
                  Zoom: {(zoom * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="1"
                  max="3"
                  step="0.1"
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                  className="profile-upload-zoom-input"
                />
              </div>

              {/* Preview */}
              {croppedImageBlob && (
                <div className="profile-upload-preview-wrap">
                  <p className="profile-upload-preview-title">Preview</p>
                  <div className="profile-upload-preview-avatar">
                    <img
                      src={URL.createObjectURL(croppedImageBlob)}
                      alt="Cropped preview"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  </div>
                </div>
              )}

              <canvas ref={canvasRef} style={{ display: 'none' }} />
            </>
          )}

          {/* Error message */}
          {validationError && (
            <div className="profile-upload-error">
              <AlertCircle size={16} />
              <span>{validationError}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="profile-upload-actions">
          {step === 'select' && (
            <button
              onClick={onClose}
              disabled={uploading}
              className="profile-upload-btn profile-upload-btn-secondary"
            >
              Cancel
            </button>
          )}

          {step === 'crop' && (
            <>
              <button
                onClick={handleBack}
                disabled={uploading}
                className="profile-upload-btn profile-upload-btn-secondary"
              >
                <RotateCcw size={16} />
                Back
              </button>
              <button
                onClick={handleUpload}
                disabled={!croppedImageBlob || uploading}
                className="profile-upload-btn profile-upload-btn-primary"
              >
                {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                {uploading ? `Uploading... ${uploadProgress}%` : 'Upload'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProfileUploadModal;
