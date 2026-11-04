import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: '../app/dashboard_static',
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (asset) => {
          if (asset.name && asset.name.endsWith('.css')) return 'app.css';
          return 'assets/[name]-[hash][extname]';
        },
      },
    },
  },
});
