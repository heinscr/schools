// API service for interacting with the backend
// Note: Vite only exposes env vars prefixed with VITE_. Use those exclusively.
// Both district and salary endpoints now use the same API Gateway
import { logger } from '../utils/logger';
import authService from './auth';

const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_DISTRICT_API_URL ||
  import.meta.env.VITE_SALARY_API_URL ||
  'http://localhost:8000';

class ApiService {
  constructor() {
    // Simple in-memory cache for town -> districts responses (keyed by lowercase town)
    // Per-fetch-function town cache to avoid cross-test leakage when tests replace global.fetch
    // Keyed by the fetch function instance (WeakMap) -> Map(townKey -> responseJson)
    this._townCacheByFetch = new WeakMap();
  }
  /**
   * Get authentication headers for API requests
   */
  _getAuthHeaders() {
    const token = authService.getToken();
    if (token) {
      return {
        'Authorization': `Bearer ${token}`,
      };
    }
    return {};
  }

  /**
   * Fetch all districts with optional filters
   * @param {Object} params - Query parameters (name, town, limit, offset)
   * @returns {Promise<Object>} - Response with districts data
   */

  async getDistricts(params = {}) {
    const queryParams = new URLSearchParams();

    if (params.name) queryParams.append('name', params.name);
    if (params.town) queryParams.append('town', params.town);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.offset) queryParams.append('offset', params.offset);

    const url = `${API_BASE_URL}/api/districts${queryParams.toString() ? '?' + queryParams.toString() : ''}`;
    // Determine the fetch function used (so tests that replace global.fetch get isolated caches)
    const fetchFn = (typeof global !== 'undefined' && global.fetch)
      ? global.fetch
      : (typeof globalThis !== 'undefined' && globalThis.fetch)
        ? globalThis.fetch
        : fetch;

    // If this is a town lookup, check the per-fetch cache first (case-insensitive)
    if (params.town) {
      const townKey = String(params.town).toLowerCase();
      const existingMap = this._townCacheByFetch.get(fetchFn);
      if (existingMap && existingMap.has(townKey)) {
        return existingMap.get(townKey);
      }
    }

    const _fetch = (typeof global !== 'undefined' && global.fetch)
      ? global.fetch
      : (typeof globalThis !== 'undefined' && globalThis.fetch)
        ? globalThis.fetch
        : fetch;
    
  const response = await _fetch(url);
    
    // Defensive: some test mocks may return undefined or null; handle that gracefully
    if (!response || !response.ok) {
      const statusText = response ? response.statusText : 'no response';
      throw new Error(`Failed to fetch districts: ${statusText}`);
    }
    const json = await response.json();
    // Store in per-fetch town cache if applicable
    if (params.town) {
      const townKey = String(params.town).toLowerCase();
      const existingMap = this._townCacheByFetch.get(_fetch) || new Map();
      existingMap.set(townKey, json);
      this._townCacheByFetch.set(_fetch, existingMap);
    }
    return json;
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

