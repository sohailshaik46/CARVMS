# Gmail Email Integration Setup

CARVMS can connect a Gmail account (via Google OAuth 2.0) for two things:
reading email, and -- since the Delayed Cash Billing / Weekly Revenue
Closure decision-notification feature was added -- **sending** the
decision emails a Vigilance reviewer's Considered/Not Considered/Needs
More Detail/Needs Proof click triggers. This is opt-in (each user clicks
"Connect Email" and consents individually) and the app runs fully without
it configured -- until these steps are done, "Connect Email" simply shows
as unavailable, and decision-notification email reports "not connected"
instead of silently failing or blocking the decision.

There is no per-reviewer mailbox: whichever CARVMS user has a connected,
send-capable Gmail account is the one decision-notification email actually
goes out from -- this is "your registered email ID" in the sense that only
one account needs to be connected for the whole system.

This is a one-time setup an administrator does in Google Cloud Console.
**The two values you get at the end (Client ID and Client Secret) are
secrets -- paste them only into `backend/.env` on the server, never into
chat, a ticket, or a commit.**

## 1. Create (or choose) a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Top-left project dropdown -> **New Project** (or select an existing one
   your organization already uses for this).
3. Give it a name, e.g. `CARVMS`, and create it.

## 2. Enable the Gmail API

1. In the left sidebar: **APIs & Services -> Library**.
2. Search for "Gmail API" -> open it -> **Enable**.

## 3. Configure the OAuth consent screen

1. **APIs & Services -> OAuth consent screen**.
2. User type: **Internal** if everyone connecting is inside your Google
   Workspace organization; otherwise **External**.
3. Fill in the required app info (app name, support email).
4. Under **Scopes**, add:
   - `.../auth/gmail.readonly`
   - `.../auth/gmail.send`
   - `openid`
   - `email`
5. If you chose **External**, add each user's Gmail address under **Test
   users** while the app is in "Testing" mode (Google restricts unverified
   external apps to explicitly listed testers).
6. Save.

## 4. Create an OAuth 2.0 Client ID

1. **APIs & Services -> Credentials -> Create Credentials -> OAuth client
   ID**.
2. Application type: **Web application**.
3. Name it, e.g. `CARVMS Backend`.
4. Under **Authorized redirect URIs**, add the backend's callback URL
   exactly as it will be reached in your deployment, for example:
   - Local development: `http://localhost:8000/email/callback`
   - Production: `https://<your-carvms-domain>/email/callback`
5. Create it. Google shows you a **Client ID** and **Client Secret** --
   copy both now (the secret is only shown once, though you can always
   generate a new one later if you lose it).

## 5. Put the values in `backend/.env`

Open `backend/.env` (create it from `backend/.env.example` if it doesn't
exist yet) and fill in:

```
GOOGLE_CLIENT_ID=<the Client ID from step 4>
GOOGLE_CLIENT_SECRET=<the Client Secret from step 4>
GOOGLE_REDIRECT_URI=http://localhost:8000/email/callback
```

`GOOGLE_REDIRECT_URI` must match one of the "Authorized redirect URIs" you
registered in step 4 exactly (scheme, host, port, and path).

## 6. Generate the local token-encryption key (separate from Google)

CARVMS encrypts every stored OAuth token at rest with a key it generates
itself -- this key is **not** issued by Google and is safe to generate
locally:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the output in `backend/.env`:

```
EMAIL_TOKEN_ENCRYPTION_KEY=<generated value>
```

Losing or rotating this key makes previously-stored tokens undecryptable --
affected users would need to reconnect.

## 7. Restart the backend

```bash
cd backend
./venv/Scripts/python.exe -m uvicorn main:app --reload
```

(Note: `--reload` has been unreliable in this environment -- always verify
with a real request, not just the "Reloading..." log line. See
`backend/README.md`.)

## 8. Verify

1. Log into CARVMS as any user.
2. Go to **Settings -> Connect Email**. It should now offer a "Connect"
   button instead of "not configured".
3. Clicking Connect redirects to Google's consent screen, then back to
   CARVMS with the account shown as connected.

## What CARVMS never does

- The agent/assistant that built this integration never saw, generated, or
  requested your `GOOGLE_CLIENT_SECRET` -- that value must always come
  directly from the Google Cloud Console into `backend/.env`.
- Tokens are stored encrypted (`EMAIL_TOKEN_ENCRYPTION_KEY`) and are never
  returned by any API response; `GET /email/status` only ever reports
  connected/provider/scope/can_send/timestamp, never the token itself.
- Disconnecting (**Settings -> Connect Email -> Disconnect**) clears the
  stored tokens immediately, not just marks the row inactive.

## If you connected Gmail before `gmail.send` existed

Google never retroactively adds a new scope to a token that's already
been issued -- a connection made before this feature was added only has
`gmail.readonly`. `GET /email/status` reports this as `"can_send": false`
even though `"connected": true`, and the Settings page shows a
**Reconnect** button in that state. Reconnecting re-runs the consent
screen with `gmail.send` included and replaces the stored token.
