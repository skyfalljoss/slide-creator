# Free Public Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy SlideForge publicly on an OCI Always Free ARM VM with a free DuckDNS hostname, trusted HTTPS, password protection, persistent data, and tested backups.

**Architecture:** One Ubuntu ARM64 VM runs the existing four-service Docker Compose stack. Host Caddy terminates TLS and requires Basic Authentication before forwarding to the Compose web service bound only to `127.0.0.1:8080`; PostgreSQL, FastAPI, and ONLYOFFICE remain private.

**Tech Stack:** OCI Ampere A1, Ubuntu 24.04 ARM64, Docker Engine, Docker Compose, Caddy, DuckDNS, React/Nginx, FastAPI, PostgreSQL 16, ONLYOFFICE 9.4

---

## File Structure

- `docs/FREE_PUBLIC_DEPLOYMENT.md`: complete operator runbook, including exact console selections, commands, file contents, verification, backups, upgrades, rollback, and troubleshooting.
- `.env` on the VM only: deployment secrets and public origins; mode `600`, excluded from Git.
- `/etc/duckdns.env` on the VM: DuckDNS domain and token; root-owned with mode `600`.
- `/usr/local/sbin/duckdns-update`: fail-fast DuckDNS updater.
- `/etc/systemd/system/duckdns-update.{service,timer}`: five-minute DNS update schedule.
- `/etc/caddy/Caddyfile`: public hostname, Basic Authentication, and reverse proxy to loopback.
- `/usr/local/sbin/slideforge-backup`: PostgreSQL logical dump and deck-volume archive with seven-day local retention.
- `/etc/systemd/system/slideforge-backup.{service,timer}`: nightly local backup schedule.

## Task 1: Publish the Deployment Documentation

**Files:**
- Create: `docs/FREE_PUBLIC_DEPLOYMENT.md`
- Create: `docs/superpowers/plans/2026-06-30-free-public-deployment.md`
- Modify: `docs/superpowers/specs/2026-06-30-free-public-deployment-design.md`

- [ ] **Step 1: Validate documentation whitespace**

Run from the repository root:

```bash
git diff --check -- docs/FREE_PUBLIC_DEPLOYMENT.md docs/superpowers/plans/2026-06-30-free-public-deployment.md docs/superpowers/specs/2026-06-30-free-public-deployment-design.md
```

Expected: no output and exit status 0.

- [ ] **Step 2: Confirm the guide covers the full lifecycle**

```bash
rg -n '^## (4|5|7|9|10|11|12|13|14|15|16|17|18)\.' docs/FREE_PUBLIC_DEPLOYMENT.md
```

Expected: headings exist for provisioning, networking, Docker, DNS, configuration, startup, TLS, verification, backup, restore, update, rollback, and routine operations.

- [ ] **Step 3: Commit only the deployment documents**

```bash
git add docs/FREE_PUBLIC_DEPLOYMENT.md docs/superpowers/plans/2026-06-30-free-public-deployment.md docs/superpowers/specs/2026-06-30-free-public-deployment-design.md
git commit -m "docs: add free public deployment runbook"
```

Expected: the commit contains only those three documentation paths.

- [ ] **Step 4: Push the deployable revision**

```bash
git push origin main
```

Expected: GitHub reports that `main` advanced to the new documentation commit. If branch protection rejects a direct push, push a branch and merge its pull request before provisioning.

## Task 2: Provision the Free OCI Host

**References:**
- `docs/FREE_PUBLIC_DEPLOYMENT.md:65` (SSH key)
- `docs/FREE_PUBLIC_DEPLOYMENT.md:85` (OCI VM)
- `docs/FREE_PUBLIC_DEPLOYMENT.md:114` (network rules)

- [ ] **Step 1: Generate the dedicated SSH key**

Run on the operator's computer:

```bash
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/slideforge_oci -C slideforge-oci
chmod 600 ~/.ssh/slideforge_oci
```

Expected: private and public keys exist at `~/.ssh/slideforge_oci` and `~/.ssh/slideforge_oci.pub`.

- [ ] **Step 2: Create the Always Free instance**

In the OCI home region, create `slideforge` with Canonical Ubuntu 24.04 ARM64, `VM.Standard.A1.Flex`, 2 OCPUs, 12 GB RAM, a 100 GB boot volume, a public subnet, a public IPv4 address, and the generated public SSH key.