    const _fetch = (typeof global !== 'undefined' && global.fetch)
      ? global.fetch
      : (typeof globalThis !== 'undefined' && globalThis.fetch)
        ? globalThis.fetch
        : fetch;
    const response = await _fetch(url);
    if (!response || !response.ok) {
      const statusText = response ? response.statusText : 'no response';
      throw new Error(`Failed to search districts: ${statusText}`);
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

    const _fetch = (typeof global !== 'undefined' && global.fetch)
      ? global.fetch
      : (typeof globalThis !== 'undefined' && globalThis.fetch)
        ? globalThis.fetch
        : fetch;
    const response = await _fetch(url);
    if (!response || !response.ok) {
      if (response && response.status === 404) {
        throw new Error('District not found');
      }
      const statusText = response ? response.statusText : 'no response';
      throw new Error(`Failed to fetch district: ${statusText}`);
    }
    const json = await response.json();
    return json;
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
        ...this._getAuthHeaders(),
      },
      body: JSON.stringify(districtData),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Failed to create district: ${response.statusText}`);
    }

    const json = await response.json();
    // Clear all per-fetch town caches on update so subsequent town lookups go to network
    this._townCacheByFetch = new WeakMap();
    return json;
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
        ...this._getAuthHeaders(),
      },
      body: JSON.stringify(districtData),
    });


    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('District not found');
      }
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to update district: ${response.statusText}`);
    }

    const json = await response.json();
    // Clear all per-fetch town caches on update so subsequent town lookups go to network
    this._townCacheByFetch = new WeakMap();
    
    return json;
  }

  /**
   * Get salary schedules for a district
   * @param {string} districtId - District ID
   * @param {string} year - Optional school year (e.g., "2021-2022")
   * @returns {Promise<Array>} - Array of salary schedules
   */
  async getSalarySchedules(districtId, year = null) {
    const yearPath = year ? `/${year}` : '';
    const url = `${API_BASE_URL}/api/salary-schedule/${districtId}${yearPath}`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        if (response.status === 404) {
          return []; // No salary data available
        }
        if (response.status === 503) {
          logger.warn('Salary schedule service is temporarily unavailable');
          return []; // Service unavailable, return empty array
        }
        throw new Error(`Failed to fetch salary schedule: ${response.statusText}`);
      }

      return response.json();
    } catch (error) {
      // Handle network errors or other fetch failures
      if (error.message.includes('Failed to fetch')) {
        logger.warn('Unable to connect to salary schedule service');
        return []; // Return empty array instead of throwing
      }
      throw error;
    }
  }

  /**
   * Get global salary metadata (max_step and edu_credit_combos)
   */
  async getGlobalSalaryMetadata() {
    const url = `${API_BASE_URL}/api/salary-metadata`;
    const _fetch = (typeof global !== 'undefined' && global.fetch)
      ? global.fetch
      : (typeof globalThis !== 'undefined' && globalThis.fetch)
        ? globalThis.fetch
        : fetch;

    const response = await _fetch(url);
    if (!response || !response.ok) {
      throw new Error(`Failed to fetch salary metadata: ${response ? response.statusText : 'no response'}`);
    }
    return response.json();
  }

  /**
   * Compare salaries across districts for specific credentials
   * @param {string} education - Education level (B, M, D)
   * @param {number} credits - Additional credits (0, 15, 30, 45, 60)
   * @param {number} step - Experience step (1-15)
   * @param {Object} options - Additional options (districtType, year, limit, includeFallback)
   * @returns {Promise<Object>} - Response with ranked salary results
   */
  async compareSalaries(education, credits, step, options = {}) {
    const queryParams = new URLSearchParams();
    queryParams.append('education', education);
    queryParams.append('credits', credits.toString());
    queryParams.append('step', step.toString());

    if (options.districtType) queryParams.append('districtType', options.districtType);
    if (options.year) queryParams.append('year', options.year);
    if (options.limit) queryParams.append('limit', options.limit.toString());
    if (options.includeFallback) queryParams.append('include_fallback', 'true');

    const url = `${API_BASE_URL}/api/salary-compare?${queryParams.toString()}`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        if (response.status === 404) {
          return { query: { education, credits, step }, results: [], total: 0 };
        }
        if (response.status === 503) {
          logger.warn('Salary comparison service is temporarily unavailable');
          return { query: { education, credits, step }, results: [], total: 0 };
        }
        throw new Error(`Failed to compare salaries: ${response.statusText}`);
      }

      return response.json();
    } catch (error) {
      if (error.message.includes('Failed to fetch')) {
        logger.warn('Unable to connect to salary comparison service');
        return { query: { education, credits, step }, results: [], total: 0 };
      }
      throw error;
    }
  }

  /**
   * Admin: Upload PDF salary schedule for a district
   * @param {string} districtId - District ID
   * @param {File} pdfFile - PDF file to upload
   * @returns {Promise<Object>} - Job status with job_id
   */
  async uploadSalarySchedule(districtId, pdfFile) {
    const url = `${API_BASE_URL}/api/admin/districts/${districtId}/salary-schedule/upload`;

    const formData = new FormData();
    formData.append('file', pdfFile);

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...this._getAuthHeaders(),
      },
      body: formData,
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to upload salary schedule: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Get job status and preview data
   * @param {string} districtId - District ID
   * @param {string} jobId - Job ID
   * @returns {Promise<Object>} - Job status with optional preview data
   */
  async getSalaryJob(districtId, jobId) {
    const url = `${API_BASE_URL}/api/admin/districts/${districtId}/salary-schedule/jobs/${jobId}`;

    const response = await fetch(url, {
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to get job status: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Apply extracted salary data to district
   * @param {string} districtId - District ID
   * @param {string} jobId - Job ID
   * @param {Object} exclusions - Optional exclusions {excluded_steps: [], excluded_columns: []}
   * @returns {Promise<Object>} - Application result with metadata change info
   */
  async applySalaryData(districtId, jobId, exclusions = null) {
    const url = `${API_BASE_URL}/api/admin/districts/${districtId}/salary-schedule/apply/${jobId}`;

    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        ...this._getAuthHeaders(),
        ...(exclusions ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(exclusions ? { body: JSON.stringify(exclusions) } : {}),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to apply salary data: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Apply manual salary records directly (no job/exclusions)
   * @param {string} districtId - District ID
   * @param {Array<Object>} records - Array of records: {school_year, period, education, credits, step, salary}
   * @returns {Promise<Object>} - Application result with metadata change info
   */
  async manualApplySalaryRecords(districtId, records) {
    const url = `${API_BASE_URL}/api/admin/districts/${districtId}/salary-schedule/manual-apply`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this._getAuthHeaders(),
      },
      body: JSON.stringify({ records }),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to apply manual salary records: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Delete a salary processing job
   * @param {string} districtId - District ID
   * @param {string} jobId - Job ID
   * @returns {Promise<Object>} - Delete result
   */
  async deleteSalaryJob(districtId, jobId) {
    const url = `${API_BASE_URL}/api/admin/districts/${districtId}/salary-schedule/jobs/${jobId}`;

    const response = await fetch(url, {
      method: 'DELETE',
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to delete job: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Get normalization status
   * @returns {Promise<Object>} - Normalization status
   */
  async getNormalizationStatus() {
    // Use string concatenation to prevent bundler from transforming 'global' to 'globalThis'
    const url = `${API_BASE_URL}/api/admin/${'glo' + 'bal'}/normalization/status`;

    const response = await fetch(url, {
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to get normalization status: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Start global normalization job
   * @returns {Promise<Object>} - Job start result
   */
  async startNormalization() {
    // Use string concatenation to prevent bundler from transforming 'global' to 'globalThis'
    const url = `${API_BASE_URL}/api/admin/${'glo' + 'bal'}/normalize`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to start normalization: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: List all backup files
   * @returns {Promise<Object>} - List of backup files
   */
  async listBackups() {
    const url = `${API_BASE_URL}/api/admin/backup/list`;

    const response = await fetch(url, {
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to list backups: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Re-apply salary data from backup files
   * @param {Array<string>} filenames - Array of backup filenames to re-apply
   * @returns {Promise<Object>} - Re-apply results
   */
  async reapplyBackups(filenames) {
    const url = `${API_BASE_URL}/api/admin/backup/reapply`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this._getAuthHeaders(),
      },
      body: JSON.stringify(filenames),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to re-apply backups: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Start backup reapply job
   * @param {Array<string>} filenames - Array of backup filenames to re-apply
   * @returns {Promise<Object>} - Job start result with job_id
   */
  async startBackupReapplyJob(filenames) {
    const url = `${API_BASE_URL}/api/admin/backup/reapply/start`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this._getAuthHeaders(),
      },
      body: JSON.stringify(filenames),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to start backup reapply job: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Admin: Get backup reapply job status
   * @returns {Promise<Object>} - Job status
   */
  async getBackupReapplyStatus(jobId = null) {
    const url = jobId
      ? `${API_BASE_URL}/api/admin/backup/reapply/status?job_id=${jobId}`
      : `${API_BASE_URL}/api/admin/backup/reapply/status`;

    const response = await fetch(url, {
      headers: {
        ...this._getAuthHeaders(),
      },
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required. Please log in as an administrator.');
      }
      const errorText = await response.text();
      throw new Error(errorText || `Failed to get backup reapply status: ${response.statusText}`);
    }

    return response.json();
  }
}

export default new ApiService();