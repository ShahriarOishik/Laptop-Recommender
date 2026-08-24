# Deploying to Oracle Cloud (OCI) Free Tier — Beginner Guide

This walks through deploying **both** the backend (FastAPI + FAISS + embedding model) and the
frontend (React SPA) to Oracle Cloud Infrastructure's **Always Free** tier, entirely on one
compute instance, with real console click-paths and exact values — not "configure as needed."

**Who this is for:** you've never used OCI before. Every setting below says exactly where to
find it and what to put in it. Sections marked **(optional/advanced)** can be skipped on a
first pass.

**Time estimate:** 45–90 minutes for a first deploy (most of it waiting for `pip install` to
build on the VM), assuming no capacity issues (see the [capacity gotcha](#a-heads-up-about-capacity)
below — this is the single most common OCI Free Tier snag and has nothing to do with this
project).

---

## Table of Contents

1. [What you'll end up with](#what-youll-end-up-with)
2. [A heads-up about capacity](#a-heads-up-about-capacity)
3. [Step 1 — Create an OCI account](#step-1--create-an-oci-account)
4. [Step 2 — Create the compute instance](#step-2--create-the-compute-instance)
5. [Step 3 — Open the network ports (the #1 OCI gotcha)](#step-3--open-the-network-ports-the-1-oci-gotcha)
6. [Step 4 — Connect and install Docker](#step-4--connect-and-install-docker)
7. [Step 5 — Get the code onto the instance](#step-5--get-the-code-onto-the-instance)
8. [Step 6 — Choose your metadata backend](#step-6--choose-your-metadata-backend)
9. [Step 7 — Configure the backend `.env`](#step-7--configure-the-backend-env)
10. [Step 8 — Build and run the backend](#step-8--build-and-run-the-backend)
11. [Step 9 — Verify the backend works](#step-9--verify-the-backend-works)
12. [Step 10 — Build and serve the frontend](#step-10--build-and-serve-the-frontend)
13. [Step 11 — Keep it running after reboot/crash](#step-11--keep-it-running-after-rebootcrash)
14. [Step 12 — HTTPS with a real domain (optional/advanced)](#step-12--https-with-a-real-domain-optionaladvanced)
15. [Troubleshooting](#troubleshooting)
16. [What's actually free, and the limits](#whats-actually-free-and-the-limits)

---

## What you'll end up with

One "Always Free" ARM (Ampere A1) compute instance running:
- The FastAPI backend in Docker, listening on port 7860, reachable at `http://<your-public-ip>:7860`.
- The React frontend, built as static files and served by nginx on port 80, reachable at
  `http://<your-public-ip>`.

No credit card charges as long as you stay within the Always Free limits described at the end
of this guide (which this project comfortably fits inside).

---

## A heads-up about capacity

OCI's free Ampere A1 (ARM) shape is popular and specific regions/availability domains
frequently show **"Out of host capacity"** when you try to create an instance. This is an OCI
platform limitation, not something you're doing wrong. If you hit it, in order of effort:

1. **Switch Availability Domain.** On the create-instance form, under "Placement," change
   **Availability Domain** from AD-1 to **AD-2** or **AD-3** (if your region has more than one)
   and retry. This alone resolves it most of the time.
2. **Ask for less.** If a 2 OCPU / 12GB request fails everywhere, try 1 OCPU / 6GB instead — a
   smaller request can fit into capacity gaps a larger one can't. This project still runs fine
   there (realistic usage is ~1.5–2.5GB — see [RAM sizing](#ram-sizing-for-this-project)).
3. **Just retry later.** Capacity frees up unpredictably as other people's instances terminate —
   a few minutes to a few hours later often just works, no config change needed.
4. **(Advanced) Automate the retry.** If you don't want to sit there clicking "Create" every few
   minutes, install the [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm),
   run `oci setup config` once (it walks you through generating an API key and linking it to
   your account — needs your tenancy/user OCIDs, both shown in the console under your profile
   menu → "Tenancy" / "User Settings"), then loop the create-instance call:
   ```bash
   until oci compute instance launch \
     --availability-domain "<AD-1, or whichever you're trying>" \
     --compartment-id "<your compartment OCID>" \
     --shape "VM.Standard.A1.Flex" \
     --shape-config '{"ocpus": 2, "memoryInGBs": 12}' \
     --image-id "<the Ubuntu image OCID for your region>" \
     --subnet-id "<your subnet OCID>" \
     --display-name "laptop-recommender" \
     --assign-public-ip true \
     --metadata "{\"ssh_authorized_keys\": \"$(cat ~/.ssh/id_rsa.pub)\"}"
   do
     echo "still out of capacity, retrying in 60s..."
     sleep 60
   done
   ```
   All the OCID values it needs are visible in the console (compartment/image/subnet OCIDs each
   have a "Copy" button next to them on their respective list/detail pages). This is genuinely
   optional — most people never need it, since option 1 or 3 above resolves it within a day.
5. If you're still setting up your account, some regions have better free-tier availability than
   others — during signup, picking a less crowded home region can help, but you generally can't
   change your home region after the fact.

This is the most common reason a first-time OCI deploy stalls. It's not a project-specific
issue — keep retrying the create-instance step.

---

## Step 1 — Create an OCI account

1. Go to Oracle's cloud sign-up page and create a free account. You'll need a phone number and
   a credit/debit card **for identity verification only** — Oracle explicitly does not charge it
   unless you deliberately upgrade to a paid account later.
2. Pick your **Home Region** during signup. This cannot easily be changed later, but for a
   single small project any region works — pick one geographically close to you for lower
   latency.
3. Once your account is active, you'll land on the **OCI Console** (`cloud.oracle.com`).

**Skip:** you do not need to set up a paid subscription, budgets/cost alerts, or any add-on
services for this guide.

---

## Step 2 — Create the compute instance

**Where:** hamburger menu (☰, top-left) → **Compute** → **Instances** → **Create Instance**.

Fill in each section as follows:

| Field | Where in the form | What to set |
|---|---|---|
| Name | Top of the form | Anything, e.g. `laptop-recommender` |
| Compartment | Top of the form | Leave as your root/default compartment (fine for a solo project) |
| Placement → Availability Domain | "Placement" section | Leave default; change here if you hit the capacity issue above |
| Image and shape → Image | Click "Edit" next to it | Choose **Canonical Ubuntu 22.04** (or 24.04) — click "Change Image" if it's not already selected |
| Image and shape → Shape | Click "Change Shape" | Choose **Ampere** → **VM.Standard.A1.Flex** (this is the ARM Always Free shape) |
| Shape → OCPUs | Same panel | **2** (leaves headroom to run a second small instance later if you want, out of the 4 total Always Free OCPUs) |
| Shape → Memory (GB) | Same panel | **12** (out of 24 total Always Free GB) — see [why this is plenty](#ram-sizing-for-this-project) below |
| Networking → Virtual cloud network | "Networking" section | Leave "Create new virtual cloud network" selected — the defaults are fine |
| Networking → Subnet | Same section | Leave "Create new public subnet" selected |
| Networking → Public IPv4 address | Same section | Leave **"Assign a public IPv4 address"** checked — you need this to reach the instance |
| Add SSH keys | "Add SSH keys" section | See below |
| Boot volume | "Boot volume" section (may need "Show advanced options") | Leave the default size (~50GB) — this project needs well under that |

**SSH keys — if you don't already have an SSH key pair:**
- Select **"Generate a key pair for me"**.
- Click **"Save private key"** and **"Save public key"** — save the private key file (`.key` or
  no extension) somewhere safe; you cannot download it again later. You'll need it to log in.
- If you're on Windows, also consider downloading the `.ppk` version if you'll use PuTTY, or use
  the `.key` file directly with `ssh` from PowerShell/WSL/Git Bash.

Click **Create**. The instance takes 1–2 minutes to provision. Once it shows **Running**, note
its **Public IP Address** shown on the instance's detail page — you'll use it constantly from
here on.

### RAM sizing for this project

The backend only loads **one** FAISS index pair (chunk-level + laptop-level, for whichever
`DEFAULT_INDEX` is configured — `hnsw` by default, ~440MB) at startup, not all five — other
index types load lazily only if a request actually asks for them. Combined with the embedding
model (~440MB of weights, ~800MB–1GB resident once loaded with its framework overhead) and
normal OS/Python overhead, realistic usage sits around 1.5–2.5GB, comfortably under the 12GB
recommended above even with headroom for every index type eventually being cached.

---

## Step 3 — Open the network ports (the #1 OCI gotcha)

OCI has **two separate firewalls** you must both configure, or nothing will be reachable from
outside. This trips up almost everyone new to OCI.

### 3a. The OCI Security List (cloud-level firewall)

**Where:** ☰ → **Networking** → **Virtual Cloud Networks** → click the VCN that was created for
you → click the **subnet** name (something like `subnet-...`) → click the **Default Security
List** → **Add Ingress Rules**.

Add these two rules (click "Another Ingress Rule" for the second one):

| Field | Rule 1 (backend) | Rule 2 (frontend) |
|---|---|---|
| Source Type | CIDR | CIDR |
| Source CIDR | `0.0.0.0/0` | `0.0.0.0/0` |
| IP Protocol | TCP | TCP |
| Destination Port Range | `7860` | `80` |
| Description | Backend API | Frontend |

`0.0.0.0/0` means "anyone on the internet" — fine for a course-project demo. Port 22 (SSH) is
already open by default from instance creation.

### 3b. The instance's own OS firewall (iptables)

Oracle's Ubuntu images ship with `iptables` rules that **also** block incoming traffic by
default, on top of the Security List above. You must open the same ports here too. Do this
after you SSH in (next step):

```bash
sudo iptables -I INPUT -p tcp --dport 7860 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save   # makes the rules survive a reboot
```

If `netfilter-persistent` isn't installed: `sudo apt-get install -y iptables-persistent` first
(it'll prompt to save current rules — say yes).

**Skip for now:** port 443 (HTTPS) — only needed if you do the optional HTTPS section later.

---

## Step 4 — Connect and install Docker

Connect via SSH (replace with your key file and instance IP):

```bash
chmod 400 /path/to/your-private-key.key
ssh -i /path/to/your-private-key.key ubuntu@<your-public-ip>
```

(The default username on Oracle's Ubuntu image is `ubuntu`, not `root`.)

Once connected, install Docker:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git nginx

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Let your user run docker without sudo (log out and back in after this)
sudo usermod -aG docker $USER
exit
```

Log back in (`ssh -i ... ubuntu@<ip>` again) so the group change takes effect, then confirm:

```bash
docker --version
```

We also installed `nginx` and `git` above since you'll need both shortly.

---

## Step 5 — Get the code onto the instance

```bash
git clone https://github.com/<your-username>/laptop_recommender.git
cd laptop_recommender
```

(Use your actual repo URL — if you followed the earlier push, that's
`https://github.com/ashikonik/laptop_recommender.git`.)

---

## Step 6 — Choose your metadata backend

The backend stores chunk text/metadata in one of two places, controlled by
`METADATA_BACKEND`. Pick one:

### Option A — Qdrant Cloud (recommended if you already have one)

If you already set up a Qdrant Cloud cluster earlier in this project (during the evaluation
round, using `scripts/upload_qdrant.py --recreate`), **reuse it** — this is the least work,
since the data's already there and correct. You just need its URL and API key, which you'd
have saved when you created that cluster. This is also what the project's own `Dockerfile`/
`.dockerignore` are already built around (the large `qdrant_records.parquet` file is
deliberately excluded from the Docker image for this reason).

If you don't have one yet: sign up free at `cloud.qdrant.io`, create a free-tier cluster
(1GB RAM is enough — this dataset needs roughly 393MB), grab its URL and API key from the
cluster's dashboard, then from a machine with the full repo and Python set up, run:

```bash
cd Backend
python scripts/upload_qdrant.py --recreate
```

(This needs `QDRANT_URL`/`QDRANT_API_KEY` set as environment variables when you run it — it's a
one-time upload, not something you run on the OCI instance itself.)

### Option B — Self-contained, no external service

Skip Qdrant Cloud entirely and serve everything from the one OCI instance. This needs one small
change: `Backend/.dockerignore` currently excludes `artifacts/qdrant_records.parquet` (413MB)
from the Docker image, since it's not needed for Option A. To use Option B instead, remove that
one line so the file gets baked into the image:

```bash
sed -i '/^artifacts\/qdrant_records.parquet$/d' Backend/.dockerignore
```

You'll also need that file present locally in `Backend/artifacts/` before building (it's
gitignored — see `Backend/README.md`'s "Rebuilding Data Artifacts" section, or copy it over
from wherever you built it, e.g. the Colab rebuild output).

**Pick one option now** — it determines what you put in `.env` in the next step.

---

## Step 7 — Configure the backend `.env`

```bash
cd Backend
cp .env.example .env
nano .env
```

Set these specifically for this deployment (everything else can stay at its `.env.example`
default — see the root `README.md`'s "Backend Environment Variables" table for what each one
does):

| Variable | Set to | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | Cosmetic, but accurate |
| `CORS_ORIGINS` | `http://<your-public-ip>` | Must match exactly where the frontend will be served from (Step 10 serves it on port 80, no port suffix needed in the origin) |
| `METADATA_BACKEND` | `qdrant` (Option A) or `parquet` (Option B) | Matches your Step 6 choice |
| `QDRANT_URL` | your cluster URL | **Only if Option A** |
| `QDRANT_API_KEY` | your cluster API key | **Only if Option A** |
| `LOCAL_METADATA_FILE` | `./artifacts/qdrant_records.parquet` | **Only if Option B** |
| `TRUST_FORWARDED_FOR` | `false` | Leave false — you're not behind a reverse proxy that sets this header correctly (unless you also do the optional nginx-reverse-proxy-for-the-API setup, which this guide doesn't cover) |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` | your keys, or leave blank | Optional — with none set, `/chat` still returns a grounded, retrieval-only answer (no LLM narrative text) |

**Skip:** `PORT` (already correct at 7860 for this setup), `EMBEDDING_DEVICE` (leave `cpu` —
Ampere A1 has no GPU), anything under the LLM circuit-breaker/cache tuning section (defaults are
fine).

Save and exit (`Ctrl+O`, Enter, `Ctrl+X` in nano).

---

## Step 8 — Build and run the backend

```bash
cd ~/laptop_recommender/Backend
docker build -t laptop-backend .
```

This step is slow the first time — expect 5–15 minutes on a 2-OCPU instance, since it's
compiling/downloading `torch`, `faiss-cpu`, and friends for ARM64. This is normal; let it finish.

> If this step fails with something like "no matching distribution found" for `torch` or
> `faiss-cpu`, see [Troubleshooting](#troubleshooting) — it usually means no prebuilt ARM64
> wheel exists for that exact package version, which is rare but does happen.

Once built, run it:

```bash
docker run -d \
  --name laptop-backend \
  --restart unless-stopped \
  -p 7860:7860 \
  --env-file .env \
  laptop-backend
```

- `-d` — run in the background.
- `--restart unless-stopped` — survives a `docker` daemon restart or VM reboot automatically
  (more on this in Step 11).
- `-p 7860:7860` — exposes the container's port 7860 on the host's port 7860 (the one you
  opened in Step 3).
- `--env-file .env` — loads everything you set in Step 7.

Watch the startup logs (loading the embedding model + FAISS index takes 15–60 seconds):

```bash
docker logs -f laptop-backend
```

`Ctrl+C` to stop watching (the container keeps running).

---

## Step 9 — Verify the backend works

From the OCI instance itself:

```bash
curl http://localhost:7860/health
```

You should get back JSON with `"status": "ready"`. If it says `"degraded"`, check
`docker logs laptop-backend` for what failed to load (usually a `.env` value that's wrong — the
`errors` field in the response tells you which subsystem).

From your **own computer** (proves the network ports are actually open):

```bash
curl http://<your-public-ip>:7860/health
```

If this hangs or times out but the `localhost` version worked, go back to
[Step 3](#step-3--open-the-network-ports-the-1-oci-gotcha) — you're missing either the Security
List rule or the iptables rule.

Try an actual query:

```bash
curl -X POST http://<your-public-ip>:7860/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "lightweight laptop under $800 for college"}'
```

---

## Step 10 — Build and serve the frontend

Building the frontend needs Node.js, which isn't installed yet:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node --version   # should print v20.x or newer
```

Build it:

```bash
cd ~/laptop_recommender/Frontend
cp .env.example .env.local
```

Edit `.env.local` (`nano .env.local`) and set:

| Variable | Set to |
|---|---|
| `VITE_API_BASE_URL` | `http://<your-public-ip>:7860` |
| `VITE_USE_MOCK_API` | `false` (or leave unset — false is the default) |

Then build:

```bash
npm install
npm run build
```

This produces static files in `Frontend/dist/`. Serve them with nginx:

```bash
sudo rm -rf /var/www/html/*
sudo cp -r dist/* /var/www/html/
```

nginx is already running on port 80 by default after installation (Step 4) and needs no further
config to serve static files from `/var/www/html/` — but React apps use client-side routing, so
add one nginx setting so refreshing a page like `/laptop/123` doesn't 404:

```bash
sudo tee /etc/nginx/sites-available/default > /dev/null <<'EOF'
server {
    listen 80 default_server;
    root /var/www/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF
sudo nginx -t && sudo systemctl reload nginx
```

Visit `http://<your-public-ip>` in a browser — you should see the app, and it should be able to
reach the backend.

---

## Step 11 — Keep it running after reboot/crash

**Backend:** already handled — `--restart unless-stopped` (Step 8) means Docker restarts the
container automatically if it crashes, and if the whole VM reboots, Docker itself starts on boot
(default on Ubuntu) and brings the container back up with it.

**Frontend:** nginx is a system service and starts on boot by default — nothing extra needed.
Confirm with:

```bash
sudo systemctl is-enabled nginx    # should print "enabled"
```

If it prints "disabled": `sudo systemctl enable nginx`.

---

## Step 12 — HTTPS with a real domain (optional/advanced)

Skip this entirely for a course-project demo using the raw IP over HTTP — everything above
already works without it. If you want a real domain with HTTPS (e.g. for a portfolio piece):

1. Point a domain's DNS `A` record at your instance's public IP (outside OCI, at your domain
   registrar).
2. Open port 443 in both firewalls (repeat Step 3 with port `443` instead of `80`/`7860`).
3. Install certbot: `sudo apt-get install -y certbot python3-certbot-nginx`.
4. Run `sudo certbot --nginx -d yourdomain.com` and follow the prompts — it edits your nginx
   config and sets up auto-renewal automatically.
5. Update `VITE_API_BASE_URL` and rebuild the frontend to use `https://` instead of a bare IP,
   and update `CORS_ORIGINS` in the backend `.env` to match, then `docker restart laptop-backend`.

This also requires proxying the backend through nginx (rather than hitting port 7860 directly)
if you want it under the same HTTPS domain — that's a further nginx `location` block + setting
`TRUST_FORWARDED_FOR=true` in the backend `.env` (nginx becomes a trusted reverse proxy at that
point). Not covered step-by-step here since it's genuinely optional for this project's scope.

---

## Troubleshooting

**"Out of host capacity" when creating the instance** — see
[the capacity section](#a-heads-up-about-capacity) above. Not a config issue; keep retrying.

**`curl` to the public IP hangs/times out, but `localhost` works on the instance** — you're
missing a firewall rule. Check *both* the [OCI Security List](#3a-the-oci-security-list-cloud-level-firewall)
and [iptables](#3b-the-instances-own-os-firewall-iptables) — both must allow the port.

**`docker build` fails on a `torch`/`faiss-cpu`/`pyarrow` install step** — this means no
prebuilt ARM64 (`aarch64`) wheel exists for the exact pinned version in `requirements.txt`.
Check the error for which package, then either: relax that package's version pin slightly in
`Backend/requirements.txt` (e.g. `torch>=2.0` instead of an exact pin) and rebuild, or check
that package's PyPI page for `manylinux_aarch64` wheel availability for a nearby version.

**`/health` says `"status": "degraded"`** — read `docker logs laptop-backend` and the response's
`errors` array. Common causes: `METADATA_BACKEND=qdrant` but `QDRANT_URL`/`QDRANT_API_KEY` are
wrong or the cluster is paused; `METADATA_BACKEND=parquet` but `LOCAL_METADATA_FILE` doesn't
exist (see [Step 6, Option B](#option-b--self-contained-no-external-service)).

**Frontend loads but every request fails / shows a CORS error in the browser console** —
`CORS_ORIGINS` in the backend `.env` doesn't match the exact origin the frontend is served from
(scheme + host, no trailing slash — `http://1.2.3.4`, not `http://1.2.3.4/` or `https://1.2.3.4`).
Fix it and `docker restart laptop-backend`.

**Instance becomes unreachable after a while** — check you're not being rate-limited by your own
ISP/network, then check the instance is still `Running` in the OCI console (☰ → Compute →
Instances). If it was auto-reclaimed, see the note on idle reclamation below.

---

## What's actually free, and the limits

Everything in this guide fits inside OCI's **Always Free** tier, which (unlike a time-limited
trial) does not expire and does not require a credit card charge, provided you stay within:

- **Compute:** up to 4 Ampere A1 OCPUs and 24GB RAM total (this guide uses 2 OCPU / 12GB — well
  under the cap), OR up to 2 AMD-based Micro VMs (not used here — too little RAM for this
  project).
- **Block storage:** up to 200GB total across your boot/block volumes (this guide uses the
  default ~50GB boot volume).
- **Outbound data transfer:** 10TB/month — far more than a course-project demo will use.
- **One thing to know:** Oracle can reclaim Always Free compute instances that sit **idle**
  (near-zero CPU, network, and disk I/O) for **7 consecutive days**. A demo you check in on
  occasionally is fine; a project left completely untouched for a week+ risks reclamation. If
  you need it to survive a long idle period, a trivial cron job hitting `/health` every so often
  keeps it "active."

Qdrant Cloud's free tier (if you chose Option A) is separately limited to 1GB of RAM per
cluster — this dataset's ~393MB of vectors fits with room to spare.
