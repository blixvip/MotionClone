# Development and verification

[Back to the README](../README.md)

Run commands from the repository root after completing setup.

## Project layout

| Path | Purpose |
| --- | --- |
| `app/` | FastAPI server, media processing, reconstruction, and exports |
| `web/` | Local workspace and optional showcase |
| `hyperframes/` | Locked dependencies for the current renderer |
| `remotion/` | Optional renderer for legacy projects; install it with `npm ci --prefix remotion` |
| `tests/` | Automated Python tests |
| `scripts/` | Browser acceptance checks and asset tools |
| `data/` | Local projects and media; ignored by Git |

## Checks

After setup, with the local app running:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/light_ui_acceptance.py
.venv\Scripts\python.exe scripts/final_ui_acceptance.py
```

The browser checks use isolated fixtures and do not start real AI work. To inspect an existing completed HyperFrames rebuild, use `scripts/hyperframes_acceptance.py --project YOUR_PROJECT_ID`. `scripts/generalized_acceptance.py --run-ai` is an optional real-model benchmark that uses your connected ChatGPT plan.

With the saved Nexa collection available, `scripts/simple_workspace_acceptance.py` checks local entry, thumbnails, search, opening a project, responsive layouts, playback, style selection, and the download handler. It intercepts export submission and never starts an AI job or render.

Browser scripts require Google Chrome and the app running at `http://127.0.0.1:4319`.
The `simple_workspace_acceptance.py` script specifically expects three saved Nexa projects; it is not a fresh-checkout smoke test.
For recording and export checks, see [Recording and exports](RECORDING.md).

## Account settings

The header keeps Settings, Star on GitHub, and Buy me a coffee visible on desktop and mobile. Settings shows the ChatGPT account and video-processing readiness. Local sign-in uses the existing Codex credential store; disconnecting also signs the Codex CLI out. Account changes are blocked while a reconstruction is active.

Run `python scripts/settings_acceptance.py` to check connection, device-code sign-in, cancellation, completion, disconnect, error recovery, keyboard focus, and responsive layouts. The script starts an isolated temporary app with a fake Codex account and never changes a real login. See the [official account protocol](https://learn.chatgpt.com/docs/app-server#authentication-endpoints) for the underlying sign-in flow.

Restart a running local server after updating Python code. An older server can show Settings and its existing connection status, but sign-in controls remain unavailable until restart.

## Reconstruction details

Detailed analysis uses roughly three-second sections and up to 24 individual reference frames per section. Detected flashes include neighboring frames; very short ending fragments stay with the preceding section. Detailed scene requests can use up to seven minutes within the shared eight-minute analysis budget. Custom reconstruction instructions are passed to the scene generator and included in scene checkpoint keys.

## Showcase

Localhost opens the workspace directly. The optional project showcase remains at `/?demo=1`, with a live comparison, walkthrough, setup instructions, and support links. Existing workspace and project links still work; the public site URL is unchanged.

The demo supports side-by-side or wipe comparison, playback speed, and fullscreen. A separate illustrative scene lets visitors toggle text, shapes, and the background or separate the layers. GitHub starring and the official Buy Me a Coffee button are visible in the header. Run `scripts/showcase_details_acceptance.py` to check these controls and mobile layouts.

Build a portable static version with `python scripts/build_showcase.py`. Serve the generated `site/` folder on a static host. It contains only the landing page, original illustrative animation, and interface assets—no saved projects or reference media. Away from the local server, the page labels its animation as an illustration and links visitors to setup instructions. Test the local landing page with `scripts/showcase_acceptance.py`.

![Optional local MotionClone showcase](showcase.png)

## Refresh documentation screenshots

With the app running and a completed project you intend to show publicly:

```powershell
.venv\Scripts\python.exe scripts/capture_readme.py --project YOUR_PROJECT_ID
```

This captures the real workspace, comparison, style picker, and optional showcase into `docs/`.
It uses a separate browser session, does not submit AI jobs, and does not render exports.
The showcase automatically displays a saved completed HyperFrames project. Review every image before publishing; screenshots can contain saved reference media.

## Brand assets

`scripts/build_brand.py` regenerates the original SVG icons, state illustrations, and MotionClone logo variants.
See [THIRD_PARTY.md](../THIRD_PARTY.md) for dependency and artwork notices.
