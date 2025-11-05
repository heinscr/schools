import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    'global': 'globalThis',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.js'],
    coverage: {
      reporter: ['text', 'html'],
      exclude: [
        'src/main.jsx',
        'src/components/ChoroplethMap.jsx',
        'src/components/DistrictEditor.jsx',
        'src/components/SalaryTable.jsx'
      ]
    },
  },
})
