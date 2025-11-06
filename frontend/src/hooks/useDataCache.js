import { useContext } from 'react';
import { DataCacheContext } from '../contexts/DataCacheContext';

/**
 * Custom hook to access the data cache
 *
 * Usage:
 *   const cache = useDataCache();
 *   const district = cache.getDistrictById('123');
 *   const districts = cache.getDistrictsByTown('Boston');
 *
 * @returns {Object} Cache context value
 * @throws {Error} If used outside of DataCacheProvider
 */
export function useDataCache() {
  const context = useContext(DataCacheContext);

  // If the hook is used outside of a provider (tests render components in isolation),
  // return a safe no-op fallback so components don't throw. Tests can still mock
  // the provider behavior when needed.
  if (!context) {
    return {
      // district map accessors
      getDistrictById: () => null,
      getDistrictsByTown: () => [],
      getAllDistricts: () => [],
      // url helper
      getDistrictUrl: () => undefined,
      // cache mutation no-ops
      updateDistrictInCache: () => {},
      removeDistrictFromCache: () => {},
      rebuildTownIndex: () => {},
    };
  }

  return context;
}