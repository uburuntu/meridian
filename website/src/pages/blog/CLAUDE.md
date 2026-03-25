# blog pages — blog index + post route

## Design decisions

**No sidebar or TOC** — blog posts are linear narratives, not reference docs. Single-column layout keeps focus on reading.

**Shared prose styles** — markdown styling lives in `src/styles/prose.css` with `.prose` class. Both BlogPost.astro and Docs.astro use it.

**English-only** — no locale infrastructure. Blog is content marketing, not essential UI for censored users.

**Slug from folder name** — Astro content collections derive slug from folder path. No `slug:` in frontmatter.

## Pitfalls

- **Hero images are co-located** — images live alongside `index.md` in each post folder. Glob loader resolves relative paths from `src/content/blog/`.
- **Mermaid rendering** — client-side via `Mermaid.astro` component. Shiki highlights mermaid blocks as code; the component dynamically imports mermaid.js and renders SVGs at runtime. Only loaded on pages with diagrams.
- **Date coercion** — `z.coerce.date()` in schema handles both `2026-03-25` and `'2026-03-25'` YAML formats.
