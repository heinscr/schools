import { createContext, useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import api from '../services/api';
import { logger } from '../utils/logger';

/**
 * DataCacheContext - Provides app-wide caching for district data
 *
 * Cache Structure:
 * {
 *   districts: Map<districtId, DistrictMetadata>,
 *   townToDistricts: Map<townName, districtId[]>,
 *   lastFetched: timestamp,
 *   status: 'idle' | 'loading' | 'ready' | 'error'
 * }
 */

export const DataCacheContext = createContext(null);

export function DataCacheProvider({ children, autoLoad = true }) {
  // Cache state
  const [districts, setDistricts] = useState(new Map());
  const [townToDistricts, setTownToDistricts] = useState(new Map());
  const [lastFetched, setLastFetched] = useState(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);

  /**
   * Build the town-to-districts map from district data
   */
  const buildTownMap = useCallback((districtsArray) => {
    const townMap = new Map();

    districtsArray.forEach(district => {
      if (district.towns && Array.isArray(district.towns)) {
        district.towns.forEach(town => {
          const normalizedTown = town.trim().toLowerCase();
          if (!townMap.has(normalizedTown)) {
            townMap.set(normalizedTown, []);
          }
          townMap.get(normalizedTown).push(district.id);
        });
      }
    });

    return townMap;
  }, []);

  /**
   * Load all districts from the API and populate cache
   */
  const loadAllDistricts = useCallback(async (force = false) => {
    // Skip if already loaded and not forcing
    if (status === 'ready' && !force) {
      logger.info('Cache already loaded, skipping fetch');
      return;
    }

    // Skip if currently loading
    if (status === 'loading') {
      logger.info('Cache load already in progress');
      return;
    }

    try {
      setStatus('loading');
      setError(null);

      logger.info('Loading all districts into cache...');

      
      const BATCH_SIZE = 100;
      let allDistricts = [];
      let offset = 0;
      let hasMore = true;

      while (hasMore) {
        const response = await api.searchDistricts('', {
          limit: BATCH_SIZE,
          offset
        });

        if (!response || !response.data) {
          throw new Error('Invalid response from API');
        }

        const batch = response.data;
        allDistricts = allDistricts.concat(batch);

        // If we got fewer results than requested, we've reached the end
        hasMore = batch.length === BATCH_SIZE;
        offset += BATCH_SIZE;

        logger.info(`Fetched ${batch.length} districts (total: ${allDistricts.length})`);
      }

      const districtsArray = allDistricts;

      // Build district map: districtId -> metadata
      const districtMap = new Map();
      districtsArray.forEach(district => {
        districtMap.set(district.id, district);
      });

      // Build town map: townName -> [districtId1, districtId2, ...]
      const townMap = buildTownMap(districtsArray);

      setDistricts(districtMap);
      setTownToDistricts(townMap);
      setLastFetched(Date.now());
      setStatus('ready');

      logger.info(`Cache loaded: ${districtMap.size} districts, ${townMap.size} towns`);
    } catch (err) {
      logger.error('Failed to load cache:', err);
      setError(err.message);
      setStatus('error');
    }
  }, [status, buildTownMap]);

  /**
   * Get a district by ID
   */
  const getDistrictById = useCallback((districtId) => {
    return districts.get(districtId) || null;
  }, [districts]);

  /**
   * Get the district_url for a given district id (or null if not available)
   */
  const getDistrictUrl = useCallback((districtId) => {
    const d = districts.get(districtId);
    if (!d) return null;
    // Support different possible field names used by API
    return d.district_url || d.url || d.website || null;
  }, [districts]);

  /**
   * Get all districts for a given town
   */
  const getDistrictsByTown = useCallback((townName) => {
    const normalizedTown = townName.trim().toLowerCase();
    const districtIds = townToDistricts.get(normalizedTown) || [];
    return districtIds.map(id => districts.get(id)).filter(Boolean);
  }, [districts, townToDistricts]);

  /**
   * Get all districts as an array
   */
  const getAllDistricts = useCallback(() => {
    return Array.from(districts.values());
  }, [districts]);

  /**
   * Search districts by name (case-insensitive partial match)
   */
  const searchDistrictsByName = useCallback((query) => {
    if (!query || !query.trim()) {
      return getAllDistricts();
    }

    const normalizedQuery = query.trim().toLowerCase();
    return getAllDistricts().filter(district =>
      district.name.toLowerCase().includes(normalizedQuery)
    );
  }, [getAllDistricts]);

  /**
   * Get all unique town names
   */
  const getAllTowns = useCallback(() => {
    return Array.from(townToDistricts.keys()).sort();
  }, [townToDistricts]);

  /**
   * Invalidate cache (force reload on next access)
   */
  const invalidateCache = useCallback(() => {
    logger.info('Invalidating cache...');
    setDistricts(new Map());
    setTownToDistricts(new Map());
    setLastFetched(null);
    setStatus('idle');
    setError(null);
  }, []);

  /**
   * Update a single district in the cache
   */
  const updateDistrictInCache = useCallback((updatedDistrict) => {
    setDistricts(prev => {
      const newMap = new Map(prev);
      newMap.set(updatedDistrict.id, updatedDistrict);
      return newMap;
    });

    // Rebuild town map with all districts
    setTownToDistricts(prev => {
      const allDistricts = Array.from(districts.values());
      const districtIndex = allDistricts.findIndex(d => d.id === updatedDistrict.id);
      if (districtIndex >= 0) {
        allDistricts[districtIndex] = updatedDistrict;
      } else {
        allDistricts.push(updatedDistrict);
      }
      return buildTownMap(allDistricts);
    });

    logger.info(`Updated district ${updatedDistrict.id} in cache`);
  }, [districts, buildTownMap]);

  /**
   * Add a new district to the cache
   */
  const addDistrictToCache = useCallback((newDistrict) => {
    updateDistrictInCache(newDistrict);
    logger.info(`Added district ${newDistrict.id} to cache`);
  }, [updateDistrictInCache]);

  /**
   * Remove a district from the cache
   */
  const removeDistrictFromCache = useCallback((districtId) => {
    setDistricts(prev => {
      const newMap = new Map(prev);
      newMap.delete(districtId);
      return newMap;
    });

    // Rebuild town map
    setTownToDistricts(prev => {
      const allDistricts = Array.from(districts.values()).filter(d => d.id !== districtId);
      return buildTownMap(allDistricts);
    });

    logger.info(`Removed district ${districtId} from cache`);
  }, [districts, buildTownMap]);

  /**
   * Auto-load on mount if enabled
   */
  useEffect(() => {
    if (autoLoad && status === 'idle') {
      loadAllDistricts();
    }
  }, [autoLoad, status, loadAllDistricts]);

  // Context value
  const value = {
    // State
    status,
    error,
    lastFetched,
    districtCount: districts.size,
    townCount: townToDistricts.size,

    // Data access methods
    getDistrictById,
  getDistrictUrl,
    getDistrictsByTown,
    getAllDistricts,
    searchDistrictsByName,
    getAllTowns,

    // Cache management methods
    loadAllDistricts,
    invalidateCache,
    updateDistrictInCache,
    addDistrictToCache,
    removeDistrictFromCache,

    // Computed states
    isLoading: status === 'loading',
    isReady: status === 'ready',
    isError: status === 'error',
    isEmpty: districts.size === 0,
  };

  return (
    <DataCacheContext.Provider value={value}>
      {children}
    </DataCacheContext.Provider>
  );
}

DataCacheProvider.propTypes = {
  children: PropTypes.node.isRequired,
  autoLoad: PropTypes.bool,
};