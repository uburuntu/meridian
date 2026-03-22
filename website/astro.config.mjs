import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://getmeridian.org',
  output: 'static',
  i18n: {
    locales: ['en'],
    defaultLocale: 'en',
  },
  build: {
    format: 'directory',
  },
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'viewport',
  },
});
