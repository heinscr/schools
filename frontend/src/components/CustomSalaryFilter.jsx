import { useState, useEffect, useContext } from 'react';
import { DataCacheContext } from '../contexts/DataCacheContext';
import './CustomSalaryFilter.css';

function CustomSalaryFilter({ onClose, onApply, onClear, selectedDistricts, selectedTowns }) {
  const cache = useContext(DataCacheContext);
  const [localDistricts, setLocalDistricts] = useState(new Set(selectedDistricts));
  const [localTowns, setLocalTowns] = useState(new Set(selectedTowns));
  const [searchQuery, setSearchQuery] = useState('');
  const [townSearchQuery, setTownSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('districts'); // 'districts' or 'towns'

  // Get all districts and towns from cache
  const allDistricts = cache?.getAllDistricts() || [];
  const allTowns = cache?.getAllTowns() || [];

  // Filter districts based on search query
  const filteredDistricts = allDistricts.filter(district =>
    district.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Sort the filtered districts alphabetically by name (case-insensitive)
  const sortedFilteredDistricts = [...filteredDistricts].sort((a, b) =>
    a.name.toLowerCase().localeCompare(b.name.toLowerCase())
  );

  // Filter towns based on search query
  const filteredTowns = allTowns.filter(town =>
    town.toLowerCase().includes(townSearchQuery.toLowerCase())
  );

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleDistrictToggle = (districtId) => {
    setLocalDistricts(prev => {
      const newSet = new Set(prev);
      if (newSet.has(districtId)) {
        newSet.delete(districtId);
      } else {
        newSet.add(districtId);
      }
      return newSet;
    });
  };

  const handleTownToggle = (townName) => {
    const normalizedTown = townName.trim().toLowerCase();
    setLocalTowns(prev => {
      const newSet = new Set(prev);
      if (newSet.has(normalizedTown)) {
        newSet.delete(normalizedTown);
      } else {
        newSet.add(normalizedTown);
      }
      return newSet;
    });
  };

  const handleSelectAllDistricts = () => {
    if (localDistricts.size === sortedFilteredDistricts.length) {
      // Deselect all
      setLocalDistricts(new Set());
    } else {
      // Select all filtered
      setLocalDistricts(new Set(sortedFilteredDistricts.map(d => d.id)));
    }
  };

  const handleSelectAllTowns = () => {
    if (localTowns.size === filteredTowns.length) {
      // Deselect all
      setLocalTowns(new Set());
    } else {
      // Select all filtered
      setLocalTowns(new Set(filteredTowns.map(t => t.trim().toLowerCase())));
    }
  };

  const handleApply = () => {
    onApply(localDistricts, localTowns);
  };

  const handleClearAll = () => {
    setLocalDistricts(new Set());
    setLocalTowns(new Set());
    onClear();
    onClose();
  };

  // helper to force checkbox visuals (unchecked white, checked accent with checkmark svg)
  const getCheckboxStyle = (checked) => ({
    width: '18px',
    height: '18px',
    cursor: 'pointer',
    boxSizing: 'border-box',
    border: '2px solid #dcdcdc',
    borderRadius: '4px',
    backgroundColor: checked ? '#4a90e2' : 'white',
    backgroundImage: checked
      ? "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 10'><path fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' d='M1 5.2l3.1 3L11 1'/></svg>\")"
      : 'none',
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'center',
    WebkitAppearance: 'none',
    MozAppearance: 'none',
    appearance: 'none',
  });

  return (
    <div className="custom-filter-backdrop" onClick={handleBackdropClick} role="presentation">
      <div
        className="custom-filter-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="custom-filter-title"
      >
        <div className="custom-filter-header">
          <h2 id="custom-filter-title">Custom Filter</h2>
          <button className="close-button" onClick={onClose} type="button" aria-label="Close filter modal">
            ×
          </button>
        </div>

        <div className="custom-filter-tabs">
          <button
            className={`filter-tab ${activeTab === 'districts' ? 'active' : ''}`}
            onClick={() => setActiveTab('districts')}
            type="button"
          >
            Districts
            {localDistricts.size > 0 && (
              <span className="tab-badge">{localDistricts.size}</span>
            )}
          </button>
          <button
            className={`filter-tab ${activeTab === 'towns' ? 'active' : ''}`}
            onClick={() => setActiveTab('towns')}
            type="button"
          >
            Towns
            {localTowns.size > 0 && (
              <span className="tab-badge">{localTowns.size}</span>
            )}
          </button>
        </div>

        <div className="custom-filter-content">
          {activeTab === 'districts' && (
            <div className="filter-section">
              <div className="filter-section-header">
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Search districts..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="filter-search-input"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleSelectAllDistricts}
                  className="select-all-btn"
                >
                  {localDistricts.size === filteredDistricts.length && filteredDistricts.length > 0
                    ? 'Deselect All'
                    : 'Select All'}
                </button>
              </div>

              <div className="filter-list">
                {sortedFilteredDistricts.length === 0 ? (
                  <div className="no-results">No districts found</div>
                ) : (
                  sortedFilteredDistricts.map(district => (
                    <label key={district.id} className="filter-item">
                      <input
                        type="checkbox"
                        checked={localDistricts.has(district.id)}
                        onChange={() => handleDistrictToggle(district.id)}
                        style={getCheckboxStyle(localDistricts.has(district.id))}
                      />
                      <span className="filter-item-label">{district.name}</span>
                      {district.district_type && (
                        <span className="filter-item-type">
                          {district.district_type.replace('_', ' ')}
                        </span>
                      )}
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === 'towns' && (
            <div className="filter-section">
              <div className="filter-section-header">
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Search towns..."
                    value={townSearchQuery}
                    onChange={(e) => setTownSearchQuery(e.target.value)}
                    className="filter-search-input"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleSelectAllTowns}
                  className="select-all-btn"
                >
                  {localTowns.size === filteredTowns.length && filteredTowns.length > 0
                    ? 'Deselect All'
                    : 'Select All'}
                </button>
              </div>

              <div className="filter-list">
                {filteredTowns.length === 0 ? (
                  <div className="no-results">No towns found</div>
                ) : (
                  filteredTowns.map(town => {
                    const normalizedTown = town.trim().toLowerCase();
                    const districts = cache?.getDistrictsByTown(town) || [];
                    return (
                      <label key={normalizedTown} className="filter-item">
                          <input
                            type="checkbox"
                            checked={localTowns.has(normalizedTown)}
                            onChange={() => handleTownToggle(town)}
                            style={getCheckboxStyle(localTowns.has(normalizedTown))}
                          />
                        <span className="filter-item-label">{town}</span>
                        <span className="filter-item-count">
                          {districts.length} {districts.length === 1 ? 'district' : 'districts'}
                        </span>
                      </label>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        <div className="custom-filter-footer">
          <div className="filter-summary">
            {localDistricts.size > 0 && (
              <span className="summary-item">
                {localDistricts.size} {localDistricts.size === 1 ? 'district' : 'districts'}
              </span>
            )}
            {localTowns.size > 0 && (
              <span className="summary-item">
                {localTowns.size} {localTowns.size === 1 ? 'town' : 'towns'}
              </span>
            )}
            {localDistricts.size === 0 && localTowns.size === 0 && (
              <span className="summary-item empty">No filters selected</span>
            )}
          </div>
          <div className="filter-actions">
            <button type="button" onClick={handleClearAll} className="btn btn-clear">
              Clear All
            </button>
            <button type="button" onClick={handleApply} className="btn btn-apply">
              Apply Filter
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CustomSalaryFilter;