# Online MotionClone

The Sites frontend is in `C:\code\motionclone-waitlist`; the validated online release is in the `motionclone-online` worktree at `C:\code\motionclone-online-release`. The normal local app remains on port 4319 with its existing data and login.

## Identity and credentials

Sites handles browser sign-in. Its server signs each engine request with HMAC-SHA256, binding the user ID, method, path/query, content type, range, timestamp, nonce, and body digest. The gateway verifies the signature before reading an upload, verifies its body, and rejects replays and timestamps older than 30 seconds. It accepts only the app's explicit route families. User credentials, cookies, and email are never forwarded from Sites to the engine.

Each signed user ID maps to a SHA-256 directory below `data/.hosted/users`. Every user gets a separate Python process, project directory, and `CODEX_HOME`. The process environment is allowlisted; it never inherits the owner's Codex home, API keys, cloud credentials, or gateway secret. The Windows Job Object contains only that new worker and its descendants. Workers bind loopback only.

The official Codex App Server owns device-code OAuth, token storage, and refresh. MotionClone exposes only the verification URL, one-time code, connection status, email, and plan. Password entry happens on OpenAI's site. Changing or disconnecting an account is blocked during a rebuild. A new rebuild requires the user's own authenticated ChatGPT connection. Provider plan restrictions and usage limits still apply.

Reference: [Codex App Server account flow](https://learn.chatgpt.com/docs/app-server#3b-log-in-with-chatgpt-device-code-flow).

## Start the processing host

The private `data/.hosted/settings.json` holds a generated `secret`, gateway `port` (4320), and `max_users` (3). It is excluded from Git. Start the gateway with the project virtualenv:

```powershell
.venv\Scripts\python.exe scripts/serve-hosted.py
```

Run background launches with a hidden window. The gateway must stay running; the normal local app is separate. Hosted API traffic must reach this gateway, never the original local server on port 4319. On Windows, grant only the operating account and SYSTEM access to `data/.hosted`.

The website requires `MOTIONCLONE_ENGINE_URL` and secret `MOTIONCLONE_GATEWAY_SECRET`, configured through Sites and followed by deployment. The latter must match the private gateway configuration. Use a stable authenticated HTTPS tunnel or reverse proxy for an always-on host.

The initial beta connection uses an ephemeral Cloudflare quick tunnel to port 4320. It works only while the PC, gateway, and tunnel run. Restarting the tunnel changes its address; update `MOTIONCLONE_ENGINE_URL` and redeploy. No scheduled restart or always-on guarantee is installed.

## Limits

- Three active user workers; one reconstruction per user. Busy visitors receive an explicit retry response.
- Five account-connection attempts per minute and ten rebuild starts/retries per hour per user. Rate counters reset if the gateway restarts.
- 25 MB browser uploads; supported public video links use the existing 250 MB/120-second media limits.
- Twenty projects or 2 GB per user before new imports/copies are blocked. These are beta admission limits, not filesystem quotas; render scratch data can exceed them.
- Hosted links are restricted to X, YouTube, Vimeo, and their known media CDN domains. Private/local addresses and non-HTTPS URLs are rejected. The local app retains its existing direct-link behavior.
- Disconnected workers are reclaimed after 30 minutes when no reconstruction is active; projects and account state remain on disk. An interrupted job can be retried.
- File storage is process-separated, not a container or OS-account boundary. Keep the engine dedicated to trusted constrained scene generation. Do not enable model shell tools or arbitrary generated executable projects.

For account data deletion, stop that user's worker and remove only their verified hashed directory after exporting requested projects. Keep gateway settings and other users intact. No automatic deletion job is installed.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The new tests cover credential isolation, required authentication, device-code lifecycle, signature/body/path binding, replay rejection, rate limiting, and separate tenant paths. Runtime checks verified distinct empty libraries, no inherited owner login, real OpenAI device-code start/cancel, link retention, and desktop/mobile forms. A completed online rebuild still requires a person to finish their own ChatGPT sign-in and submit a reference.
