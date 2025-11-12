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
  const [excludedRows, setExcludedRows] = useState(new Set());
  const [excludedColumns, setExcludedColumns] = useState(new Set());

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

      // Convert Sets to Arrays for API
      const exclusions = {
        excluded_steps: Array.from(excludedRows),
        excluded_columns: Array.from(excludedColumns)
      };

      const result = await api.applySalaryData(district.id, jobId, exclusions);

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
      // Structure data similar to SalaryTable
      const records = jobStatus.preview_records || [];

      // Group by year and period
      const scheduleGroups = {};
      records.forEach(record => {
        const key = `${record.school_year}#${record.period}`;
        if (!scheduleGroups[key]) {
          scheduleGroups[key] = {
            school_year: record.school_year,
            period: record.period,
            salariesByStep: {},
            eduCreditsSet: new Set()
          };
        }

        const step = record.step;
        const eduCredKey = record.credits > 0 ? `${record.education}+${record.credits}` : record.education;

        if (!scheduleGroups[key].salariesByStep[step]) {
          scheduleGroups[key].salariesByStep[step] = {};
        }
        scheduleGroups[key].salariesByStep[step][eduCredKey] = record.salary;
        scheduleGroups[key].eduCreditsSet.add(JSON.stringify({
          education: record.education,
          credits: record.credits,
          key: eduCredKey
        }));
      });

      const schedules = Object.values(scheduleGroups);

      const toggleRow = (step) => {
        const newExcluded = new Set(excludedRows);
        if (newExcluded.has(step)) {
          newExcluded.delete(step);
        } else {
          newExcluded.add(step);
        }
        setExcludedRows(newExcluded);
      };

      const toggleColumn = (colKey) => {
        const newExcluded = new Set(excludedColumns);
        if (newExcluded.has(colKey)) {
          newExcluded.delete(colKey);
        } else {
          newExcluded.add(colKey);
        }
        setExcludedColumns(newExcluded);
      };

      return (
        <div className="preview-step">
          <h3>Preview & Edit Extracted Data</h3>
          <p className="district-name">{district.name}</p>

          <div className="extraction-summary">
            <p>
              <strong>Records extracted:</strong> {jobStatus.extracted_records_count}
            </p>
            <p>
              <strong>School years found:</strong> {jobStatus.years_found?.join(', ') || 'N/A'}
            </p>
            <p className="preview-hint">
              Click on row or column headers with × to remove them from import
            </p>
          </div>

          {schedules.map((schedule, scheduleIdx) => {
            // Sort education columns
            const eduOrder = { 'B': 1, 'M': 2, 'D': 3 };
            const sortedColumns = Array.from(schedule.eduCreditsSet)
              .map(str => JSON.parse(str))
              .sort((a, b) => {
                const eduA = eduOrder[a.education] || 99;
                const eduB = eduOrder[b.education] || 99;
                if (eduA !== eduB) return eduA - eduB;
                return a.credits - b.credits;
              })
              .filter(col => !excludedColumns.has(col.key));

            const sortedSteps = Object.keys(schedule.salariesByStep)
              .sort((a, b) => Number(a) - Number(b))
              .filter(step => !excludedRows.has(Number(step)));

            return (
              <div key={scheduleIdx} className="preview-table-container">
                <h4>{schedule.school_year} - {schedule.period}</h4>
                <div className="salary-table-wrapper">
                  <table className="preview-table salary-table">
                    <thead>
                      <tr>
                        <th>Step</th>
                        {sortedColumns.map(col => (
                          <th key={col.key}>
                            <div className="th-content">
                              <span>{col.key}</span>
                              <button
                                className="remove-btn"
                                onClick={() => toggleColumn(col.key)}
                                title={`Remove ${col.key} column`}
                                type="button"
                              >
                                ×
                              </button>
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedSteps.map(step => (
                        <tr key={step}>
                          <td className="step-cell">
                            <div className="td-content">
                              <span>{step}</span>
                              <button
                                className="remove-btn"
                                onClick={() => toggleRow(Number(step))}
                                title={`Remove step ${step}`}
                                type="button"
                              >
                                ×
                              </button>
                            </div>
                          </td>
                          {sortedColumns.map(col => {
                            const salary = schedule.salariesByStep[step]?.[col.key];
                            return (
                              <td key={col.key} className="salary-cell">
                                {salary ? `$${salary.toLocaleString()}` : '-'}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}

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
