import { useState, useContext, useMemo, useCallback } from 'react';
import api from '../services/api';
import { DataCacheContext } from '../contexts/DataCacheContext';
import SalaryComparisonMap from './SalaryComparisonMap';
import SalaryTable from './SalaryTable';
import CustomSalaryFilter from './CustomSalaryFilter';
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
  const [showCustomFilter, setShowCustomFilter] = useState(false);
  const [selectedDistricts, setSelectedDistricts] = useState(new Set());
  const [selectedTowns, setSelectedTowns] = useState(new Set());
  const _dataCache = useContext(DataCacheContext);
  const getDistrictUrl = _dataCache?.getDistrictUrl;
  const [modalOpen, setModalOpen] = useState(false);
  const [modalDistrictId, setModalDistrictId] = useState(null);
  const [modalDistrictInfo, setModalDistrictInfo] = useState(null);
  const [modalHighlight, setModalHighlight] = useState(null);

  const openDistrictModal = (result) => {
    const districtId = result.district_id;
    // Try to get richer district metadata from the DataCache. The cache may store districts keyed
    // differently (e.g. `id` vs `district_id`), so attempt multiple fallbacks.
    let cacheInfo = null;
    if (_dataCache?.getDistrictById) {
      cacheInfo = _dataCache.getDistrictById(districtId);
    }
    if (!cacheInfo && _dataCache?.getAllDistricts) {
      // Try to locate a matching district object in the cache by several possible id fields
      const all = _dataCache.getAllDistricts();
      cacheInfo = all.find(d => d && (d.district_id === districtId || d.id === districtId || String(d.id) === String(districtId) || String(d.district_id) === String(districtId)) ) || null;
    }

    const info = {
      district_id: districtId,
      district_name: result.district_name,
      district_url: (getDistrictUrl && getDistrictUrl(districtId)) || result.district_url,
      // Try common address fields on cache or result
      address: cacheInfo?.main_address || null,
      towns: cacheInfo?.towns || result.towns || [],
      school_year: result.school_year || null,
    };
    setModalDistrictId(districtId);
    setModalDistrictInfo(info);
    setModalHighlight({
      education: searchParams.education,
      credits: Number(searchParams.credits),
      step: String(searchParams.step),
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setModalDistrictId(null);
    setModalDistrictInfo(null);
    setModalHighlight(null);
  };

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

  const applyFilters = useCallback((data, types, districts = selectedDistricts, towns = selectedTowns) => {
    if (!data || !data.results) {
      setFilteredResults(null);
      return;
    }

    // Filter results by selected district types, districts, and towns
    const filtered = data.results.filter(result => {
      // Check district type (required)
      const matchesType = types.includes(result.district_type);
      if (!matchesType) {
        return false;
      }

      // If no custom filters are selected, include all districts (that match type)
      const hasCustomFilters = districts.size > 0 || towns.size > 0;
      if (!hasCustomFilters) {
        return true;
      }

      // Check if district is specifically selected
      const matchesDistrict = districts.has(result.district_id);

      // Check if district contains any selected town
      let matchesTown = false;
      if (towns.size > 0) {
        const district = _dataCache?.getDistrictById(result.district_id);
        if (district && district.towns && Array.isArray(district.towns)) {
          matchesTown = district.towns.some(town =>
            towns.has(town.trim().toLowerCase())
          );
        }
      }

        // Include district if it matches either the district filter OR the town filter
        return matchesDistrict || matchesTown;
      });

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
    }, [selectedDistricts, selectedTowns, _dataCache]);

    // Count how many districts (from the latest cachedResults) match the current custom filters
    const customIndicatorCount = useMemo(() => {
      // If there's no cachedResults yet, fall back to the number of selected items
      if (!cachedResults || !cachedResults.results) {
        return selectedDistricts.size + selectedTowns.size;
      }

      const results = cachedResults.results;
      const townsLower = new Set(Array.from(selectedTowns).map(t => String(t).toLowerCase()));
      const matched = new Set();

      for (const r of results) {
        if (selectedDistricts.has(r.district_id)) {
          matched.add(r.district_id);
          continue;
        }
        if (townsLower.size > 0) {
          const district = _dataCache?.getDistrictById(r.district_id);
          if (district && Array.isArray(district.towns)) {
            for (const t of district.towns) {
              if (townsLower.has(String(t).trim().toLowerCase())) {
                matched.add(r.district_id);
                break;
              }
            }
          }
        }
      }

      return matched.size;
    }, [cachedResults, selectedDistricts, selectedTowns, _dataCache]);

    // Input change helper
    const handleInputChange = (field, value) => {
      setSearchParams(prev => ({
        ...prev,
        [field]: value
      }));
    };

    // Perform the comparison search against the API and cache results
    const handleSearch = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await api.compareSalaries(
          searchParams.education,
          parseInt(searchParams.credits, 10),
          parseInt(searchParams.step, 10)
        );

        setCachedResults(data);
        // Apply current client-side filters immediately
        applyFilters(data, selectedTypes);
      } catch (err) {
        setError(err?.message || String(err));
        setCachedResults(null);
        setFilteredResults(null);
      } finally {
        setLoading(false);
      }
    };

    const handleCustomFilterApply = (districts, towns) => {
      setSelectedDistricts(districts);
      setSelectedTowns(towns);
      setShowCustomFilter(false);

      if (cachedResults) {
        applyFilters(cachedResults, selectedTypes, districts, towns);
      }
    };

    const handleCustomFilterClear = () => {
      setSelectedDistricts(new Set());
      setSelectedTowns(new Set());

      if (cachedResults) {
        applyFilters(cachedResults, selectedTypes, new Set(), new Set());
      }
    };

    const hasActiveCustomFilters = selectedDistricts.size > 0 || selectedTowns.size > 0;

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

          {/* Custom Filter Button */}
          <button
            type="button"
            className={`district-type-toggle custom-filter-button${hasActiveCustomFilters ? ' active' : ''}`}
            onClick={() => setShowCustomFilter(true)}
            disabled={!cachedResults}
            title="Filter by Districts and Towns"
          >
            <span className="custom-filter-icon">🎯</span>
            <span className="custom-filter-label">Custom</span>
            {hasActiveCustomFilters && (
              <span className="custom-filter-indicator">{customIndicatorCount}</span>
            )}
          </button>
        </div>
      </div>

      {/* Custom Filter Modal */}
      {showCustomFilter && (
        <CustomSalaryFilter
          onClose={() => setShowCustomFilter(false)}
          onApply={handleCustomFilterApply}
          onClear={handleCustomFilterClear}
          selectedDistricts={selectedDistricts}
          selectedTowns={selectedTowns}
        />
      )}

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
          <th className="details-col" aria-label="Details"></th>
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

                      {/* Website link column */}
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
                              onClick={(e) => e.stopPropagation()}
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
                                aria-hidden="true"
                              >
                                <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                                <polyline points="15 3 21 3 21 9" />
                                <line x1="10" y1="14" x2="21" y2="3" />
                              </svg>
                            </a>
                          );
                        })()}
                      </td>

                      {/* Details button column */}
                      <td className="details-cell">
                        <button
                          type="button"
                          className="details-button"
                          onClick={(e) => { e.stopPropagation(); openDistrictModal(result); }}
                          title={`View salary tables for ${result.district_name}`}
                          aria-label={`View salary tables for ${result.district_name}`}
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            <path d="M3 9h18"></path>
                            <path d="M9 21V9"></path>
                          </svg>
                        </button>
                      </td>

                      <td className="district-cell">
                        {result.district_name}
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
      {/* District salary modal */}
      {modalOpen && modalDistrictId && (
        <div className="salary-modal-overlay" onClick={closeModal}>
          <div className="salary-modal" onClick={(e) => e.stopPropagation()}>
            <div className="salary-modal-header">
              <div className="salary-modal-title">
                <h2>{modalDistrictInfo?.district_name}</h2>
                {modalDistrictInfo?.address && (
                  <div className="salary-modal-address">
                    {modalDistrictInfo.address}
                    {modalDistrictInfo.address && (
                      <a
                        className="salary-modal-map"
                        href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(modalDistrictInfo.address)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        title={`Open ${modalDistrictInfo.district_name} in Google Maps`}
                      >
                        {/* simple map pin icon */}
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="salary-modal-icon" aria-hidden="true">
                          <path d="M21 10c0 6-9 13-9 13S3 16 3 10a9 9 0 0 1 18 0z"></path>
                          <circle cx="12" cy="10" r="3"></circle>
                        </svg>
                      </a>
                    )}
                  </div>
                )}
                {modalDistrictInfo?.towns && modalDistrictInfo.towns.length > 0 && (
                  <div className="salary-modal-towns">Towns: {modalDistrictInfo.towns.join(', ')}</div>
                )}

                {/* show search criteria used */}
                <div className="salary-modal-criteria">
                  Current Search: {searchParams.education === 'B' ? "Bachelor's" : searchParams.education === 'M' ? "Master's" : 'Doctorate'}
                  {Number(searchParams.credits) > 0 && ` + ${searchParams.credits} credits`}, Step {searchParams.step}
                </div>
              </div>
              <div className="salary-modal-actions">
                {modalDistrictInfo?.district_url && (
                  <a
                    href={modalDistrictInfo.district_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="external-link"
                    onClick={(e) => e.stopPropagation()}
                    title={`Open ${modalDistrictInfo.district_name} website`}
                  >
                    {/* reuse the external-link svg used in the table */}
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
                      aria-hidden="true"
                    >
                      <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                )}
                <button className="btn btn-secondary" onClick={closeModal}>Close</button>
              </div>
            </div>
            <div className="salary-modal-body">
              <SalaryTable districtId={modalDistrictId} highlight={modalHighlight} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SalaryComparison;