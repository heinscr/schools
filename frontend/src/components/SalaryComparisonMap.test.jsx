import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import SalaryComparisonMap from './SalaryComparisonMap'

const originalFetch = global.fetch

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get() { return 800 } })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get() { return 600 } })
})

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ type: 'FeatureCollection', features: [] }) })
})

afterEach(() => {
  global.fetch = originalFetch
})

it('shows legend when results exist and fetches geojson', async () => {
  render(<div style={{width: '800px', height: '400px'}}><SalaryComparisonMap results={[{ district_id: 'd1', district_name: 'Alpha', towns: ['Town1'], salary: 1 }]} /></div>)
  await waitFor(() => expect(global.fetch).toHaveBeenCalled())
  expect(screen.getByText('Salary Ranking')).toBeInTheDocument()
})
