import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { DataCacheContext } from '../contexts/DataCacheContext'

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
  getMunicipalitiesGeojson: vi.fn(() => null),
  loadAllDistricts: vi.fn(),
  loadMunicipalitiesGeojson: vi.fn(),
  invalidateCache: vi.fn(),
  updateDistrictInCache: vi.fn(),
  addDistrictToCache: vi.fn(),
  removeDistrictFromCache: vi.fn(),
}

vi.mock('./ChoroplethMap', () => ({ default: () => <div data-testid="map" /> }))
vi.mock('./DistrictEditor', () => ({ default: () => <div data-testid="editor" /> }))
vi.mock('./SalaryTable', () => ({ default: () => <div data-testid="table" /> }))
vi.mock('./SalaryComparison', () => ({ default: () => <div><h2>Compare Salaries Across Districts</h2></div> }))
vi.mock('../services/api', () => ({
  default: {
    searchDistricts: vi.fn(async () => ({ data: [] })),
    getDistricts: vi.fn(async () => ({ data: [] })),
    getDistrict: vi.fn(async () => ({ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' })),
    updateDistrict: vi.fn(async () => ({ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' })),
  }
}))

import DistrictBrowser from './DistrictBrowser'

it('can switch to the salaries tab and see comparison header', async () => {
  render(
    <DataCacheContext.Provider value={mockCacheContext}>
      <DistrictBrowser />
    </DataCacheContext.Provider>
  )
  fireEvent.click(screen.getByRole('button', { name: /Compare Salaries/i }))
  await waitFor(() => {
    expect(screen.getByText(/Compare Salaries Across Districts/i)).toBeInTheDocument()
  })
})

it('searches and renders empty list, then clears', async () => {
  const { default: api } = await import('../services/api')
  api.searchDistricts.mockResolvedValueOnce({ data: [{ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' }] })

  render(
    <DataCacheContext.Provider value={mockCacheContext}>
      <DistrictBrowser />
    </DataCacheContext.Provider>
  )
  // ensure starting on districts tab (h2 heading)
  expect(screen.getByRole('heading', { level: 2, name: /Districts \(0\)/ })).toBeInTheDocument()

  // enter query and submit
  const input = screen.getByPlaceholderText(/Search districts or towns.../)
  fireEvent.change(input, { target: { value: 'a' } })
  fireEvent.click(screen.getByRole('button', { name: /Search/i }))

  // list should render 1 item
  expect(await screen.findByText('Alpha')).toBeInTheDocument()

  // clear button
  fireEvent.click(screen.getByRole('button', { name: /Clear/i }))
  expect(screen.getByText(/Districts \(0\)/)).toBeInTheDocument()
})
