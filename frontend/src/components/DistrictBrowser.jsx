import { useState, lazy, Suspense } from 'react';
import api from '../services/api';
import DistrictEditor from './DistrictEditor';
import SalaryUploadModal from './SalaryUploadModal';
import ContractPdfModal from './ContractPdfModal';
import Toast from './Toast';
import ErrorBoundary from './ErrorBoundary';
import { DISTRICT_TYPE_OPTIONS, DISTRICT_TYPE_ORDER } from '../constants/districtTypes';
import { normalizeTownName } from '../utils/formatters';
import { sortDistrictsByTypeAndName } from '../utils/sortDistricts';
import './DistrictBrowser.css';
import { useDataCache } from '../hooks/useDataCache';

// Lazy load heavy components for better performance
const ChoroplethMap = lazy(() => import('./ChoroplethMap'));
const SalaryTable = lazy(() => import('./SalaryTable'));
const SalaryComparison = lazy(() => import('./SalaryComparison'));

function DistrictBrowser({ user }) {
  const [activeTab, setActiveTab] = useState('districts'); // 'districts' or 'salaries'
  const [editingDistrict, setEditingDistrict] = useState(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const EditSalaryModal = lazy(() => import('./EditSalaryModal'));
  const [toast, setToast] = useState({ isOpen: false, message: '', variant: 'success' });
  // District type filters
  const [selectedTypes, setSelectedTypes] = useState(DISTRICT_TYPE_OPTIONS.map(opt => opt.value));

  // Check if user is admin; allow local override via VITE_SHOW_ADMIN_CONTROLS=true
  const isAdmin = (user?.is_admin || false) || (import.meta.env.VITE_SHOW_ADMIN_CONTROLS === 'true');

  // Handle checkbox change
  const handleTypeChange = (type) => {
    setSelectedTypes(prev =>
      prev.includes(type)
        ? prev.filter(t => t !== type)
        : [...prev, type]
    );
  };

  const [districts, setDistricts] = useState([]);
  // Filter districts by selected types and sort by custom type order
  const filteredDistricts = sortDistrictsByTypeAndName(
    districts.filter(d => selectedTypes.includes(d.district_type))
  );

  // Get total count for each type
  const typeCounts = DISTRICT_TYPE_OPTIONS.reduce((acc, opt) => {
    acc[opt.value] = districts.filter(d => d.district_type === opt.value).length;
    return acc;
  }, {});
  const [selectedDistrict, setSelectedDistrict] = useState(null);
  const [clickedTown, setClickedTown] = useState(null);
  const [districtCycleIndex, setDistrictCycleIndex] = useState(0);
  const [lastClickedTown, setLastClickedTown] = useState(null);
  const [districtsForTown, setDistrictsForTown] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all', 'name', 'town'
  const [salaryRefreshKey, setSalaryRefreshKey] = useState(0);
  const [contractPdfUrl, setContractPdfUrl] = useState(null);
  const [contractDistrictName, setContractDistrictName] = useState(null);

  const cache = useDataCache();
  const getDistrictUrl = cache.getDistrictUrl;

  // Do not auto-load districts on mount

  const loadDistricts = async (query, type) => {
    try {
      setLoading(true);
      setError(null);
      let response;
      if (type === 'all') {
        response = await api.searchDistricts(query, { limit: 100 });
      } else if (type === 'name') {
        response = await api.getDistricts({ name: query, limit: 100 });
      } else if (type === 'town') {
        response = await api.getDistricts({ town: query, limit: 100 });
      }
      setDistricts(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setSelectedDistrict(null); // Clear highlight on new search
    if (!searchQuery.trim()) {
      setDistricts([]); // Clear districts if search is blank
      return;
    }
    await loadDistricts(searchQuery, filterType);
  };

  const handleDistrictClick = async (district) => {
    try {
      setError(null);
      setClickedTown(null); // Clear clicked town when district is selected
      // Fetch full district details
      const fullDistrict = await api.getDistrict(district.id);
      setSelectedDistrict(fullDistrict);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSelectedDistrict(null); // Clear highlight on clear
    setClickedTown(null); // Clear clicked town
    setDistricts([]); // Clear districts list
  };

  const handleTownClick = async (townName) => {
    // Normalize town name for cache lookup
    const townKey = normalizeTownName(townName);
    // If new town, reset cycle and fetch districts
    if (lastClickedTown !== townKey) {
      setLastClickedTown(townKey);
      setDistrictCycleIndex(0);
      setSelectedDistrict(null);
      setClickedTown(townName);
      setSearchQuery(townName);
      setFilterType('town');
      setLoading(true);
      setError(null);
      try {
        // Use cache if available
        let districtsList = cache.getDistrictsByTown(townName);
        if (!districtsList || districtsList.length === 0) {
          const response = await api.getDistricts({ town: townName });
          districtsList = response.data;
        }
        // Sort districts alphabetically by name to match tooltip
        districtsList = districtsList.slice().sort((a, b) => a.name.localeCompare(b.name));
        setDistrictsForTown(districtsList);
        setDistricts(districtsList);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
      return;
    }
    // If same town, cycle through districts
    if (districtsForTown.length > 0) {
      // Always cycle in custom type order, then by name
      const sortedDistricts = districtsForTown.slice().sort((a, b) => {
        const typeA = DISTRICT_TYPE_ORDER[a.district_type] ?? 99;
        const typeB = DISTRICT_TYPE_ORDER[b.district_type] ?? 99;
        if (typeA !== typeB) return typeA - typeB;
        return a.name.localeCompare(b.name);
      });
      let nextIndex = districtCycleIndex + 1;
      if (nextIndex > sortedDistricts.length) {
        nextIndex = 0;
      }
      setDistrictCycleIndex(nextIndex);
      if (nextIndex === 0) {
        // Highlight town only (orange)
        setSelectedDistrict(null);
        setClickedTown(townName);
      } else {
        // Highlight the next district
        setSelectedDistrict(sortedDistricts[nextIndex - 1]);
        setClickedTown(null);
      }
    }
  };

  const handleUploadSuccess = (result) => {
    // Refresh the salary table after successful upload
    if (result.needs_global_normalization) {
      setToast({
        isOpen: true,
        message: `Salary data applied successfully! ${result.records_added} records added.\n\nGlobal metadata has changed. Please run normalization from the user menu.`,
        variant: 'warning'
      });
    } else {
      setToast({
        isOpen: true,
        message: `Salary data applied successfully! ${result.records_added} records added.`,
        variant: 'success'
      });
    }
    // Trigger refetch in SalaryTable by bumping refresh key
    setSalaryRefreshKey((k) => k + 1);
    // Optionally refresh selected district details as well
    if (selectedDistrict) {
      handleDistrictClick(selectedDistrict);
    }
  };

  const handleSaveDistrict = async (updatedData) => {
    try {
      const updatedDistrict = await api.updateDistrict(editingDistrict.id, updatedData);

      // Update the cache
      cache.updateDistrictInCache(updatedDistrict);

      // Update the districts list
      setDistricts(prev =>
        prev.map(d => d.id === updatedDistrict.id ? updatedDistrict : d)
      );

      // Update selected district if it's the one being edited
      if (selectedDistrict?.id === updatedDistrict.id) {
        setSelectedDistrict(updatedDistrict);
      }

      setEditingDistrict(null);
    } catch (err) {
      throw err;
    }
  };

  const handleAfterDistrictEditorClose = async () => {
    // Refetch the district to get any updates made after save (like contract_pdf)
    if (editingDistrict && editingDistrict.id) {
      try {
        const freshDistrict = await api.getDistrict(editingDistrict.id);

        // Update cache
        cache.updateDistrictInCache(freshDistrict);

        // Update districts list
        setDistricts(prev =>
          prev.map(d => d.id === freshDistrict.id ? freshDistrict : d)
        );

        // Update selected district if it matches
        if (selectedDistrict?.id === freshDistrict.id) {
          setSelectedDistrict(freshDistrict);
        }
      } catch (err) {
        console.error('Failed to refresh district after close:', err);
      }
    }
    setEditingDistrict(null);
  };

  const handleContractClick = async (district) => {
    try {
      const response = await api.getContractPdf(district.name);
      if (response && response.download_url) {
        setContractPdfUrl(response.download_url);
        setContractDistrictName(district.name);
      } else {
        setToast({
          isOpen: true,
          message: 'Contract PDF not available for this district',
          variant: 'error'
        });
      }
    } catch (err) {
      setToast({
        isOpen: true,
        message: `Failed to load contract: ${err.message}`,
        variant: 'error'
      });
    }
  };

  return (
    <>
      <Toast
        isOpen={toast.isOpen}
        message={toast.message}
        variant={toast.variant}
        duration={6000}
        onClose={() => setToast({ ...toast, isOpen: false })}
      />

      <div className="district-browser">
        <header className="browser-header">
          <h1>Massachusetts School Districts</h1>
          <div className="tab-navigation">
            <button
              className={`tab-button ${activeTab === 'districts' ? 'active' : ''}`}
              onClick={() => setActiveTab('districts')}
            >
              🗺️ District Browser
            </button>
            <button
              className={`tab-button ${activeTab === 'salaries' ? 'active' : ''}`}
              onClick={() => setActiveTab('salaries')}
            >
              💰 Compare Salaries
            </button>
          </div>
        </header>

      {activeTab === 'districts' ? (
        <>
          <div className="search-section">
        <form onSubmit={handleSearch} className="search-form">
          <div className="search-controls">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="filter-select"
              aria-label="Filter search by type"
            >
              <option value="all">Search All</option>
              <option value="name">District Name</option>
              <option value="town">Town Name</option>
            </select>

            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={
                filterType === 'name'
                  ? 'Search by district name...'
                  : filterType === 'town'
                  ? 'Search by town name...'
                  : 'Search districts or towns...'
              }
              className="search-input"
              aria-label="Search districts or towns"
            />

            <button type="submit" className="btn btn-primary">
              Search
            </button>

            {searchQuery && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="btn btn-secondary"
              >
                Clear
              </button>
            )}
          </div>

          {/* District Type Filters - in same container */}
          <div className="district-type-filters-row">
            {DISTRICT_TYPE_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                className={`district-type-toggle${selectedTypes.includes(opt.value) ? ' active' : ''}`}
                onClick={() => handleTypeChange(opt.value)}
                aria-pressed={selectedTypes.includes(opt.value)}
              >
                <span className="district-type-icon">{opt.icon}</span>
                <span className="district-type-label">{opt.label}</span>
                <span className="district-type-count">{typeCounts[opt.value] ?? 0}</span>
              </button>
            ))}
          </div>
        </form>
      </div>

      {error && (
        <div className="error-message">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="content-area">
        <div className="district-list">
          <h2>
            Districts ({districts.length})
          </h2>

          {loading ? (
            <div className="loading">Loading districts...</div>
          ) : filteredDistricts.length === 0 ? (
            <div className="no-results">
              No districts found. {searchQuery && 'Try a different search term.'}
            </div>
          ) : (
            <ul className="district-items">
              {filteredDistricts.map((district) => {
                const typeOpt = DISTRICT_TYPE_OPTIONS.find(opt => opt.value === district.district_type);
                return (
                  <li
                    key={district.id}
                    className={`district-item ${
                      selectedDistrict?.id === district.id ? 'active' : ''
                    }`}
                    onClick={() => handleDistrictClick(district)}
                  >
                    {/* external link icon (top-right) */}
                    {(() => {
                      const url = (getDistrictUrl && getDistrictUrl(district.id)) || district.district_url;
                      if (!url) return null;
                      return (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="external-link-btn"
                          title={`Open ${district.name} website`}
                          aria-label={`Open ${district.name} website`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
                            <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                        </a>
                      );
                    })()}

                    {/* contract PDF icon */}
                    <button
                      className={`contract-link-btn${district.contract_pdf ? '' : ' disabled'}`}
                      title={district.contract_pdf ? `View ${district.name} contract PDF` : 'No contract available'}
                      aria-label={district.contract_pdf ? `View ${district.name} contract PDF` : 'No contract available'}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (district.contract_pdf) {
                          handleContractClick(district);
                        }
                      }}
                      disabled={!district.contract_pdf}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                      </svg>
                    </button>

                    {isAdmin && (
                      <button
                        className="edit-district-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingDistrict(district);
                        }}
                        title="Edit district"
                      >
                        🔧
                      </button>
                    )}
                    <div className="district-name">
                      <span className="district-type-icon" style={{marginRight: '6px'}}>{typeOpt?.icon}</span>
                      {district.name}
                    </div>
                    <div className="district-towns">
                      {district.towns.map((town, idx) => (
                        <span key={town} className="district-town-span">
                          {town}{idx < district.towns.length - 1 ? ', ' : ''}
                        </span>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="map-section">
          <ErrorBoundary
            errorTitle="Map Error"
            errorMessage="There was a problem loading the map. Try refreshing the page."
            showDetails={false}
          >
            <Suspense fallback={<div className="loading">Loading map...</div>}>
              <ChoroplethMap
                selectedDistrict={selectedDistrict}
                clickedTown={clickedTown}
                onTownClick={handleTownClick}
                districtTypeOptions={DISTRICT_TYPE_OPTIONS}
              />
            </Suspense>
          </ErrorBoundary>
        </div>

        {selectedDistrict && (
          <div className="salary-section">
            <div className="salary-section-header">
              <h3>Salary Schedule</h3>
              {isAdmin && (selectedDistrict.district_type === 'municipal' || selectedDistrict.district_type === 'regional_academic') && (
                <div className="salary-actions" role="group" aria-label="Salary actions">
                  <button
                    className="salary-action-button edit-salary-button"
                    onClick={() => setShowEditModal(true)}
                    title="Edit salary table data"
                  >
                    ✏️ Edit
                  </button>
                  <button
                    className="salary-action-button upload-salary-button"
                    onClick={() => setShowUploadModal(true)}
                    title="Upload PDF salary schedule"
                  >
                    <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    Upload
                  </button>
                </div>
              )}
            </div>
            <Suspense fallback={<div className="loading">Loading salary table...</div>}>
              <SalaryTable districtId={selectedDistrict.id} refreshKey={salaryRefreshKey} />
            </Suspense>
          </div>
        )}
      </div>

      <DistrictEditor
        district={editingDistrict}
        onClose={handleAfterDistrictEditorClose}
        onSave={handleSaveDistrict}
        user={user}
      />

      {showUploadModal && selectedDistrict && (
        <SalaryUploadModal
          district={selectedDistrict}
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {showEditModal && selectedDistrict && (
        <Suspense fallback={<div className="loading">Loading editor...</div>}>
          <EditSalaryModal
            district={selectedDistrict}
            onClose={() => setShowEditModal(false)}
            onSuccess={(result) => {
              // mirror upload success handling
              if (result.needs_global_normalization) {
                setToast({
                  isOpen: true,
                  message: `Salary data applied successfully! ${result.records_added} records added.\n\nGlobal metadata has changed. Please run normalization from the user menu.`,
                  variant: 'warning'
                });
              } else {
                setToast({
                  isOpen: true,
                  message: `Salary data applied successfully! ${result.records_added} records added.`,
                  variant: 'success'
                });
              }
              setSalaryRefreshKey((k) => k + 1);
              setShowEditModal(false);
            }}
          />
        </Suspense>
      )}
        </>
      ) : (
        <div className="salary-comparison-tab">
          <ErrorBoundary
            errorTitle="Salary Comparison Error"
            errorMessage="There was a problem loading salary comparisons. Try refreshing the page."
            showDetails={false}
          >
            <Suspense fallback={<div className="loading">Loading salary comparison...</div>}>
              <SalaryComparison />
            </Suspense>
          </ErrorBoundary>
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
    </>
  );
}

export default DistrictBrowser;