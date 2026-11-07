"""Real saved-media checks for recording looks, framing and URL persistence. No AI jobs."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True)
args = parser.parse_args()
base = f'http://127.0.0.1:4319/?project={args.project}&view=compare'
out = Path('test-results/recording-presets')
out.mkdir(parents=True, exist_ok=True)
presets = {
    'studio': ('landscape', 'split'), 'paper': ('square', 'stack'),
    'signal': ('portrait', 'stack'), 'cobalt': ('landscape', 'spotlight'),
    'peach': ('portrait', 'spotlight'), 'mono': ('square', 'split'),
}
formats = {'landscape': (1920, 1080), 'portrait': (1080, 1920), 'square': (1080, 1080)}

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome')
    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base + '&look=studio')
    expect(page.locator('#recording-options')).to_be_visible()
    page.locator('#recording-style-options > summary').click()
    page.locator('#recording-options').screenshot(path=str(out / 'picker.png'))
    original_sources = page.locator('#players video').evaluate_all('(els)=>els.map(v=>v.src)')

    for look, (format_name, layout) in presets.items():
        page.locator(f'.recording-preset[data-look="{look}"]').click()
        expect(page.locator('#comparison-stage')).to_have_attribute('data-look', look)
        expect(page.locator('#recording-format')).to_have_value(format_name)
        expect(page.locator('#recording-layout')).to_have_value(layout)
        assert page.locator('#players video').evaluate_all('(els)=>els.map(v=>v.src)') == original_sources
        params = parse_qs(urlparse(page.url).query)
        assert params['look'] == [look] and params['format'] == [format_name]

    # Custom combinations and a local link retain every choice on reload.
    page.locator('#recording-format').select_option('portrait')
    page.locator('#recording-layout').select_option('stack')
    page.locator('#copy-recording-link').click()
    link = page.evaluate('() => navigator.clipboard.readText()')
    assert all(x in link for x in ['look=mono', 'format=portrait', 'layout=stack', 'record=1'])
    page.goto(link)
    expect(page.locator('body')).to_have_class(__import__('re').compile('recording-view'))
    expect(page.locator('#comparison-stage')).to_have_attribute('data-layout', 'stack')
    assert page.locator('#promo-exit').evaluate('(el)=>getComputedStyle(el).opacity') == '0'
    page.keyboard.press('Shift+Tab')
    expect(page.locator('#promo-exit')).to_be_focused()
    page.keyboard.press('Space')
    expect(page.locator('#recording-options')).to_be_visible()
    page.goto(base)
    expect(page.locator('#recording-format')).to_have_value('portrait')
    expect(page.locator('.recording-preset[data-look="mono"]')).to_have_attribute('aria-pressed', 'true')

    # Clipboard-denied environments still offer a selectable local link.
    page.evaluate("() => Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('denied')}}})")
    page.locator('#copy-recording-link').click()
    expect(page.locator('#recording-link-fallback')).to_be_visible()
    assert 'record=1' in page.locator('#recording-link-value').input_value()

    # Check all 18 palette/format combinations at their actual output ratios.
    for look, (_, layout) in presets.items():
        for format_name, (width, height) in formats.items():
            viewport = {'width': width // 2, 'height': height // 2}
            page.set_viewport_size(viewport)
            page.goto(base + f'&record=1&look={look}&format={format_name}&layout={layout}')
            page.wait_for_function('() => document.body.classList.contains("recording-view")')
            page.wait_for_function('() => ["source-video","result-video"].every(id=>document.getElementById(id).readyState>=2)')
            page.evaluate('() => {document.getElementById("result-video").pause();document.getElementById("source-video").pause()}')
            page.locator('#promo-seek').evaluate('(el)=>{el.value=10;el.dispatchEvent(new Event("input",{bubbles:true}))}')
            page.wait_for_function('() => ["source-video","result-video"].every(id=>!document.getElementById(id).seeking)')
            canvas = page.locator('#recording-canvas').bounding_box()
            assert abs(canvas['width'] / canvas['height'] - width / height) < .001
            assert abs(canvas['width'] - viewport['width']) < 1
            assert abs(canvas['height'] - viewport['height']) < 1
            for selector in ['#promo-website', '#promo-identities', '#source-video', '#result-video']:
                bounds = page.locator(selector).bounding_box()
                assert bounds and bounds['width'] > 0 and bounds['height'] > 0, (look, format_name, selector)
                assert bounds['x'] >= -.5 and bounds['y'] >= -.5, (look, format_name, selector, bounds)
                assert bounds['x'] + bounds['width'] <= viewport['width'] + 1, (look, format_name, selector, bounds)
                assert bounds['y'] + bounds['height'] <= viewport['height'] + 1, (look, format_name, selector, bounds)
            for selector in ['#source-video', '#result-video']:
                assert page.locator(selector).evaluate('(v)=>getComputedStyle(v).objectFit') == 'contain'
            expect(page.locator('#promo-controls')).to_be_hidden()
            assert page.locator('#promo-exit').evaluate('(el)=>getComputedStyle(el).opacity') == '0'
            assert page.evaluate('() => document.documentElement.scrollWidth<=innerWidth')
            if format_name == presets[look][0]:
                page.mouse.move(0, viewport['height'] - 1)
                page.locator('#recording-canvas').screenshot(path=str(out / f'{look}.png'))
            page.keyboard.press('Space')
            page.wait_for_function('() => ["source-video","result-video"].every(id=>!document.getElementById(id).paused)')
            assert page.evaluate('() => Math.abs(document.getElementById("result-video").currentTime-document.getElementById("source-video").currentTime)<.15')
            page.keyboard.press('Escape')
            expect(page.locator('#recording-options')).to_be_visible()

    # The picker and fitted preview must stay usable on a small phone.
    for width in [320, 768, 1440]:
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto(base + '&look=signal')
        expect(page.locator('#recording-options')).to_be_visible()
        assert page.evaluate('() => document.documentElement.scrollWidth<=innerWidth')
        page.locator('#recording-options').screenshot(path=str(out / f'picker-{width}.png'))
    page.goto(base + '&look=invalid&format=bogus&layout=bogus')
    expect(page.locator('#comparison-stage')).to_have_attribute('data-look', 'studio')
    expect(page.locator('#recording-format')).to_have_value('landscape')
    expect(page.locator('#recording-layout')).to_have_value('split')
    assert not errors, errors
    browser.close()
print('PASS: six looks, 18 framed combinations, uncropped videos, controls, sync, local links, persistence, keyboard exit, clipboard fallback, narrow layouts')
