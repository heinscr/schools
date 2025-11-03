import { render, screen } from '@testing-library/react'
import App from './App'

vi.mock('./components/ChoroplethMap', () => ({ default: () => <div data-testid="choropleth-map" /> }))
vi.mock('./components/DistrictEditor', () => ({ default: () => <div data-testid="district-editor" /> }))
vi.mock('./components/SalaryTable', () => ({ default: () => <div data-testid="salary-table" /> }))

it('renders the app header', () => {
  render(<App />)
  expect(screen.getByText(/Massachusetts School Districts/i)).toBeInTheDocument()
})
