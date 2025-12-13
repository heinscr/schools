import { useState, useEffect } from 'react';
import api from '../services/api';
import { logger } from '../utils/logger';
import './MissingContractsModal.css';

function MissingContractsModal({ onClose }) {
  const [selectedYear, setSelectedYear] = useState('2025-2026');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  // Generate year options (current year and next 2 years)
  const currentYear = new Date().getFullYear();
  const yearOptions = [];
  for (let i = 0; i < 3; i++) {
    const startYear = currentYear + i;
    const endYear = startYear + 1;
    yearOptions.push(`${startYear}-${endYear}`);
  }


  // Load data when year changes
  useEffect(() => {
    loadData();
  }, [selectedYear]);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.getDistrictsMissingContracts(selectedYear);
      setData(result);
      logger.log(`Loaded ${result.missing_count} districts missing contracts for ${selectedYear}`);
    } catch (err) {
      logger.error('Failed to load districts missing contracts:', err);
      setError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleYearChange = (e) => {
    setSelectedYear(e.target.value);
  };

  const handleRefresh = () => {
    loadData();
  };

  const handleExportCSV = () => {
    if (!data || !data.districts || data.districts.length === 0) {
      return;
    }

    // Create CSV header
    const headers = ['District Name', 'Type', 'Towns'];
    const csvRows = [headers.join(',')];

    // Add data rows
    data.districts.forEach(district => {
      const row = [
        `"${district.name || ''}"`,
        `"${district.district_type || 'N/A'}"`,
        `"${district.towns && district.towns.length > 0 ? district.towns.join('; ') : 'N/A'}"`
      ];
      csvRows.push(row.join(','));
    });

    // Create CSV content
    const csvContent = csvRows.join('\n');

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.setAttribute('href', url);
    link.setAttribute('download', `missing_contracts_${selectedYear}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    logger.log(`Exported ${data.districts.length} districts to CSV for ${selectedYear}`);
  };

  return (
    <div className="missing-contracts-modal-backdrop" onClick={onClose}>
      <div className="missing-contracts-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="missing-contracts-modal-header">
          <h2>Districts Without Contract Data</h2>
          <button className="missing-contracts-modal-close" onClick={onClose}>×</button>
        </div>

        <div className="missing-contracts-controls">
          <div className="missing-contracts-year-selector">
            <label htmlFor="year-select">School Year:</label>
            <select
              id="year-select"
              value={selectedYear}
              onChange={handleYearChange}
              disabled={loading}
            >
              {yearOptions.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
          <button
            className="missing-contracts-refresh-btn"
            onClick={handleRefresh}
            disabled={loading}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Refresh
          </button>
          <button
            className="missing-contracts-export-btn"
            onClick={handleExportCSV}
            disabled={loading || !data || !data.districts || data.districts.length === 0}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export to CSV
          </button>
        </div>

        <div className="missing-contracts-modal-body">
          {loading && (
            <div className="missing-contracts-loading">
              <div className="spinner"></div>
              <p>Loading...</p>
            </div>
          )}

          {error && (
            <div className="missing-contracts-error">
              <p>{error}</p>
            </div>
          )}

          {!loading && !error && data && (
            <>
              <div className="missing-contracts-summary">
                <p>
                  <strong>{data.missing_count}</strong> out of <strong>{data.total_districts}</strong> Regional/Municipal districts
                  are missing contract data for <strong>{data.year}</strong> ({data.period})
                </p>
              </div>

              {data.missing_count > 0 && (
                <div className="missing-contracts-list">
                  <table>
                    <thead>
                      <tr>
                        <th>District Name</th>
                        <th>Type</th>
                        <th>Towns</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.districts.map(district => (
                        <tr key={district.id}>
                          <td>{district.name}</td>
                          <td className="district-type">{district.district_type || 'N/A'}</td>
                          <td className="district-towns">
                            {district.towns && district.towns.length > 0
                              ? district.towns.join(', ')
                              : 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {data.missing_count === 0 && (
                <div className="missing-contracts-empty">
                  <p>All Regional/Municipal districts have contract data for this year!</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default MissingContractsModal;
