# Your first MotionClone project

[Back to MotionClone](../README.md) · [Windows setup](../README.md#run-locally) · [简体中文](../README.zh-CN.md)

From a reference clip to a comparison MP4 and editable animation. These screenshots show real saved projects; example media is not bundled with a fresh clone.

## 1. Add your reference

Paste a public link from X / Twitter, YouTube, Vimeo, or a direct video URL. You can also drag in a file or choose **Upload a video**. Open **Audio settings** to keep the original soundtrack or export silently. This choice applies when you rebuild or render. **Getting started & help** in the app links to setup, the Chinese guide, and issue reporting.

![The import form with a public reference link, Rebuild video button, upload area, and audio options](images/01-add-reference.png)

Start with a short clip whose typography and movement are easy to read. Use footage you own or have permission to adapt. Local inputs can be up to **120 seconds and 250 MB**.

## 2. Rebuild the motion

Click **Rebuild video**. MotionClone analyzes reference frames, builds the animation, and renders the result. The progress view shows the current stage; completed scenes are saved for retries.

When it finishes, your rebuilt video appears with its download options:

![A completed Leo reconstruction with the rebuilt video and MP4 and editable-project downloads](images/02-rebuilt-video.png)

This is a saved result. Downloading, AI analysis, rendering, and encoding each take time. Failed rebuilds report an error; the original video is never substituted for a failed reconstruction.

## 3. Check it against the original

Open **Compare & export**. Play both videos together, scrub to a specific moment, or slow down playback. Check the words, shapes, spacing, and transitions before using the result.

![Synchronized original and rebuilt videos, with shared playback, seeking, speed, and audio controls](images/03-compare.png)

The **Rebuilt** and **Reference** tabs let you inspect either video on its own. A successful export means a file was produced; the comparison tells you how closely the motion matches.

## 4. Choose how to present it

Expand **Choose a style**. Pick Studio, Editorial, Signal, Cobalt, Peach, or Monochrome, then choose the **Format** and **Arrangement** separately.

![All six recording styles and the independent format and arrangement controls](images/04-style-picker.png)

Comparison exports support landscape **1920 × 1080**, portrait **1080 × 1920**, square **1080 × 1080**, ultrawide **3840 × 1080**, and feed **1080 × 1350**. Use side-by-side, stacked, or rebuild-spotlight arrangements. **Fullscreen** opens the recording view.

<p align="center">
  <img src="images/portrait-comparison.png" width="380" alt="The actual System Prompts reference and reconstruction in a portrait Signal comparison">
</p>

*The System Prompts example in a portrait comparison. Both the source and reconstructed animation remain visible.*

## 5. Download a video or keep editing

![Completed-project controls for downloading an MP4 or an editable HyperFrames project](images/05-downloads.png)

| If you want… | Choose… |
| --- | --- |
| The complete original/rebuilt comparison | **Compare & export → Download MP4** |
| Only the reconstructed animation | **Export details → Rebuilt video only** |
| Text, shapes, assets, and animation code to edit | **Editable project** |

The comparison MP4 uses the selected style, format, and arrangement. It includes the original audio when that audio was retained, even if preview playback is muted.

For an editable project, extract the ZIP and read its included README. From that folder:

```powershell
npm install
npm run preview
```

Generated scenes use `project.json` and `npm run sync`. Authored scenes use `scene-*.js` and `tokens.css`. Once the changes look right, run `npm run render` to make a video.

A coding agent can work on the exported project too. Give it a specific edit:

```text
Read this project's README and package.json.
Replace the headline with our product name and use our brand colors.
Keep the current scene duration and entrance animation.
Preview the result. Check for clipped text and missing assets before rendering.
```

The editable ZIP includes project code and required assets, fonts, and audio. It excludes the original reference video and reference screenshots. See [Recording and exports](RECORDING.md) for the full archive, local view links, and export details.

## 6. Pick up where you left off

Open **Saved videos** to find a previous project. Search by name, filter favorites or ready videos, and organize projects into collections. Reopen a result to compare it or download it again.

![Saved videos filtered to the Leo example, with search, favorites, status filters, and collection controls](images/06-saved-videos.png)

*This is an existing local library. Example projects and reference videos are not bundled with a fresh clone.*

## Making a demo or launch video

For a product demo, use MotionClone for an opening title or animated feature callout, then combine that graphic with your own screen recording. For a launch, adapt a headline reveal or closing sequence and replace the reference copy and assets with your own.

MotionClone starts from a reference clip. Record your product workflow separately; a script alone does not produce a finished demo.

Read the [motion graphics workflow](https://motionclone.lol/ai-motion-graphics), [product demo guide](https://motionclone.lol/ai-demo-videos), or [launch video guide](https://motionclone.lol/ai-launch-videos) for a worked process. The [coding-agent guide](AGENT-WORKFLOW.md) covers exported project edits.

