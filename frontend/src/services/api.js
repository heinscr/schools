// API service for interacting with the backend
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiService {
  /**
   * Fetch all districts with optional filters
   * @param {Object} params - Query parameters (name, town, limit, offset)
   * @returns {Promise<Object>} - Response with districts data
   */
  // Simple in-memory cache for town-based queries
  _districtsByTownCache = {};

  async getDistricts(params = {}) {
    const queryParams = new URLSearchParams();

    if (params.name) queryParams.append('name', params.name);
    if (params.town) queryParams.append('town', params.town);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.offset) queryParams.append('offset', params.offset);

    // Cache only for town queries (no limit/offset)
    if (params.town && !params.name && !params.limit && !params.offset) {
      const townKey = params.town.trim().toLowerCase();
      if (this._districtsByTownCache[townKey]) {
        return { data: this._districtsByTownCache[townKey] };
      }
      const url = `${API_BASE_URL}/api/districts?town=${encodeURIComponent(params.town)}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch districts: ${response.statusText}`);
      }
      const result = await response.json();
      this._districtsByTownCache[townKey] = result.data;
      return result;
    }

    // Default: no caching
    const url = `${API_BASE_URL}/api/districts${queryParams.toString() ? '?' + queryParams.toString() : ''}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch districts: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * Search districts by name or town
   * @param {string} query - Search query
   * @param {Object} params - Additional query parameters (limit, offset)
   * @returns {Promise<Object>} - Response with districts data
   */
  async searchDistricts(query, params = {}) {
    const queryParams = new URLSearchParams();

    if (query) queryParams.append('q', query);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.offset) queryParams.append('offset', params.offset);

    const url = `${API_BASE_URL}/api/districts/search${queryParams.toString() ? '?' + queryParams.toString() : ''}`;

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to search districts: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get a specific district by ID
   * @param {string} districtId - District ID
   * @returns {Promise<Object>} - District data
   */
  async getDistrict(districtId) {
    const url = `${API_BASE_URL}/api/districts/${districtId}`;

    const response = await fetch(url);
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('District not found');
      }
      throw new Error(`Failed to fetch district: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Create a new district
   * @param {Object} districtData - District data
   * @returns {Promise<Object>} - Created district
   */
  async createDistrict(districtData) {
    const url = `${API_BASE_URL}/api/districts`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(districtData),
    });

    if (!response.ok) {
      throw new Error(`Failed to create district: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Update an existing district
   * @param {string} districtId - District ID
   * @param {Object} districtData - Updated district data
   * @returns {Promise<Object>} - Updated district
   */
  async updateDistrict(districtId, districtData) {
    const url = `${API_BASE_URL}/api/districts/${districtId}`;

    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(districtData),
    });

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('District not found');
      }
      throw new Error(`Failed to update district: ${response.statusText}`);
    }

    // Clear cache after update
    this._districtsByTownCache = {};

    return response.json();
  }
}

export default new ApiService();