Expected: OCI labels the resources Always Free eligible, estimated recurring cost is zero, and instance state becomes Running. Stop if OCI displays a charge.

- [ ] **Step 3: Restrict ingress**

Add stateful TCP ingress for port 22 from the operator's public `/32`, and ports 80 and 443 from `0.0.0.0/0`.

Expected: no ingress exists for ports 5432, 8000, 8080, or ONLYOFFICE.

- [ ] **Step 4: Connect and patch Ubuntu**

```bash
ssh -i ~/.ssh/slideforge_oci ubuntu@OCI_PUBLIC_IP
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
sudo apt install -y ca-certificates curl git gnupg openssl ufw
sudo reboot
```

Expected: SSH connects as `ubuntu`; package commands complete without errors; the VM reconnects after reboot.

- [ ] **Step 5: Enable the host firewall**

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Expected: default incoming policy is deny and only SSH, HTTP, and HTTPS are allowed.

## Task 3: Install and Verify Docker

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:182`

- [ ] **Step 1: Install Docker from its signed Ubuntu repository**

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker
```

Expected: package installation succeeds and `systemctl is-active docker` prints `active`.

- [ ] **Step 2: Reconnect and verify ARM64 container execution**

```bash
docker version
docker compose version
docker run --rm hello-world
uname -m
```

Expected: Docker and Compose print versions, the container succeeds, and `uname -m` prints `aarch64`.

## Task 4: Install the Application Configuration

**References:**
- `docs/FREE_PUBLIC_DEPLOYMENT.md:228` (clone)
- `docs/FREE_PUBLIC_DEPLOYMENT.md:376` (application environment)

- [ ] **Step 1: Clone the repository**

```bash
sudo mkdir -p /opt/slideforge
sudo chown ubuntu:ubuntu /opt/slideforge
git clone https://github.com/skyfalljoss/slide-creator.git /opt/slideforge
cd /opt/slideforge
git branch --show-current
```

Expected: clone succeeds and branch is `main`. If the repository is private, use the read-only GitHub deploy-key procedure in Section 8 of the guide.

- [ ] **Step 2: Generate independent service secrets**

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Expected: two different 64-character hexadecimal strings. Store them only in the VM's `.env`.

- [ ] **Step 3: Write the local-storage deployment environment**

Create `/opt/slideforge/.env` with this complete key set, replacing both secret values and `slideforge-demo`:

```dotenv
POSTGRES_PASSWORD=FIRST_RANDOM_HEX_VALUE
ONLYOFFICE_JWT_SECRET=SECOND_RANDOM_HEX_VALUE
ONLYOFFICE_CALLBACK_TOKEN_TTL_SECONDS=604800
PUBLIC_APP_URL=https://slideforge-demo.duckdns.org
ONLYOFFICE_PUBLIC_URL=https://slideforge-demo.duckdns.org/onlyoffice
WEB_PORT=127.0.0.1:8080
STORAGE_PROVIDER=local
GCP_PROJECT_ID=disabled-local-storage
GCP_REGION=us-central1
GCS_BUCKET=disabled-local-storage
ALLOW_INCOMPLETE_LOCAL_BACKUP=true
AI_PROVIDER=local
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
CITI_SSO_ENABLED=false
```

```bash
chmod 600 /opt/slideforge/.env
cd /opt/slideforge
docker compose --env-file .env config --quiet
```

Expected: `.env` mode is `600`; Compose validation exits without output.

## Task 5: Configure DuckDNS

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:261`

- [ ] **Step 1: Register the hostname**

Add the selected slug in the DuckDNS dashboard and update it to `OCI_PUBLIC_IP`.

Expected: `getent ahostsv4 SLUG.duckdns.org` includes `OCI_PUBLIC_IP` after propagation.

- [ ] **Step 2: Install the protected updater and systemd units**

Create `/etc/duckdns.env` with the chosen values:

```dotenv
DUCKDNS_DOMAIN=slideforge-demo
DUCKDNS_TOKEN=DUCKDNS_ACCOUNT_TOKEN
```

Create `/usr/local/sbin/duckdns-update`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
source /etc/duckdns.env
result="$(curl --fail --silent --show-error --get \
  --data-urlencode "domains=${DUCKDNS_DOMAIN}" \
  --data-urlencode "token=${DUCKDNS_TOKEN}" \
  --data-urlencode "ip=" \
  https://www.duckdns.org/update)"
if [[ "$result" != "OK" ]]; then
  echo "DuckDNS update failed: $result" >&2
  exit 1
fi
```

