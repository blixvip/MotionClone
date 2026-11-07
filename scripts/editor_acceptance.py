"""Exercise the real Editor in an isolated local server. AI submission is intercepted."""
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect
from app.process import popen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/editor';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='motionclone-editor-') as temp:
    data=Path(temp)
    for ident in ['cf8c4707e634','5db95a3a7c73']:
        dest=data/ident;dest.mkdir()
        for name in ['job.json','source.mp4','media.json','thumbnail.jpg']:
            source=ROOT/'data'/ident/name
            if source.exists():shutil.copy2(source,dest/name)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=dict(os.environ,FRAMEFORGE_DATA=str(data),FRAMEFORGE_PORT=str(port))
    with (OUT/'server.log').open('wb') as log:
        proc=popen([sys.executable,'-m','uvicorn','app.server:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            for _ in range(80):
                if proc.poll() is not None:raise RuntimeError('Isolated server failed to start; see outputs/editor/server.log')
                try:
                    with urlopen(base+'/editor',timeout=1) as response:
                        if response.status==200:break
                except Exception:time.sleep(.25)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome')
                page=browser.new_page(viewport={'width':1512,'height':1080})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/editor/draft',lambda route:route.fulfill(status=503,json={'detail':'Temporary draft load failure'}))
                page.goto(base+'/editor')
                expect(page.locator('#notice')).to_have_text('Temporary draft load failure')
                expect(page.locator('#brand')).to_be_disabled()
                page.unroute('**/api/editor/draft')
                page.locator('#refresh').click()
                expect(page.locator('#brand')).to_be_enabled()
                expect(page.locator('#notice')).to_be_hidden()
                expect(page.locator('.reference-item')).to_have_count(2,timeout=30000)
                page.screenshot(path=str(OUT/'empty.png'),full_page=True)
                page.locator('[data-project="cf8c4707e634"]').click()
                page.locator('#trim-start').fill('7');page.locator('#trim-end').fill('9')
                page.locator('#add-segment').click()
                page.locator('[data-project="5db95a3a7c73"]').click()
                page.locator('#trim-start').fill('0.5');page.locator('#trim-end').fill('2')
                page.locator('#add-segment').click()
                page.get_by_role('button',name='Move earlier segment 2').click()
                page.locator('.segment input').first.fill('Use our blue brand color')
                page.locator('#brand').fill('My launch');page.locator('#instructions').fill('A short launch video with clear product titles.')
                page.locator('#save').click();expect(page.locator('#save-status')).to_have_text('Sequence saved')
                page.reload();expect(page.locator('.segment')).to_have_count(2)
                expect(page.locator('#brand')).to_have_value('My launch')
                assert '0.50s' in page.locator('.segment-range').first.inner_text()
                page.locator('#play-sequence').click()
                page.wait_for_function('() => !document.getElementById("preview").paused')
                page.wait_for_function('() => document.getElementById("preview").src.includes("cf8c4707e634")',timeout=15000)
                page.wait_for_function('() => document.getElementById("preview").paused',timeout=15000)
                page.locator('#play-sequence').click()
                expect(page.locator('#play-sequence')).to_have_text('Stop sequence')
                page.locator('#trim-start').fill('0.75')
                expect(page.locator('#play-sequence')).to_have_text('Play sequence')
                assert page.locator('#preview').evaluate('(video) => video.paused')
                # Invalid selection cannot be added.
                page.locator('#trim-start').fill('10');page.locator('#trim-end').fill('9')
                expect(page.locator('#add-segment')).to_be_disabled()
                expect(page.locator('#selected-duration')).to_have_text('Choose a valid range')
                expect(page.locator('.segment')).to_have_count(2)
                page.locator('#refresh').click();expect(page.locator('#notice')).to_be_hidden()
                page.locator('[data-project="cf8c4707e634"]').click();page.locator('#trim-end').fill('10');page.locator('#trim-start').fill('8')
                page.wait_for_function('() => document.getElementById("preview").readyState>=2 && !document.getElementById("preview").seeking')
                for width in [1512,768,390,320]:
                    page.set_viewport_size({'width':width,'height':1080})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
                    page.screenshot(path=str(OUT/f'editor-{width}.png'),full_page=True)
                # An offline account cannot generate.
                def offline(route):
                    response=route.fetch();state=response.json();state['chatgpt']=False
                    route.fulfill(response=response,json=state)
                page.route('**/api/status',offline);page.locator('#refresh').click()
                expect(page.locator('#generate')).to_be_disabled()
                expect(page.locator('#connection-title')).to_contain_text('Connect your own')
                page.unroute('**/api/status',offline)
                # Prove import uses real media processing, without invoking AI.
                page.locator('#reference-file').set_input_files(str(ROOT/'data/5db95a3a7c73/source.mp4'))
                expect(page.locator('#import-status')).to_have_text('Reference ready. Select a segment to add.',timeout=120000)
                expect(page.locator('.reference-item')).to_have_count(3)
                # Check the generation request and actionable errors without spending AI allowance.
                def online(route):
                    response=route.fetch();state=response.json();state['chatgpt']=True
                    route.fulfill(response=response,json=state)
                page.route('**/api/status',online);page.locator('#refresh').click()
                expect(page.locator('#generate')).to_be_enabled()
                submitted=[]
                def generate(route):
                    submitted.append(route.request.post_data_json)
                    route.fulfill(status=503,json={'detail':'Test: generation worker offline'})
                page.route('**/api/editor/generate',generate)
                saves=[]
                page.route('**/api/editor/draft',lambda route:saves.append(route))
                page.locator('#generate').click()
                expect(page.locator('#generate')).to_be_disabled()
                # Repeated activation while saving must not submit another paid job.
                page.locator('#generate').dispatch_event('click')
                page.locator('#brand').fill('My next video')
                assert len(saves)==1
                saves[0].continue_()
                expect(page.locator('#notice')).to_have_text('Test: generation worker offline')
                assert len(submitted)==1
                assert submitted[0]['segments'][0]['project']=='5db95a3a7c73'
                assert submitted[0]['brand']=='My launch'
                expect(page.locator('#brand')).to_have_value('My next video')
                expect(page.locator('#save-status')).to_have_text('Unsaved changes')
                expect(page.locator('#generate')).to_be_enabled()
                assert not errors,errors
                browser.close()
            print('PASS: load failure/retry, real import, trim validation, reorder, notes, saved draft/reload, sequence playback, account gate, single generation/snapshot, desktop/mobile, no browser errors')
        finally:
            proc.terminate();proc.wait(timeout=15) # Only the isolated test server created above; never Warp.
