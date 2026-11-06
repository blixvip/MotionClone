# Contributing to MotionClone

Thanks for helping! Questions and ideas are welcome in the **[Discord](https://discord.gg/zEB4VjmfSb)**, and bugs go in [GitHub issues](https://github.com/blixvip/MotionClone/issues/new/choose).

## Finding something to work on

- [Good first issues](https://github.com/blixvip/MotionClone/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are small and list the files to touch.
- [Help wanted](https://github.com/blixvip/MotionClone/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) issues are bigger.
- Comment on the issue to claim it so two people don't build the same thing. If you go quiet for a week, it opens up again.
- Have your own idea? Open a [Discussion](https://github.com/blixvip/MotionClone/discussions) first for anything larger than a bug fix.

By contributing, you agree your work is released under the project's [MIT License](LICENSE).

## Setup

MotionClone is **Windows-first** today. You need **Python 3.11+**, **Node.js 22+**, **FFmpeg and ffprobe** on your `PATH`, **Google Chrome**, and the official **Codex CLI** signed into a ChatGPT account.

```sh
git clone https://github.com/<you>/MotionClone.git
cd MotionClone
codex login
.\start.ps1          # creates .venv, installs both dependency sets, opens the browser
```

`start.ps1` serves the app on <http://127.0.0.1:4319>. Double-clicking `Start MotionClone.vbs` does the same thing.

Working on macOS or Linux? Nothing is documented yet and some paths are Windows-only, so you can run the test suite but not the app. Fixing that is genuinely wanted — see the `platform` label.

## Before you open a pull request

```sh
.venv\Scripts\python.exe -m pytest -q     # ~105 tests in tests/
cd remotion && npm test                   # only if you touched remotion/
```

- Keep changes small and focused. One fix or feature per pull request.
- Check UI changes in a real browser and add a screenshot or GIF.
- There is no linter or formatter. Match the style of the file you are editing — this codebase is deliberately dense, with short names and few blank lines.
- Don't commit reference footage, `data/`, or anything from `.venv`.
- Don't add a runtime dependency without saying why in the pull request. If you do add one, update both `requirements.txt` and `requirements.lock.txt`.
- The browser only talks to this project's own server on `127.0.0.1`. Don't add calls to other origins, and don't weaken the localhost-and-token check in `local_boundary`.
- Keep third-party notices in `THIRD_PARTY.md` and `licenses/`.

## Where things live

- `app/server.py`: the FastAPI app — every route, the single-slot job queue (`POOL`/`ACTIVE`/`LOCK`), the `pipeline()` branch per mode, and the `local_boundary` middleware
- `app/scene_pipeline.py`: splits a reference into ~6s scenes, rebuilds each in parallel, screenshots in Chrome, scores against the source with RGB SSIM, retries the two worst
- `app/rebuild_author.py`: the Pydantic contract the model must satisfy (`Pose`/`Layer`/`SceneProject`), the safe-CSS allowlist, and the `RENDERER` JS that draws those layers
- `app/media.py`: URL validation and SSRF guards, yt-dlp/httpx download, ffprobe/ffmpeg normalization, and the motion scan that picks which frames the model sees
- `app/editor.py`, `app/render.py`, `app/recording_export.py`: sequence assembly, frame drawing, and the Chrome frame-by-frame MP4 export
- `tests/`: pytest. `scripts/`: Playwright acceptance scripts needing Chrome and a live server on :4319

Made something with it? Show it off in the [Discord](https://discord.gg/zEB4VjmfSb).
