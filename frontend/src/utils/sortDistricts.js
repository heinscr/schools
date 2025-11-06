/**
 * Utility functions for sorting districts
 */

import { DISTRICT_TYPE_ORDER } from '../constants/districtTypes';

/**
 * Sort districts by type order (Regional, Local, Vocational) then by name alphabetically
 * @param {Array} districts - Array of district objects
 * @returns {Array} - Sorted array of districts
 */
export function sortDistrictsByTypeAndName(districts) {
  if (!Array.isArray(districts)) {
    return [];
  }

  return [...districts].sort((a, b) => {
    const typeA = DISTRICT_TYPE_ORDER[a.district_type] ?? 99;
    const typeB = DISTRICT_TYPE_ORDER[b.district_type] ?? 99;

    if (typeA !== typeB) {
      return typeA - typeB;
    }

    return a.name.localeCompare(b.name);
  });
}

/**
 * Sort district info objects (with name and type properties)
 * @param {Array} districtInfos - Array of objects with {name, type} properties
 * @returns {Array} - Sorted array
 */
export function sortDistrictInfosByType(districtInfos) {
  if (!Array.isArray(districtInfos)) {
    return [];
  }

  return [...districtInfos].sort((a, b) => {
    const typeA = DISTRICT_TYPE_ORDER[a.type] ?? 99;
    const typeB = DISTRICT_TYPE_ORDER[b.type] ?? 99;

    if (typeA !== typeB) {
      return typeA - typeB;
    }

    return a.name.localeCompare(b.name);
  });
}