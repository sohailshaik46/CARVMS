# Deploying CARVMS to the internet (Render, free tier)

This gets the app reachable from any laptop, anywhere -- not just this
machine's local network. It uses [Render](https://render.com)'s free tier
for both the backend (FastAPI) and frontend (the built React app), driven by
the `render.yaml` Blueprint at the repo root.

**Read "Known limitations of this free setup" at the bottom before you rely
on this for real data.**

## 1. Push this repo to GitHub

Render deploys from a git branch it can see. This repo is already connected
to `https://github.com/sohailshaik46/CARVMS` -- push whichever branch has
this deployment setup (e.g. `deploy/render-setup`) if you haven't already:

```bash
git push -u origin deploy/render-setup
```

## 2. Create a Render account

Go to [render.com](https://render.com) and sign up (GitHub sign-in is the
fastest path since it also grants repo access in the next step). This step
has to be done by you -- account creation and payment details are things I
won't and can't do on your behalf.

## 3. Create the Blueprint

1. In the Render dashboard: **New +** -> **Blueprint**.
2. Connect your GitHub account if asked, then pick the `CARVMS` repo.
3. Pick the branch you pushed (`deploy/render-setup`, or `main` once you've
   merged).
4. Render reads `render.yaml` and proposes two services:
   - `carvms-backend` (the API)
   - `carvms-frontend` (the web app you'll actually open in a browser)
5. Before clicking **Apply**, fill in the three prompted fields (these have
   no default on purpose -- see `render.yaml`'s comments):
   - `BOOTSTRAP_ADMIN_USERNAME` -- e.g. `sohail.shaik`
   - `BOOTSTRAP_ADMIN_EMAIL` -- e.g. `sohail.shaik@nephroplus.com`
   - `BOOTSTRAP_ADMIN_PASSWORD` -- a real password; this becomes your first
     Admin login. **Change it from Settings once you're in** -- see step 6.
6. Click **Apply**. Both services build and deploy (a few minutes each).

## 4. Wire the two services together

`render.yaml` ships with placeholder URLs (`http://localhost:...`) for each
service's env vars pointing at the other, because Render only assigns the
real `https://carvms-backend-XXXX.onrender.com` / `https://carvms-frontend-
XXXX.onrender.com` URLs once a service exists -- there's no way to know them
before the first deploy. Fix this once, right after the first deploy:

1. Open **carvms-backend** -> **Environment** tab. Note this service's own
   URL, shown at the top of its dashboard page.
2. Open **carvms-frontend** -> its dashboard page shows its own URL.
3. Back in **carvms-backend** -> **Environment**, edit:
   - `CORS_ORIGINS` -> the frontend's real URL (no trailing slash), e.g.
     `https://carvms-frontend-ab12.onrender.com`
   - `FRONTEND_URL` -> the same URL
   Save -> this redeploys the backend automatically.
4. In **carvms-frontend** -> **Environment**, edit:
   - `VITE_API_BASE_URL` -> the backend's real URL, e.g.
     `https://carvms-backend-cd34.onrender.com`
   Save -> **this must trigger a rebuild, not just a restart** (Vite bakes
   this value in at build time) -- Render does this automatically on an env
   var change for static sites, but if the frontend still calls
   `localhost:8000` after saving, use **Manual Deploy -> Clear build cache &
   deploy** to force it.

## 5. Log in and lock it down

1. Open the frontend's URL. Log in with the `BOOTSTRAP_ADMIN_*` credentials
   from step 3.
2. Go to **Settings -> Users** and create real named accounts for whoever
   needs access (Admin-only action, already built into the app).
3. **Change the bootstrap Admin's password** via Settings -> Security, or
   deactivate that account entirely once real accounts exist -- it was only
   ever meant to get you in the door once.

## 6. Sharing it with your friend / anyone else

Just send them the `carvms-frontend...onrender.com` URL. They log in with
their own account (created in step 5) -- no VPN, no network requirement,
works from any laptop with internet.

---

## Known limitations of this free setup

You explicitly chose to start fully free and accept these for now -- keep
them in mind:

- **Data can be lost on redeploy or restart.** The backend stores data in a
  SQLite file on local disk. Render's free web services have no persistent
  disk, so that file resets to empty on every deploy and on every restart
  (including the automatic restart after the free tier's idle sleep). This
  is fine for a demo/trial; it is **not** safe for real ongoing billing/
  penalty data. When you're ready to stop accepting this risk, either:
  - Add a Render PostgreSQL database (free for 30 days, then ~$7/month) and
    point `DATABASE_URL` at it, or
  - Hand this to your IT team's infrastructure, which is what you mentioned
    doing eventually anyway.
- **The backend "sleeps" after ~15 minutes of no traffic** on Render's free
  plan, and takes 30-60 seconds to wake up on the next request -- the first
  load after a quiet period will feel slow, that's expected, not broken.
- **Optional features stay unconfigured** until you fill in their env vars
  later: Gmail OAuth (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
  `GOOGLE_REDIRECT_URI`), the Centers Master Google Sheet sync
  (`CENTERS_MASTER_SHEET_CSV_URL`), and real SMS delivery for OTP/
  escalation alerts (no provider is wired in yet at all -- see
  `docs/SMS_SETUP.md`). Nothing breaks without them; those specific features
  just report "not configured" instead of running.
