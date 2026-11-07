[English](README.md) | **简体中文**

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/motionclone-wordmark-light.png">
    <img src="docs/images/motionclone-wordmark.png" width="320" alt="MotionClone">
  </picture>
</p>

# MotionClone：用参考视频制作 AI 动效

MotionClone 使用 Codex 和你的 ChatGPT 账号，将参考视频中的文字、形状、图像和动画重建为**可编辑的 HyperFrames 项目**。你可以替换文案、调整动画节奏，再把这些动效用在产品演示或发布视频中。

<p>
  <a href="https://motionclone.lol">试用在线工作室</a> ·
  <a href="#本地运行">在 Windows 上运行</a> ·
  <a href="docs/AGENT-WORKFLOW.md">编程智能体使用指南（英文）</a>
</p>

<a href="https://buymeacoffee.com/blix"><img src="web/assets/buymeacoffee-yellow.png" width="170" alt="请 blix 喝杯咖啡"></a>

[![MotionClone 实际播放效果：左侧为原始参考视频，右侧为重建结果](docs/images/motionclone-in-action.gif)](https://motionclone.lol/#examples)

*这是实际保存的重建结果。左侧是原视频，右侧是 MotionClone 的重建版本。[打开播放器查看](https://motionclone.lol/#examples) · [查看静态图片](docs/images/hero-comparison.png)*

**请连接你自己的 AI 账号。** 生成视频需要你自己的 ChatGPT/Codex 连接。下载本仓库不包含 AI 访问权限、额度或无限次生成；模型权限、费用和用量限制取决于你的账号套餐。登录网站与连接 AI 账号是两个独立步骤。重建结果可能与原视频有差异；小字、不常见的字体、照片和复杂 3D 画面往往需要进一步调整。

在 **Editor** 页面可导入参考视频，选择片段的起止时间，排序并添加创作说明，然后用自己的 AI 账号生成可编辑视频。最多 12 个片段，总时长不超过 120 秒。点击 **Save sequence** 保存草稿，点击 **Generate my video** 开始生成。详见 [Editor 使用说明（英文）](docs/EDITOR.md)。

## 本地运行

下面的教程使用 Windows 本地应用。[在线工作室](https://motionclone.lol)目前也已开放早期试用，需要登录、单独连接 ChatGPT，并且后台处理服务处于运行状态。

本文已翻译为简体中文，软件界面和截图仍为英文。操作步骤中会保留英文按钮名，方便对照。

运行启动脚本前，请先安装以下工具：

| 环境或工具 | 用途 |
| --- | --- |
| Windows、Git、Python 3.11+ | 运行本地应用 |
| Node.js 22+ 和 npm | 运行 HyperFrames |
| FFmpeg 和 ffprobe | 读取与导出视频 |
| Google Chrome | 渲染动画 |
| 官方 Codex CLI，以及具备相应使用权限的 ChatGPT 账号 | 分析并重建参考视频 |

确保 `git`、`python`、`npm`、`ffmpeg`、`ffprobe` 和 `codex` 已加入 PATH，然后在 PowerShell 中运行：

```powershell
git clone https://github.com/blixvip/MotionClone.git
cd MotionClone
codex login
.\start.ps1
```

启动脚本会安装锁定版本的依赖，并打开 **http://127.0.0.1:4319**。首次启动需要联网。以后运行 `start.ps1` 或双击 **Start MotionClone.vbs** 即可。

无需 API 密钥，MotionClone 会使用你的 Codex 登录状态。如需改用账号支持的其他模型，请在启动前设置 `FRAMEFORGE_MODEL`。这个环境变量沿用了旧名称，以保持兼容。

## 1. 添加参考视频

粘贴 X / Twitter、YouTube、Vimeo 的公开视频链接，或视频文件的直链。也可以直接拖入文件，或点击 **Upload a video（上传视频）**。打开 **Options（选项）**，选择是否保留原视频音频。

![导入表单：已填入公开视频链接，旁边有重建按钮，下方有上传区域和音频选项](docs/images/01-add-reference.png)

建议先用一段文字清晰、动作容易辨认的短视频。请使用你拥有或获准改编的素材。本地应用支持最长 **120 秒**、最大 **250 MB** 的输入文件。

## 2. 重建动效

点击 **Rebuild video（重建视频）**。MotionClone 会分析参考帧、构建动画并渲染结果。进度区域会显示当前阶段；已完成的场景会保存下来，供重试时使用。

完成后，页面会显示重建视频和下载选项：

![已完成的 Leo 重建结果，包含视频预览、MP4 下载和可编辑项目下载按钮](docs/images/02-rebuilt-video.png)

图中展示的是已经保存的结果。下载、AI 分析、渲染和编码都需要时间。如果重建失败，应用会报错，不会拿原视频冒充重建结果。

## 3. 对照原视频检查

打开 **Compare & export（对比与导出）**。两个视频可以同步播放，你也可以拖动进度条定位到某一时刻，或降低播放速度。使用结果前，请检查文字、形状、间距和转场。

![原视频与重建视频同步显示，共用播放、进度、速度和音频控制](docs/images/03-compare.png)

通过 **Rebuilt（重建结果）** 和 **Reference（参考视频）** 标签页，可以单独查看任一版本。导出成功说明文件已生成；还原得是否准确，需要通过对比来判断。

## 4. 选择展示方式

展开 **Choose a style（选择样式）**，从 Studio、Editorial、Signal、Cobalt、Peach 和 Monochrome 中选择一种样式，再分别设置 **Format（画幅）** 和 **Arrangement（排列方式）**。

![六种录制样式，以及可独立设置的画幅与排列方式](docs/images/04-style-picker.png)

对比视频支持横屏 **1920 × 1080**、竖屏 **1080 × 1920** 和正方形 **1080 × 1080**。排列方式包括左右并排、上下排列，以及突出显示重建结果。点击 **Fullscreen（全屏）** 可进入录制视图。

<p align="center">
  <img src="docs/images/portrait-comparison.png" width="380" alt="System Prompts 原视频与重建结果，使用 Signal 样式的竖屏对比布局">
</p>

*System Prompts 示例的竖屏对比视图，原视频和重建动画同时可见。*

## 5. 下载视频，或继续编辑

![项目完成后的下载按钮，可下载 MP4 或可编辑的 HyperFrames 项目](docs/images/05-downloads.png)

| 想获得什么 | 选择哪个选项 |
| --- | --- |
| 完整的原视频与重建结果对比视频 | **Compare & export → Download MP4（对比与导出 → 下载 MP4）** |
| 仅包含重建动画的视频 | **Export details → Rebuilt video only（导出详情 → 仅重建视频）** |
| 可继续编辑的文字、形状、素材和动画代码 | **Editable project（可编辑项目）** |

对比 MP4 会使用你选择的样式、画幅和排列方式。如果导入时保留了原视频音频，导出时也会包含音频，即使预览播放器处于静音状态。

如果下载的是可编辑项目，先解压 ZIP 并阅读其中的 README，然后在项目文件夹中运行：

```powershell
npm install
npm run preview
```

生成式场景使用 `project.json` 和 `npm run sync`；直接编写的场景使用 `scene-*.js` 和 `tokens.css`。预览确认无误后，运行 `npm run render` 生成视频。

编程智能体也可以修改导出的项目。给它一条明确的编辑指令，例如：

```text
先阅读这个项目的 README 和 package.json。
将标题替换为我们的产品名称，并使用我们的品牌配色。
保留当前场景时长和入场动画。
预览结果，在渲染前检查文字是否被裁切、素材是否缺失。
```

可编辑项目 ZIP 包含项目代码及所需的素材、字体和音频，不包含原始参考视频和参考截图。完整归档、本地视图链接和其他导出说明，请参阅[录制与导出文档（英文）](docs/RECORDING.md)。

## 6. 随时回来继续做

打开 **Saved videos（已保存的视频）** 查找之前的项目。你可以按名称搜索、筛选收藏或已完成的视频，并通过集合整理项目。重新打开结果后，可以继续对比或再次下载。

![已保存的视频列表，已筛选出 Leo 示例，包含搜索、收藏、状态筛选和集合选项](docs/images/06-saved-videos.png)

*图中是已有的本地视频库。新克隆的仓库不包含这些示例项目和参考视频。*

## 制作产品演示或发布视频

制作产品演示时，可以用 MotionClone 重建片头标题或功能说明动效，再与你自己的屏幕录制画面剪辑到一起。制作发布视频时，可以改编标题入场或结尾动画，并换成自己的文案和素材。

MotionClone 需要参考视频作为起点。产品操作过程需要另外录屏；仅提供脚本不会直接生成完整的演示视频。

更多操作示例见[动态图形制作流程](https://motionclone.lol/ai-motion-graphics)、[产品演示指南](https://motionclone.lol/ai-demo-videos)和[发布视频指南](https://motionclone.lol/ai-launch-videos)。这些页面目前为英文。[编程智能体指南（英文）](docs/AGENT-WORKFLOW.md)介绍了如何编辑导出的项目。

## 使用前了解这些

本地项目和媒体文件保存在电脑上的 `data/` 文件夹中。选取的参考帧会发送给 ChatGPT 进行分析，下载视频时也会访问相应的视频来源网站，因此本地应用并非完全离线运行。在线版的存储方式不同，请查看在线工作室中的账号与隐私说明。

<details>
<summary>常见问题</summary>

- **找不到命令：** 安装对应工具，将其加入 PATH，然后重新打开 PowerShell。
- **ChatGPT 连接断开：** 运行 `codex login`，再刷新应用中的连接状态。
- **视频链接无法下载：** 尝试直接上传文件。私有链接或已失效的链接可能无法下载。
- **服务无法启动：** 查看项目文件夹中的 `server-error.log`。
- **重建结果不准确：** 使用对比视图检查。小字、缺失字体、照片和复杂动作可能与参考视频有明显差异。

</details>

参与开发时，完成环境配置后可运行 `.venv\Scripts\python.exe -m pytest -q`。[开发与验证文档（英文）](docs/DEVELOPMENT.md)介绍了代码结构和浏览器检查方法。可复现的问题请提交到 [GitHub Issues](https://github.com/blixvip/MotionClone/issues)。

目前尚未为整个项目指定开源许可证。第三方组件仍遵循各自的许可证，详见 [THIRD_PARTY.md](THIRD_PARTY.md) 和 [licenses/](licenses/)。

## 作者：blix

如果 MotionClone 帮到了你的项目，欢迎[请我喝杯咖啡](https://buymeacoffee.com/blix)。

<a href="https://buymeacoffee.com/blix"><img src="web/assets/buymeacoffee-yellow.png" width="200" alt="请我喝杯咖啡"></a>

[GitHub @blixvip](https://github.com/blixvip) · [X @waselyyy](https://x.com/waselyyy) · [motionclone.lol](https://motionclone.lol)
