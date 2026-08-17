# Deploying CARVMS to the internet (Render, free tier)

This gets the app reachable from any laptop, anywhere -- not just this
machine's local network. It uses [Render](https://render.com)'s free tier
for the backend (FastAPI), the frontend (the built React app), and a real
managed Postgres database, all driven by the `render.yaml` Blueprint at the
repo root.

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
4. Render reads `render.yaml` and proposes a database plus two services:
   - `carvms-db` (a real Postgres database -- persists across restarts,
     unlike the SQLite this project started on)
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

`render.yaml` already has this deploy's real URLs baked in
(`CORS_ORIGINS`/`FRONTEND_URL` on the backend, `VITE_API_BASE_URL` on the
frontend all point at `carvms-backend.onrender.com` /
`carvms-frontend.onrender.com`) -- **for this specific deploy, there's
nothing to do here.** This step only applies if you ever fork this to a
*different* Render account:

1. Open **carvms-backend**'s dashboard page and note its actual URL --
   if `carvms-backend` was already taken by someone else's Render service,
   yours got a random suffix appended (e.g. `carvms-backend-ab12.onrender.com`).
2. Same for **carvms-frontend**.
3. If either URL differs from what's in `render.yaml`, update
   `CORS_ORIGINS`/`FRONTEND_URL` (on the backend) and `VITE_API_BASE_URL`
   (on the frontend) in the Render dashboard's Environment tab for that
   service, then save.
4. The backend just needs a restart to pick this up. The frontend needs a
   full **rebuild** since Vite bakes this value in at build time -- if
   saving doesn't auto-trigger one, use **Manual Deploy -> Clear build
   cache & deploy** to force it.

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

- **The free Postgres database (`carvms-db`) expires 30 days after
  creation.** Render then either deletes it or requires upgrading to a paid
  instance (~$7/month) to keep it. Mark your calendar -- this is the one
  real deadline in this setup. When it's time, either:
  - Upgrade `carvms-db` to a paid plan in the Render dashboard (data carries
    over, no migration needed), or
  - Hand this to your IT team's infrastructure, which is what you mentioned
    doing eventually anyway -- export the data first if so (Render's
    dashboard has a backup/export option for Postgres databases).
- **The backend "sleeps" after ~15 minutes of no traffic** on Render's free
  web-service plan, and takes 30-60 seconds to wake up on the next request
  -- the first load after a quiet period will feel slow, that's expected,
  not broken. (The database itself doesn't sleep -- only the API server
  does, so no data is at risk during that gap, just responsiveness.)
- **Optional features stay unconfigured** until you fill in their env vars
  later: Gmail OAuth (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
  `GOOGLE_REDIRECT_URI`), the Centers Master Google Sheet sync
  (`CENTERS_MASTER_SHEET_CSV_URL`), and real SMS delivery for OTP/
  escalation alerts (no provider is wired in yet at all -- see
  `docs/SMS_SETUP.md`). Nothing breaks without them; those specific features
  just report "not configured" instead of running.
- **Local dev (your laptop) and the deployed app still use separate
  databases.** Your local `.env` still points at a local SQLite file by
  default -- logging in locally uses different accounts than the deployed
  version. If you want your laptop and the deployed app to share the exact
  same data, point your local `DATABASE_URL` at `carvms-db`'s *external*
  connection string (shown on its Render dashboard page, under
  "External Connection") instead of the local sqlite default -- ask if you
  want help wiring that up.
