"""Build brand wrappers around the approved logo, plus interface illustrations."""
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'web' / 'assets'
ROOT.mkdir(exist_ok=True)
ICONS = {
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'library': '<rect x="3" y="7" width="18" height="14" rx="3"/><path d="M7 3h10m-7 9 5 3-5 3z"/>',
    'arrow-left': '<path d="m10 5-7 7 7 7M3 12h18"/>',
    'arrow-right': '<path d="m14 5 7 7-7 7M3 12h18"/>',
    'external': '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    'link': '<path d="m10 13 4-4m-6 7-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 1 2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(2 0) scale(.9)"/>',
    'upload': '<path d="M12 16V3m-5 5 5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    'drop': '<rect x="3" y="3" width="18" height="18" rx="4" stroke-dasharray="3 3"/><path d="M12 7v10m-4-4 4 4 4-4"/>',
    'video': '<rect x="3" y="5" width="14" height="14" rx="3"/><path d="m17 9 4-2v10l-4-2"/>',
    'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm0 0v6h6M9 12l6 3-6 3z"/>',
    'close': '<path d="m6 6 12 12M18 6 6 18"/>',
    'audio': '<path d="m11 4-6 5H2v6h3l6 5zM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    'settings': '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2" fill="white"/><circle cx="16" cy="12" r="2" fill="white"/><circle cx="10" cy="18" r="2" fill="white"/>',
    'lock': '<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M7 10V7a5 5 0 0 1 10 0v3m-5 5v2"/>',
    'download': '<path d="M12 3v13m-5-5 5 5 5-5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    'scan': '<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3M3 12h18"/>',
    'layers': '<path d="m12 3 10 5-10 5L2 8zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
    'render': '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m10 8 6 4-6 4z"/>',
    'compare': '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M12 2v20m-6-10h2m8 0h2"/>',
    'saved': '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M7 3v6h10M7 21v-8h10v8"/>',
    'stop': '<rect x="5" y="5" width="14" height="14" rx="3"/>',
    'refresh': '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.4 7a8 8 0 0 1 13.2-2L20 7M4 17l1.4 2A8 8 0 0 0 18.6 17"/>',
    'play': '<path d="m8 4 13 8-13 8z"/>',
    'pause': '<path d="M8 4v16M16 4v16"/>',
    'archive': '<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v13h14V8m-10 4h6"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    'search': '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
    'filter': '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
    'sort': '<path d="M8 3v18m-4-4 4 4 4-4M16 3h5m-5 5h4m-4 5h3"/>',
    'star': '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>',
    'copy': '<rect x="8" y="8" width="13" height="13" rx="3"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    'folder': '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>',
    'tag': '<path d="m3 3 9 0 9 9-9 9-9-9z"/><circle cx="8" cy="8" r="1"/>',
    'check': '<path d="m5 12 4 4L19 6"/>',
    'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'offline': '<path d="m3 3 18 18M8 16a6 6 0 0 1 7-1M5 12a10 10 0 0 1 5-2m5-3a15 15 0 0 1 6 3M3 8a15 15 0 0 1 3-2M12 20h.01"/>',
    'loader': '<path d="M21 12a9 9 0 1 1-9-9"/>',
    'warning': '<path d="m12 3 10 18H2zM12 9v5m0 3v.1"/>',
    'error': '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'chevron': '<path d="m9 5 7 7-7 7"/>',
}
symbols = ''.join(f'<symbol id="{name}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{body}</g></symbol>' for name, body in ICONS.items())
(ROOT/'icons.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg">{symbols}</svg>',encoding='utf-8')
logo = base64.b64encode((ROOT/'motionclone-logo-source.png').read_bytes()).decode('ascii')
# Keep the uploaded pixels intact. The SVG viewport frames the app tile.
mark = f'<svg viewBox="128 138 1000 1000" width="42" height="42"><image href="data:image/png;base64,{logo}" width="1280" height="1280"/></svg>'
for variant,color,cut in [('color','#6953cc','#fff'),('dark','#23252b','#fff'),('light','#fff','#23252b')]:
    art=mark
    (ROOT/f'motionclone-icon-{variant}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 42 42">{art}</svg>',encoding='utf-8')
    (ROOT/f'motionclone-wordmark-{variant}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 44">{art}<text x="51" y="30" fill="{color if variant != "color" else "#23252b"}" font-family="Segoe UI,Arial,sans-serif" font-size="27" font-weight="650" letter-spacing="-1">MotionClone</text></svg>',encoding='utf-8')
decorations={
 'empty': '<path d="M44 43h51l12 10h32v49H44z" fill="#eee9fb" stroke="#bcb0df"/><path d="m82 63 23 14-23 14z" fill="#6953cc"/>',
 'search': '<rect x="42" y="37" width="79" height="61" rx="9" fill="white" stroke="#cfc8df"/><path d="M54 52h40m-40 13h21" stroke="#cfc8df"/><circle cx="116" cy="79" r="22" fill="#eee9fb" stroke="#6953cc"/><path d="m131 95 18 18" stroke="#6953cc" stroke-width="5"/>',
 'upload': '<rect x="50" y="30" width="83" height="76" rx="12" fill="#eee9fb" stroke="#bcb0df" stroke-dasharray="5 5"/><path d="M92 85V49m-14 14 14-14 14 14" stroke="#6953cc" stroke-width="4"/>',
 'processing': '<rect x="42" y="31" width="79" height="63" rx="9" fill="#eee9fb" stroke="#c9bce6"/><rect x="64" y="48" width="79" height="63" rx="9" fill="white" stroke="#bcb0df"/><path d="m102 59 23 12-23 12-23-12zm-23 21 23 12 23-12" fill="none" stroke="#6953cc" stroke-width="2"/>',
 'error': '<rect x="43" y="35" width="96" height="66" rx="10" fill="white" stroke="#d2cadf"/><path d="m70 51 20 14-20 14z" fill="#ded5f0"/><circle cx="130" cy="96" r="21" fill="#fff0f1" stroke="#b1384c"/><path d="M130 84v14m0 7v1" stroke="#b1384c" stroke-width="3"/>',
 'success': '<rect x="45" y="31" width="80" height="67" rx="10" fill="#eee9fb" stroke="#c9bce6"/><path d="m76 48 23 16-23 16z" fill="#6953cc"/><circle cx="126" cy="96" r="23" fill="#edf7f1" stroke="#438566"/><path d="m114 96 8 8 15-17" fill="none" stroke="#438566" stroke-width="3"/>',
}
for name,art in decorations.items():
    (ROOT/f'illustration-{name}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 140" fill="none" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="94" cy="120" rx="55" ry="5" fill="#eeeef3"/>{art}</svg>',encoding='utf-8')
print(f'Generated {len(ICONS)} icons, six illustrations, and six brand SVGs.')
