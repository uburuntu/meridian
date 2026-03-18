# Meridian

One command deploys a censorship-resistant proxy server. Invisible to DPI, active probing, and TLS fingerprinting.

```bash
curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash
```

The script asks for your server IP, configures everything over SSH, and outputs a QR code.
Send the generated HTML file to whoever needs it — they scan, connect, done.

**What you need:** A Debian/Ubuntu VPS with root SSH key access. The script handles the rest.

**Uninstall:** `curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash -s -- --uninstall`
Removes the proxy container and configs. Does **not** remove Docker or system packages (they may be used by other apps). The script finds the server IP from saved credentials automatically.

**Full docs:** [meridian.msu.rocks](https://meridian.msu.rocks)
