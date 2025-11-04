/**
 * District type configuration
 * Centralized configuration for district types used across the application
 */

export const DISTRICT_TYPE_OPTIONS = [
  { value: 'municipal', label: 'Municipal', icon: '🏛️', order: 0 },
  { value: 'regional_academic', label: 'Regional', icon: '🏫', order: 1 },
  { value: 'regional_vocational', label: 'Vocational', icon: '🛠️', order: 2 },
  { value: 'county_agricultural', label: 'Agricultural', icon: '🌾', order: 3 },
  { value: 'charter', label: 'Charter', icon: '📜', order: 4 }
];

export const DISTRICT_TYPE_ORDER = Object.fromEntries(
  DISTRICT_TYPE_OPTIONS.map(opt => [opt.value, opt.order])
);
