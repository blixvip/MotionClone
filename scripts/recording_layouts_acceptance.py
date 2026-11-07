"""Lean layout checks against saved media; no generation or full video renders."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True)
args = parser.parse_args()
base = f'http://127.0.0.1:4319/?project={args.project}&view=compare&capture=1&look=mono'
out = Path('test-results/recording-layouts')
out.mkdir(parents=True, exist_ok=True)
formats = {'landscape': (960, 540), 'portrait': (540, 960), 'square': (540, 540),
           'ultrawide': (1280, 360), 'feed': (540, 675)}

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome')
    try:
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '&format=landscape&layout=split')
        expect(page.locator('#recording-options')).to_be_visible()
        sources = page.locator('#players video').evaluate_all('(videos)=>videos.map(v=>v.src)')
        for choice, format_name, layout in [('wide', 'ultrawide', 'split'), ('square', 'square', 'stack'),
                                           ('reveal', 'landscape', 'wipe'), ('inset', 'landscape', 'spotlight')]:
            page.locator(f'[data-composition="{choice}"]').click()
            expect(page.locator('#recording-format')).to_have_value(format_name)
            expect(page.locator('#recording-layout')).to_have_value(layout)
            page.reload()
            expect(page.locator('#recording-options')).to_be_visible()
            expect(page.locator(f'[data-composition="{choice}"]')).to_have_attribute('aria-pressed', 'true')
            assert page.locator('#players video').evaluate_all('(videos)=>videos.map(v=>v.src)') == sources

        # Exact output bounds and visible media across every supported combination.
        for format_name, (width, height) in formats.items():
            page.set_viewport_size({'width': width, 'height': height})
            for layout in ['split', 'stack', 'spotlight', 'wipe']:
                page.goto(base + f'&record=1&format={format_name}&layout={layout}')
                page.wait_for_function('() => document.body.classList.contains("recording-view")')
                page.wait_for_function('() => [...document.querySelectorAll("#players video")].every(v=>v.readyState>=2)')
                page.evaluate('() => document.querySelectorAll("video").forEach(v=>{v.pause();v.currentTime=5})')
                page.wait_for_function('() => [...document.querySelectorAll("#players video")].every(v=>!v.seeking)')
                canvas = page.locator('#recording-canvas').bounding_box()
                assert abs(canvas['width'] - width) < 1 and abs(canvas['height'] - height) < 1
                for selector in ['#promo-website', '#promo-identities', '#source-video', '#result-video']:
                    box = page.locator(selector).bounding_box()
                    assert box and box['width'] > 0 and box['height'] > 0, (format_name, layout, selector)
                    assert box['x'] >= -.5 and box['y'] >= -.5, (format_name, layout, selector, box)
                    assert box['x'] + box['width'] <= width + 1 and box['y'] + box['height'] <= height + 1, (format_name, layout, selector, box)
                if (format_name, layout) in [('ultrawide', 'split'), ('square', 'stack'), ('landscape', 'wipe'), ('landscape', 'spotlight'), ('feed', 'stack')]:
                    page.screenshot(path=str(out / f'{format_name}-{layout}.png'))
                if layout == 'wipe':
                    original = page.locator('#source-video').bounding_box()
                    rebuilt = page.locator('#result-video').bounding_box()
                    assert original == rebuilt, 'Reveal must align both complete frames'
                    assert page.locator('#source-video').evaluate('(el)=>getComputedStyle(el).clipPath') == 'inset(0px 50% 0px 0px)'
                if format_name == 'landscape' and layout == 'spotlight':
                    box = page.locator('#result-video').bounding_box()
                    assert box['width'] * box['height'] > width * height * .85
        for width in [360, 1440]:
            page.set_viewport_size({'width': width, 'height': 1000})
            page.goto(base + '&format=landscape&layout=wipe')
            expect(page.locator('#recording-options')).to_be_visible()
            assert page.evaluate('() => document.documentElement.scrollWidth<=innerWidth')
            page.locator('#recording-options').screenshot(path=str(out / f'controls-{width}.png'))
            page.locator('#promo-play').click()
            page.wait_for_function('() => !document.getElementById("result-video").paused')
            page.locator('#promo-play').click()
            page.locator('#promo-seek').fill('10')
            page.wait_for_function('() => Math.abs(document.getElementById("source-video").currentTime-10)<.1')
        assert not errors, errors
    finally:
        browser.close()
print('PASS: 4 compositions, 20 format/layout combinations, persistence, playback, seeking, narrow/wide controls')
