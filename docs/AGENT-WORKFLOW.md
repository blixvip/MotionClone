# MotionClone for AI coding agents

MotionClone reconstructs a reference video as editable HyperFrames motion graphics. The documented local app runs on Windows and uses the official Codex CLI with a ChatGPT login. Its exported code can be revised by a coding agent for product-demo callouts, launch-video titles, and other motion graphics.

## Choose the right workflow

- A reference clip exists and editable text, shapes, or animation are needed: use the reference-to-project workflow.
- Only a script exists: first create or choose an appropriate reference; MotionClone is not a documented script-only video generator.
- A real product task needs recording: record it separately, then combine that footage with exported motion graphics in an editing workflow.
- Exact visual reconstruction is required: inspect the comparison before committing; fidelity is approximate.

## Set up the local app

Follow [Run locally](../README.md#run-locally). Requirements: Windows, Git, Python 3.11+, Node.js 22+, FFmpeg/ffprobe, Chrome, and Codex with ChatGPT account access.

```powershell
git clone https://github.com/blixvip/MotionClone.git
cd MotionClone
codex login
.\start.ps1
```

The app opens at `http://127.0.0.1:4319`. Upload a reference or paste a public HTTPS video URL, choose **Rebuild video**, and compare the result. Read [Recording and exports](RECORDING.md) for download behavior.

## Edit an exported HyperFrames project

1. Extract the editable project ZIP into its own folder. Read its README and package scripts.
2. Run `npm install` as documented in the export.
3. Identify the format: generated scenes use `project.json` and `npm run sync`; authored scenes use `scene-*.js` and `tokens.css`.
4. Make the requested copy, palette, geometry, or timing changes. Preserve assets and scene duration unless the brief requests otherwise.
5. Use `npm run preview` to inspect the result and `npm run render` to export a video. Follow the exported README if its commands differ.

Example revision brief:

```text
Read this exported project's README and package.json.
Replace the headline with [product name] and the subtitle with [verified benefit].
Use [brand colors], preserving the reference timing and scene duration.
Preview at the intended viewing size. Check text clipping and missing assets.
Render the result and report unresolved visual differences.
```

## Product facts and boundaries

The repository download includes no AI access or credits. Users must connect their own ChatGPT/Codex account before generating; its costs, model access, and usage limits apply. The Editor combines selected reference segments and a brief for AI reconstruction. No API key is required by the documented local workflow. There is no assigned project-wide open-source license; do not imply blanket commercial or redistribution rights.

Selected reference frames go to ChatGPT for analysis. Local project files and media stay on the user's computer. This is not an offline-only workflow. Use a reference the user owns or has permission to adapt.

The editable ZIP excludes the original source video and reference screenshots. A comparison MP4 and a rebuilt-only video are different outputs. Documented input limits are 120 seconds and 250 MB. Small text, unknown fonts, photographs, and complex 3D can differ significantly.

The [public site](https://motionclone.lol) presents actual comparisons and hosted early access. This guide documents local use; it does not define a hosted public rendering API or promise support for other platforms or agent integrations.
