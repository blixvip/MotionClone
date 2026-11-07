"""Render the native SVG brand assets and website share card with Chrome.

The approved source PNG is preserved verbatim by build_brand.py.
Run after build_brand.py; optional --site points at a public website checkout.
"""
import argparse
import base64
from pathlib import Path
import struct

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/assets'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', action='append', type=Path, default=[])
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome')
        page = browser.new_page(device_scale_factor=1)

        def render(svg, width, height, path):
            page.set_viewport_size({'width': width, 'height': height})
            data = base64.b64encode(svg.encode()).decode()
            page.set_content(f'<style>html,body{{margin:0;background:transparent}}img{{display:block;width:100%;height:100%}}</style><img src="data:image/svg+xml;base64,{data}">')
            page.locator('img').evaluate('(img) => img.decode()')
            return page.screenshot(path=str(path), omit_background=True)

        for variant in ['color', 'dark', 'light']:
            for kind, width, height in [('icon', 256, 256), ('wordmark', 1040, 176)]:
                name = f'motionclone-{kind}-{variant}'
                render((ASSETS / f'{name}.svg').read_text(), width, height, ASSETS / f'{name}.png')
        icon = (ASSETS / 'motionclone-icon-color.svg').read_text()
        png = (ASSETS / 'motionclone-icon-color.png').read_bytes()
        # ICO supports a PNG payload; use the browser-rendered 256px icon.
        ico = struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png
        (ROOT / 'web/favicon.ico').write_bytes(ico)
        for site in args.site:
            public = site / 'public'
            (public / 'mark.svg').write_text(icon, encoding='utf-8')
            (public / 'favicon.svg').write_text(icon, encoding='utf-8')
            (public / 'favicon.ico').write_bytes(ico)
            (public / 'motionclone-logo.png').write_bytes((ASSETS / 'motionclone-logo-source.png').read_bytes())
            render(icon, 180, 180, public / 'apple-touch-icon.png')
            image = base64.b64encode(icon.encode()).decode()
            page.set_viewport_size({'width': 1200, 'height': 630})
            page.set_content(f'''<style>*{{box-sizing:border-box}}body{{margin:0;background:#08080d;color:#f7f5ff;font-family:Arial,sans-serif;width:1200px;height:630px;display:flex;align-items:center;padding:88px;gap:58px}}img{{width:280px;height:280px}}h1{{font-size:70px;letter-spacing:-4px;margin:0 0 26px}}p{{font-size:30px;line-height:1.35;color:#c6c0d7;margin:0}}small{{display:block;font-size:22px;color:#a594ff;margin-top:42px}}</style><img src="data:image/svg+xml;base64,{image}"><div><h1>MotionClone</h1><p>See the motion.<br>Make it yours.</p><small>motionclone.lol</small></div>''')
            page.locator('img').evaluate('(img) => img.decode()')
            page.screenshot(path=str(public / 'og.png'))
        browser.close()
    print('Rendered brand PNGs, favicons, and website share cards.')


if __name__ == '__main__':
    main()