Create `/etc/systemd/system/duckdns-update.service`:

```ini
[Unit]
Description=Update the SlideForge DuckDNS address
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/duckdns-update
```

Create `/etc/systemd/system/duckdns-update.timer`:

```ini
[Unit]
Description=Update SlideForge DuckDNS every five minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

Apply permissions:

```bash
sudo chown root:root /etc/duckdns.env /usr/local/sbin/duckdns-update
sudo chmod 600 /etc/duckdns.env
sudo chmod 700 /usr/local/sbin/duckdns-update
```

Expected: `/etc/duckdns.env` is root-owned mode `600`; the updater is executable and fails on a DuckDNS response other than `OK`.

- [ ] **Step 3: Enable and verify the timer**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now duckdns-update.timer
sudo systemctl start duckdns-update.service
sudo journalctl -u duckdns-update.service -n 20 --no-pager
systemctl list-timers duckdns-update.timer
```

Expected: the oneshot service succeeds and the timer lists its next activation.

## Task 6: Start and Inspect the Compose Stack

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:431`

- [ ] **Step 1: Build and start all services**

```bash
cd /opt/slideforge
make stack-up
docker compose --env-file .env ps
```

Expected: `postgres`, `onlyoffice`, `backend`, and `web` start; after initialization they report healthy or running as defined by Compose.

- [ ] **Step 2: Verify the loopback-only web entry point**

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/v1/health
sudo ss -ltnp | grep 8080
```

Expected: `ok`, healthy API JSON, and a `127.0.0.1:8080` listener. A `0.0.0.0:8080` listener fails the security check.

- [ ] **Step 3: Diagnose any unhealthy service before proceeding**

```bash
docker compose --env-file .env logs --tail=200 postgres onlyoffice backend web
```

Expected: no migration failure, missing secret, storage initialization error, or repeated container restart remains unresolved.

