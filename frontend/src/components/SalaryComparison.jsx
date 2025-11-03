import { useState } from 'react';
import api from '../services/api';
import SalaryComparisonMap from './SalaryComparisonMap';
import './SalaryComparison.css';

function SalaryComparison() {
  const [searchParams, setSearchParams] = useState({
    step: '5',
    education: 'M',
    credits: '30'
  });
  const [results, setResults] = useState(null);
  const [enrichedResults, setEnrichedResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await api.compareSalaries(
        searchParams.education,
        parseInt(searchParams.credits),
        parseInt(searchParams.step)
      );
      setResults(data);
      
      // Fetch full district details for each result to get towns
      const enriched = await Promise.all(
        data.results.map(async (result) => {
          try {
            const districtDetails = await api.getDistrict(result.district_id);
            return {
              ...result,
              towns: districtDetails.towns || []
            };
          } catch (err) {
            console.error(`Error fetching district ${result.district_id}:`, err);
            return {
              ...result,
              towns: []
            };
          }
        })
      );
      setEnrichedResults(enriched);
    } catch (err) {
      setError(err.message);
      setResults(null);
      setEnrichedResults([]);
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
      <div className="comparison-header">
        <h2>Compare Salaries Across Districts</h2>
        <p className="comparison-description">
          Search for teacher salaries by education level, credits, and experience step
        </p>
      </div>

      <div className="search-form">
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

        <button 
          className="search-button" 
          onClick={handleSearch}
          disabled={loading}
        >
          {loading ? 'Searching...' : 'Search Salaries'}
        </button>
      </div>

      {error && (
        <div className="comparison-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Map Section */}
      <div className="comparison-map-section">
        <SalaryComparisonMap results={enrichedResults} />
      </div>

      {results && (
        <div className="comparison-results">
          <div className="results-header">
            <h3>Results</h3>
            <div className="search-summary">
              Showing salaries for <strong>{results.query.education === 'B' ? "Bachelor's" : results.query.education === 'M' ? "Master's" : "Doctorate"}</strong>
              {results.query.credits > 0 && <span> + {results.query.credits} credits</span>} at <strong>Step {results.query.step}</strong>
              <span className="result-count"> ({results.total} {results.total === 1 ? 'district' : 'districts'})</span>
            </div>
          </div>

          {results.results.length === 0 ? (
            <div className="no-results">
              No salary data found for these criteria.
            </div>
          ) : (
            <div className="results-table-wrapper">
              <table className="results-table">
                <thead>
                  <tr>
                    <th className="rank-col">Rank</th>
                    <th className="district-col">District</th>
                    <th className="type-col">Type</th>
                    <th className="year-col">Year</th>
                    <th className="salary-col">Salary</th>
                  </tr>
                </thead>
                <tbody>
                  {results.results.map((result, index) => (
                    <tr key={result.district_id} className="result-row">
                      <td className="rank-cell">
                        <span className={`rank-badge ${index < 3 ? 'top-rank' : ''}`}>
                          {result.rank}
                        </span>
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
                        ${result.salary ? Number(result.salary).toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2
                        }) : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {results.results.length > 0 && (
            <div className="results-stats">
              <div className="stat-item">
                <span className="stat-label">Highest:</span>
                <span className="stat-value">${Number(results.results[0].salary).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Lowest:</span>
                <span className="stat-value">${Number(results.results[results.results.length - 1].salary).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Difference:</span>
                <span className="stat-value highlight">${(Number(results.results[0].salary) - Number(results.results[results.results.length - 1].salary)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SalaryComparison;
