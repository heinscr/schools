import { useState, useEffect } from 'react';
import api from '../services/api';
import './DistrictBrowser.css';

function DistrictBrowser() {
  const [districts, setDistricts] = useState([]);
  const [selectedDistrict, setSelectedDistrict] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all', 'name', 'town'

  useEffect(() => {
    loadDistricts();
  }, []);

  const loadDistricts = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.getDistricts({ limit: 100 });
      setDistricts(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      loadDistricts();
      return;
    }

    try {
      setLoading(true);
      setError(null);

      let response;
      if (filterType === 'all') {
        response = await api.searchDistricts(searchQuery, { limit: 100 });
      } else if (filterType === 'name') {
        response = await api.getDistricts({ name: searchQuery, limit: 100 });
      } else if (filterType === 'town') {
        response = await api.getDistricts({ town: searchQuery, limit: 100 });
      }

      setDistricts(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDistrictClick = async (district) => {
    try {
      setError(null);
      // Fetch full district details
      const fullDistrict = await api.getDistrict(district.id);
      setSelectedDistrict(fullDistrict);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    loadDistricts();
  };

  return (
    <div className="district-browser">
      <header className="browser-header">
        <h1>Massachusetts School Districts</h1>
        <p>Search and browse teacher contract information by school district</p>
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

          {loading ? (
            <div className="loading">Loading districts...</div>
          ) : districts.length === 0 ? (
            <div className="no-results">
              No districts found. {searchQuery && 'Try a different search term.'}
            </div>
          ) : (
            <ul className="district-items">
              {districts.map((district) => (
                <li
                  key={district.id}
                  onClick={() => handleDistrictClick(district)}
                  className={`district-item ${
                    selectedDistrict?.id === district.id ? 'active' : ''
                  }`}
                >
                  <div className="district-name">{district.name}</div>
                  <div className="district-towns">
                    {district.towns.join(', ')}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="district-detail">
          {selectedDistrict ? (
            <div className="detail-content">
              <h2>District Information</h2>
              <div className="json-display">
                <pre>{JSON.stringify(selectedDistrict, null, 2)}</pre>
              </div>
              <button
                onClick={() => setSelectedDistrict(null)}
                className="btn btn-secondary"
              >
                Close
              </button>
            </div>
          ) : (
            <div className="detail-placeholder">
              <p>Select a district to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default DistrictBrowser;
