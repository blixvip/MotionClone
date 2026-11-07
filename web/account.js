(async () => {
  const get = id => document.getElementById(id);
  // Older running local servers serve index.html directly until their next restart.
  if (!get('settings-dialog')) {
    const response = await fetch('/static/account.html');
    if (!response.ok) throw new Error('Could not load Settings. Refresh MotionClone and try again.');
    const fragment = new DOMParser().parseFromString(await response.text(), 'text/html');
    const settings = fragment.getElementById('settings-dialog');
    if (!settings) throw new Error('Settings is unavailable. Refresh MotionClone and try again.');
    document.body.append(settings);
    decorateControls(settings);
  }
  const dialog = get('settings-dialog'), panel = get('account-panel');
  if (!dialog || !panel) return;
  const hosted = document.body.dataset.hosted === 'true';
  let busy = false, pending = false, checking = false, returnFocus = null;
  const message = text => {get('account-message').textContent = text; get('account-message').hidden = !text;};
  get('account-local-note').hidden = hosted;
  get('account-signout').hidden = !hosted;
  get('settings-storage').textContent = hosted ? 'Private to your account' : 'On this computer';
  function render(state) {
    const connected = state.status === 'connected';
    pending = state.status === 'pending';
    panel.dataset.state = state.status;
    get('account-badge').textContent = connected ? 'Connected' : pending ? 'Sign-in pending' : 'Not connected';
    get('connect-account').hidden = connected || pending;
    get('disconnect-account').hidden = !connected && !pending;
    get('disconnect-account').textContent = pending ? 'Cancel sign-in' : 'Disconnect';
    get('account-device').hidden = !pending;
    get('account-title').textContent = connected ? state.email || 'ChatGPT is connected' : pending ? 'Finish connecting your account' : 'Connect your ChatGPT account';
    get('account-description').textContent = connected ? 'Ready to rebuild. Selected reference frames are sent to ChatGPT.' : 'Sign in on OpenAI’s website. No API key needed.';
    get('account-plan').hidden = !connected || !state.plan;
    get('account-plan').textContent = state.plan ? `ChatGPT ${state.plan}` : '';
    get('account-code').textContent = pending ? state.userCode : '';
    if (pending) get('account-verify').href = state.verificationUrl;
    else get('account-verify').removeAttribute('href');
    if (state.status === 'expired') message('Sign-in expired or was cancelled. Connect again to get a new code.');
    else message('');
    if (connected) get('auth-help').hidden = true;
  }
  async function check() {
    if (checking || busy || document.hidden) return;
    checking = true;
    get('refresh-account').disabled = true;
    get('connect-account').disabled = true;
    get('disconnect-account').disabled = true;
    try {render(await api('/api/account')); await status();}
    catch (error) {
      if (error.status === 404) {
        const state = await status();
        if (state) render({status:state.chatgpt ? 'connected' : 'disconnected'});
        get('connect-account').hidden = true;
        get('disconnect-account').hidden = true;
        message('Restart MotionClone to enable ChatGPT sign-in controls. Your existing login is unchanged.');
      } else {
        get('account-badge').textContent = 'Unavailable'; panel.dataset.state = 'error';
        get('account-title').textContent = 'Couldn’t check your account'; message(error.message);
      }
    } finally {
      checking = false;
      get('refresh-account').disabled = false;
      get('connect-account').disabled = false;
      get('disconnect-account').disabled = false;
    }
  }
  function openSettings() {
    if (!dialog.open) {returnFocus = document.activeElement; dialog.showModal();}
    const url = new URL(location.href); url.searchParams.set('settings', '1'); history.replaceState({}, '', url);
    void check();
  }
  window.openSettings = openSettings;
  get('open-settings').addEventListener('click', openSettings);
  get('auth-settings').addEventListener('click', openSettings);
  get('close-settings').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    const url = new URL(location.href); url.searchParams.delete('settings'); history.replaceState({}, '', url);
    if (returnFocus?.isConnected) returnFocus.focus();
  });
  get('refresh-account').addEventListener('click', check);
  async function change(action) {
    if (busy || checking) return;
    busy = true; message('');
    get('connect-account').disabled = true; get('disconnect-account').disabled = true; get('refresh-account').disabled = true;
    get('connect-account').textContent = 'Connecting…';
    try {
      await status(); render(await api('/api/account/' + action, {method:'POST'}));
      if (pending) get('account-verify').focus();
      await status();
    } catch (error) {message(error.message);}
    finally {
      busy = false; get('connect-account').disabled = false; get('disconnect-account').disabled = false; get('refresh-account').disabled = false;
      get('connect-account').textContent = 'Connect ChatGPT';
    }
  }
  get('connect-account').addEventListener('click', () => change('connect'));
  get('disconnect-account').addEventListener('click', () => change('disconnect'));
  get('copy-account-code').addEventListener('click', async () => {
    try {await navigator.clipboard.writeText(get('account-code').textContent); message('Code copied.');}
    catch {message('Select the code above and copy it.');}
  });
  window.onAccountStatus = state => {
    for (const [id, ready] of [['settings-ffmpeg',state.ffmpeg], ['settings-renderer',state.hyperframes]]) {
      get(id).textContent = ready ? 'Ready' : 'Setup needed'; get(id).dataset.ready = String(!!ready);
    }
    get('settings-version').textContent = state.version ? `v${state.version}` : '';
  };
  document.addEventListener('visibilitychange', () => {if (dialog.open || pending) void check();});
  setInterval(() => {if (pending) void check();}, 2500);
  const reference = new URLSearchParams(location.search).get('url');
  if (hosted && reference && reference.length <= 2048 && reference.startsWith('https://')) get('url').value = reference;
  if (new URLSearchParams(location.search).has('settings')) openSettings();
})().catch(error => {
  const notice = document.getElementById('global-error');
  notice.textContent = error.message; notice.hidden = false;
});
