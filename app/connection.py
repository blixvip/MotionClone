"""Official Codex-managed device sign-in. Credentials never cross the HTTP API."""
import atexit
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .ai import codex_command
from .process import popen


def safe_environment(home):
    # Allowlist: no owner API keys, cloud credentials, gateway secret, or Codex config.
    allowed = {'path', 'systemroot', 'windir', 'comspec', 'pathext', 'temp', 'tmp',
               'lang', 'lc_all', 'ssl_cert_file', 'ssl_cert_dir', 'codex_ca_certificate',
               'programfiles', 'programfiles(x86)', 'programdata'}
    env = {k: v for k, v in os.environ.items() if k.lower() in allowed}
    home = Path(home).resolve()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env.update(CODEX_HOME=str(home), HOME=str(home), USERPROFILE=str(home),
               APPDATA=str(home / 'appdata'), LOCALAPPDATA=str(home / 'localappdata'))
    return env


class RPC:
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}
        self.sequence = 0
        self.notifications = queue.Queue(maxsize=50)
        hosted = os.environ.get('FRAMEFORGE_HOSTED') == '1'
        home = Path(os.environ['CODEX_HOME']) if hosted else Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        home.mkdir(parents=True, exist_ok=True)
        args = codex_command() + ['app-server', '--listen', 'stdio://']
        if hosted:
            args += ['-c', 'cli_auth_credentials_store="file"', '-c', 'forced_login_method="chatgpt"']
        # Local mode uses the same credential store and environment as the Codex CLI.
        # Hosted workers retain their isolated home and credential allowlist.
        self.proc = popen(args,
            cwd=home, env=safe_environment(home) if hosted else None, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.call('initialize', {'clientInfo': {'name': 'motionclone', 'title': 'MotionClone', 'version': '1.0.0'}})
            self._send({'method': 'initialized', 'params': {}})
        except Exception:
            self.close()
            raise
        atexit.register(self.close)

    def _send(self, message):
        with self.lock:
            if self.proc.poll() is not None:
                raise ValueError('Account connection stopped. Try connecting again.')
            self.proc.stdin.write(json.dumps(message) + '\n')
            self.proc.stdin.flush()

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if 'id' in message:
                    with self.lock:
                        target = self.pending.get(message['id'])
                    if target:
                        target.put(message)
                elif message.get('method') == 'account/login/completed':
                    try:
                        self.notifications.put_nowait(message['params'])
                    except queue.Full:
                        pass
        finally:
            with self.lock:
                for target in self.pending.values():
                    target.put({'error': {}})

    def call(self, method, params=None):
        with self.lock:
            self.sequence += 1
            ident = self.sequence
            target = queue.Queue()
            self.pending[ident] = target
        try:
            self._send({'id': ident, 'method': method, 'params': params})
            try:
                response = target.get(timeout=25)
            except queue.Empty:
                raise ValueError('ChatGPT did not respond. Try connecting again.') from None
            if 'error' in response:
                raise ValueError('Could not connect to ChatGPT. Enable device code login in your ChatGPT security settings, then retry.')
            return response.get('result', {})
        finally:
            with self.lock:
                self.pending.pop(ident, None)

    def close(self):
        # Exact child launched above only; never broad process cleanup.
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class Connection:
    def __init__(self, factory=RPC):
        self.factory = factory
        self.rpc = None
        self.lock = threading.RLock()
        self.pending = None
        self.deadline = 0
        self.last_state = 'disconnected'

    def client(self):
        if self.rpc is not None and hasattr(self.rpc, 'proc') and self.rpc.proc.poll() is not None:
            self.rpc = None
            self.pending = None
        if self.rpc is None:
            self.rpc = self.factory()
        return self.rpc

    def state(self, *, initialize=False):
        with self.lock:
            if initialize:
                self.client()
            if self.pending and time.monotonic() >= self.deadline:
                self._cancel()
                self.last_state = 'expired'
            if self.rpc is None:
                return {'status': self.last_state}
            self.client()
            account = self.rpc.call('account/read', {'refreshToken': False}).get('account')
            if account and account.get('type') == 'chatgpt':
                self.pending = None
                self.last_state = 'connected'
                return {'status': 'connected', 'email': account.get('email'), 'plan': account.get('planType')}
            notifications = self.rpc.notifications
            if hasattr(notifications, 'get_nowait'):
                while True:
                    try:
                        event = notifications.get_nowait()
                    except queue.Empty:
                        break
                    if self.pending and event.get('loginId') == self.pending['loginId'] and not event.get('success'):
                        self.pending = None
                        self.last_state = 'expired'
            if self.pending:
                return {k: v for k, v in self.pending.items() if k != 'loginId'}
            return {'status': self.last_state if self.last_state == 'expired' else 'disconnected'}

    def start(self):
        with self.lock:
            state = self.state(initialize=True)
            if state['status'] in ('pending', 'connected'):
                return state
            client = self.client()
            result = client.call('account/login/start', {'type': 'chatgptDeviceCode'})
            url = urlsplit(result.get('verificationUrl', ''))
            if url.scheme != 'https' or url.hostname != 'auth.openai.com' or url.port not in (None, 443) or url.username:
                client.call('account/login/cancel', {'loginId': result.get('loginId')})
                raise ValueError('ChatGPT returned an unexpected sign-in address. Try again.')
            self.deadline = time.monotonic() + 15 * 60
            self.pending = {'status': 'pending', 'loginId': result['loginId'],
                            'verificationUrl': result['verificationUrl'], 'userCode': result['userCode']}
            return {k: v for k, v in self.pending.items() if k != 'loginId'}

    def _cancel(self):
        if self.pending and self.rpc:
            self.rpc.call('account/login/cancel', {'loginId': self.pending['loginId']})
        self.pending = None

    def disconnect(self):
        with self.lock:
            self._cancel()
            if self.rpc:
                self.rpc.call('account/logout')
                self.rpc.close()
                self.rpc = None
            self.last_state = 'disconnected'
            return {'status': 'disconnected'}
