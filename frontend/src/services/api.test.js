import api from './api'

const originalFetch = global.fetch

beforeEach(() => {
  global.fetch = vi.fn()
})

afterEach(() => {
  global.fetch = originalFetch
})

test('getDistricts caches town lookups', async () => {
  const firstResp = {
    ok: true,
    json: async () => ({ data: [{ id: 'd1', name: 'Alpha' }] })
  }
  global.fetch.mockResolvedValueOnce(firstResp)

  const r1 = await api.getDistricts({ town: 'Egremont' })
  expect(r1.data[0].id).toBe('d1')
  expect(global.fetch).toHaveBeenCalledTimes(1)

  const r2 = await api.getDistricts({ town: 'egremont' })
  expect(r2.data[0].id).toBe('d1')
  expect(global.fetch).toHaveBeenCalledTimes(1)
})

test('getDistrict throws on 404 and update clears cache', async () => {
  global.fetch.mockResolvedValueOnce({ ok: false, status: 404, statusText: 'Not Found' })
  await expect(api.getDistrict('NOPE')).rejects.toThrow('District not found')

  // seed cache then update
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ data: [{ id: 'd1' }] }) })
  await api.getDistricts({ town: 'A' })

  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'd1', name: 'Alpha' }) })
  await api.updateDistrict('d1', { name: 'Alpha' })

  // Should have cleared cache; subsequent town fetch goes to network again
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ data: [] }) })
  await api.getDistricts({ town: 'a' })
  expect(global.fetch).toHaveBeenCalledTimes(4)
})

test('getSalarySchedules handles 404/503/network gracefully', async () => {
  // 404 -> []
  global.fetch.mockResolvedValueOnce({ ok: false, status: 404, statusText: 'Not Found' })
  expect(await api.getSalarySchedules('d1')).toEqual([])

  // 503 -> []
  global.fetch.mockResolvedValueOnce({ ok: false, status: 503, statusText: 'Service Unavailable' })
  expect(await api.getSalarySchedules('d1')).toEqual([])

  // network error -> []
  global.fetch.mockRejectedValueOnce(new Error('Failed to fetch'))
  expect(await api.getSalarySchedules('d1')).toEqual([])

  // success
  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ([{ school_year: '2023-2024' }]) })
  const data = await api.getSalarySchedules('d1')
  expect(data[0].school_year).toBe('2023-2024')
})

test('compareSalaries handles 404/503/network gracefully', async () => {
  const baseQuery = { query: { education: 'M', credits: 30, step: 5 }, results: [], total: 0 }

  global.fetch.mockResolvedValueOnce({ ok: false, status: 404, statusText: 'Not Found' })
  expect(await api.compareSalaries('M', 30, 5)).toEqual(baseQuery)

  global.fetch.mockResolvedValueOnce({ ok: false, status: 503, statusText: 'Service Unavailable' })
  expect(await api.compareSalaries('M', 30, 5)).toEqual(baseQuery)

  global.fetch.mockRejectedValueOnce(new Error('Failed to fetch'))
  expect(await api.compareSalaries('M', 30, 5)).toEqual(baseQuery)

  global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ total: 1, results: [{ district_id: 'd1' }] }) })
  const ok = await api.compareSalaries('M', 30, 5)
  expect(ok.total).toBe(1)
})
