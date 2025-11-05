import { useState, useContext } from 'react';
import api from '../services/api';
import { DataCacheContext } from '../contexts/DataCacheContext';
import SalaryComparisonMap from './SalaryComparisonMap';
import { DISTRICT_TYPE_OPTIONS } from '../constants/districtTypes';
import { formatCurrency } from '../utils/formatters';
import './SalaryComparison.css';

function SalaryComparison() {
  const [searchParams, setSearchParams] = useState({
    step: '5',
    education: 'M',
    credits: '30'
  });
  const [selectedTypes, setSelectedTypes] = useState(DISTRICT_TYPE_OPTIONS.map(opt => opt.value));
  const [cachedResults, setCachedResults] = useState(null); // Full results from API (cached)
  const [filteredResults, setFilteredResults] = useState(null); // Filtered by district type
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { getDistrictUrl } = useContext(DataCacheContext);

  const handleTypeChange = (type) => {
    setSelectedTypes(prev => {
      const newTypes = prev.includes(type)
        ? prev.filter(t => t !== type)
        : [...prev, type];

      // Apply client-side filtering
      if (cachedResults) {
        applyFilters(cachedResults, newTypes);
      }

      return newTypes;
    });
  };

  const applyFilters = (data, types) => {
    if (!data || !data.results) {
      setFilteredResults(null);
      return;
    }

    // Filter results by selected district types
    const filtered = data.results.filter(result =>
      types.includes(result.district_type)
    );

    // Re-rank filtered results
    const rankedFiltered = filtered.map((result, index) => ({
      ...result,
      rank: index + 1
    }));

    setFilteredResults({
      ...data,
      results: rankedFiltered,
      total: rankedFiltered.length
    });
  };

  const handleSearch = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all results (no district type filter on backend)
      const data = await api.compareSalaries(
        searchParams.education,
        parseInt(searchParams.credits),
        parseInt(searchParams.step)
      );

      // Cache the full results
      setCachedResults(data);

      // Apply current filters
      applyFilters(data, selectedTypes);
    } catch (err) {
      setError(err.message);
      setCachedResults(null);
      setFilteredResults(null);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field, value) => {
    setSearchParams(prev => ({
      ...prev,
      [field]: value
    }));
  };

  return (
    <div className="salary-comparison">
      <div className="search-form">
        <div className="comparison-header">
          <h2>Compare Salaries Across Districts</h2>
        </div>

        <div className="search-controls-row">
          <div className="form-group">
            <label htmlFor="education">Education Level</label>
            <select
              id="education"
              value={searchParams.education}
              onChange={(e) => handleInputChange('education', e.target.value)}
            >
              <option value="B">Bachelor's</option>
              <option value="M">Master's</option>
              <option value="D">Doctorate</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="credits">Additional Credits</label>
            <select
              id="credits"
              value={searchParams.credits}
              onChange={(e) => handleInputChange('credits', e.target.value)}
            >
              <option value="0">0</option>
              <option value="15">15</option>
              <option value="30">30</option>
              <option value="45">45</option>
              <option value="60">60</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="step">Experience Step</label>
            <select
              id="step"
              value={searchParams.step}
              onChange={(e) => handleInputChange('step', e.target.value)}
            >
              {[...Array(15)].map((_, i) => (
                <option key={i + 1} value={i + 1}>{i + 1}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>&nbsp;</label>
            <button
              className="search-button"
              onClick={handleSearch}
              disabled={loading}
            >
              {loading ? 'Searching...' : 'Search Salaries'}
            </button>
          </div>
        </div>

        <p className="comparison-description">
          Search for teacher salaries by education level, credits, and experience step
        </p>

        {/* District Type Filters - in same container */}
        <div className="district-type-filters-row">
          {DISTRICT_TYPE_OPTIONS.map(opt => {
            const typeCount = cachedResults?.results.filter(r => r.district_type === opt.value).length || 0;
            return (
              <button
                key={opt.value}
                type="button"
                className={`district-type-toggle${selectedTypes.includes(opt.value) ? ' active' : ''}`}
                onClick={() => handleTypeChange(opt.value)}
                aria-pressed={selectedTypes.includes(opt.value)}
                disabled={!cachedResults}
              >
                <span className="district-type-icon">{opt.icon}</span>
                <span className="district-type-label">{opt.label}</span>
                {cachedResults && <span className="district-type-count">{typeCount}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="comparison-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Map Section */}
      <div className="comparison-map-section">
        <SalaryComparisonMap results={filteredResults?.results || []} />
      </div>

      {filteredResults && (
        <div className="comparison-results">
          <div className="results-header">
            <h3>Results</h3>
            <div className="search-summary">
              Showing salaries for <strong>{filteredResults.query.education === 'B' ? "Bachelor's" : filteredResults.query.education === 'M' ? "Master's" : "Doctorate"}</strong>
              {filteredResults.query.credits > 0 && <span> + {filteredResults.query.credits} credits</span>} at <strong>Step {filteredResults.query.step}</strong>
              <span className="result-count"> ({filteredResults.total} {filteredResults.total === 1 ? 'district' : 'districts'})</span>
            </div>
            {filteredResults.results.length > 0 && (
              <div className="results-stats">
                <div className="stat-item">
                  <span className="stat-label">Highest:</span>
                  <span className="stat-value">{formatCurrency(filteredResults.results[0].salary)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Lowest:</span>
                  <span className="stat-value">{formatCurrency(filteredResults.results[filteredResults.results.length - 1].salary)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Difference:</span>
                  <span className="stat-value highlight">{formatCurrency(Number(filteredResults.results[0].salary) - Number(filteredResults.results[filteredResults.results.length - 1].salary))}</span>
                </div>
              </div>
            )}
          </div>

          {filteredResults.results.length === 0 ? (
            <div className="no-results">
              No districts match the selected filters.
            </div>
          ) : (
            <div className="results-table-wrapper">
              <table className="results-table">
                <thead>
                  <tr>
                    <th className="rank-col">Rank</th>
                    <th className="link-col" aria-label="Website"></th>
                    <th className="district-col">District</th>
                    <th className="type-col">Type</th>
                    <th className="year-col">Year</th>
                    <th className="salary-col">Salary</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.results.map((result, index) => (
                      <tr key={result.district_id} className="result-row">
                      <td className="rank-cell">
                        <span className={`rank-badge ${index < 3 ? 'top-rank' : ''}`}>
                          {result.rank}
                        </span>
                      </td>
                      <td className="link-cell">
                        {(() => {
                          const districtUrl = (getDistrictUrl && getDistrictUrl(result.district_id)) || result.district_url;
                          if (!districtUrl) return null;
                          return (
                            <a
                              href={districtUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="external-link"
                              title={`Open ${result.district_name} website`}
                              aria-label={`Open ${result.district_name} website in a new tab`}
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="14"
                                height="14"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                style={{ verticalAlign: 'middle' }}
                              >
                                <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                                <polyline points="15 3 21 3 21 9" />
                                <line x1="10" y1="14" x2="21" y2="3" />
                              </svg>
                            </a>
                          );
                        })()}
                      </td>
                      <td className="district-cell">
                        <strong>{result.district_name}</strong>
                      </td>
                      <td className="type-cell">
                        <span className="district-type-badge">
                          {result.district_type ? result.district_type.replace('_', ' ') : 'N/A'}
                        </span>
                      </td>
                      <td className="year-cell">
                        {result.school_year || 'N/A'}
                      </td>
                      <td className="salary-cell">
                        {formatCurrency(result.salary)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          
        </div>
      )}
    </div>
  );
}

export default SalaryComparison;
