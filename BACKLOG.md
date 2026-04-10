# Backlog

Active backlog only. Keep this file focused on P0/P1 work and the current review loop.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Agent Pass 1

- [x] **P0 · XHTTP routing analyst** — exact-path and slash-path XHTTP requests now route to the same nginx upstream. The worktree change is in `src/meridian/provision/services.py`, covered by `tests/provision/test_services.py`, and the focused XHTTP/provisioning test suite passes.
- [ ] **P0 · TLS camouflage analyst** — unknown SNI now falls through to the Reality destination, but IP-mode direct-IP / no-SNI traffic still exposes the nginx-served IP certificate path. Next: decide the desired probe behavior for bare-IP HTTPS in IP mode, then add stream/http tests that lock the behavior down before changing cert strategy.
- [ ] **P0 · State authority analyst** — `meridian deploy` now force-refreshes before provisioning, but deploy-time branding writes, scanned-SNI writes, and the final sync back to `/etc/meridian/proxy.yml` still do not consistently use the same fail-closed authority boundary as client/relay mutations. Next: move all remaining deploy/scan writes onto the same refresh-and-sync contract.
- [ ] **P0 · Rebuild migration analyst** — there is no rebuild/migrate command yet; the closest current path is `meridian deploy` in `src/meridian/commands/setup.py`, which can already load prior credentials but cannot transfer a server to a new IP safely. Next: design `deploy --from OLD_IP` around existing `ServerCredentials` data, with explicit source refresh and transactional publish.
- [ ] **P1 · Relay stealth analyst** — fresh relay deploys already scan the relay network and persist a relay-local SNI when `--sni` is omitted in `src/meridian/commands/relay.py`. Residual gap: legacy relays with empty `relay.sni` still fall back to the exit SNI in generated URLs/pages. Next: add a backfill/migration path and regenerate affected client pages.

## Agent Pass 2

- [x] **P1 · Domain deploy UX** — domain-mode deploy success output now prints explicit Cloudflare DNS/SSL/WebSocket steps instead of sending users to rediscover the flow after deploy.
- [x] **P1 · Deploy page fanout** — deploy/redeploy now regenerates saved client handoff pages after provisioning, so branding/domain/SNI changes fan out to existing clients instead of leaving stale local/hosted pages behind.
- [x] **P1 · Relay SNI fail-closed** — new relay deploys no longer silently fall back to a global default SNI when subnet scanning finds nothing or the operator declines the scanned choices.

## Agent Pass 3

- [x] **P1 · Firewall safety** — `ConfigureFirewall` no longer deletes arbitrary user-managed TCP rules; cleanup is limited to Meridian-owned public ports instead of silently removing custom SSH/monitoring access.
- [x] **P1 · Handoff page self-containment** — generated HTML/PWA handoff surfaces no longer point users at `getmeridian.org/ping`; troubleshooting text is now self-contained and keeps the critical connection handoff path local.

---

## P0 — Critical

### Anti-censorship

- [ ] **Residual IP-cert fingerprinting path in IP mode** — keep tightening the direct-IP / no-SNI probe surface so the server does not hand out a distinctive nginx-served IP certificate response outside the intended camouflage path
- [x] **Fix XHTTP nginx path mismatch** — nginx now routes both `/<xhttp_path>` and `/<xhttp_path>/` to the XHTTP upstream, matching URL generation and Xray config

### Product

- [ ] **Client migration for rebuilds** — add `meridian deploy NEW_IP --from OLD_IP` or equivalent so SNI, domain, clients, relays, and hosted handoff state can move without manual reconstruction
- [ ] **Eliminate state split-brain between local cache and server** — deploy now force-refreshes before provisioning; remaining work is to make branding writes, scanned-SNI writes, and deploy-time publish/sync paths fail closed so stale local `proxy.yml` never silently wins
- [ ] **Redeploy must update live state before publishing new handoff state** — never save or render URLs/pages/subscriptions that the live server is not yet serving
- [ ] **Partial panel recovery must preserve existing clients and relays** — recovery in `ConfigurePanel` still rebuilds only baseline state; it needs to reconstruct known clients, relay inbounds, and hosted pages from credentials before claiming success

