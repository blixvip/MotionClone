"""Exercise the branded recording view against saved media; never starts AI jobs."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import argparse
import json
from urllib.request import urlopen

OUT=Path('test-results/promo');OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--project');args=parser.parse_args()
with urlopen('http://127.0.0.1:4319/api/library') as response:jobs=json.load(response)
project=args.project or next((job['id'] for job in jobs if job['status']=='complete' and all(name in job['files'] for name in ['source.mp4','output.mp4'])),None)
if not project:raise SystemExit('A completed source/rebuild pair is required. Pass --project ID.')
URL=f'http://127.0.0.1:4319/?project={project}&view=compare'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome')
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL,wait_until='domcontentloaded')
    stage=page.locator('#comparison-stage')
    expect(page.locator('#promo-website')).to_be_visible(timeout=15000)
    for href in ['https://motionclone.lol','https://x.com/waselyyy']:
        expect(stage.locator(f'a[href="{href}"]').first).to_be_visible()
    expect(stage.locator('a')).to_have_count(2)
    expect(page.locator('#promo-labels')).to_have_text('BeforeAI generated')
    expect(page.locator('#promo-identities')).to_have_text('@waselyyy')
    stage.scroll_into_view_if_needed()
    page.emulate_media(reduced_motion='reduce')
    source=page.locator('#source-video');result=page.locator('#result-video')
    assert source.bounding_box()['x']<result.bounding_box()['x']
    assert source.get_attribute('src')!=result.get_attribute('src')
    page.locator('#promo-play').click()
    page.wait_for_function("() => ['source-video','result-video'].every(id=>{const v=document.getElementById(id);return !v.paused&&v.currentTime>.3})")
    page.locator('#promo-play').click()
    expect(page.locator('#promo-play')).to_have_attribute('aria-label','Play both videos')
    page.locator('#promo-speed').select_option('1.5')
    assert source.evaluate('(v)=>v.playbackRate')==result.evaluate('(v)=>v.playbackRate')==1.5
    page.locator('#promo-speed').select_option('1')
    page.locator('#promo-sound').click()
    assert source.evaluate('(v)=>v.muted') and not result.evaluate('(v)=>v.muted')
    page.locator('#promo-sound').click()
    page.locator('#promo-seek').fill('4')
    page.wait_for_function("() => ['source-video','result-video'].every(id=>Math.abs(document.getElementById(id).currentTime-4)<.1)")
    page.locator('#promo-restart').click()
    page.wait_for_function("() => document.getElementById('result-video').currentTime<2&&!document.getElementById('result-video').paused")
    page.locator('#promo-play').click()
    expect(page.locator('#promo-error')).to_be_hidden()
    page.locator('#promo-seek').fill(str(round(result.evaluate('(v)=>v.duration-.15'),2)))
    page.locator('#promo-play').click()
    page.wait_for_function("() => document.getElementById('result-video').currentTime<2&&!document.getElementById('result-video').paused")
    page.locator('#promo-play').click()
    stage.screenshot(path=str(OUT/'comparison-desktop.png'))
    page.locator('#present-comparison').click()
    expect(page.locator('body')).to_have_class(__import__('re').compile(r'recording-view'))
    expect(page.locator('#promo-controls')).to_be_hidden()
    for width,height in [(1920,1080),(1280,720),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        for selector in ['#promo-website','#promo-identities']:
            bounds=page.locator(selector).bounding_box()
            assert bounds and bounds['x']>=0 and bounds['y']>=0
            assert bounds['x']+bounds['width']<=width+1 and bounds['y']+bounds['height']<=height+1,(selector,bounds)
        for video in [source,result]:
            bounds=video.bounding_box();header=page.locator('#promo-header').bounding_box()
            assert bounds['height']>40 and bounds['y']>=header['y']+header['height'],(width,bounds,header)
        page.screenshot(path=str(OUT/f'recording-{width}.png'))
    page.keyboard.press('Escape')
    expect(page.locator('body')).not_to_have_class(__import__('re').compile(r'recording-view'))
    page.set_viewport_size({'width':390,'height':844})
    stage.screenshot(path=str(OUT/'comparison-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#result-tab').click()
    expect(page.locator('#promo-website')).to_be_hidden()
    expect(source).to_be_hidden()
    expect(result).to_be_visible()
    page.locator('#compare-tab').click()
    expect(page.locator('#promo-website')).to_be_visible()
    page.goto(URL+'&record=1',wait_until='domcontentloaded')
    expect(page.locator('body')).to_have_class(__import__('re').compile(r'recording-view'))
    page.keyboard.press('Escape')
    expect(page.locator('#promo-controls')).to_be_visible()
    assert not errors,errors
    browser.close()
print('PASS: minimal attribution, before/AI labels, reduced motion, synchronized playback/seek/replay, recording view, mobile, exit, tab recovery')
