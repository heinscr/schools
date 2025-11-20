/**
 * Tests for district sorting utilities
 */
import { sortDistrictsByTypeAndName, sortDistrictInfosByType } from './sortDistricts';

describe('sortDistrictsByTypeAndName', () => {
  it('sorts districts by type order', () => {
    const districts = [
      { name: 'Charter School', district_type: 'charter' },
      { name: 'Municipal District', district_type: 'municipal' },
      { name: 'Regional School', district_type: 'regional_academic' }
    ];

    const sorted = sortDistrictsByTypeAndName(districts);

    expect(sorted[0].district_type).toBe('municipal'); // order 0
    expect(sorted[1].district_type).toBe('regional_academic'); // order 1
    expect(sorted[2].district_type).toBe('charter'); // order 4
  });

  it('sorts alphabetically within same type', () => {
    const districts = [
      { name: 'Zebra Town', district_type: 'municipal' },
      { name: 'Apple Town', district_type: 'municipal' },
      { name: 'Maple Town', district_type: 'municipal' }
    ];

    const sorted = sortDistrictsByTypeAndName(districts);

    expect(sorted[0].name).toBe('Apple Town');
    expect(sorted[1].name).toBe('Maple Town');
    expect(sorted[2].name).toBe('Zebra Town');
  });

  it('handles mixed types and names', () => {
    const districts = [
      { name: 'Zebra Regional', district_type: 'regional_academic' },
      { name: 'Apple Municipal', district_type: 'municipal' },
      { name: 'Banana Municipal', district_type: 'municipal' },
      { name: 'Alpha Regional', district_type: 'regional_academic' }
    ];

    const sorted = sortDistrictsByTypeAndName(districts);

    expect(sorted[0].name).toBe('Apple Municipal');
    expect(sorted[1].name).toBe('Banana Municipal');
    expect(sorted[2].name).toBe('Alpha Regional');
    expect(sorted[3].name).toBe('Zebra Regional');
  });

  it('handles unknown district types', () => {
    const districts = [
      { name: 'Known Type', district_type: 'municipal' },
      { name: 'Unknown Type A', district_type: 'unknown_type' },
      { name: 'Unknown Type B', district_type: 'another_unknown' }
    ];

    const sorted = sortDistrictsByTypeAndName(districts);

    // Known types should come before unknown types (order 99)
    expect(sorted[0].name).toBe('Known Type');
    // Unknown types should be sorted alphabetically (both have same order 99)
    expect(sorted[1].name).toBe('Unknown Type A');
    expect(sorted[2].name).toBe('Unknown Type B');
  });

  it('handles empty array', () => {
    const sorted = sortDistrictsByTypeAndName([]);
    expect(sorted).toEqual([]);
  });

  it('handles non-array input', () => {
    expect(sortDistrictsByTypeAndName(null)).toEqual([]);
    expect(sortDistrictsByTypeAndName(undefined)).toEqual([]);
    expect(sortDistrictsByTypeAndName('not an array')).toEqual([]);
  });

  it('does not mutate original array', () => {
    const districts = [
      { name: 'B', district_type: 'municipal' },
      { name: 'A', district_type: 'municipal' }
    ];
    const original = [...districts];

    const sorted = sortDistrictsByTypeAndName(districts);

    expect(districts).toEqual(original);
    expect(sorted).not.toBe(districts);
  });

  it('handles all district types correctly', () => {
    const districts = [
      { name: 'Charter', district_type: 'charter' },
      { name: 'Vocational', district_type: 'regional_vocational' },
      { name: 'Municipal', district_type: 'municipal' },
      { name: 'Agricultural', district_type: 'county_agricultural' },
      { name: 'Regional', district_type: 'regional_academic' }
    ];

    const sorted = sortDistrictsByTypeAndName(districts);

    expect(sorted[0].name).toBe('Municipal'); // order 0
    expect(sorted[1].name).toBe('Regional'); // order 1
    expect(sorted[2].name).toBe('Vocational'); // order 2
    expect(sorted[3].name).toBe('Agricultural'); // order 3
    expect(sorted[4].name).toBe('Charter'); // order 4
  });
});

describe('sortDistrictInfosByType', () => {
  it('sorts district infos by type order', () => {
    const infos = [
      { name: 'Charter School', type: 'charter' },
      { name: 'Municipal District', type: 'municipal' },
      { name: 'Regional School', type: 'regional_academic' }
    ];

    const sorted = sortDistrictInfosByType(infos);

    expect(sorted[0].type).toBe('municipal');
    expect(sorted[1].type).toBe('regional_academic');
    expect(sorted[2].type).toBe('charter');
  });

  it('sorts alphabetically within same type', () => {
    const infos = [
      { name: 'Zebra', type: 'municipal' },
      { name: 'Apple', type: 'municipal' },
      { name: 'Maple', type: 'municipal' }
    ];

    const sorted = sortDistrictInfosByType(infos);

    expect(sorted[0].name).toBe('Apple');
    expect(sorted[1].name).toBe('Maple');
    expect(sorted[2].name).toBe('Zebra');
  });

  it('handles empty array', () => {
    const sorted = sortDistrictInfosByType([]);
    expect(sorted).toEqual([]);
  });

  it('handles non-array input', () => {
    expect(sortDistrictInfosByType(null)).toEqual([]);
    expect(sortDistrictInfosByType(undefined)).toEqual([]);
  });

  it('does not mutate original array', () => {
    const infos = [
      { name: 'B', type: 'municipal' },
      { name: 'A', type: 'municipal' }
    ];
    const original = [...infos];

    const sorted = sortDistrictInfosByType(infos);

    expect(infos).toEqual(original);
    expect(sorted).not.toBe(infos);
  });

  it('handles unknown types', () => {
    const infos = [
      { name: 'Known', type: 'municipal' },
      { name: 'Unknown', type: 'unknown_type' }
    ];

    const sorted = sortDistrictInfosByType(infos);

    expect(sorted[0].name).toBe('Known');
    expect(sorted[1].name).toBe('Unknown');
  });
});
