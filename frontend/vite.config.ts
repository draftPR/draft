import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import backendLauncher from './vite-plugin-backend-launcher'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), backendLauncher()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
