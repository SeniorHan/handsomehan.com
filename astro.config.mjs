// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  site: 'https://handsomehan.com',
  output: 'static',
  vite: {
    plugins: [tailwindcss()]
  },
  adapter: cloudflare(),
  markdown: {
    shikiConfig: {
      theme: 'github-dark',
    },
  },
});