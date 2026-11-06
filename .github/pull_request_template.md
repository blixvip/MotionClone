## What does this change?

<!-- A short description. Link the issue it fixes, e.g. "Fixes #12". -->

## How did you test it?

- [ ] `.venv\Scripts\python.exe -m pytest -q` passes
- [ ] `cd remotion && npm test` passes (only if you touched `remotion/`)
- [ ] UI changes checked in a real browser (screenshot or GIF below)
- [ ] Rebuilt a reference end to end (if the pipeline, reconstruction, or export changed)

## Checklist

- [ ] One fix or feature, kept small and focused
- [ ] No new runtime dependency — or it's explained above, and both `requirements.txt` and `requirements.lock.txt` are updated
- [ ] No calls to other origins, and the `local_boundary` localhost-and-token check is intact
- [ ] Nothing committed from `data/`, `.venv/`, or any reference footage
- [ ] Docs updated if behavior or setup changed
- [ ] Third-party notices updated in `THIRD_PARTY.md` / `licenses/` if you vendored anything

<!-- Which OS did you test on? Windows is the best-tested; macOS and Linux reports are especially useful. -->

<!-- Questions? Ask in the Discord: https://discord.gg/zEB4VjmfSb -->
