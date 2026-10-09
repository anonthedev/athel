import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  root: new URL('./src/renderer', import.meta.url).pathname,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': new URL('./src/renderer/src', import.meta.url).pathname,
      '@renderer': new URL('./src/renderer/src', import.meta.url).pathname
    }
  }
})
