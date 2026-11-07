(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let items = [], token = '', view = 'all', platform = 'all', editing = null, toastTimer;
  let displayMode = 'calendar', month = new Date(new Date().getFullYear(), new Date().getMonth(), 1), selectedDay = null;
  const dayKey = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const platforms = {x: {name:'X / Twitter', icon:'𝕏'}, threads:{name:'Threads', icon:'@'}, linkedin:{name:'LinkedIn', icon:'in'}, youtube:{name:'YouTube', icon:'▶'}};
  const isComposition = post => !!post.status;
  const postDay = post => isComposition(post) ? post.date : dayKey(new Date(post.created * 1000));
  const statusName = value => ({draft:'Draft', planned:'Planned', published:'Published'}[value] || 'Saved link');
  let composing = null, composeSnapshot = '';
  const tags = value => value.split(',').map(v => v.trim()).filter(Boolean);
  function notify(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 5000); }
  function failure(id, message = '') { $(id).textContent = message; $(id).hidden = !message; }
  async function request(path, options = {}, retry = true) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    let response;
    try {
      response = await fetch(path, {...options, signal: controller.signal, headers: {'Content-Type':'application/json', 'X-Frameforge-Token': token, ...options.headers}});
    } catch (error) { throw new Error(error.name === 'AbortError' ? 'The request timed out. Your entered text is still here; please retry.' : 'Couldn’t reach Post Schedule. Check the connection and retry.'); }
    finally { clearTimeout(timer); }
    if (response.status === 403 && retry && options.method) { token = (await request('/api/status')).token; return request(path, options, false); }
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map(e => e.msg.replace(/^Value error, /, '')).join(' ') : data.detail;
      throw new Error(detail || 'Couldn’t save this change. Please retry.');
    }
    return data;
  }
  const element = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  function replace(post) { const at = items.findIndex(p => p.id === post.id); if (at < 0) items.unshift(post); else items[at] = post; render(); }
  async function change(post, values, button) {
    button.disabled = true;
    try { const action = button.dataset.action; replace(await request(isComposition(post) ? `/api/compositions/${post.id}` : `/api/posts/${post.id}`, {method:isComposition(post) ? 'PUT' : 'PATCH', body:JSON.stringify(isComposition(post) ? {...post, ...values} : values)})); const focus = document.querySelector(`.post[data-id="${post.id}"] [data-action="${action}"]`) || document.querySelector(`[data-view="${view}"]`); focus?.focus({preventScroll:true}); notify(values.archived === true ? 'Moved to archive.' : values.archived === false ? 'Restored to saved posts.' : values.favorite ? 'Added to favorites.' : 'Removed from favorites.'); }
    catch (error) { notify(error.message); button.disabled = false; }
  }
  function edit(post) {
    if (isComposition(post)) { compose(post); return; }
    editing = post; $('edit-title').value = post.title; $('edit-text').value = post.text; $('edit-notes').value = post.notes; $('edit-tags').value = post.tags.join(', '); $('edit-link').textContent = post.url; failure('edit-error'); $('edit-dialog').showModal(); $('edit-title').focus();
  }
  function card(post) {
    const root = element('article', 'post'); root.dataset.id = post.id;
    const head = element('div', 'post-head'), icon = element('span', 'platform-icon', platforms[post.platform].icon); icon.setAttribute('aria-hidden', 'true');
    const author = element('div', 'post-author'); author.append(element('strong', '', isComposition(post) ? platforms[post.platform].name : post.author), element('span', 'post-date', isComposition(post) ? `${statusName(post.status)} · ${post.date ? new Date(post.date + 'T12:00:00').toLocaleDateString(undefined, {month:'short', day:'numeric'}) + (post.time ? ' · ' + post.time : '') : 'No date yet'}` : `${platforms[post.platform].name} · Saved ${new Date(post.created * 1000).toLocaleDateString(undefined, {month:'short', day:'numeric'})}`));
    const favorite = element('button', 'icon-button', post.favorite ? '★' : '☆'); favorite.dataset.action = 'favorite'; favorite.setAttribute('aria-label', post.favorite ? 'Remove from favorites' : 'Add to favorites'); favorite.setAttribute('aria-pressed', String(post.favorite)); favorite.addEventListener('click', () => change(post, {favorite:!post.favorite}, favorite));
    head.append(icon, author, favorite); root.append(head, element('h2', '', post.title || (isComposition(post) ? `${platforms[post.platform].name} post` : `Post by ${post.author}`)));
    const text = element('p', 'post-text', post.text || (isComposition(post) ? 'An idea to keep working on.' : 'Link saved. Open the original, or add the post text and your notes.')); root.append(text);
    if (post.text.length > 220 || post.text.split('\n').length > 5) { const expand = element('button', 'quiet expand', 'Read saved text'); expand.setAttribute('aria-expanded', 'false'); expand.addEventListener('click', () => { const expanded = text.classList.toggle('expanded'); expand.textContent = expanded ? 'Show less' : 'Read saved text'; expand.setAttribute('aria-expanded', String(expanded)); }); root.append(expand); }
    if (post.notes) root.append(element('div', 'note', post.notes));
    if (post.tags.length) { const list = element('div', 'tags'); for (const tag of post.tags) { const button = element('button', 'tag', '#' + tag); button.addEventListener('click', () => { $('search').value = tag; render(); $('search').focus(); }); list.append(button); } root.append(list); }
    const footer = element('div', 'post-footer'), open = element('a', 'open-post', 'Open original ↗'); open.href = post.url; open.target = '_blank'; open.rel = 'noopener noreferrer';
    const editButton = element('button', 'quiet', 'Edit'); editButton.addEventListener('click', () => edit(post));
    const archive = element('button', 'quiet', post.archived ? 'Restore' : 'Archive'); archive.dataset.action = 'archive'; archive.addEventListener('click', () => change(post, {archived:!post.archived}, archive));
    if (isComposition(post)) { const badge = element('span', `status-badge ${post.status}`, statusName(post.status)); footer.append(badge); } else { footer.append(open); } footer.append(editButton, archive); root.append(footer); return root;
  }
  function renderCalendar(posts) {
    $('calendar').hidden = displayMode !== 'calendar';
    $('agenda-heading').hidden = false;
    $('agenda-title').textContent = selectedDay ? `Posts for ${new Date(selectedDay + 'T12:00:00').toLocaleDateString(undefined, {month:'long', day:'numeric', year:'numeric'})}` : ({all:'All posts', draft:'Drafts', planned:'Planned posts', published:'Published posts', saved:'Saved links', favorites:'Favorites', archived:'Archive'}[view]);
    $('clear-day').hidden = !selectedDay;
    $('sort').closest('label').hidden = displayMode === 'calendar';
    document.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === displayMode)));
    $('calendar-month').textContent = month.toLocaleDateString(undefined, {month:'long', year:'numeric'});
    const grouped = new Map();
    for (const post of posts) { const key = postDay(post); if (!key) continue; if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(post); }
    const start = new Date(month.getFullYear(), month.getMonth(), 1 - (month.getDay() + 6) % 7);
    const length = Math.ceil(((month.getDay() + 6) % 7 + new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()) / 7) * 7;
    const today = dayKey(new Date()), cells = [];
    for (let index = 0; index < length; index++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index), key = dayKey(date), daily = grouped.get(key) || [];
      const button = element('button', 'calendar-day'); button.type = 'button'; button.dataset.date = key;
      button.classList.toggle('outside', date.getMonth() !== month.getMonth());
      button.classList.toggle('today', key === today); button.classList.toggle('has-posts', daily.length > 0);
      button.setAttribute('aria-pressed', String(selectedDay === key));
      button.setAttribute('aria-label', `${date.toLocaleDateString(undefined, {weekday:'long', year:'numeric', month:'long', day:'numeric'})}, ${daily.length} ${daily.length === 1 ? 'post' : 'posts'}, click to write${key === today ? ', today' : ''}`);
      if (key === today) button.setAttribute('aria-current', 'date');
      const number = element('span', 'day-number', date.getDate()); button.append(number);
      const previews = element('span', 'day-previews');
      daily.slice(0, 2).forEach(post => { const preview = element('span', `day-post ${post.platform}`, `${platforms[post.platform].icon}  ${post.title || post.text || post.author || 'Untitled post'}`); preview.dataset.postId = post.id; preview.title = `${statusName(post.status)}: ${post.title || post.text || post.author}`; previews.append(preview); });
      if (daily.length > 2) previews.append(element('span', 'day-more', `+${daily.length - 2} more`));
      button.append(previews);
      if (daily.length) button.append(element('span', 'day-count', daily.length));
      button.addEventListener('click', event => { const ident = event.target.closest('[data-post-id]')?.dataset.postId; selectedDay = key; month = new Date(date.getFullYear(), date.getMonth(), 1); render(); if (ident) edit(items.find(post => post.id === ident)); else compose(null, key); });
      cells.push(button);
    }
    $('calendar-days').replaceChildren(...cells);
    const total = posts.filter(post => { const key = postDay(post); if (!key) return false; const date = new Date(key + 'T12:00:00'); return date.getFullYear() === month.getFullYear() && date.getMonth() === month.getMonth(); }).length;
    $('month-count').textContent = `${total} ${total === 1 ? 'post' : 'posts'} this month`;
  }
  function render() {
    $('all-count').textContent = items.filter(p => !p.archived).length; for (const state of ['draft', 'planned', 'published']) $(state + '-count').textContent = items.filter(p => !p.archived && p.status === state).length; $('saved-count').textContent = items.filter(p => !p.archived && !isComposition(p)).length; $('favorite-count').textContent = items.filter(p => !p.archived && p.favorite).length; $('archive-count').textContent = items.filter(p => p.archived).length;
    document.querySelectorAll('[data-view]').forEach(b => { const active = b.dataset.view === view; b.classList.toggle('selected', active); b.setAttribute('aria-pressed', String(active)); });
    document.querySelectorAll('[data-platform]').forEach(b => { const active = b.dataset.platform === platform; b.classList.toggle('selected', active); b.setAttribute('aria-pressed', String(active)); });
    const query = $('search').value.trim().toLocaleLowerCase();
    const visible = items.filter(p => (view === 'archived' ? p.archived : !p.archived && (view === 'favorites' ? p.favorite : view === 'saved' ? !isComposition(p) : ['draft','planned','published'].includes(view) ? p.status === view : true)) && (platform === 'all' || p.platform === platform) && [p.title, p.text, p.notes, p.author, p.url, ...p.tags].join(' ').toLocaleLowerCase().includes(query));
    visible.sort((a,b) => $('sort').value === 'oldest' ? a.created - b.created : $('sort').value === 'title' ? (a.title || a.author || a.text).localeCompare(b.title || b.author || b.text) : b.created - a.created);
    renderCalendar(visible);
    const listed = selectedDay ? visible.filter(post => postDay(post) === selectedDay) : visible;
    $('posts').replaceChildren(...listed.map(card)); $('result-count').textContent = `${visible.length} ${visible.length === 1 ? 'post' : 'posts'}`; $('empty').hidden = listed.length > 0; $('export').disabled = items.length === 0;
    $('bookmark-panel').open = view === 'saved';
    const first = items.length === 0, filtered = !!query || platform !== 'all';
    $('empty-title').textContent = first ? 'Your next post starts here.' : filtered ? 'No posts match that search.' : view === 'favorites' ? 'Keep your best finds close.' : view === 'archived' ? 'Your archive is clear.' : `No ${view === 'all' ? 'posts' : view} yet.`;
    $('empty-copy').textContent = first ? 'Click a calendar date or New post. Choose a platform and start writing.' : filtered ? 'Try another search or show all platforms.' : view === 'favorites' ? 'Star a saved post to find it here.' : view === 'archived' ? 'Archived posts stay saved. Restore them whenever you want.' : 'Create a post and choose Draft, Planned, or Published. Undated drafts stay in your library.';
    $('empty-action').textContent = filtered ? 'Clear filters' : view === 'favorites' ? 'Browse saved posts' : '+ New post';
    if (selectedDay && !listed.length) { $('empty-title').textContent = 'No posts on this day yet.'; $('empty-copy').textContent = 'Choose another day or browse your full library.'; $('empty-action').textContent = 'Show all days'; }
  }
  async function load() {
    $('loading').hidden = false; $('empty').hidden = true; $('load-error').hidden = true; $('save').disabled = true; $('new-post').disabled = true; $('retry').disabled = true;
    try { const state = await request('/api/status'); token = state.token; items = [...await request('/api/posts'), ...await request('/api/compositions')]; render(); $('save').disabled = false; $('new-post').disabled = false; }
    catch (error) { $('load-error').hidden = false; $('load-error').querySelector('span').textContent = error.message; $('result-count').textContent = 'Unavailable'; }
    finally { $('loading').hidden = true; $('retry').disabled = false; }
  }
  $('save-form').addEventListener('submit', async event => {
    event.preventDefault(); if ($('save').disabled) return; failure('save-error'); $('save').disabled = true; $('save').textContent = 'Saving…';
    try {
      const result = await request('/api/posts', {method:'POST', body:JSON.stringify({url:$('post-url').value, title:$('post-title').value, text:$('post-text').value, notes:$('post-notes').value, tags:tags($('post-tags').value)})});
      view = result.post.archived ? 'archived' : 'saved'; platform = 'all'; selectedDay = null; const savedDate = new Date(result.post.created * 1000); month = new Date(savedDate.getFullYear(), savedDate.getMonth(), 1); $('search').value = ''; replace(result.post);
      if (result.duplicate) { notify('Already saved. Your existing notes are unchanged.'); }
      else { $('save-form').reset(); $('save-details').open = false; notify('Post saved for later.'); }
    } catch (error) { failure('save-error', error.message); }
    finally { $('save').disabled = false; $('save').textContent = '+ Save post'; }
  });
  $('edit-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!editing || $('save-edit').disabled) return; $('save-edit').disabled = true; failure('edit-error');
    try { replace(await request(`/api/posts/${editing.id}`, {method:'PATCH', body:JSON.stringify({title:$('edit-title').value, text:$('edit-text').value, notes:$('edit-notes').value, tags:tags($('edit-tags').value)})})); $('edit-dialog').close(); notify('Changes saved.'); }
    catch (error) { failure('edit-error', error.message); }
    finally { $('save-edit').disabled = false; }
  });
  for (const id of ['close-edit', 'cancel-edit']) $(id).addEventListener('click', () => $('edit-dialog').close());
  $('views').addEventListener('click', event => { const button = event.target.closest('[data-view]'); if (button) { view = button.dataset.view; selectedDay = null; render(); } });
  $('platforms').addEventListener('click', event => { const button = event.target.closest('[data-platform]'); if (button) { platform = button.dataset.platform; render(); } });
  $('search').addEventListener('input', render); $('sort').addEventListener('change', render); $('retry').addEventListener('click', load);
  $('empty-action').addEventListener('click', () => { if (selectedDay) { selectedDay = null; render(); } else if ($('search').value || platform !== 'all') { $('search').value = ''; platform = 'all'; render(); } else if (view === 'favorites') { view = 'saved'; render(); } else { compose(); } });
  $('display-modes').addEventListener('click', event => { const button = event.target.closest('[data-mode]'); if (button) { displayMode = button.dataset.mode; selectedDay = null; render(); } });
  $('clear-day').addEventListener('click', () => { selectedDay = null; render(); });
  for (const [id, delta] of [['calendar-prev', -1], ['calendar-next', 1]]) $(id).addEventListener('click', () => { month = new Date(month.getFullYear(), month.getMonth() + delta, 1); selectedDay = null; render(); });
  $('calendar-today').addEventListener('click', () => { const now = new Date(); month = new Date(now.getFullYear(), now.getMonth(), 1); selectedDay = dayKey(now); render(); });
  $('export').addEventListener('click', () => { const blob = new Blob([JSON.stringify({version:2, exported:new Date().toISOString(), posts:items.filter(p => !isComposition(p)), compositions:items.filter(isComposition)}, null, 2)], {type:'application/json'}); const url = URL.createObjectURL(blob); const link = element('a'); link.href = url; link.download = `post-schedule-${new Date().toISOString().slice(0,10)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); notify('Library backup downloaded.'); });
  $('import').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', async () => {
    const file = $('import-file').files[0]; if (!file) return;
    $('import').disabled = true;
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('Choose a backup smaller than 5 MB.');
      let data; try { data = JSON.parse(await file.text()); } catch { throw new Error('That file isn’t a JSON library backup.'); }
      const result = await request('/api/posts/import', {method:'POST', body:JSON.stringify(data)});
      items = [...await request('/api/posts'), ...await request('/api/compositions')]; selectedDay = null; view = 'all'; platform = 'all'; $('search').value = ''; render();
      notify(`${result.imported} ${result.imported === 1 ? 'post' : 'posts'} restored. ${result.skipped} already saved.`);
    } catch (error) { notify(error.message); }
    finally { $('import').disabled = false; $('import-file').value = ''; }
  });
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey || $('edit-dialog').open || $('compose-dialog').open || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    if (event.key === '/') { event.preventDefault(); $('search').focus(); }
    if (event.key.toLowerCase() === 'n' && !$('new-post').disabled) { event.preventDefault(); compose(); }
  });
  function composeValues() {
    return {platform:$('compose-platform').value, status:$('compose-status').value, date:$('compose-date').value || null, time:$('compose-time').value, title:$('compose-title').value, text:$('compose-text').value, notes:$('compose-notes').value, tags:tags($('compose-tags').value), favorite:composing?.favorite || false, archived:composing?.archived || false};
  }
  function updatePreview() {
    const values = composeValues();
    $('preview-icon').textContent = platforms[values.platform].icon;
    $('preview-platform').textContent = platforms[values.platform].name;
    $('preview-status').textContent = statusName(values.status);
    $('preview-status').className = `status-badge ${values.status}`;
    $('preview-text').textContent = values.text || 'Your words will appear here.';
    $('preview-date').textContent = values.date ? new Date(values.date + 'T12:00:00').toLocaleDateString(undefined, {weekday:'short', month:'long', day:'numeric', year:'numeric'}) + (values.time ? ' · ' + values.time : '') : 'No date picked';
    $('compose-count').textContent = `${Array.from(values.text).length.toLocaleString()} characters`;
    $('compose-date').required = values.status === 'planned' || !!values.time;
    $('compose-text-label').textContent = values.platform === 'youtube' ? 'YouTube post / video description' : values.platform === 'threads' ? 'Post or thread text' : 'Post text';
    $('save-compose').textContent = values.status === 'draft' ? 'Save draft' : values.status === 'planned' ? 'Save to calendar' : 'Save as published';
  }
  function compose(post = null, date = null) {
    composing = post;
    $('compose-form').reset();
    $('compose-heading').textContent = post ? 'Edit post' : 'New post';
    $('compose-platform').value = post?.platform || (platform !== 'all' ? platform : 'x');
    $('compose-status').value = post?.status || 'draft';
    $('compose-date').value = post?.date || date || '';
    $('compose-time').value = post?.time || '';
    for (const field of ['title','text','notes']) $('compose-' + field).value = post?.[field] || '';
    $('compose-tags').value = (post?.tags || []).join(', ');
    failure('compose-error'); updatePreview(); composeSnapshot = JSON.stringify(composeValues());
    $('compose-dialog').showModal(); $('compose-text').focus();
  }
  function closeComposer() {
    if ($('save-compose').disabled) return;
    if (JSON.stringify(composeValues()) !== composeSnapshot && !window.confirm('Discard your unsaved changes?')) return;
    $('compose-dialog').close();
  }
  $('new-post').addEventListener('click', () => compose(null, selectedDay));
  $('compose-form').addEventListener('input', updatePreview);
  $('compose-form').addEventListener('change', updatePreview);
  for (const id of ['close-compose','cancel-compose']) $(id).addEventListener('click', closeComposer);
  $('compose-dialog').addEventListener('cancel', event => { event.preventDefault(); closeComposer(); });
  $('copy-compose').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('compose-text').value); notify('Post text copied.'); } catch { $('compose-text').focus(); $('compose-text').select(); notify('Select and copy the highlighted text.'); } });
  $('compose-form').addEventListener('submit', async event => {
    event.preventDefault(); if ($('save-compose').disabled) return;
    failure('compose-error'); $('save-compose').disabled = true;
    const values = composeValues();
    try {
      const post = await request(composing ? `/api/compositions/${composing.id}` : '/api/compositions', {method:composing ? 'PUT' : 'POST', body:JSON.stringify(values)});
      view = post.archived ? 'archived' : post.status; platform = 'all'; selectedDay = null; $('search').value = '';
      if (post.date) { const date = new Date(post.date + 'T12:00:00'); month = new Date(date.getFullYear(), date.getMonth(), 1); }
      replace(post); $('compose-dialog').close(); notify(`${statusName(post.status)} saved.`);
    } catch (error) { failure('compose-error', error.message); }
    finally { $('save-compose').disabled = false; updatePreview(); }
  });
  void load();
})();
