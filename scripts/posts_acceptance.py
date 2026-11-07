"""Exercise the real UI and API with an isolated temporary post database."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
import app.server as server

OUT = ROOT / 'test-results/posts-library'
OUT.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='motionclone-posts-') as temporary, sync_playwright() as pw:
    server.DATA = Path(temporary)
    client = TestClient(server.app)
    browser = pw.chromium.launch(channel='chrome')
    page = browser.new_page(viewport={'width':1440, 'height':1080})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    failure = {'read': False, 'write': False}

    def api(route):
        request = route.request
        path = request.url.split('127.0.0.1:4319', 1)[1]
        if path == '/api/status':
            route.fulfill(json={'token':server.TOKEN}); return
        if path.startswith('/api/posts') and ((request.method == 'GET' and failure['read']) or (request.method != 'GET' and failure['write'])):
            route.fulfill(status=503, json={'detail':'Connection interrupted. Please retry.'}); return
        headers = {'X-Frameforge-Token':request.headers.get('x-frameforge-token', ''), 'Content-Type':'application/json'}
        response = client.request(request.method, path, content=request.post_data, headers=headers)
        route.fulfill(status=response.status_code, content_type=response.headers.get('content-type','application/json'), body=response.content)

    page.route('**/api/posts**', api)
    page.route('**/api/status', api)
    page.route('**/posts', api)
    page.add_init_script("const originalFetch=window.fetch; window.fetch=async (...args)=>{if(args[0]==='/api/posts'&&!args[1]?.method)await new Promise(r=>setTimeout(r,900));return originalFetch(...args)}")
    page.goto('http://127.0.0.1:4319/posts', wait_until='domcontentloaded')
    expect(page.locator('#loading')).to_be_visible()
    page.screenshot(path=str(OUT / 'loading.png'))
    expect(page.locator('#save')).to_be_enabled()
    expect(page.locator('#empty')).to_be_visible()
    page.screenshot(path=str(OUT / 'empty-wide.png'))
    page.locator('#post-url').fill('https://x.com/kai')
    page.locator('#save').click()
    expect(page.locator('#save-error')).to_contain_text('Paste a link')
    page.screenshot(path=str(OUT / 'validation.png'))

    def save(url, title, text, notes, tags):
        page.locator('#post-url').fill(url)
        if not page.locator('#save-details').evaluate('(e)=>e.open'):
            page.locator('#save-details summary').click()
        for name, value in [('title',title), ('text',text), ('notes',notes), ('tags',tags)]:
            page.locator('#post-'+name).fill(value)
        page.locator('#save').click()
        expect(page.locator('#toast')).to_contain_text('Post saved')

    save('https://x.com/rajzmotion/status/2096237878464622927', 'Motion worth studying', 'Small UI details make the whole animation feel intentional.\nStudy the pacing, then try a different composition.', 'Look at how the type settles before the transition.', 'Motion, inspiration')
    save('https://www.threads.net/@studio/post/AbC_12', 'A useful creative-process thread', 'Collect the references. Find what they have in common. Make one deliberate choice for your own project.', 'Try this on the next project.', 'Process, read later')
    expect(page.locator('.post')).to_have_count(2)
    page.locator('.post').filter(has_text='Motion worth studying').get_by_role('button', name='Add to favorites').click()
    page.locator('[data-view=favorites]').click()
    expect(page.locator('.post')).to_have_count(1)
    page.locator('[data-view=saved]').click()
    page.locator('[data-platform=threads]').click()
    expect(page.locator('.post')).to_have_count(1)
    page.locator('[data-platform=all]').click()
    page.locator('#search').fill('pacing')
    expect(page.locator('.post')).to_have_count(1)
    page.locator('#search').fill('')
    page.locator('#page-title').click()
    page.keyboard.press('/')
    expect(page.locator('#search')).to_be_focused()
    page.locator('#page-title').click()
    page.keyboard.press('n')
    expect(page.locator('#post-url')).to_be_focused()
    page.locator('.post').filter(has_text='Motion worth studying').get_by_role('button', name='Edit', exact=True).click()
    page.locator('#edit-notes').fill('Saved note after editing. <script>window.injected=true</script>')
    page.locator('#save-edit').click()
    expect(page.locator('#edit-dialog')).not_to_be_visible()
    assert page.evaluate('window.injected') is None
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('.post')).to_have_count(2)
    expect(page.locator('.note').filter(has_text='Saved note after editing')).to_be_visible()
    page.locator('#post-url').fill('https://twitter.com/other/status/2096237878464622927?s=20')
    page.locator('#save').click()
    expect(page.locator('#toast')).to_contain_text('Already saved')
    expect(page.locator('.post')).to_have_count(2)
    page.locator('#post-url').fill('')
    page.locator('.post').filter(has_text='Motion worth studying').get_by_role('button', name='Archive', exact=True).click()
    expect(page.locator('.post')).to_have_count(1)
    page.locator('[data-view=archived]').click()
    expect(page.locator('.post')).to_have_count(1)
    page.get_by_role('button', name='Restore', exact=True).click()
    page.locator('[data-view=saved]').click()
    expect(page.locator('.post')).to_have_count(2)
    with page.expect_download() as event:
        page.locator('#export').click()
    backup = event.value.path()
    assert len(json.loads(Path(backup).read_text())['posts']) == 2
    page.locator('#import-file').set_input_files(str(backup))
    expect(page.locator('#toast')).to_contain_text('0 posts restored. 2 already saved.')
    imported = {'version':1, 'posts':[{'url':'https://www.threads.com/@studio/post/Restore_2', 'title':'Restored from a backup'}]}
    page.locator('#import-file').set_input_files({'name':'backup.json', 'mimeType':'application/json', 'buffer':json.dumps(imported).encode()})
    expect(page.locator('#toast')).to_contain_text('1 post restored.')
    expect(page.locator('.post')).to_have_count(3)
    page.locator('.post').filter(has_text='Restored from a backup').get_by_role('button', name='Archive', exact=True).click()
    expect(page.locator('.post')).to_have_count(2)
    page.screenshot(path=str(OUT / 'saved-wide.png'), full_page=True)

    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT / 'saved-narrow.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.post').first.get_by_role('button', name='Edit', exact=True).click()
    page.screenshot(path=str(OUT / 'edit-narrow.png'), full_page=True)
    page.keyboard.press('Escape')
    expect(page.locator('#edit-dialog')).not_to_be_visible()
    page.locator('#search').fill('no matching posts here')
    expect(page.locator('#empty-title')).to_contain_text('No posts match')
    page.locator('#empty-action').click()
    expect(page.locator('.post')).to_have_count(2)
    failure['write'] = True
    page.locator('#post-url').fill('https://x.com/kai/status/999')
    page.locator('#save').click()
    expect(page.locator('#save-error')).to_contain_text('Connection interrupted')
    expect(page.locator('#post-url')).to_have_value('https://x.com/kai/status/999')
    failure['write'] = False
    failure['read'] = True
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#load-error')).to_be_visible()
    page.screenshot(path=str(OUT / 'error-narrow.png'))
    failure['read'] = False
    page.locator('#retry').click()
    expect(page.locator('.post')).to_have_count(2)
    assert not errors, errors
    browser.close()
print('PASS: persistent saves, duplicate safety, validation, edit, favorites, archive/restore, search, platform filter, export, failure recovery, desktop/mobile layout.')
