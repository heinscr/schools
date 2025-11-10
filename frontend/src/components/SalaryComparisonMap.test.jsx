import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import SalaryComparisonMap from './SalaryComparisonMap'
import { DataCacheContext } from '../contexts/DataCacheContext'

const originalFetch = global.fetch

const mockGeojson = { type: 'FeatureCollection', features: [] }

// Mock the cache context
const mockCacheContext = {
  status: 'ready',
  error: null,
  lastFetched: Date.now(),
  districtCount: 0,
  townCount: 0,
  getDistrictById: vi.fn(),
  getDistrictUrl: vi.fn(),
  getDistrictsByTown: vi.fn(),
  getAllDistricts: vi.fn(() => []),
  searchDistrictsByName: vi.fn(() => []),
  getAllTowns: vi.fn(() => []),
  getMunicipalitiesGeojson: vi.fn(() => mockGeojson),
  loadAllDistricts: vi.fn(),
  loadMunicipalitiesGeojson: vi.fn(async () => mockGeojson),
  invalidateCache: vi.fn(),
  updateDistrictInCache: vi.fn(),
  addDistrictToCache: vi.fn(),
  removeDistrictFromCache: vi.fn(),
}

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get() { return 800 } })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get() { return 600 } })
})

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => mockGeojson })
  mockCacheContext.getMunicipalitiesGeojson.mockReturnValue(mockGeojson)
})

afterEach(() => {
  global.fetch = originalFetch
  vi.clearAllMocks()
})

it('shows legend when results exist and fetches geojson', async () => {
  render(
    <DataCacheContext.Provider value={mockCacheContext}>
      <div style={{width: '800px', height: '400px'}}>
        <SalaryComparisonMap results={[{ district_id: 'd1', district_name: 'Alpha', towns: ['Town1'], salary: 1 }]} />
      </div>
    </DataCacheContext.Provider>
  )
  await waitFor(() => expect(mockCacheContext.getMunicipalitiesGeojson).toHaveBeenCalled())
  expect(screen.getByText('Salary Ranking')).toBeInTheDocument()
})
