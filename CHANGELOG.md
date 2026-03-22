# Changelog

All notable changes to Meridian are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).

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