## Task 7: Publish Through Caddy

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:467`

- [ ] **Step 1: Install Caddy from its signed repository**

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Expected: `caddy version` succeeds and the systemd service is installed.

- [ ] **Step 2: Generate a password hash without storing plaintext in Caddy**

```bash
caddy hash-password
```

Expected: Caddy prompts without echoing the password and emits a hash suitable for `basic_auth`.

- [ ] **Step 3: Install and validate the Caddyfile**

Create `/etc/caddy/Caddyfile` with the real DuckDNS hostname, chosen username, and generated hash:

```caddyfile
slideforge-demo.duckdns.org {
    encode zstd gzip

    basic_auth {
        slideforge CADDY_PASSWORD_HASH
    }

    reverse_proxy 127.0.0.1:8080
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Expected: configuration validation succeeds, Caddy is active, and its log shows successful certificate management.

## Task 8: Run Acceptance and Persistence Tests

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:534`

- [ ] **Step 1: Verify authentication and HTTPS**

Run on the operator's computer:

```bash
curl -I https://SLUG.duckdns.org
curl -u APP_USERNAME https://SLUG.duckdns.org/healthz
curl -u APP_USERNAME https://SLUG.duckdns.org/api/v1/health
```

Expected: unauthenticated access returns 401; authenticated access prompts for the password and returns `ok` plus healthy JSON over a trusted TLS connection.

- [ ] **Step 2: Exercise the complete browser workflow**

Generate a three-slide quarterly update, verify previews, save it, edit one text element in ONLYOFFICE, save, export, and download the PPTX.

Expected: every stage completes without console-visible authentication, mixed-content, callback, or download errors.

- [ ] **Step 3: Verify restart persistence**

```bash
sudo reboot
```

Expected: after reconnecting, the HTTPS site returns, all four containers recover automatically, and the saved deck is still present.

## Task 9: Install and Prove Backups

**References:**
- `docs/FREE_PUBLIC_DEPLOYMENT.md:567` (backup)
- `docs/FREE_PUBLIC_DEPLOYMENT.md:672` (restore drill)

- [ ] **Step 1: Install the local backup script and timer**

Create `/usr/local/sbin/slideforge-backup`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

root=/opt/slideforge
destination=/var/backups/slideforge
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_backup="$destination/postgres-$timestamp.sql.gz"
deck_backup="$destination/deck-files-$timestamp.tar.gz"

cd "$root"
docker compose --env-file .env exec -T postgres \
  pg_dump --username slideforge --dbname slideforge --no-owner --no-privileges \
  | gzip -9 >"$database_backup"

docker run --rm \
  -v slideforge_deck-files:/source:ro \
  -v "$destination:/backup" \
  alpine:3.22 \
  tar -czf "/backup/$(basename "$deck_backup")" -C /source .

gzip -t "$database_backup"
tar -tzf "$deck_backup" >/dev/null
find "$destination" -type f -mtime +7 -delete
```

Create `/etc/systemd/system/slideforge-backup.service`:

```ini
[Unit]
Description=Back up SlideForge PostgreSQL and deck files locally
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
ExecStart=/usr/local/sbin/slideforge-backup
```

Create `/etc/systemd/system/slideforge-backup.timer`:

```ini
[Unit]
Description=Run the SlideForge local backup nightly

[Timer]
OnCalendar=*-*-* 02:00:00 UTC
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
```

Apply the directory and script permissions:

```bash
sudo install -d -m 0700 -o ubuntu -g ubuntu /var/backups/slideforge
sudo chown root:root /usr/local/sbin/slideforge-backup
sudo chmod 755 /usr/local/sbin/slideforge-backup
```

Expected: `/var/backups/slideforge` is mode `700`; the script creates a compressed PostgreSQL dump and read-only deck-volume archive, validates both, and removes files older than seven days.

- [ ] **Step 2: Run and inspect the first backup**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now slideforge-backup.timer
sudo systemctl start slideforge-backup.service
sudo journalctl -u slideforge-backup.service -n 50 --no-pager
sudo ls -lh /var/backups/slideforge
```

Expected: service succeeds and one nonempty `.sql.gz` plus one nonempty `.tar.gz` exist.

- [ ] **Step 3: Restore into a disposable database**

Substitute the actual newest database backup filename:

```bash
cd /opt/slideforge
BACKUP=/var/backups/slideforge/postgres-20260630T020000Z.sql.gz
gzip -t "$BACKUP"
docker compose --env-file .env exec -T postgres createdb --username slideforge slideforge_restore
gunzip -c "$BACKUP" | docker compose --env-file .env exec -T postgres psql --username slideforge --dbname slideforge_restore --set ON_ERROR_STOP=1 --single-transaction
docker compose --env-file .env exec -T postgres psql --username slideforge --dbname slideforge_restore --command 'SELECT count(*) FROM decks;'
docker compose --env-file .env exec -T postgres dropdb --username slideforge slideforge_restore
```

Expected: gzip integrity passes, SQL restore completes in `slideforge_restore`, the `decks` count query succeeds, and the disposable database is dropped.

- [ ] **Step 4: Create an OCI boot-volume backup**

Create a dated manual backup from the instance's boot volume after checking the tenancy's remaining Always Free backup allowance.

Expected: OCI reports the backup Available and no nonzero estimated charge.

## Task 10: Record the Operations Procedure

**Reference:** `docs/FREE_PUBLIC_DEPLOYMENT.md:703`

- [ ] **Step 1: Test observability commands**

```bash
cd /opt/slideforge
docker compose --env-file .env ps
systemctl status caddy --no-pager
systemctl list-timers duckdns-update.timer slideforge-backup.timer
df -h /
free -h
```

Expected: services are available, both timers are scheduled, disk has safe free space, and memory does not show sustained exhaustion.

- [ ] **Step 2: Rehearse the pre-update sequence without pulling**

```bash
cd /opt/slideforge
git status --short
git rev-parse HEAD
sudo systemctl start slideforge-backup.service
```

Expected: Git status is clean, the deployed revision is recorded, and the backup succeeds. Do not stop ONLYOFFICE or pull code during this rehearsal.

- [ ] **Step 3: Store the runbook location with the deployment record**

Record `docs/FREE_PUBLIC_DEPLOYMENT.md` and the deployed Git commit hash in the operator's private deployment note.

Expected: another operator can identify the exact revision and follow update, rollback, shutdown, startup, and troubleshooting procedures without reconstructing commands from shell history.
