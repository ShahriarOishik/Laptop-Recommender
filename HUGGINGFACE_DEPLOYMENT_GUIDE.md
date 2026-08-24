# Deploying to Hugging Face Spaces (Free, No Credit Card) — Beginner Guide

An alternative to the OCI guide for when you don't want to deal with cloud capacity issues, or
just want a simpler path. Hugging Face Spaces' free **CPU basic** tier gives **16GB RAM / 2 vCPU**
— genuinely free forever, no credit card, no trial expiry — which comfortably fits this
project's real usage (~1.5–2.5GB). The frontend goes to Vercel, also free forever, no card.

**Why this is a good fit specifically for this project:** HF Spaces' Docker runtime defaults to
port 7860 — which is *already* this project's default port, so the existing `Backend/Dockerfile`
works completely unmodified, no edits needed.

**The one real tradeoff of $0 hosting (not a project compromise):** a free Space goes to sleep
after 48 hours with no visits, and "wakes up" (rebuilds/restarts, ~1-2 minutes) the next time
someone opens it. This is standard for any free-tier compute — OCI's own Always Free tier has an
equivalent idle-reclamation rule (see that guide's final section).

**Time estimate:** 20–40 minutes.

---

## Table of Contents

1. [What you'll end up with](#what-youll-end-up-with)
2. [Step 1 — Create a Hugging Face account](#step-1--create-a-hugging-face-account)
3. [Step 2 — Create the Space](#step-2--create-the-space)
4. [Step 3 — Choose your metadata backend](#step-3--choose-your-metadata-backend)
5. [Step 4 — Prepare and push the backend code](#step-4--prepare-and-push-the-backend-code)
6. [Step 5 — Set secrets](#step-5--set-secrets)
7. [Step 6 — Watch it build and verify](#step-6--watch-it-build-and-verify)
8. [Step 7 — Deploy the frontend to Vercel](#step-7--deploy-the-frontend-to-vercel)
9. [Step 8 — Point the frontend at the backend (CORS)](#step-8--point-the-frontend-at-the-backend-cors)
10. [Troubleshooting](#troubleshooting)
11. [What's actually free, and the limits](#whats-actually-free-and-the-limits)

---

## What you'll end up with

- Backend running at `https://<your-username>-<space-name>.hf.space`.
- Frontend running at `https://<your-project>.vercel.app`.

---

## Step 1 — Create a Hugging Face account

Go to `huggingface.co/join`. Email + password (or GitHub/Google sign-in) — no phone number, no
card, nothing to verify beyond your email.

---

## Step 2 — Create the Space

**Where:** click your profile icon (top-right) → **New Space**, or go directly to
`huggingface.co/new-space`.

| Field | What to set |
|---|---|
| Owner | Your username |
| Space name | e.g. `laptop-recommender-backend` |
| License | `mit` (matches this project's license) |
| Select the Space SDK | **Docker** — click it, then choose the **"Blank"** Docker template (not one of the pre-built app templates) |
| Space hardware | **CPU basic · FREE** — this is selected by default; do not change it to a paid tier |
| Visibility | **Public** (needed for the frontend to reach it without extra auth setup) — or Private if you're OK doing an extra token-auth step later, not covered here |

Click **Create Space**. You'll land on an empty Space with a git remote URL shown, something
like `https://huggingface.co/spaces/<your-username>/laptop-recommender-backend`.

**Skip:** "Space secrets" prompt if shown at creation — you'll add those properly in Step 5.

---

## Step 3 — Choose your metadata backend

Same choice as the OCI guide — pick one:

### Option A — Qdrant Cloud (recommended if you already have one)

Reuse the Qdrant Cloud cluster from earlier in this project (built via
`scripts/upload_qdrant.py --recreate`) if you still have its URL/API key saved. Least work,
smallest image to push.

### Option B — Self-contained, no external service

Skip Qdrant Cloud; bake `artifacts/qdrant_records.parquet` (413MB) into the image instead. From
your local repo:

```bash
cd Backend
sed -i '/^artifacts\/qdrant_records.parquet$/d' .dockerignore
```

You'll need that file present in `Backend/artifacts/` locally first (see `Backend/README.md`'s
"Rebuilding Data Artifacts" section if you don't have it).

**Pick one now** — it determines the secrets you set in Step 5.

---

## Step 4 — Prepare and push the backend code

HF Spaces builds whatever's at the **root** of the Space's git repo — but this project's
`Dockerfile` lives inside `Backend/`, not at the monorepo root. Rather than restructuring your
GitHub repo, create a separate local copy just for pushing to the Space:

```bash
mkdir ~/laptop-recommender-space
cd ~/laptop-recommender-space
git init
git lfs install
```

Copy the backend's contents (not the `Backend/` folder itself — its *contents*) into this new
directory:

```bash
cp -r ~/laptop_recommender/Backend/. .
```

(Adjust the source path to wherever you cloned the GitHub repo locally.)

**Large files need Git LFS** — HF's git backend requires it for files over a few MB, and FAISS
`.index` files (up to ~410MB each) aren't covered by any default LFS pattern. Track them
explicitly *before* your first commit:

```bash
git lfs track "*.index"
git lfs track "*.parquet"
git add .gitattributes
```

Create the Space's required `README.md` — this is **not optional**, it's how HF knows this is a
Docker Space and which port to use:

```bash
cat > README.md <<'EOF'
---
title: Laptop Recommender Backend
emoji: 💻
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

FastAPI RAG backend for the Laptop Recommender System. See the main repo:
https://github.com/<your-username>/laptop_recommender
EOF
```

Now commit and push everything:

```bash
git add -A
git commit -m "Initial backend deploy"
git remote add space https://huggingface.co/spaces/<your-username>/laptop-recommender-backend
git push space main
```

You'll be prompted for HF credentials — use your HF username and, as the password, a HF
**access token** (create one at `huggingface.co/settings/tokens`, "Write" role is enough,
copy it once and treat it like a password).

This push is slow the first time (uploading ~1.3GB of FAISS indexes via LFS, more if you also
included `qdrant_records.parquet` for Option B) — let it finish.

---

## Step 5 — Set secrets

**Where:** on the Space's page → **Settings** tab → **Variables and secrets** section →
**New secret** (for anything sensitive) or **New variable** (for non-sensitive config).

| Name | Type | Set to |
|---|---|---|
| `METADATA_BACKEND` | Variable | `qdrant` (Option A) or `parquet` (Option B) |
| `QDRANT_URL` | Secret | your cluster URL — **Option A only** |
| `QDRANT_API_KEY` | Secret | your cluster API key — **Option A only** |
| `LOCAL_METADATA_FILE` | Variable | `./artifacts/qdrant_records.parquet` — **Option B only** |
| `CORS_ORIGINS` | Variable | leave blank for now — set in Step 8 once you have the Vercel URL |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` | Secret | your keys, or skip entirely | 

**Skip:** `PORT` (already correct via the Dockerfile's default), `TRUST_FORWARDED_FOR` (leave
unset/false — HF's own edge proxy handling doesn't need this project to trust
`X-Forwarded-For` itself), `EMBEDDING_DEVICE` (leave `cpu` — the free tier has no GPU).

Adding/changing a secret automatically restarts the Space.

---

## Step 6 — Watch it build and verify

The Space's page shows build logs automatically. First build takes several minutes (installing
`torch`, `faiss-cpu`, etc.) — this is normal. Once it says **Running** (green dot, top of the
page), test it:

```bash
curl https://<your-username>-laptop-recommender-backend.hf.space/health
```

(Note the URL format: your username and the Space name joined by a hyphen, `.hf.space` — not
the `huggingface.co/spaces/...` URL you used for git.)

You should get `"status": "ready"`. If not, the **Logs** tab on the Space's page shows exactly
what failed (same idea as `docker logs` — usually a wrong/missing secret).

Try a real query:

```bash
curl -X POST https://<your-username>-laptop-recommender-backend.hf.space/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "lightweight laptop under $800 for college"}'
```

---

## Step 7 — Deploy the frontend to Vercel

1. Go to `vercel.com`, sign up free (GitHub sign-in is easiest — no card required for the
   Hobby plan).
2. **Add New** → **Project** → **Import** your `laptop_recommender` GitHub repo (the one from
   the earlier push in this session).
3. Vercel auto-detects it's a monorepo with multiple things in it — you need to point it at the
   frontend specifically:

| Field | What to set |
|---|---|
| Root Directory | Click "Edit" next to it, select **`Frontend`** |
| Framework Preset | Should auto-detect **Vite** once you set the root directory above |
| Build Command | Leave default (`npm run build` / auto-detected) |
| Output Directory | Leave default (`dist` / auto-detected) |

4. Before deploying, expand **Environment Variables** and add:

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<your-username>-laptop-recommender-backend.hf.space` |
| `VITE_USE_MOCK_API` | `false` |

5. Click **Deploy**. Takes 1-2 minutes. You'll get a URL like
   `https://laptop-recommender-<something>.vercel.app`.

**Skip:** custom domains, Vercel's paid tiers, any of the "Analytics"/"Speed Insights" upsells
shown during setup — none of it is needed.

---

## Step 8 — Point the frontend at the backend (CORS)

Go back to the HF Space's **Settings → Variables and secrets**, and set the `CORS_ORIGINS`
variable you skipped earlier:

```
CORS_ORIGINS=https://laptop-recommender-<something>.vercel.app
```

(Your actual Vercel URL from Step 7, no trailing slash.) Saving this restarts the Space
automatically. Once it's back to "Running," open your Vercel URL in a browser — the app should
now work end-to-end.

---

## Troubleshooting

**`git push space main` fails with something about file size / LFS** — you missed
`git lfs track` before committing. Fix: `git lfs track "*.index" "*.parquet"`, then
`git add .gitattributes && git commit -m "track large files with lfs"`, then re-add and
re-commit the actual `.index`/`.parquet` files so they get picked up as LFS pointers, then push
again.

**Space shows "Runtime error" or won't leave "Building"** — check the **Logs** tab. A missing or
wrong secret (Step 5) is the most common cause — the error there tells you exactly which
subsystem failed to initialize, same as the `/health` response's `errors` field would.

**Space works, but going idle then re-opening it is slow** — expected (cold start after 48h
sleep, ~1-2 minutes to rebuild the container and reload the embedding model). Nothing to fix;
this is the tradeoff of $0 always-on-adjacent compute. Visiting the URL wakes it — no manual
restart needed.

**Frontend loads but requests fail with a CORS error in the browser console** — `CORS_ORIGINS`
on the Space doesn't exactly match your Vercel URL (scheme + host, no trailing slash). Fix it in
Settings and let it restart.

**Vercel build fails** — almost always means "Root Directory" wasn't actually set to `Frontend`
in Step 7 (Vercel tried to build the whole monorepo root instead). Go to Project Settings →
General → Root Directory and fix it, then redeploy.

---

## What's actually free, and the limits

- **Hugging Face Spaces, CPU basic:** free forever, no card, no time limit on the account itself
  — the only "limit" is the 48-hour idle-sleep behavior described above. No compute-hour cap
  during active use.
- **Vercel Hobby plan:** free forever, no card, generous bandwidth/build-minute allowances that
  a course-project demo won't come close to hitting.
- **Qdrant Cloud free tier** (if using Option A): 1GB RAM per cluster — this dataset's ~393MB of
  vectors fits comfortably.

Nothing here is a trial or requires adding a payment method anywhere in the chain.
