# Changelog

All notable changes to Meridian are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.7.0] - 2026-03-22

### Added — Website (getmeridian.org)
- **New Astro website** replacing old static HTML docs — 45 pages, fully static
- **Full i18n**: 30 translated doc pages (10 each for Russian, Farsi, Chinese) + landing page UI translations (~250 keys)
- **CommandBuilder**: 5-tab interactive CLI builder (Deploy, Preflight, SNI Scan, Doctor, Teardown) with real-time command generation, localStorage persistence, IPv4 validation
- **Pagefind search**: static full-text search across all 40 doc pages in 4 languages
- **Scroll reveal animations**: IntersectionObserver fade-in-up on landing page sections
- **Mobile navigation**: hamburger menu at <640px with slide-down drawer
- **404 page**: branded with noindex meta tag
- **Sitemap** (`@astrojs/sitemap`) and `robots.txt`
- **Mermaid diagram rendering** via `rehype-mermaid` (build-time inline SVGs)
- **llms.txt endpoints**: `/llms.txt`, `/llms-full.txt`, `/md/{locale}/{slug}` for AI consumption
- **Terminal deploy SVG**: recorded from live server deploy, sanitized with RFC 5737 example IPs
- **Locale-aware docs**: sidebar filters by locale, locale switcher buttons, `<link rel="alternate" hreflang>` for SEO
- **hreflang links** on all doc pages for proper multi-language indexing
- **CSS sync script** (`sync-template-css.mjs`): extracts tokens from Astro and injects into Jinja2 template (ready for SYNC markers)
- **App links single source of truth**: `src/data/apps.json` validated by CI and pre-push hook against Jinja2 template

### Changed — Website
- **Self-hosted fonts**: Fraunces, Source Sans 3, JetBrains Mono served from `/fonts/` — zero external requests to Google (critical for users in censored regions)
- **Demo page dark mode**: all hardcoded hex colors replaced with CSS custom properties
- Protocol card colors (`--blue`, `--amber`) added to design token system with dark mode variants
- Early `<script>` in `<head>` sets `lang`/`dir` from localStorage before paint (prevents RTL layout shift)
- Docs redirect (`/docs/`) detects stored locale preference before redirecting

### Changed — CI/CD
- **Release workflow** builds Astro site instead of copying old `docs/`
- **Website Build** job added to CI pipeline
- Actions upgraded: `setup-node` v6 (Node 24, npm caching), `setup-python` v6, `setup-uv` v7, `upload-pages-artifact` v4
- Playwright Chromium installed in CI/release for Mermaid rendering
- Pre-push hook validates app links against `apps.json` (was `docs/demo.html`)
- AI docs source moved to `website/src/content/ai/` (Makefile, hooks, workflows updated)

### Changed — Repository
- `docs/` directory removed entirely — all content consolidated under `website/`
- README.md image paths updated to `website/public/img/`

### Security
- `<meta name="referrer" content="no-referrer">` prevents origin leaks for at-risk users
- Ping page XSS fix: HTML-escape all localStorage-rendered values
- Demo page uses RFC 5737 documentation IPs (was real-ish subnet)
- Terminal SVG uses example IPs and redacted paths (was live server data)
- All `target="_blank"` links have `rel="noopener"`

### Accessibility
- `aria-current="page"` on active sidebar link
- `aria-label` on search input
- `for=` attributes linking CommandBuilder labels to inputs
- Translatable timeline steps, code block labels, callouts, TOC label, "then" separator

## [3.6.0] - 2026-03-22

### Changed
- **BREAKING:** XHTTP now routed through port 443 via Caddy (no extra port exposed)
  - URLs simplified: `security=tls`, path-based routing, no Reality params
  - Old XHTTP URLs (with separate port + Reality) no longer work
  - XHTTP remains enabled by default — it's now a free fallback with zero cost
- Deploy wizard redesigned with protocol explanation, Rich Panel summary
- Inline SNI scan: wizard offers to scan for optimal camouflage target (~30s)
- "Camouflage target" terminology replaces "SNI" in user-facing text
- Flag descriptions improved for non-VPN-expert users

### Added
- `scan_for_sni()` extracted as reusable function for wizard integration
- `xhttp_path` field in credentials (random 16-char path for Caddy routing)
- Caddy reverse proxy for XHTTP in both IP and domain modes

### Fixed
- XHTTP no longer opens external firewall port (localhost-only)

## [3.5.0] - 2026-03-22

### Added
- Codified architecture patterns in CLAUDE.md for consistent development
- Light mode support for website and ping tool
- WCAG accessibility improvements (color contrast, keyboard focus, ARIA labels)
- Step counter in provisioner output ([1/14] format)
- SNI and XHTTP visibility in setup wizard summary
- qrencode missing warning
- Mermaid architecture diagrams replacing ASCII art
- CHANGELOG.md

### Fixed
- Documentation accuracy for v3.4.0 architecture (HAProxy+Caddy in all modes)
- XHTTP checkbox default in website command builder
- base64 encoding cross-platform consistency in services.py
- render.py template code duplication
- HTML escaping in minimal fallback renderer

### Changed
- Renamed CLI commands for clarity: `setup` → `deploy`, `check` → `preflight`, `ping` → `test`, `diagnostics` → `doctor` (alias: `rage`), `uninstall` → `teardown`, `self-update` → `update`
- Removed `version` subcommand (use `--version` / `-v` flag instead)
- Improved CLI help text for deploy, preflight, test, doctor commands
- Improved connection page QR code guidance for non-technical users
- Reordered client add terminal output (shareable URL first)

## [3.4.0] - 2025-03-21

### Added
- Server-hosted connection pages via Let's Encrypt IP certificates
- HAProxy + Caddy deployment in standalone mode (all modes now use this architecture)
- Per-client hosted pages with shareable URLs
- Usage stats on server-hosted connection pages
- `render_hosted_html()` for server-hosted page rendering

### Changed
- Architecture: all modes now deploy HAProxy (port 443) + Caddy (port 8443) + Xray
- Connection pages automatically deployed during `client add`

## [3.3.1] - 2025-03-20

### Fixed
- Uninstall cron grep pattern never matched actual cron entry
- i18n textContent stripped ping test link for RU/FA/ZH users
- test_panel.py body format test always passed due to `assert X or Y`

### Changed
- Completed output.py migration to urls.py/render.py/display.py
- Centralized magic values in config.py
- Normalized provisioner step names to human-readable format

## [3.3.0] - 2025-03-18

### Fixed
- `--xhttp` flag was always True, now proper `--xhttp/--no-xhttp` toggle
- `InstallHAProxy` status always "changed" (copy-paste bug)
- `ConfigureFirewall` idempotency was fake

### Removed
- Complete Ansible purge (88 files, -3,785 lines)

### Changed
- Provisioner refactored: timed decorator deduplicated, PanelClient methods public
- Setup success celebration message
- Better error messages throughout

## [3.2.0] - 2025-03-15

### Added
- Python provisioner engine (15 steps replacing Ansible)
- Protocol foundation (ProtocolURL, dict registry)
- Output split into urls.py / render.py / display.py
- Error taxonomy and sudo escalation
- PanelClient context manager

### Removed
- Ansible fully deleted (-2,825 lines)

## [3.1.0] - 2025-03-12

### Added
- Uninstall provisioner
- E2E test pipeline
