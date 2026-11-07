"""Real planner UI and SQLite API, with test data isolated from the user's library."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.posts import install

OUT = ROOT / 'test-results/posts-planner'
OUT.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='post-planner-test-') as temporary, sync_playwright() as pw:
    app = FastAPI()
    install(app, SimpleNamespace(ROOT=ROOT, DATA=Path(temporary)))
    app.mount('/static', StaticFiles(directory=ROOT / 'web'))
    client = TestClient(app)
    browser = pw.chromium.launch(channel='chrome')
    page = browser.new_page(viewport={'width':1440, 'height':1080})
    page.clock.set_fixed_time(datetime(2026, 9, 17, 12, tzinfo=timezone.utc))
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    failure = {'write':False, 'read':False}

    def handle(route):
        request = route.request
        path = request.url.split('127.0.0.1:4321', 1)[1]
        if path == '/api/status':
            route.fulfill(json={'token':'isolated-test'}); return
        if path.startswith('/api/compositions') and (failure['read'] or failure['write'] and request.method != 'GET'):
            route.fulfill(status=503, json={'detail':'Connection interrupted. Please retry.'}); return
        response = client.request(request.method, path, content=request.post_data, headers={'Content-Type':'application/json'})
        route.fulfill(status=response.status_code, content_type=response.headers.get('content-type','application/json'), body=response.content)

    page.route('http://127.0.0.1:4321/**', handle)
    page.goto('http://127.0.0.1:4321/posts', wait_until='networkidle')
    expect(page.locator('#new-post')).to_be_enabled()
    page.screenshot(path=str(OUT/'empty-wide.png'), full_page=True)
    for platform in ['linkedin','threads','x','youtube']:
        page.locator('[data-date="2026-09-23"] .day-number').click()
        expect(page.locator('#compose-dialog')).to_be_visible()
        expect(page.locator('#compose-date')).to_have_value('2026-09-23')
        page.locator('#compose-platform').select_option(platform)
        page.locator('#compose-title').fill(platform.title() + ' launch idea')
        page.locator('#compose-text').fill('A look behind the scenes of the next MotionClone update.\n\nWhat would you like to see next?')
        if platform == 'linkedin':
            page.screenshot(path=str(OUT/'composer-wide.png'))
        page.locator('#save-compose').click()
        expect(page.locator('#compose-dialog')).to_be_hidden()
    expect(page.locator('#draft-count')).to_have_text('4')
    page.reload(wait_until='networkidle')
    expect(page.locator('#draft-count')).to_have_text('4')
    page.locator('[data-view=draft]').click()
    expect(page.locator('.post')).to_have_count(4)
    page.locator('.post').filter(has_text='Linkedin launch idea').get_by_role('button', name='Edit', exact=True).click()
    expect(page.locator('#compose-text')).to_have_value('A look behind the scenes of the next MotionClone update.\n\nWhat would you like to see next?')
    page.locator('#compose-status').select_option('planned')
    page.locator('#compose-date').fill('2026-10-06')
    page.locator('#compose-time').fill('09:30')
    page.locator('#save-compose').click()
    expect(page.locator('#planned-count')).to_have_text('1')
    expect(page.locator('#calendar-month')).to_have_text('October 2026')
    expect(page.locator('[data-date="2026-10-06"] .day-post')).to_have_count(1)
    page.locator('[data-date="2026-10-06"] .day-post').click()
    expect(page.locator('#compose-heading')).to_have_text('Edit post')
    expect(page.locator('#compose-time')).to_have_value('09:30')
    page.set_viewport_size({'width':390, 'height':844})
    page.screenshot(path=str(OUT/'composer-narrow.png'))
    page.locator('#compose-status').select_option('published')
    page.locator('#save-compose').click()
    expect(page.locator('#published-count')).to_have_text('1')
    page.locator('[data-view=draft]').click()
    page.locator('[data-platform=youtube]').click()
    expect(page.locator('.post')).to_have_count(1)
    page.locator('.post').get_by_role('button', name='Edit', exact=True).click()
    page.locator('#compose-date').fill('')
    page.locator('#compose-text').fill('Revised YouTube post')
    failure['write'] = True
    page.locator('#save-compose').click()
    expect(page.locator('#compose-error')).to_contain_text('Connection interrupted')
    expect(page.locator('#compose-text')).to_have_value('Revised YouTube post')
    failure['write'] = False
    page.locator('#save-compose').click()
    expect(page.locator('.post').filter(has_text='No date yet')).to_have_count(1)
    page.locator('[data-view=all]').click()
    page.locator('[data-platform=all]').click()
    page.locator('#calendar-prev').click()
    for width in [320,390,768,1024,1440]:
        page.set_viewport_size({'width':width, 'height':1080})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        if width in [390,1440]:
            page.screenshot(path=str(OUT/f'planner-{width}.png'), full_page=True)
    page.locator('#new-post').click()
    page.locator('#compose-text').fill('Unsaved idea')
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.locator('#cancel-compose').click()
    expect(page.locator('#compose-dialog')).to_be_visible()
    expect(page.locator('#compose-text')).to_have_value('Unsaved idea')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#cancel-compose').click()
    expect(page.locator('#compose-dialog')).to_be_hidden()
    with page.expect_download() as downloaded:
        page.locator('#export').click()
    backup = json.loads(Path(downloaded.value.path()).read_text())
    assert backup['version'] == 2 and len(backup['compositions']) == 4
    page.locator('#import-file').set_input_files({'name':'backup.json', 'mimeType':'application/json', 'buffer':json.dumps(backup).encode()})
    expect(page.locator('#toast')).to_contain_text('4 already saved')
    failure['read'] = True
    page.reload(wait_until='networkidle')
    expect(page.locator('#load-error')).to_be_visible()
    failure['read'] = False
    page.locator('#retry').click()
    expect(page.locator('#new-post')).to_be_enabled()
    assert len(client.get('/api/compositions').json()) == 4
    assert not errors, errors
    browser.close()
print('PASS: date composer, all four platforms, persistent drafts, reschedule, statuses, undated drafts, filters, failed saves, unsaved changes, backup restore, responsive layout, no browser errors.')
