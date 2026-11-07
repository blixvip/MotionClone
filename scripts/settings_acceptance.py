"""Settings UI against an isolated app and a fake Codex account; no real sign-in."""
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'test-results/settings'
OUT.mkdir(parents=True, exist_ok=True)


class AccountRPC:
    def __init__(self):
        self.account = None
        self.notifications = []
        self.fail = False
        self.starts = 0

    def call(self, method, params=None):
        if self.fail:
            raise ValueError('ChatGPT could not be reached. Try again.')
        if method == 'account/read':
            return {'account': self.account}
        if method == 'account/login/start':
            self.starts += 1
            return dict(loginId='fixture-login', verificationUrl='https://auth.openai.com/codex/device', userCode='TEST-1234')
        if method == 'account/logout':
            self.account = None
        return {}

    def close(self):
        pass


with tempfile.TemporaryDirectory(prefix='motionclone-settings-') as data:
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    os.environ['FRAMEFORGE_DATA'] = data
    os.environ['FRAMEFORGE_PORT'] = str(port)
    os.environ.pop('FRAMEFORGE_HOSTED', None)
    from app import server
    from app.connection import Connection
    rpc = AccountRPC()
    server.CONNECTION = Connection(lambda: rpc)
    server.auth_status = lambda: bool(rpc.account)
    host = uvicorn.Server(uvicorn.Config(server.app, log_level='error'))
    worker = threading.Thread(target=host.run, kwargs={'sockets': [sock]}, daemon=True)
    worker.start()
    try:
        for _ in range(100):
            if host.started:
                break
            time.sleep(.05)
        assert host.started, 'Preview server did not start'
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome')
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/?workspace=1', wait_until='networkidle')
            page.locator('#url').fill('https://x.com/example/status/123')
            for width in (1440, 768, 390, 320):
                page.set_viewport_size({'width':width, 'height':1000})
                for selector in ('.header-support .github-link', '.header-support .coffee-link', '#open-settings'):
                    expect(page.locator(selector)).to_be_visible()
                    bounds = page.locator(selector).bounding_box()
                    assert bounds['y'] + bounds['height'] < 250, (width, selector, bounds)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
                page.screenshot(path=str(OUT / f'header-{width}.png'))
                page.locator('#open-settings').click()
                expect(page.locator('#account-badge')).to_have_text('Not connected')
                expect(page.locator('#connect-account')).to_be_visible()
                expect(page.locator('#settings-ffmpeg')).to_have_text('Ready')
                assert page.locator('#settings-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth'), width
                page.screenshot(path=str(OUT / f'disconnected-{width}.png'))
                page.keyboard.press('Escape')
                expect(page.locator('#settings-dialog')).not_to_be_visible()
                expect(page.locator('#open-settings')).to_be_focused()
                expect(page.locator('#url')).to_have_value('https://x.com/example/status/123')
            assert page.locator('.header-support .github-link').get_attribute('href') == 'https://github.com/blixvip/MotionClone'
            assert page.locator('.header-support .coffee-link').get_attribute('href') == 'https://buymeacoffee.com/blix'
            page.locator('#open-settings').click()
            expect(page.locator('#refresh-account')).to_be_enabled()
            page.locator('#connect-account').click()
            expect(page.locator('#account-code')).to_have_text('TEST-1234')
            expect(page.locator('#account-verify')).to_have_attribute('href', 'https://auth.openai.com/codex/device')
            expect(page.locator('#disconnect-account')).to_have_text('Cancel sign-in')
            page.screenshot(path=str(OUT / 'pending-320.png'))
            assert rpc.starts == 1
            page.locator('#disconnect-account').click()
            expect(page.locator('#account-device')).to_be_hidden()
            page.locator('#connect-account').click()
            expect(page.locator('#account-device')).to_be_visible()
            rpc.account = dict(type='chatgpt', email='creator@example.com', planType='plus')
            expect(page.locator('#account-badge')).to_have_text('Connected', timeout=10000)
            expect(page.locator('#account-plan')).to_have_text('ChatGPT plus')
            expect(page.locator('#account-device')).to_be_hidden()
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':1000})
                page.screenshot(path=str(OUT / f'connected-{width}.png'))
            rpc.fail = True
            page.locator('#refresh-account').click()
            expect(page.locator('#account-message')).to_contain_text('could not be reached')
            expect(page.locator('#refresh-account')).to_be_enabled()
            page.screenshot(path=str(OUT / 'error-390.png'))
            rpc.fail = False
            page.locator('#refresh-account').click()
            expect(page.locator('#account-badge')).to_have_text('Connected')
            page.locator('#disconnect-account').click()
            expect(page.locator('#account-badge')).to_have_text('Not connected')
            page.reload(wait_until='networkidle')
            expect(page.locator('#settings-dialog')).to_be_visible()
            assert not errors, errors
            browser.close()
    finally:
        host.should_exit = True
        worker.join(timeout=10)
        sock.close()
print('PASS: visible support, Settings, device sign-in/cancel/completion/disconnect, error recovery, Escape/focus, saved input, responsive layouts')
