import './LoadingOverlay.css';

function LoadingOverlay({ isOpen, message = 'Processing...' }) {
  if (!isOpen) return null;

  // Split message by newlines for multi-line display
  const lines = message.split('\n');

  return (
    <div className="loading-overlay">
      <div className="loading-overlay-content">
        <div className="loading-spinner"></div>
        <div className="loading-message">
          {lines.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      </div>
    </div>
  );
}

export default LoadingOverlay;
