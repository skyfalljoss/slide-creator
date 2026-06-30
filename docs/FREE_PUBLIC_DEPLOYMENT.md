# Deploy SlideForge Online for Free

This guide deploys SlideForge to one Oracle Cloud Infrastructure (OCI) Always
Free ARM VM and publishes it through a free DuckDNS hostname with HTTPS. It is
written for a personal demo or a small, low-traffic installation.

The final topology is:

```text
Browser
  -> https://SLUG.duckdns.org
  -> Caddy on the VM (TLS + password prompt)
  -> 127.0.0.1:8080
  -> SlideForge Nginx container
       -> React frontend
       -> FastAPI container at /api/
       -> ONLYOFFICE container at /onlyoffice/
  -> PostgreSQL and Docker volumes on the same VM
```

## 1. Understand the limits

- OCI currently documents an Always Free allowance of 2 Ampere A1 OCPUs,
  12 GB RAM, 200 GB total block storage, and five volume backups in the account's
  home region. Free limits can change. Read the current
  [OCI Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
  before creating anything.
- Stop if the OCI creation page shows a nonzero estimated monthly cost or does
  not label the selected resources **Always Free eligible**.
- Free A1 capacity is sometimes unavailable. Retry another availability domain
  or wait; selecting a paid shape is not part of this guide.
- The app uses local deterministic generation in this configuration. Gemini is
  disabled because API usage may cost money.
- Caddy Basic Authentication protects the public deployment because the app's
  Citi SSO integration is disabled. This is reasonable for a personal demo,
  but it is not enterprise identity management.
- Same-VM backups are not disaster recovery. Section 13 also creates a free OCI
  boot-volume backup, but important data still needs an encrypted off-provider
  copy.

## 2. Create the accounts

Create these accounts in a browser:

1. Create or sign in to an [Oracle Cloud account](https://www.oracle.com/cloud/free/).
   Oracle may request a payment card for identity verification. Do not enable
   paid resources while following this guide.
2. Create or sign in to [DuckDNS](https://www.duckdns.org/). Keep the page open;
   its dashboard displays your account token.
3. Confirm that you can access
   `https://github.com/skyfalljoss/slide-creator`. If the repository is private,
   Section 8 explains the SSH-key setup.

Record these values in a private note. Do not commit the note:

```text
DUCKDNS_SLUG       The name before .duckdns.org, for example slideforge-demo
DUCKDNS_TOKEN      Token shown after signing in to DuckDNS
OCI_PUBLIC_IP      Filled in after the VM is created
APP_USERNAME       Username for the browser password prompt, for example slideforge
APP_PASSWORD       A unique password of at least 20 characters
SSH_KEY_PATH       Local private-key path, for example ~/.ssh/slideforge_oci
```

## 3. Create an SSH key on your computer

Open Terminal on macOS or Linux and run:

```bash
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/slideforge_oci -C slideforge-oci
chmod 600 ~/.ssh/slideforge_oci
```

Enter a passphrase when prompted. This creates:

- `~/.ssh/slideforge_oci`: private key; never upload or share it.
- `~/.ssh/slideforge_oci.pub`: public key; upload this to OCI.

Display the public key if you need to copy it:

```bash
cat ~/.ssh/slideforge_oci.pub
```

## 4. Create the free OCI VM

The OCI console wording can change slightly. Oracle's canonical reference is
[Creating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm).

1. Sign in to OCI and verify that the selected region is your **home region**.
   Always Free block storage must be created there.
2. Open **Compute → Instances → Create instance**.
3. Name the instance `slideforge`.
4. Under image, click **Change image**, select **Canonical Ubuntu**, and choose
   an **Ubuntu 24.04** ARM64 image marked **Always Free eligible**.
5. Under shape, click **Change shape**, select **Ampere**, then
   `VM.Standard.A1.Flex`.
6. Set **2 OCPUs** and **12 GB memory**. Do not exceed the current Always Free
   allowance shown in your tenancy.
7. Create a new VCN and public subnet if you do not already have them. Keep
   **Assign a public IPv4 address** enabled.
8. Under SSH keys, choose **Paste public keys** and paste the contents of
   `~/.ssh/slideforge_oci.pub`.
9. Set the boot volume to **100 GB**. This leaves part of the documented 200 GB
   allowance unused for backup/other volume needs.
10. Verify that the page says **Always Free eligible** and shows no recurring
    charge, then click **Create**.
11. Wait until the instance state is **Running**. Copy its public IPv4 address
    into `OCI_PUBLIC_IP` in your private note.

If OCI reports no A1 capacity, do not choose a paid shape. Try another
availability domain in the same home region or retry later.

## 5. Open only the required OCI network ports

In OCI:

1. Open the `slideforge` instance.
2. Click its primary VNIC, then click the subnet.
3. Open the subnet's default security list.
4. Keep or add a **stateful ingress** rule for SSH:
   - Source type: `CIDR`
   - Source: your current public IP followed by `/32`
   - IP protocol: `TCP`
   - Destination port: `22`
5. Add a stateful ingress rule for HTTP:
   - Source: `0.0.0.0/0`
   - IP protocol: `TCP`
   - Destination port: `80`
6. Add a stateful ingress rule for HTTPS:
   - Source: `0.0.0.0/0`
   - IP protocol: `TCP`
   - Destination port: `443`
7. Keep the default egress rule that allows outbound traffic.

You can discover your current public IP from your computer with:

```bash
curl -4 https://ifconfig.me
```

Do not expose ports 5432, 8000, 8080, or ONLYOFFICE directly. OCI explains the
rule model in its [Security Rules documentation](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

## 6. Connect to the VM and patch Ubuntu

From your computer, replace `OCI_PUBLIC_IP` with the recorded address:

```bash
ssh -i ~/.ssh/slideforge_oci ubuntu@OCI_PUBLIC_IP
```

The remaining commands in this guide run on the VM unless explicitly marked
"on your computer."

Update Ubuntu and install base utilities:

```bash
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
sudo apt install -y ca-certificates curl git gnupg openssl ufw
sudo reboot
```

Wait about one minute, then reconnect with the same SSH command.

Configure the VM firewall:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Expected: SSH, 80/tcp, and 443/tcp are allowed; the default incoming policy is
deny.

## 7. Install Docker Engine and Compose

Use Docker's signed Ubuntu repository, following the
[official Docker installation instructions](https://docs.docker.com/engine/install/ubuntu/):

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

Log out and reconnect so the new `docker` group membership applies:

```bash
exit
```

On your computer, reconnect:

```bash
ssh -i ~/.ssh/slideforge_oci ubuntu@OCI_PUBLIC_IP
```

Verify the installation:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Expected: the server architecture is `linux/arm64`, Compose prints a version,
and `hello-world` prints a success message.

## 8. Clone SlideForge

For a public repository:

```bash
sudo mkdir -p /opt/slideforge
sudo chown ubuntu:ubuntu /opt/slideforge
git clone https://github.com/skyfalljoss/slide-creator.git /opt/slideforge
cd /opt/slideforge
git branch --show-current
```

Expected branch: `main`.

If GitHub says the repository is private or not found, use a read-only deploy
key instead:

```bash
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/slideforge_github -C slideforge-deploy
cat ~/.ssh/slideforge_github.pub
```

In GitHub, open the repository, then **Settings → Deploy keys → Add deploy
key**. Paste the public key, name it `slideforge-oci`, and leave **Allow write
access** unchecked. Then run on the VM:

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
GIT_SSH_COMMAND='ssh -i ~/.ssh/slideforge_github' git clone git@github.com:skyfalljoss/slide-creator.git /opt/slideforge
cd /opt/slideforge
git branch --show-current
```

## 9. Create the DuckDNS hostname and updater

In the DuckDNS dashboard:

1. Enter your chosen `DUCKDNS_SLUG` without `.duckdns.org`.
2. Click **add domain**.
3. Enter the VM's public IPv4 address and click **update ip**.

On the VM, create the protected updater configuration:

```bash
sudo nano /etc/duckdns.env
```

Paste the following two lines, replacing the values from your private note:

```dotenv
DUCKDNS_DOMAIN=slideforge-demo
DUCKDNS_TOKEN=the-token-shown-by-duckdns
```

Save in Nano with `Ctrl+O`, Enter, then `Ctrl+X`. Protect it:

```bash
sudo chown root:root /etc/duckdns.env
sudo chmod 600 /etc/duckdns.env
```

Create the update script:

```bash
sudo nano /usr/local/sbin/duckdns-update
```

Paste:

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

Save, then install the permissions and systemd units:

```bash
sudo chmod 700 /usr/local/sbin/duckdns-update
sudo nano /etc/systemd/system/duckdns-update.service
```

Paste:

```ini
[Unit]
Description=Update the SlideForge DuckDNS address
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/duckdns-update
```

Create the timer:

```bash
sudo nano /etc/systemd/system/duckdns-update.timer
```

Paste:

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

Enable and test it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now duckdns-update.timer
sudo systemctl start duckdns-update.service
sudo journalctl -u duckdns-update.service -n 20 --no-pager
systemctl list-timers duckdns-update.timer
```

Expected: the service exits successfully and the timer has a next-run time.
DuckDNS's [Linux update documentation](https://www.duckdns.org/install.jsp)
describes the same update endpoint.

Check DNS, replacing the hostname:

```bash
getent ahostsv4 slideforge-demo.duckdns.org
```

Expected: it includes `OCI_PUBLIC_IP`. Wait several minutes if DNS has not
propagated.

## 10. Configure SlideForge

Create two independent random application secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Copy the first output as the PostgreSQL password and the second as the
ONLYOFFICE JWT secret. Do not reuse either as the browser password.

Create the environment file:

```bash
cd /opt/slideforge
cp .env.example .env
nano .env
```

Replace the entire file with the following. Replace the hostname and both
generated secrets. The `disabled-*` values are required by current Compose
interpolation but are not contacted when `STORAGE_PROVIDER=local`.

```dotenv
POSTGRES_PASSWORD=PASTE_FIRST_RANDOM_HEX_VALUE
ONLYOFFICE_JWT_SECRET=PASTE_SECOND_RANDOM_HEX_VALUE
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

Save and protect the file:

```bash
chmod 600 .env
docker compose --env-file .env config --quiet
```

Expected: `config --quiet` exits without output. If it reports an unset
variable, edit `.env` and provide that value before continuing.

## 11. Start SlideForge

Building and pulling the large ONLYOFFICE image can take several minutes:

```bash
cd /opt/slideforge
make stack-up
docker compose --env-file .env ps
```

Wait until `postgres`, `onlyoffice`, `backend`, and `web` are healthy. Recheck
every 20–30 seconds:

```bash
docker compose --env-file .env ps
```

Test the private host binding:

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/v1/health
sudo ss -ltnp | grep 8080
```

Expected: `/healthz` returns `ok`, the API returns JSON with a healthy status,
and port 8080 is bound to `127.0.0.1`, not `0.0.0.0`.

If a service fails, inspect logs:

```bash
docker compose --env-file .env logs --tail=200 postgres onlyoffice backend web
```

Do not continue to TLS until the local health checks pass.

## 12. Install Caddy, HTTPS, and the browser password

Install Caddy from its
[official Ubuntu repository](https://caddyserver.com/docs/install):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Generate the Basic Authentication password hash interactively:

```bash
caddy hash-password
```

Enter `APP_PASSWORD` when prompted. Caddy does not echo it. Copy the resulting
hash.

Edit Caddy's configuration:

```bash
sudo nano /etc/caddy/Caddyfile
```

Paste the following, replacing the hostname, username, and hash. The hash must
remain on one line.

```caddyfile
slideforge-demo.duckdns.org {
    encode zstd gzip

    basic_auth {
        slideforge PASTE_CADDY_PASSWORD_HASH
    }

    reverse_proxy 127.0.0.1:8080
}
```

Validate, format, and activate it:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Caddy obtains a public certificate automatically when DNS points at the VM and
ports 80/443 are open. See Caddy's
[Automatic HTTPS documentation](https://caddyserver.com/docs/automatic-https).

If certificate issuance fails, inspect:

```bash
sudo journalctl -u caddy -n 100 --no-pager
getent ahostsv4 slideforge-demo.duckdns.org
sudo ufw status verbose
```

## 13. Verify the public deployment

On your computer, replace the hostname and username:

```bash
curl -I https://slideforge-demo.duckdns.org
curl -u slideforge https://slideforge-demo.duckdns.org/healthz
curl -u slideforge https://slideforge-demo.duckdns.org/api/v1/health
```

The first request should return `401 Unauthorized`. The authenticated commands
prompt for `APP_PASSWORD` and should return `ok` and healthy JSON.

Open `https://slideforge-demo.duckdns.org` in a browser and enter the Basic
Authentication username and password. Complete this smoke test:

1. Open the create page.
2. Generate a small deck with the prompt `Create a three-slide quarterly update`.
3. Confirm slide previews render.
4. Save the deck.
5. Open it in the ONLYOFFICE editor.
6. Change one text element and save.
7. Export and download the PPTX.

Then reboot the VM:

```bash
sudo reboot
```

After two to three minutes, confirm the site returns and the saved deck still
exists. This verifies Docker restart policies and named-volume persistence.

## 14. Configure nightly local backups

Create a protected backup directory:

```bash
sudo install -d -m 0700 -o ubuntu -g ubuntu /var/backups/slideforge
sudo nano /usr/local/sbin/slideforge-backup
```

Paste:

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

Save and set permissions:

```bash
sudo chown root:root /usr/local/sbin/slideforge-backup
sudo chmod 755 /usr/local/sbin/slideforge-backup
sudo nano /etc/systemd/system/slideforge-backup.service
```

Paste:

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

Create the timer:

```bash
sudo nano /etc/systemd/system/slideforge-backup.timer
```

Paste:

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

Enable it and run the first backup now:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now slideforge-backup.timer
sudo systemctl start slideforge-backup.service
sudo journalctl -u slideforge-backup.service -n 50 --no-pager
sudo ls -lh /var/backups/slideforge
systemctl list-timers slideforge-backup.timer
```

Expected: one `.sql.gz` and one `.tar.gz` file exist, the service succeeded,
and the timer has a next-run time.

Create a free OCI boot-volume backup after the deployment is verified:

1. In OCI, open **Block Storage → Boot Volumes**.
2. Select the `slideforge` instance's boot volume.
3. Click **Create manual backup** and name it with the UTC date.
4. Confirm it is covered by the remaining Always Free backup allowance before
   creating it.
5. Keep no more than the documented free number of volume backups.

## 15. Test database restoration

List backups and choose the newest database file:

```bash
sudo ls -1t /var/backups/slideforge/postgres-*.sql.gz
```

Run a restore drill without touching the live database. Replace the backup
filename in the first command:

```bash
cd /opt/slideforge
BACKUP=/var/backups/slideforge/postgres-20260630T020000Z.sql.gz
gzip -t "$BACKUP"
docker compose --env-file .env exec -T postgres createdb --username slideforge slideforge_restore
gunzip -c "$BACKUP" | docker compose --env-file .env exec -T postgres psql --username slideforge --dbname slideforge_restore --set ON_ERROR_STOP=1 --single-transaction
docker compose --env-file .env exec -T postgres psql --username slideforge --dbname slideforge_restore --command 'SELECT count(*) FROM decks;'
docker compose --env-file .env exec -T postgres dropdb --username slideforge slideforge_restore
```

Expected: gzip validation succeeds, restore completes without SQL errors, the
query returns a count, and the disposable database is removed.

Inspect the deck archive without changing live files:

```bash
LATEST_DECK_BACKUP="$(sudo find /var/backups/slideforge -maxdepth 1 -type f -name 'deck-files-*.tar.gz' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
sudo tar -tzf "$LATEST_DECK_BACKUP" | head
```

## 16. Update SlideForge safely

Run these commands from the VM. Do not update while someone is editing a deck.

```bash
cd /opt/slideforge
git status --short
git rev-parse HEAD | tee /tmp/slideforge-previous-revision
sudo systemctl start slideforge-backup.service
make onlyoffice-shutdown
git fetch origin main
git pull --ff-only origin main
make stack-up
docker compose --env-file .env ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

`git status --short` should print nothing. If it lists files, stop and resolve
the local modifications before pulling. After the update, repeat the browser
generation/edit/export smoke test.

## 17. Roll back an application update

Use rollback only after saving the failed-update logs and identifying the last
known-good revision:

```bash
cd /opt/slideforge
PREVIOUS_REVISION="$(cat /tmp/slideforge-previous-revision)"
make onlyoffice-shutdown
git switch --detach "$PREVIOUS_REVISION"
make stack-up
docker compose --env-file .env ps
curl --fail http://127.0.0.1:8080/api/v1/health
```

If the failed release applied a database migration that the old release cannot
read, do not repeatedly restart it. Restore the pre-update database backup in a
maintenance window. Return to the tracked branch after the issue is corrected:

```bash
git switch main
git pull --ff-only origin main
```

## 18. Routine operations

Check status:

```bash
cd /opt/slideforge
docker compose --env-file .env ps
systemctl status caddy --no-pager
systemctl list-timers duckdns-update.timer slideforge-backup.timer
df -h /
free -h
```

Read recent logs:

```bash
cd /opt/slideforge
docker compose --env-file .env logs --tail=200 backend onlyoffice web
sudo journalctl -u caddy -n 100 --no-pager
```

Gracefully stop the application:

```bash
cd /opt/slideforge
make stack-down
```

Start it again:

```bash
cd /opt/slideforge
make stack-up
```

Never run `docker compose down -v`; the `-v` option deletes the named volumes
that contain PostgreSQL and deck files.

## 19. Common failures

### OCI says out of capacity

Try a different availability domain in the home region or retry later. Do not
silently choose a paid compute shape.

### Caddy cannot obtain a certificate

Confirm DuckDNS resolves to the VM, OCI and UFW allow ports 80/443, and no other
service owns those ports:

```bash
getent ahostsv4 slideforge-demo.duckdns.org
sudo ss -ltnp | grep -E ':(80|443) '
sudo journalctl -u caddy -n 100 --no-pager
```

### The site returns 502

Caddy is running but the internal web container is unavailable:

```bash
curl -v http://127.0.0.1:8080/healthz
cd /opt/slideforge
docker compose --env-file .env ps
docker compose --env-file .env logs --tail=200 web backend
```

### ONLYOFFICE does not load

Confirm its container health and that the public URL uses HTTPS plus the
`/onlyoffice` suffix:

```bash
cd /opt/slideforge
grep '^ONLYOFFICE_PUBLIC_URL=' .env
docker compose --env-file .env ps onlyoffice
docker compose --env-file .env logs --tail=200 onlyoffice backend web
```

### The VM becomes unresponsive

Use the OCI console to inspect CPU and memory, then use its serial console if
SSH is unavailable. Once connected, check:

```bash
free -h
df -h /
docker stats --no-stream
```

If normal editing exhausts 12 GB RAM, the fully free target is not large enough
for that workload. Reduce concurrency or move to a paid VM; do not remove
resource safeguards without measuring the effect.
