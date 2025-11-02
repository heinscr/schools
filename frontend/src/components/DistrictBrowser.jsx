import { useState, useEffect } from 'react';
import api from '../services/api';
import ChoroplethMap from './ChoroplethMap';
import DistrictEditor from './DistrictEditor';
import './DistrictBrowser.css';

function DistrictBrowser() {
  const [editingDistrict, setEditingDistrict] = useState(null);
  // District type filters
  const districtTypeOptions = [
    { value: 'municipal', label: 'Municipal', icon: '🏛️' },
    { value: 'regional_academic', label: 'Regional', icon: '🏫' },
    { value: 'regional_vocational', label: 'Vocational', icon: '🛠️' },
    { value: 'county_agricultural', label: 'Agricultural', icon: '🌾' },  
    { value: 'charter', label: 'Charter', icon: '📜' }
  ];
  const [selectedTypes, setSelectedTypes] = useState(districtTypeOptions.map(opt => opt.value));

  const DISTRICT_TYPE_ORDER = {
  municipal: 0,
  regional_academic: 1,
  regional_vocational: 2,
  county_agricultural: 3,
  charter: 4,
};

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
  const filteredDistricts = districts
    .filter(d => selectedTypes.includes(d.district_type))
    .slice()
    .sort((a, b) => {
      const typeA = DISTRICT_TYPE_ORDER[a.district_type] ?? 99;
      const typeB = DISTRICT_TYPE_ORDER[b.district_type] ?? 99;
      if (typeA !== typeB) return typeA - typeB;
      return a.name.localeCompare(b.name);
    });

  // Get total count for each type
  const typeCounts = districtTypeOptions.reduce((acc, opt) => {
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
    const townKey = townName.trim().toLowerCase();
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
        let districtsList = api._districtsByTownCache[townKey];
        if (!districtsList) {
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

  const handleSaveDistrict = async (updatedData) => {
    try {
      const updatedDistrict = await api.updateDistrict(editingDistrict.id, updatedData);

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

  return (
    <div className="district-browser">
      <header className="browser-header">
        <h1>Massachusetts School Districts</h1>
      </header>

      <div className="search-section">
        <form onSubmit={handleSearch} className="search-form">
          <div className="search-controls">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="filter-select"
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
          <div className="district-type-filters">
            {districtTypeOptions.map(opt => (
              <button
                key={opt.value}
                type="button"
                className={`district-type-toggle${selectedTypes.includes(opt.value) ? ' active' : ''}`}
                onClick={() => handleTypeChange(opt.value)}
                aria-pressed={selectedTypes.includes(opt.value)}
              >
                <span className="district-type-icon" style={{marginRight: '6px'}}>{opt.icon}</span>
                <span className="district-type-label">{opt.label}</span> <span className="district-type-count">{typeCounts[opt.value] ?? 0}</span>
              </button>
            ))}
          </div>

          {loading ? (
            <div className="loading">Loading districts...</div>
          ) : filteredDistricts.length === 0 ? (
            <div className="no-results">
              No districts found. {searchQuery && 'Try a different search term.'}
            </div>
          ) : (
            <ul className="district-items">
              {filteredDistricts.map((district) => {
                const typeOpt = districtTypeOptions.find(opt => opt.value === district.district_type);
                return (
                  <li
                    key={district.id}
                    className={`district-item ${
                      selectedDistrict?.id === district.id ? 'active' : ''
                    }`}
                    onClick={() => handleDistrictClick(district)}
                  >
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
          <ChoroplethMap
            selectedDistrict={selectedDistrict}
            clickedTown={clickedTown}
            onTownClick={handleTownClick}
            districtTypeOptions={districtTypeOptions}
          />
        </div>
      </div>

      <DistrictEditor
        district={editingDistrict}
        onClose={() => setEditingDistrict(null)}
        onSave={handleSaveDistrict}
      />
    </div>
  );
}

export default DistrictBrowser;
