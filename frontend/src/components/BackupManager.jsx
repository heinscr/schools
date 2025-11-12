import { useState, useEffect } from 'react';
import api from '../services/api';
import './BackupManager.css';

function BackupManager({ onClose, onSuccess }) {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBackups, setSelectedBackups] = useState(new Set());
  const [reapplying, setReapplying] = useState(false);
  const [results, setResults] = useState(null);

  // Load backups on mount
  useEffect(() => {
    loadBackups();
  }, []);

  const loadBackups = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.listBackups();
      setBackups(response.backups || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleBackup = (filename) => {
    const newSelected = new Set(selectedBackups);
    if (newSelected.has(filename)) {
      newSelected.delete(filename);
    } else {
      newSelected.add(filename);
    }
    setSelectedBackups(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedBackups.size === backups.length) {
      setSelectedBackups(new Set());
    } else {
      setSelectedBackups(new Set(backups.map(b => b.filename)));
    }
  };

  const handleReapply = async () => {
    if (selectedBackups.size === 0) {
      setError('Please select at least one backup to re-apply');
      return;
    }

    const confirmed = window.confirm(
      `Are you sure you want to re-apply ${selectedBackups.size} backup(s)? This will replace existing salary data for these districts.`
    );

    if (!confirmed) return;

    try {
      setReapplying(true);
      setError(null);
      setResults(null);

      const filenames = Array.from(selectedBackups);
      const response = await api.reapplyBackups(filenames);

      setResults(response);
      setSelectedBackups(new Set());

      if (response.success && onSuccess) {
        onSuccess(response);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setReapplying(false);
    }
  };

  const formatDate = (isoDate) => {
    const date = new Date(isoDate);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-container backup-manager">
        <div className="modal-header">
          <h2>Backup Manager</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="modal-body">
          {error && (
            <div className="error-message">
              <strong>Error:</strong> {error}
            </div>
          )}

          {results && (
            <div className="results-message">
              <h3>Re-apply Results</h3>
              <p>Successfully processed: {results.total_processed}</p>
              {results.total_errors > 0 && <p className="error">Errors: {results.total_errors}</p>}

              {results.results && results.results.length > 0 && (
                <div className="results-list">
                  <h4>Successful:</h4>
                  <ul>
                    {results.results.map((r, idx) => (
                      <li key={idx}>
                        {r.district_name}: {r.records_added} records + {r.calculated_entries} calculated
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {results.errors && results.errors.length > 0 && (
                <div className="errors-list">
                  <h4>Failed:</h4>
                  <ul>
                    {results.errors.map((e, idx) => (
                      <li key={idx} className="error">
                        {e.filename}: {e.error}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {loading ? (
            <div className="loading-state">Loading backups...</div>
          ) : backups.length === 0 ? (
            <div className="empty-state">
              <p>No backup files found.</p>
              <p className="hint">Backups are created automatically when salary data is applied to a district.</p>
            </div>
          ) : (
            <div className="backups-container">
              <div className="backups-header">
                <p>{backups.length} backup file{backups.length !== 1 ? 's' : ''} available</p>
                <button
                  className="btn-secondary"
                  onClick={handleSelectAll}
                  disabled={reapplying}
                >
                  {selectedBackups.size === backups.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              <div className="backups-list">
                {backups.map((backup) => (
                  <div
                    key={backup.filename}
                    className={`backup-item ${selectedBackups.has(backup.filename) ? 'selected' : ''}`}
                    onClick={() => handleToggleBackup(backup.filename)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedBackups.has(backup.filename)}
                      onChange={() => handleToggleBackup(backup.filename)}
                      disabled={reapplying}
                    />
                    <div className="backup-info">
                      <div className="backup-name">{backup.district_name}</div>
                      <div className="backup-meta">
                        Last modified: {formatDate(backup.last_modified)} • Size: {formatSize(backup.size)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose} disabled={reapplying}>
            Close
          </button>
          <button
            className="btn-primary"
            onClick={handleReapply}
            disabled={selectedBackups.size === 0 || reapplying || loading}
          >
            {reapplying ? 'Re-applying...' : `Re-apply Selected (${selectedBackups.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default BackupManager;
