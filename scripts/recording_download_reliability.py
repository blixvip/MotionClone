"""Exercise export recovery in the real UI; mock only export HTTP responses."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = 'http://127.0.0.1:4319'
PROJECT = '09a418cdd005'
KEY = 'a' * 20
OUT = Path('test-results/reliability')
OUT.mkdir(parents=True, exist_ok=True)


def task(status='running'):
    return dict(key=KEY, status=status, stage='Exporting recording view', progress=42,
                error=None, url=f'/api/jobs/{PROJECT}/recording/{KEY}/download',
                settings=dict(look='mono', format='landscape', layout='split'))


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome')
    for case in ('network', 'reload', 'download-error', 'project-switch'):
        context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        state = {'posts': 0, 'polls': 0, 'complete': False}

        def route_export(route):
            if route.request.url.endswith('/recording'):
                state['posts'] += 1
                route.fulfill(json=task())
            elif route.request.url.endswith('/download'):
                if case == 'download-error':
                    route.fulfill(status=409, json={'detail': 'Export file needs to be recreated.'})
                else:
                    route.fulfill(path='data/09a418cdd005/output.mp4', content_type='video/mp4', headers={
                        'Content-Disposition': 'attachment; filename="motionclone-mono-landscape-split.mp4"'})
            else:
                state['polls'] += 1
                if case == 'network' and state['polls'] == 1:
                    route.abort('connectionreset')
                else:
                    route.fulfill(json=task('complete' if state['complete'] else 'running'))

        page.route(f'**/api/jobs/{PROJECT}/recording**', route_export)
        page.goto(f'{BASE}/?project={PROJECT}&view=compare&look=mono&format=landscape&layout=split')
        expect(page.locator('#download')).to_be_visible()
        page.locator('#download').click()
        page.locator('#download').click(force=True)
        expect(page.locator('#download')).to_have_attribute('aria-busy', 'true')
        if case == 'reload':
            page.reload()
            expect(page.locator('#finished')).to_be_visible()
        if case == 'project-switch':
            page.evaluate("() => openProject('09782d1f7c63')")
            expect(page.locator('#recording-export-status')).to_be_hidden()
            expect(page.locator('#download')).not_to_have_attribute('aria-busy', 'true')
            page.evaluate(f"() => openProject('{PROJECT}')")
        state['complete'] = True
        if case == 'download-error':
            expect(page.locator('#recording-export-status')).to_have_class('export-error', timeout=15000)
            expect(page.locator('#recording-export-status')).not_to_contain_text('MP4 ready')
        else:
            with page.expect_download(timeout=20000) as event:
                expect(page.locator('#recording-export-status')).to_contain_text('MP4 ready', timeout=20000)
            assert event.value.failure() is None, event.value.failure()
            assert state['posts'] == 1, state
            for width in (390, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                page.locator('#finished').screenshot(path=str(OUT / f'{case}-{width}.png'))
        assert not errors, errors
        print(f'PASS {case}: {state}', flush=True)
        context.close()
    browser.close()
