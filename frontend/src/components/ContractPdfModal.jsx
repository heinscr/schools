import { useState, useRef, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './ContractPdfModal.css';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

function ContractPdfModal({ districtName, pdfUrl, onClose }) {
  const [numPages, setNumPages] = useState(null);
  const [containerWidth, setContainerWidth] = useState(null);
  const [scale, setScale] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);

  // Measure container width on mount and window resize
  useEffect(() => {
    const measureWidth = () => {
      if (containerRef.current) {
        // Account for padding (20px on each side = 40px total)
        const width = containerRef.current.offsetWidth - 40;
        setContainerWidth(width);
      }
    };

    measureWidth();
    window.addEventListener('resize', measureWidth);
    return () => window.removeEventListener('resize', measureWidth);
  }, []);

  const onDocumentLoadSuccess = ({ numPages }) => {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  };

  const onDocumentLoadError = (error) => {
    console.error('Error loading PDF:', error);
    setError('Failed to load PDF. Please try again.');
    setLoading(false);
  };

  const zoomIn = () => {
    setScale(prev => Math.min(prev + 0.2, 3.0));
  };

  const zoomOut = () => {
    setScale(prev => Math.max(prev - 0.2, 0.5));
  };

  const handleDownload = () => {
    window.open(pdfUrl, '_blank');
  };

  return (
    <div className="contract-pdf-overlay" onClick={onClose}>
      <div className="contract-pdf-modal" onClick={(e) => e.stopPropagation()}>
        <div className="contract-pdf-header">
          <div className="contract-pdf-title">
            <h2>{districtName} - Contract</h2>
          </div>
          <div className="contract-pdf-actions">
            <button
              className="pdf-action-btn"
              onClick={handleDownload}
              title="Download or open in new tab"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            <button className="pdf-close-btn" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        <div className="contract-pdf-controls">
          <div className="pdf-zoom-controls">
            <button onClick={zoomOut} disabled={scale <= 0.5} title="Zoom out">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="8" y1="11" x2="14" y2="11"></line>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </button>
            <span className="zoom-level">{Math.round(scale * 100)}%</span>
            <button onClick={zoomIn} disabled={scale >= 3.0} title="Zoom in">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="11" y1="8" x2="11" y2="14"></line>
                <line x1="8" y1="11" x2="14" y2="11"></line>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </button>
          </div>

          {numPages && (
            <div className="pdf-page-info">
              <span className="page-count">{numPages} {numPages === 1 ? 'page' : 'pages'}</span>
            </div>
          )}
        </div>

        <div className="contract-pdf-viewer" ref={containerRef}>
          {loading && <div className="pdf-loading">Loading PDF...</div>}
          {error && <div className="pdf-error">{error}</div>}

          {containerWidth && (
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading=""
              error=""
            >
              {Array.from(new Array(numPages), (el, index) => (
                <Page
                  key={`page_${index + 1}`}
                  pageNumber={index + 1}
                  width={containerWidth * scale}
                  renderTextLayer={true}
                  renderAnnotationLayer={true}
                />
              ))}
            </Document>
          )}
        </div>
      </div>
    </div>
  );
}

export default ContractPdfModal;
