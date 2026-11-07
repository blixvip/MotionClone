# Editor

Open `/editor` to build a video from selected reference moments. The Editor uses the same private workspace, account connection, and render pipeline as the studio.

1. Upload a reference or paste a supported public video link. Saved references are also available.
2. Select a reference. Set its in/out points with the sliders, seconds fields, or **Set in / Set out** at the current playhead.
3. **Add segment**. Repeat with other references, reorder with the arrows, or remove a segment. Use **Play sequence** to preview the order.
4. Add segment notes, a project/brand name, and your creative direction. Select the output format and whether to retain reference audio.
5. **Save sequence** stores the draft in your workspace. It is restored when you return. Limits: 12 segments, 120 seconds total, minimum 0.25 seconds per segment. Select from the first 120 seconds of each reference.
6. Connect your own ChatGPT/Codex account in Settings, then **Generate my video**. Follow progress in the studio. Completed videos offer the usual MP4 and editable-project downloads.

The selected source segments are trimmed and assembled in order, fitted without cropping to the chosen format, then passed to AI reconstruction with your brief. This produces a new editable reconstruction; it does not promise an exact match. Inspect the output before publishing. Imported reference footage stays in the workspace and is excluded from editable project exports.

No AI access or credits are included with MotionClone or its repository. Generation uses your connected account's allowance, with its costs and limits. Selecting clips or saving a sequence does not call the AI. Supported generation currently uses ChatGPT through Codex.

Local drafts are stored in `data/editor-draft.json`; hosted drafts live inside each user's isolated project directory. Originals remain unchanged. Imports and generation share the existing single-job queue, upload bounds, hosted storage limits, and signed user routing.

If the saved sequence fails to load, **Refresh** retries without leaving the page. Generation saves and submits one snapshot of your sequence; edits you make while it starts remain marked as unsaved for your next video. Repeated Generate clicks cannot submit duplicate requests.
