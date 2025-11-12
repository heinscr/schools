import { useEffect } from 'react';
import './Toast.css';

function Toast({
  isOpen,
  message,
  variant = 'success', // 'success', 'error', 'info', 'warning'
  duration = 4000,
  onClose
}) {
  useEffect(() => {
    if (isOpen && duration > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, duration);

      return () => clearTimeout(timer);
    }
  }, [isOpen, duration, onClose]);

  if (!isOpen) return null;

  return (
    <div className={`toast toast-${variant}`}>
      <div className="toast-content">
        <span className="toast-icon">
          {variant === 'success' && '✓'}
          {variant === 'error' && '✕'}
          {variant === 'warning' && '⚠'}
          {variant === 'info' && 'ℹ'}
        </span>
        <p>{message}</p>
      </div>
      <button className="toast-close" onClick={onClose} aria-label="Close">
        &times;
      </button>
    </div>
  );
}

export default Toast;
