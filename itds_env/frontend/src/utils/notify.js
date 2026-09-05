import { toast } from 'react-toastify';

const baseOptions = {
  position: 'top-right',
  autoClose: 3600,
  hideProgressBar: false,
  closeOnClick: true,
  pauseOnHover: true,
  draggable: false,
  pauseOnFocusLoss: true
};

export const notifySuccess = (message, options = {}) =>
  toast.success(message, { ...baseOptions, ...options });

export const notifyError = (message, options = {}) =>
  toast.error(message, { ...baseOptions, ...options });

export const notifyInfo = (message, options = {}) =>
  toast.info(message, { ...baseOptions, ...options });

export const notifyWarning = (message, options = {}) =>
  toast.warning(message, { ...baseOptions, ...options });
