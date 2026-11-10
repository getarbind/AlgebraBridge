/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Relative `base` lets the same build work on Vercel (served from /) and on
// GitHub Pages (served from /<repo>/). The app has no client-side routes.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          katex: ['katex'],
          motion: ['framer-motion'],
        },
      },
    },
  },
  server: {
    // During development, forward telemetry to the optional Express logger.
    proxy: { '/api': 'http://localhost:4000' },
  },
  test: {
    environment: 'node',
  },
});