### Security / Supply Chain

- [ ] **Replace mutable install/update trust chain with pinned, verified artifacts** — finish the release-artifact + checksum path for install/update flows
- [ ] **Stop executing unsigned remote scanner binaries as root** — pin and verify scanner artifacts, or vendor the scanner locally

---

## P1 — High

### Security

- [x] **Firewall cleanup deletes user's custom rules** — cleanup is now limited to Meridian-managed ports instead of deleting arbitrary user TCP rules
- [ ] **Remove public 3x-ui management from the shared 443 identity** — move the operator surface off the public camouflage identity or require an explicit operator-only access path

### Anti-censorship

- [ ] **Legacy relays need SNI backfill** — new relay deploys now fail closed without a relay-local SNI; remaining work is to repair legacy relay entries with blank `relay.sni` and regenerate affected hosted pages
- [ ] **Default SNI `www.microsoft.com` monitored** — make scanning the normal path, not the exceptional one
- [ ] **Make probe/check tooling mode-aware** — domain mode intentionally serves a real domain cert; verification must distinguish that from an IP-mode stealth leak

### Product

- [x] **Post-deploy Cloudflare setup guidance** — domain-mode deploy now prints the DNS-only → proxied and SSL/WebSocket steps in CLI success output
- [ ] **Rebuild state transfer UX** — once `--from` exists, make the CLI explain what is being copied, what is live, and what still needs redeploy
- [ ] **Make destructive mutations transactional** — keep remote cleanup, local credential mutation, registry writes, and hosted page updates in one fail-closed transaction boundary
- [x] **Regenerate all hosted client pages when shared server state changes** — relay changes already regenerated pages; deploy/redeploy now also refreshes saved client pages after branding/domain/SNI changes
- [ ] **Hosted connection page must stay self-hosted in recovery flows** — generated handoff pages no longer depend on `getmeridian.org/ping`; remaining work is to remove other third-party recovery/install dependencies from the critical path

### Reliability

- [ ] **WARP must be health-gated and reversible** — only switch outbound routing after WARP is actually up, and support full rollback
- [ ] **Domain mode must support safe steady-state redeploys behind orange-cloud** — redeploy should not require temporarily breaking the documented Cloudflare setup

### Testing

- [ ] **Make E2E fail on idempotency and redeploy regressions** — stop downgrading core deploy/redeploy failures to warnings
- [ ] **Add real-host coverage for production-sensitive branches** — cert issuance, nginx bootstrap, systemd, and redeploy migrations still need real-host coverage
- [ ] **Add end-to-end coverage for domain mode, WARP, relay migration, and recovery** — current mocks are not enough for deployment-changing behavior

---

## Done

Collapsed — see [CHANGELOG.md](CHANGELOG.md) for release history.

- **Review loop (current pass)** — XHTTP exact/slash nginx routing fixed in the worktree, deploy now force-refreshes credentials before provisioning, provision sharp-edge documented, focused setup/provisioning tests passing
- **Review loop (wave 2)** — deploy success output now includes Cloudflare setup steps, deploy/redeploy regenerates saved client handoff pages, new relay deploys fail closed when no relay-local SNI is available, targeted setup/relay tests passing
- **Review loop (wave 3)** — firewall cleanup no longer deletes unknown user TCP rules, generated HTML/PWA handoff pages dropped the external ping dependency, focused provision/render/template tests passing
- **Review loop (worktree)** — release workflow pinned to CI-passed SHA, nested credential field round-tripping preserved, PWA honors canonical `subscription_url`, client + relay remove paths fail closed on refresh/sync, silent patch auto-upgrade removed, sshd hardening moved to an authoritative drop-in with `sshd -T` validation, relay lifecycle commands reuse stored relay SSH users
