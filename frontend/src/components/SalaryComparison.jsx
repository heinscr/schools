import { useState, useContext, useEffect } from 'react';
import api from '../services/api';
import { DataCacheContext } from '../contexts/DataCacheContext';
import SalaryComparisonMap from './SalaryComparisonMap';
import SalaryTable from './SalaryTable';
import CustomSalaryFilter from './CustomSalaryFilter';
import ContractPdfModal from './ContractPdfModal';
import { DISTRICT_TYPE_OPTIONS } from '../constants/districtTypes';
import { formatCurrency } from '../utils/formatters';
import './SalaryComparison.css';

// Filter district types to only Municipal, Regional, and Custom for salary comparison
const SALARY_COMPARISON_DISTRICT_TYPES = DISTRICT_TYPE_OPTIONS.filter(opt =>
  opt.value === 'municipal' || opt.value === 'regional_academic'
);

// Helper functions for URL parameter management
const getUrlParams = () => {
  const params = new URLSearchParams(window.location.search);
  return {
    education: params.get('education'),
    credits: params.get('credits'),
    step: params.get('step'),
    types: params.get('types')?.split(',').filter(Boolean),
    districts: params.get('districts')?.split(',').filter(Boolean),
    towns: params.get('towns')?.split(',').filter(Boolean),
  };
};

const updateUrlParams = (searchParams, selectedTypes, selectedDistricts, selectedTowns) => {
  const params = new URLSearchParams();

  if (searchParams.education) params.set('education', searchParams.education);
  if (searchParams.credits) params.set('credits', searchParams.credits);
  if (searchParams.step) params.set('step', searchParams.step);

  // Only add types if not all are selected (default state)
  const allTypes = SALARY_COMPARISON_DISTRICT_TYPES.map(opt => opt.value);
  if (selectedTypes.length > 0 && selectedTypes.length < allTypes.length) {
    params.set('types', selectedTypes.join(','));
  }

  if (selectedDistricts.size > 0) {
    params.set('districts', Array.from(selectedDistricts).join(','));
  }

  if (selectedTowns.size > 0) {
    params.set('towns', Array.from(selectedTowns).join(','));
  }

  const newUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState({}, '', newUrl);
};

