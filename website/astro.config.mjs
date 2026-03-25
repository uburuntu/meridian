import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://getmeridian.org',
  output: 'static',
  integrations: [sitemap()],
  i18n: {
    locales: ['en', 'ru', 'fa', 'zh'],
    defaultLocale: 'en',
  },
  build: {
    format: 'directory',
  },
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'viewport',
  },
  markdown: {
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
      defaultColor: false,
    },
  },
});
