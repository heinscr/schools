import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

vi.mock('./ChoroplethMap', () => ({ default: () => <div data-testid="map" /> }))
vi.mock('./DistrictEditor', () => ({ default: () => <div data-testid="editor" /> }))
vi.mock('./SalaryTable', () => ({ default: () => <div data-testid="table" /> }))
vi.mock('../services/api', () => ({
  default: {
    searchDistricts: vi.fn(async () => ({ data: [] })),
    getDistricts: vi.fn(async () => ({ data: [] })),
    getDistrict: vi.fn(async () => ({ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' })),
    updateDistrict: vi.fn(async () => ({ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' })),
  }
}))

import DistrictBrowser from './DistrictBrowser'

it('can switch to the salaries tab and see comparison header', () => {
  render(<DistrictBrowser />)
  fireEvent.click(screen.getByRole('button', { name: /Compare Salaries/i }))
  expect(screen.getByText(/Compare Salaries Across Districts/i)).toBeInTheDocument()
})

it('searches and renders empty list, then clears', async () => {
  const { default: api } = await import('../services/api')
  api.searchDistricts.mockResolvedValueOnce({ data: [{ id: 'd1', name: 'Alpha', towns: [], district_type: 'municipal' }] })

  render(<DistrictBrowser />)
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