function SalaryComparison() {
  // Read initial values from URL or use defaults
  const urlParams = getUrlParams();

  const [searchParams, setSearchParams] = useState({
    step: urlParams.step || '5',
    education: urlParams.education || 'M',
    credits: urlParams.credits || '30'
  });
  const [selectedTypes, setSelectedTypes] = useState(
    urlParams.types?.length > 0
      ? urlParams.types
      : SALARY_COMPARISON_DISTRICT_TYPES.map(opt => opt.value)
  );
  const [cachedResults, setCachedResults] = useState(null); // Full results from API (cached)
  const [filteredResults, setFilteredResults] = useState(null); // Filtered by district type
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showCustomFilter, setShowCustomFilter] = useState(false);
  const [selectedDistricts, setSelectedDistricts] = useState(
    urlParams.districts?.length > 0 ? new Set(urlParams.districts) : new Set()
  );
  const [selectedTowns, setSelectedTowns] = useState(
    urlParams.towns?.length > 0 ? new Set(urlParams.towns) : new Set()
  );
  const [salaryMeta, setSalaryMeta] = useState(null);
  const [salaryMetaError, setSalaryMetaError] = useState(null);
  const [salaryMetaLoading, setSalaryMetaLoading] = useState(false);
  const [urlLoaded, setUrlLoaded] = useState(false);
  const [showCopyNotification, setShowCopyNotification] = useState(false);
  const _dataCache = useContext(DataCacheContext);
  const getDistrictUrl = _dataCache?.getDistrictUrl;
  const [modalOpen, setModalOpen] = useState(false);
  const [modalDistrictId, setModalDistrictId] = useState(null);
  const [modalDistrictInfo, setModalDistrictInfo] = useState(null);
  const [modalHighlight, setModalHighlight] = useState(null);
  const [contractPdfUrl, setContractPdfUrl] = useState(null);
  const [contractDistrictName, setContractDistrictName] = useState(null);
  const [lastSearchTime, setLastSearchTime] = useState(null);

  const openDistrictModal = async (result) => {
    const districtId = result.district_id;

    // Try to get district info from cache, or fetch it if not available
    let cacheInfo = null;
    if (_dataCache?.getDistrictById) {
      cacheInfo = _dataCache.getDistrictById(districtId);
    }

    // If not in cache, fetch it on-demand
    if (!cacheInfo && _dataCache?.ensureDistrictById) {
      try {
        cacheInfo = await _dataCache.ensureDistrictById(districtId);
      } catch (err) {
        console.error(`Failed to fetch district ${districtId}:`, err);
        // Continue with result data if fetch fails
      }
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

      // Update URL with new filters
      updateUrlParams(searchParams, newTypes, selectedDistricts, selectedTowns);

      return newTypes;
    });
  };

  const applyFilters = (data, types, districts = selectedDistricts, towns = selectedTowns) => {
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
    };

    // Count how many districts (from the latest cachedResults) match the current custom filters
    const getCustomIndicatorCount = () => {
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
    };

    // Input change helper
    const handleInputChange = (field, value) => {
      setSearchParams(prev => {
        const next = { ...prev, [field]: value };

        // When education changes, validate and adjust credits if needed
        if (field === 'education' && eduCreditMap) {
          const validCredits = eduCreditMap.get(value);
          if (validCredits && !validCredits.has(parseInt(prev.credits, 10))) {
            // Current credits not valid for new education, select first valid one
            const sortedCredits = Array.from(validCredits).sort((a, b) => a - b);
            next.credits = String(sortedCredits[0] || 0);
          }
        }

        return next;
      });
    };

    // Fetch global salary metadata (edu_credit_combos, max_step) on mount
    useEffect(() => {
      let mounted = true;
      const load = async () => {
        setSalaryMetaLoading(true);
        try {
          const data = await api.getGlobalSalaryMetadata();
          if (!mounted) return;
          setSalaryMeta(data || null);
          setSalaryMetaError(null);
        } catch (err) {
          if (!mounted) return;
          setSalaryMeta(null);
          setSalaryMetaError(err?.message || String(err));
        } finally {
          if (mounted) setSalaryMetaLoading(false);
        }
      };

      load();
      return () => { mounted = false; };
    }, []);

    // Derive option lists from metadata with sensible fallbacks
    const DEFAULT_MAX_STEP = 15;
    const DEFAULT_EDU_OPTIONS = [
      { value: 'B', label: "Bachelor's" },
      { value: 'M', label: "Master's" },
      { value: 'D', label: 'Doctorate' },
    ];
    const DEFAULT_CREDITS = [0, 15, 30, 45, 60];

    // Parse edu_credit_combos into a map for easy lookup
    const eduCreditMap = (() => {
      if (!salaryMeta || !Array.isArray(salaryMeta.edu_credit_combos)) return null;

      const map = new Map(); // Map<education, Set<credits>>

      for (const combo of salaryMeta.edu_credit_combos) {
        if (!combo) continue;
        const parts = String(combo).split('+');
        const edu = parts[0];
        const cred = parts.length > 1 ? parseInt(parts[1], 10) : 0;

        if (edu && !Number.isNaN(cred)) {
          if (!map.has(edu)) {
            map.set(edu, new Set());
          }
          map.get(edu).add(cred);
        }
      }

      return map.size > 0 ? map : null;
    })();

    // Get all unique education levels from metadata
    const parsedEduOptions = (() => {
      if (!eduCreditMap) return DEFAULT_EDU_OPTIONS;

      const order = ['B', 'M', 'D'];
      const eduSet = new Set(eduCreditMap.keys());
      const found = order.filter(o => eduSet.has(o));
      const rest = Array.from(eduSet).filter(e => !order.includes(e));
      const final = [...found, ...rest].map(e => ({
        value: e,
        label: e === 'B' ? "Bachelor's" : e === 'M' ? "Master's" : e === 'D' ? 'Doctorate' : e
      }));

      return final.length > 0 ? final : DEFAULT_EDU_OPTIONS;
    })();

    // Get valid credits for the currently selected education level
    const validCreditsForEducation = (() => {
      if (!eduCreditMap) return DEFAULT_CREDITS;

      const currentEdu = searchParams.education;
      const creditsSet = eduCreditMap.get(currentEdu);

      if (!creditsSet || creditsSet.size === 0) {
        // Fallback: return all credits from all education levels
        const allCredits = new Set();
        for (const credits of eduCreditMap.values()) {
          for (const c of credits) {
            allCredits.add(c);
          }
        }
        return Array.from(allCredits).sort((a, b) => a - b);
      }

      return Array.from(creditsSet).sort((a, b) => a - b);
    })();

    const maxStep = (salaryMeta && Number.isFinite(Number(salaryMeta.max_step))) ? Number(salaryMeta.max_step) : DEFAULT_MAX_STEP;

    // Ensure current searchParams values are present in options; if not, adjust them
    useEffect(() => {
      if (!salaryMeta || !eduCreditMap) return;
      setSearchParams(prev => {
        let changed = false;
        const next = { ...prev };
        const eduVals = parsedEduOptions.map(o => o.value);
        if (!eduVals.includes(next.education)) {
          next.education = eduVals[0] || next.education;
          changed = true;
        }

        // Check if current credits are valid for current education
        const validCredits = eduCreditMap.get(next.education);
        if (validCredits && !validCredits.has(parseInt(next.credits, 10))) {
          // Select first valid credit for this education level
          const sortedCredits = Array.from(validCredits).sort((a, b) => a - b);
          next.credits = String(sortedCredits[0] || 0);
          changed = true;
        }

        if (Number(next.step) < 1 || Number(next.step) > maxStep) {
          next.step = String(Math.max(1, Math.min(Number(next.step) || 1, maxStep)));
          changed = true;
        }
        return changed ? next : prev;
      });
    // Only run when salaryMeta changes
    }, [salaryMeta, eduCreditMap]);

    // Auto-load search results if URL parameters exist
    useEffect(() => {
      if (!urlLoaded && salaryMeta && urlParams.education && urlParams.credits && urlParams.step) {
        setUrlLoaded(true);
        handleSearch();
      }
    }, [salaryMeta, urlLoaded]);

    // Perform the comparison search against the API and cache results
    const handleSearch = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await api.compareSalaries(
          searchParams.education,
          parseInt(searchParams.credits, 10),
          parseInt(searchParams.step, 10),
          { includeFallback: true }  // Enable cross-education fallback
        );

        setCachedResults(data);
        // Apply current client-side filters immediately
        applyFilters(data, selectedTypes);

        // Update URL with current search parameters
        updateUrlParams(searchParams, selectedTypes, selectedDistricts, selectedTowns);

        // Set timestamp to trigger map to exit selection mode
        setLastSearchTime(Date.now());
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

      // Update URL with new custom filters
      updateUrlParams(searchParams, selectedTypes, districts, towns);
    };

    const handleCustomFilterClear = () => {
      setSelectedDistricts(new Set());
      setSelectedTowns(new Set());

      if (cachedResults) {
        applyFilters(cachedResults, selectedTypes, new Set(), new Set());
      }

      // Update URL to remove custom filters
      updateUrlParams(searchParams, selectedTypes, new Set(), new Set());
    };

    const handleCopyLink = async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        setShowCopyNotification(true);
        setTimeout(() => setShowCopyNotification(false), 2000);
      } catch (err) {
        console.error('Failed to copy link:', err);
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
            <label htmlFor="education">Education</label>
            <select
              id="education"
              value={searchParams.education}
              onChange={(e) => handleInputChange('education', e.target.value)}
            >
              {parsedEduOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="credits">Credits</label>
            <select
              id="credits"
              value={searchParams.credits}
              onChange={(e) => handleInputChange('credits', e.target.value)}
            >
              {validCreditsForEducation.map(c => (
                <option key={String(c)} value={String(c)}>{String(c)}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="step">Step</label>
            <select
              id="step"
              value={searchParams.step}
              onChange={(e) => handleInputChange('step', e.target.value)}
            >
              {[...Array(maxStep)].map((_, i) => (
                <option key={i + 1} value={String(i + 1)}>{i + 1}</option>
              ))}
            </select>
          </div>

          <div className="button-row">
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

            {filteredResults && (
              <div className="form-group share-button-group">
                <label>&nbsp;</label>
                <button
                  className="share-icon-button"
                  onClick={handleCopyLink}
                  title={showCopyNotification ? 'Copied!' : 'Copy shareable link'}
                >
                  {showCopyNotification ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="18" cy="5" r="3"></circle>
                      <circle cx="6" cy="12" r="3"></circle>
                      <circle cx="18" cy="19" r="3"></circle>
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                    </svg>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        <p className="comparison-description">
          Search for teacher salaries by education level, credits, and experience step
        </p>

        {/* District Type Filters - in same container */}
        <div className="district-type-filters-row">
          {SALARY_COMPARISON_DISTRICT_TYPES.map(opt => {
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
            <span className="district-type-icon">🎯</span>
            <span className="district-type-label">Custom</span>
            {hasActiveCustomFilters && (
              <span className="custom-filter-indicator">{getCustomIndicatorCount()}</span>
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
        <SalaryComparisonMap
          results={filteredResults?.results || []}
          selectedTowns={selectedTowns}
          hasResults={filteredResults !== null && filteredResults.results && filteredResults.results.length > 0}
          lastSearchTime={lastSearchTime}
          onTownSelectionChange={(newSelectedTowns) => {
            setSelectedTowns(newSelectedTowns);
            // Apply filters with the new town selections
            if (cachedResults) {
              applyFilters(cachedResults, selectedTypes, selectedDistricts, newSelectedTowns);
            }
            // Update URL
            updateUrlParams(searchParams, selectedTypes, selectedDistricts, newSelectedTowns);
          }}
        />
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
          <th className="contract-col" aria-label="Contract"></th>
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

                      {/* Contract PDF column */}
                      <td className="contract-cell">
                        <button
                          type="button"
                          className={`contract-button${result.contract_pdf ? '' : ' disabled'}`}
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!result.contract_pdf) return;
                            try {
                              const response = await api.getContractPdf(result.district_name);
                              if (response && response.download_url) {
                                setContractPdfUrl(response.download_url);
                                setContractDistrictName(result.district_name);
                              }
                            } catch (err) {
                              console.error('Failed to load contract:', err);
                            }
                          }}
                          title={result.contract_pdf ? `View ${result.district_name} contract PDF` : 'No contract available'}
                          aria-label={result.contract_pdf ? `View ${result.district_name} contract PDF` : 'No contract available'}
                          disabled={!result.contract_pdf}
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                            <line x1="16" y1="13" x2="8" y2="13"></line>
                            <line x1="16" y1="17" x2="8" y2="17"></line>
                            <polyline points="10 9 9 9 8 9"></polyline>
                          </svg>
                        </button>
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
                      <td className={`salary-cell${result.is_calculated || result.is_exact_match==false ? ' fallback-highlight' : ''}`}>
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

      {/* Contract PDF modal */}
      {contractPdfUrl && contractDistrictName && (
        <ContractPdfModal
          districtName={contractDistrictName}
          pdfUrl={contractPdfUrl}
          onClose={() => {
            setContractPdfUrl(null);
            setContractDistrictName(null);
          }}
        />
      )}
    </div>
  );
}

export default SalaryComparison;