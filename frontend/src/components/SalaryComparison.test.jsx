import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'

vi.mock('../services/api', () => ({
  default: {
    compareSalaries: vi.fn(async () => ({
      query: { education: 'M', credits: 30, step: 5 },
      total: 2,
      results: [
        { rank: 1, district_id: 'd1', district_name: 'Alpha', district_type: 'municipal', school_year: '2023-2024', salary: 90000 },
        { rank: 2, district_id: 'd2', district_name: 'Beta', district_type: 'regional_academic', school_year: '2023-2024', salary: 80000 },
      ]
    }))
  }
}))

vi.mock('./SalaryComparisonMap', () => ({ default: ({ results }) => <div data-testid="map" data-count={results?.length || 0} /> }))

import SalaryComparison from './SalaryComparison'

it('renders comparison header and fetches results on Search', async () => {
  render(<SalaryComparison />)
  expect(screen.getByText(/Compare Salaries Across Districts/i)).toBeInTheDocument()

  const button = screen.getByRole('button', { name: /Search Salaries/i })
  fireEvent.click(button)

  await waitFor(() => expect(screen.getByText(/Results/i)).toBeInTheDocument())
  expect(screen.getByText(/2 districts/)).toBeInTheDocument()
  expect(screen.getByTestId('map')).toHaveAttribute('data-count', '2')
})
