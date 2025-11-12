import { createContext, useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import api from '../services/api';
import { logger } from '../utils/logger';

/**
 * DataCacheContext - Provides app-wide caching for district data and geojson
 *
 * Cache Structure:
 * {
 *   districts: Map<districtId, DistrictMetadata>,
 *   townToDistricts: Map<normalizedTownName, {original: string, districtIds: number[]}>,
 *   municipalitiesGeojson: GeoJSON object,
 *   lastFetched: timestamp,
 *   status: 'idle' | 'loading' | 'ready' | 'error'
 * }
 */

export const DataCacheContext = createContext(null);

export function DataCacheProvider({ children, autoLoad = true }) {
  // Cache state
  const [districts, setDistricts] = useState(new Map());
  const [townToDistricts, setTownToDistricts] = useState(new Map());
  const [municipalitiesGeojson, setMunicipalitiesGeojson] = useState(null);
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
            townMap.set(normalizedTown, {
              original: town.trim(),
              districtIds: []
            });
          }
          townMap.get(normalizedTown).districtIds.push(district.id);
        });
      }
    });

    return townMap;
  }, []);

  /**
   * Load municipalities geojson data
   */
  const loadMunicipalitiesGeojson = useCallback(async () => {
    try {
      logger.info('Loading municipalities geojson...');
      const response = await fetch('/ma_municipalities.geojson');

      if (!response.ok) {
        throw new Error(`Failed to fetch geojson: ${response.status} ${response.statusText}`);
      }

      const geojsonData = await response.json();

      if (!geojsonData || !geojsonData.features) {
        throw new Error('Invalid geojson data: missing features');
      }

      setMunicipalitiesGeojson(geojsonData);
      logger.info(`Municipalities geojson loaded: ${geojsonData.features.length} features`);

      return geojsonData;
    } catch (err) {
      logger.error('Failed to load municipalities geojson:', err);
      throw err;
    }
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

      // Load geojson and districts in parallel
      const geojsonPromise = municipalitiesGeojson ? Promise.resolve(municipalitiesGeojson) : loadMunicipalitiesGeojson();

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

      // Wait for geojson to complete
      await geojsonPromise;

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
  }, [status, buildTownMap, municipalitiesGeojson, loadMunicipalitiesGeojson]);

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
    const townData = townToDistricts.get(normalizedTown);
    if (!townData) return [];
    return townData.districtIds.map(id => districts.get(id)).filter(Boolean);
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
    return Array.from(townToDistricts.values())
      .map(townData => townData.original)
      .sort();
  }, [townToDistricts]);

  /**
   * Get municipalities geojson
   */
  const getMunicipalitiesGeojson = useCallback(() => {
    return municipalitiesGeojson;
  }, [municipalitiesGeojson]);

  /**
   * Invalidate cache (force reload on next access)
   */
  const invalidateCache = useCallback(() => {
    logger.info('Invalidating cache...');
    setDistricts(new Map());
    setTownToDistricts(new Map());
    setMunicipalitiesGeojson(null);
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
      // Rebuild town map from the updated districts map
      setTownToDistricts(buildTownMap(Array.from(newMap.values())));
      return newMap;
    });

    logger.info(`Updated district ${updatedDistrict.id} in cache`);
  }, [buildTownMap]);

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
      // Rebuild town map from remaining districts
      setTownToDistricts(buildTownMap(Array.from(newMap.values())));
      return newMap;
    });

    logger.info(`Removed district ${districtId} from cache`);
  }, [buildTownMap]);

  /**
   * Load geojson immediately on mount
   */
  useEffect(() => {
    if (!municipalitiesGeojson) {
      loadMunicipalitiesGeojson().catch(err => {
        logger.error('Failed to preload geojson:', err);
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Auto-load districts on mount if enabled
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
    getMunicipalitiesGeojson,

    // Cache management methods
    loadAllDistricts,
    loadMunicipalitiesGeojson,
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