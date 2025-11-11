import { useState, useEffect, Suspense, lazy } from 'react';
import api from '../services/api';
import './SalaryUploadModal.css';

const SalaryTable = lazy(() => import('./SalaryTable'));

function SalaryUploadModal({ district, onClose, onSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState(null);
  const [polling, setPolling] = useState(false);
  const [applying, setApplying] = useState(false);

  // Poll for job status when job is processing
  useEffect(() => {
    if (!jobId || !polling) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await api.getSalaryJob(district.id, jobId);
        setJobStatus(status);

        // Stop polling if job is completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          setPolling(false);
        }
      } catch (err) {
        console.error('Error polling job status:', err);
        setError(err.message);
        setPolling(false);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [jobId, polling, district.id]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setError(null);
    } else {
      setSelectedFile(null);
      setError('Please select a PDF file');
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    try {
      setUploading(true);
      setError(null);

      const result = await api.uploadSalarySchedule(district.id, selectedFile);
      setJobId(result.job_id);
      setJobStatus({ status: result.status });
      setPolling(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleAccept = async () => {
    try {
      setApplying(true);
      setError(null);

      const result = await api.applySalaryData(district.id, jobId);

      // Show success and close modal
      if (onSuccess) {
        onSuccess(result);
      }
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const handleReject = async () => {
    try {
      setError(null);
      await api.deleteSalaryJob(district.id, jobId);
      onClose();
    } catch (err) {
      setError(err.message);
    }
  };

  const renderContent = () => {
    // Step 1: File selection
    if (!jobId) {
      return (
        <div className="upload-step">
          <h3>Upload Salary Schedule PDF</h3>
          <p className="district-name">{district.name}</p>

          <div className="file-input-wrapper">
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              id="pdf-file-input"
              className="file-input"
            />
            <label htmlFor="pdf-file-input" className="file-input-label">
              {selectedFile ? selectedFile.name : 'Choose PDF file...'}
            </label>
          </div>

          {error && <div className="error-message">{error}</div>}

          <div className="modal-actions">
            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
              className="btn btn-primary"
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
            <button onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
          </div>
        </div>
      );
    }

    // Step 2: Processing
    if (jobStatus?.status === 'pending' || jobStatus?.status === 'processing') {
      return (
        <div className="processing-step">
          <h3>Processing PDF...</h3>
          <p className="district-name">{district.name}</p>

          <div className="spinner-container">
            <div className="spinner"></div>
            <p>Extracting salary data from PDF...</p>
            <p className="status-text">Status: {jobStatus.status}</p>
          </div>

          <div className="modal-actions">
            <button onClick={onClose} className="btn btn-secondary">
              Close
            </button>
          </div>
        </div>
      );
    }

    // Step 3: Failed
    if (jobStatus?.status === 'failed') {
      return (
        <div className="failed-step">
          <h3>Processing Failed</h3>
          <p className="district-name">{district.name}</p>

          <div className="error-message">
            <strong>Error:</strong> {jobStatus.error_message || 'Unknown error occurred'}
          </div>

          <div className="modal-actions">
            <button onClick={onClose} className="btn btn-primary">
              Close
            </button>
          </div>
        </div>
      );
    }

    // Step 4: Completed - Show preview
    if (jobStatus?.status === 'completed') {
      return (
        <div className="preview-step">
          <h3>Preview Extracted Data</h3>
          <p className="district-name">{district.name}</p>

          <div className="extraction-summary">
            <p>
              <strong>Records extracted:</strong> {jobStatus.extracted_records_count}
            </p>
            <p>
              <strong>School years found:</strong> {jobStatus.years_found?.join(', ') || 'N/A'}
            </p>
            <p>
              <strong>Processed:</strong> {new Date(jobStatus.completed_at).toLocaleString()}
            </p>
          </div>

          {jobStatus.preview_records && jobStatus.preview_records.length > 0 && (
            <div className="preview-table-container">
              <h4>Preview (first 10 records)</h4>
              <Suspense fallback={<div className="loading">Loading preview...</div>}>
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Period</th>
                      <th>Education</th>
                      <th>Credits</th>
                      <th>Step</th>
                      <th>Salary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobStatus.preview_records.map((record, idx) => (
                      <tr key={idx}>
                        <td>{record.school_year}</td>
                        <td>{record.period}</td>
                        <td>{record.education_level}</td>
                        <td>{record.additional_credits}</td>
                        <td>{record.step}</td>
                        <td>${record.salary.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Suspense>
            </div>
          )}

          {jobStatus.metadata_will_change && (
            <div className="warning-message">
              <strong>⚠️ Warning:</strong> Applying this data will change global metadata.
              You'll need to normalize all districts afterward.
            </div>
          )}

          {error && <div className="error-message">{error}</div>}

          <div className="modal-actions">
            <button
              onClick={handleAccept}
              disabled={applying}
              className="btn btn-primary"
            >
              {applying ? 'Applying...' : 'Accept & Apply'}
            </button>
            <button
              onClick={handleReject}
              disabled={applying}
              className="btn btn-secondary"
            >
              Reject
            </button>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content salary-upload-modal" onClick={(e) => e.stopPropagation()}>
        {renderContent()}
      </div>
    </div>
  );
}

export default SalaryUploadModal;
