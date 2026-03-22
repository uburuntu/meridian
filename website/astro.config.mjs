import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://getmeridian.org',
  output: 'static',
  i18n: {
    locales: ['en', 'ru', 'fa', 'zh'],
    defaultLocale: 'en',
    routing: {
      prefixDefaultLocale: false,
    },
  },
  build: {
    format: 'directory',
  },
});
