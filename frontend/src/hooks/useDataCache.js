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

  if (!context) {
    throw new Error('useDataCache must be used within a DataCacheProvider');
  }

  return context;
}