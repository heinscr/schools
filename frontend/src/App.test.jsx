import { render, screen, waitFor } from '@testing-library/react'
import App from './App'

vi.mock('./components/ChoroplethMap', () => ({ default: () => <div data-testid="choropleth-map" /> }))
vi.mock('./components/DistrictEditor', () => ({ default: () => <div data-testid="district-editor" /> }))
vi.mock('./components/SalaryTable', () => ({ default: () => <div data-testid="salary-table" /> }))

// Mock fetch for geojson
const originalFetch = global.fetch
beforeAll(() => {
  global.fetch = vi.fn((url) => {
    if (url === '/ma_municipalities.geojson' || url.includes('ma_municipalities.geojson')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ type: 'FeatureCollection', features: [] })
      })
    }
    return originalFetch(url)
  })
})

afterAll(() => {
  global.fetch = originalFetch
})

it('renders the app header', async () => {
  render(<App />)
  await waitFor(() => {
    expect(screen.getByText(/Massachusetts School Districts/i)).toBeInTheDocument()
  })
})
