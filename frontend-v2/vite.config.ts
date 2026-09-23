import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    rolldownOptions: {
      output: {
        // Stable vendor chunks: app-code changes don't bust the cached
        // framework/chart bundles (served immutable under /assets/).
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](?:react|react-dom|react-router-dom|@tanstack[\\/]react-query)[\\/]/ },
            { name: 'charts', test: /node_modules[\\/]recharts[\\/]/ },
            { name: 'motion', test: /node_modules[\\/]framer-motion[\\/]/ },
          ],
        },
      },
    },
  },
})
