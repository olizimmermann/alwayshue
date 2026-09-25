'use strict';
// alwayshue admin UI. Vanilla JS, no innerHTML with data -> no XSS via bridge light names.

const S = { csrf: null, cfg: null, saved: null, lights: null, bridgeGroups: null, clientIp: '', logTimer: null };
const $ = (sel) => document.querySelector(sel);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : String(c));
  return el;
}

// ---------- API ----------
class ApiError extends Error {}

function fmtDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).filter((x) => x !== 'body').join(' › ')}: ${d.msg}`).join('\n');
  }
  return String(detail ?? 'Request failed');
}

async function api(method, path, body) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (S.csrf) opts.headers['X-CSRF-Token'] = S.csrf;
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch { /* empty */ }
  if (r.status === 401 && path !== '/api/login') { showLogin(); throw new ApiError('Session expired'); }
  if (!r.ok) throw new ApiError(fmtDetail(data && data.detail) || `HTTP ${r.status}`);
  return data;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 7000 : 2500);
}

async function guarded(fn, btn) {
  if (btn) btn.disabled = true;
  try { return await fn(); } catch (e) { if (!(e instanceof ApiError && e.message === 'Session expired')) toast(e.message, true); }
  finally { if (btn) btn.disabled = false; }
}

// ---------- auth ----------
function showLogin() {
  S.csrf = null;
  $('#app').hidden = true;
  $('#login').hidden = false;
  $('#login-password').focus();
}

$('#login-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  $('#login-error').textContent = '';
  try {
    const r = await api('POST', '/api/login', { password: $('#login-password').value });
    S.csrf = r.csrf;
    $('#login-password').value = '';
    await start();
  } catch (e) { $('#login-error').textContent = e.message; }
});

$('#logout').addEventListener('click', () => guarded(async () => { await api('POST', '/api/logout'); showLogin(); }));

// ---------- color helpers ----------
function hueColor(o) {
  const v = o.bri / 254;
  if (!o.use_color) return `hsl(40 90% ${Math.round(30 + v * 45)}%)`;
  const hDeg = Math.round((o.hue / 65535) * 360), s = o.sat / 254;
  const l = v * (1 - s / 2), sl = (l === 0 || l === 1) ? 0 : (v - l) / Math.min(l, 1 - l);
  return `hsl(${hDeg} ${Math.round(sl * 100)}% ${Math.round(Math.max(l, 0.12) * 100)}%)`;
}

// ---------- dirty state ----------
function markDirty() {
  const dirty = JSON.stringify(collect()) !== JSON.stringify(S.saved);
  $('#savebar').hidden = !dirty;
}

function collect() {
  const lines = (s) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
  const out = {
    bridge_ip: $('#bridge-ip').value.trim(),
    allowed_hosts: lines($('#allowed-hosts').value),
    admin_allowed_hosts: lines($('#admin-hosts').value),
    trusted_proxies: lines($('#trusted-proxies').value),
    switch_token: $('#switch-token').value.trim(),
    rooms: S.cfg.rooms,
    groups: S.cfg.groups,
  };
  const key = $('#api-key').value.trim();
  if (key) out.api_key = key;
  return out;
}

function snapshot(cfg) {
  const { api_key_set, ...rest } = cfg;
  return JSON.parse(JSON.stringify(rest));
}

function loadConfig(cfg) {
  S.cfg = snapshot(cfg);
  S.saved = snapshot(cfg);
  $('#bridge-ip').value = cfg.bridge_ip;
  $('#api-key').value = '';
  const st = $('#api-key-status');
  st.textContent = cfg.api_key_set ? 'set' : 'missing';
  st.className = 'pill ' + (cfg.api_key_set ? 'ok' : 'warn');
  $('#allowed-hosts').value = cfg.allowed_hosts.join('\n');
  $('#admin-hosts').value = cfg.admin_allowed_hosts.join('\n');
  $('#trusted-proxies').value = cfg.trusted_proxies.join('\n');
  $('#switch-token').value = cfg.switch_token;
  renderSwitches();
  markDirty();
}

$('#save').addEventListener('click', (ev) => guarded(async () => {
  const cfg = await api('PUT', '/api/config', collect());
  loadConfig(cfg);
  api('GET', '/api/session').then(showIps, () => {});
  toast('Saved');
}, ev.currentTarget));

$('#discard').addEventListener('click', () => loadConfig({ ...S.saved, api_key_set: $('#api-key-status').textContent === 'set' }));

for (const id of ['#bridge-ip', '#api-key', '#allowed-hosts', '#admin-hosts', '#trusted-proxies', '#switch-token']) {
  $(id).addEventListener('input', markDirty);
}

// ---------- switches ----------
function endpoint(kind, id) {
  const q = [];
  const tok = $('#switch-token').value.trim();
  if (tok) q.push('key=' + encodeURIComponent(tok));
  return `${location.protocol}//${location.host}/${kind}/${id}${q.length ? '?' + q.join('&') : ''}`;
}

function nextId(items) { return items.reduce((m, x) => Math.max(m, x.id), 0) + 1; }

function slider(label, obj, key, min, max, onChange, cls) {
  const out = h('output', {}, obj[key]);
  const input = h('input', {
    type: 'range', min, max, value: obj[key], class: cls,
    oninput: () => { obj[key] = Number(input.value); out.textContent = input.value; onChange(); },
  });
  const lab = h('span', {}, label);
  return { nodes: [lab, input, out], input, lab, out };
}

function lightControls(obj, swatch) {
  const refresh = () => {
    swatch.style.background = hueColor(obj);
    for (const s of [hueS, satS]) {
      s.input.disabled = !obj.use_color;
      for (const n of s.nodes) n.classList.toggle('disabled', !obj.use_color);
    }
    markDirty();
  };
  const briS = slider('Brightness', obj, 'bri', 1, 254, refresh);
  const hueS = slider('Hue', obj, 'hue', 0, 65535, refresh, 'hue-track');
  const satS = slider('Saturation', obj, 'sat', 0, 254, refresh);
  const fadeS = slider('Fade (ms)', obj, 'transition_ms', 0, 3000, refresh);
  fadeS.input.step = 100;
  fadeS.input.title = '0 = instant switching, bridge default is 400 ms';
  const color = h('input', { type: 'checkbox', checked: obj.use_color, onchange: () => { obj.use_color = color.checked; refresh(); } });
  const wrap = h('div', {},
    h('div', { class: 'sub' }, h('span', {}, 'Light'),
      h('label', { class: 'check' }, color, 'set color (off for white-only bulbs)')),
    h('div', { class: 'sliders' }, briS.nodes, hueS.nodes, satS.nodes, fadeS.nodes));
  queueMicrotask(refresh);
  return wrap;
}

function testButtons(kind, obj) {
  const run = (state) => (ev) => guarded(async () => {
    const target = { ...obj };
    delete target.id;
    const r = await api('POST', '/api/bridge/apply', { kind, target, state });
    const failed = r.failed && r.failed.length ? ` (failed: ${r.failed.join(', ')})` : '';
    toast(`${r.state_new ? 'On' : 'Off'}${failed}`, Boolean(failed));
  }, ev.currentTarget);
  return h('div', { class: 'left' },
    h('button', { class: 'btn small', onclick: run('on'), title: 'Test with current (unsaved) settings' }, 'On'),
    h('button', { class: 'btn small', onclick: run('off') }, 'Off'),
    h('button', { class: 'btn small', onclick: run('toggle') }, 'Toggle'));
}

function cardHead(obj, list, kind, swatch) {
  return h('div', { class: 'card-head' },
    swatch,
    h('label', {}, 'Name', h('input', { type: 'text', value: obj.name, maxlength: 64, oninput: (e) => { obj.name = e.target.value; markDirty(); } })),
    h('label', {}, 'ID', h('input', {
      type: 'number', min: 1, max: 9999, value: obj.id,
      onchange: (e) => { obj.id = Number(e.target.value); renderSwitches(); markDirty(); },
    })),
    h('button', {
      class: 'btn ghost small danger del', title: `Delete ${kind}`,
      onclick: () => { if (confirm(`Delete ${kind} "${obj.name || obj.id}"?`)) { list.splice(list.indexOf(obj), 1); renderSwitches(); markDirty(); } },
    }, 'Delete'));
}

function urlRow(kind, id) {
  const url = endpoint(kind, id);
  return h('div', {},
    h('div', { class: 'sub' }, h('span', {}, 'Switch URL'), h('span', { class: 'small' }, 'append &state=on|off for fixed actions')),
    h('div', { class: 'url' }, h('code', { title: url }, url),
      h('button', { class: 'btn small', onclick: () => navigator.clipboard.writeText(url).then(() => toast('Copied'), () => toast('Copy failed', true)) }, 'Copy')));
}

function lampPicker(room) {
  const box = h('div', {});
  const lightName = (id) => (S.lights || []).find((l) => l.id === id)?.name;
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= room.lamps.length) return;
    [room.lamps[i], room.lamps[j]] = [room.lamps[j], room.lamps[i]];
    draw(); markDirty();
  };
  const draw = () => {
    box.replaceChildren();
    box.append(h('div', { class: 'sub' }, h('span', {}, 'Lamps'),
      h('span', { class: 'small' }, S.lights ? 'click to add/remove — added lamps go to the end of the sequence' : '')));
    if (!S.lights) {
      box.append(h('input', {
        type: 'text', value: room.lamps.join(', '), placeholder: 'lamp ids in switching order, e.g. 1, 2, 5',
        onchange: (e) => {
          room.lamps = [...new Set(e.target.value.split(/[\s,]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0))];
          draw(); markDirty();
        },
      }), h('p', { class: 'muted small' }, 'Bridge not reachable — enter lamp IDs manually, in switching order.'));
    } else {
      const known = new Set(S.lights.map((l) => l.id));
      const chips = S.lights.map((l) => {
        const pos = room.lamps.indexOf(l.id);
        return h('button', {
          class: 'chip', 'aria-pressed': String(pos >= 0), title: `${l.type}${l.reachable ? '' : ' (unreachable)'}`,
          onclick: () => {
            room.lamps = pos >= 0 ? room.lamps.filter((x) => x !== l.id) : [...room.lamps, l.id];
            draw(); markDirty();
          },
        }, pos >= 0 ? h('span', { class: 'pos' }, pos + 1) : null, l.name, h('span', { class: 'id' }, `#${l.id}`));
      });
      const missing = room.lamps.filter((id) => !known.has(id)).map((id) => h('button', {
        class: 'chip missing', 'aria-pressed': 'true', title: 'Not found on bridge — click to remove',
        onclick: () => { room.lamps = room.lamps.filter((x) => x !== id); draw(); markDirty(); },
      }, 'missing', h('span', { class: 'id' }, `#${id}`)));
      box.append(h('div', { class: 'chips' }, chips, missing));
    }
    if (!room.lamps.length) return;
    const rows = room.lamps.map((id, i) => h('li', {},
      h('span', { class: 'pos' }, i + 1),
      h('span', { class: 'seq-name' }, lightName(id) || 'unknown', h('span', { class: 'id' }, ` #${id}`)),
      h('button', { class: 'btn ghost small', title: 'Earlier', disabled: i === 0, onclick: () => move(i, -1) }, '▲'),
      h('button', { class: 'btn ghost small', title: 'Later', disabled: i === room.lamps.length - 1, onclick: () => move(i, 1) }, '▼')));
    box.append(h('details', { class: 'seq', open: box.dataset.open === '1', ontoggle: (e) => { box.dataset.open = e.target.open ? '1' : ''; } },
      h('summary', {}, `Switching sequence (${room.lamps.length} lamps)`),
      h('ol', {}, rows)));
  };
  draw();
  return box;
}

function sequenceControls(room) {
  const info = h('span', { class: 'muted small' });
  const upd = () => {
    const total = (Math.max(room.lamps.length - 1, 0) * room.step_delay_ms) / 1000;
    info.textContent = room.step_delay_ms ? `full sweep ≈ ${total.toFixed(1)} s` : 'all lamps at once';
    markDirty();
  };
  const delay = slider('Delay (ms)', room, 'step_delay_ms', 0, 1000, upd);
  delay.input.step = 10;
  const rev = h('input', { type: 'checkbox', checked: room.reverse_off, onchange: () => { room.reverse_off = rev.checked; markDirty(); } });
  queueMicrotask(upd);
  return h('div', {},
    h('div', { class: 'sub' }, h('span', {}, 'Effect'), h('label', { class: 'check' }, rev, 'turn off in reverse order')),
    h('div', { class: 'sliders' }, delay.nodes), info);
}

function groupPicker(group) {
  const label = h('div', { class: 'sub' }, h('span', {}, 'Bridge group'));
  if (!S.bridgeGroups) {
    return h('div', {}, label, h('input', {
      type: 'number', min: 0, max: 9999, value: group.group,
      oninput: (e) => { group.group = Number(e.target.value); markDirty(); },
    }));
  }
  const opts = S.bridgeGroups.map((g) => h('option', { value: String(g.id), selected: g.id === group.group },
    `${g.name} (#${g.id}, ${g.type}, ${g.lights.length} lights)`));
  if (!S.bridgeGroups.some((g) => g.id === group.group)) {
    opts.unshift(h('option', { value: String(group.group), selected: true }, group.group === 0 ? 'All lights (#0)' : `missing (#${group.group})`));
  }
  if (!S.bridgeGroups.some((g) => g.id === 0) && group.group !== 0) opts.unshift(h('option', { value: '0' }, 'All lights (#0)'));
  return h('div', {}, label, h('select', { onchange: (e) => { group.group = Number(e.target.value); markDirty(); } }, opts));
}

function renderSwitches() {
  const rooms = $('#rooms'), groups = $('#groups');
  rooms.replaceChildren(...S.cfg.rooms.map((room) => {
    const sw = h('div', { class: 'swatch' });
    return h('article', { class: 'card' },
      cardHead(room, S.cfg.rooms, 'room', sw), urlRow('room', room.id), lampPicker(room), sequenceControls(room), lightControls(room, sw),
      h('div', { class: 'actions' }, testButtons('room', room)));
  }));
  if (!S.cfg.rooms.length) rooms.append(h('div', { class: 'empty' }, 'No rooms yet.'));
  groups.replaceChildren(...S.cfg.groups.map((group) => {
    const sw = h('div', { class: 'swatch' });
    return h('article', { class: 'card' },
      cardHead(group, S.cfg.groups, 'group', sw), urlRow('group', group.id), groupPicker(group), lightControls(group, sw),
      h('div', { class: 'actions' }, testButtons('group', group)));
  }));
  if (!S.cfg.groups.length) groups.append(h('div', { class: 'empty' }, 'No groups yet.'));
}

$('#add-room').addEventListener('click', () => {
  S.cfg.rooms.push({ id: nextId(S.cfg.rooms), name: `Room ${nextId(S.cfg.rooms)}`, lamps: [], step_delay_ms: 0, reverse_off: false, bri: 254, use_color: true, hue: 8895, sat: 89, transition_ms: 400 });
  renderSwitches(); markDirty();
});
$('#add-group').addEventListener('click', () => {
  S.cfg.groups.push({ id: nextId(S.cfg.groups), name: `Group ${nextId(S.cfg.groups)}`, group: 0, bri: 254, use_color: false, hue: 8895, sat: 89, transition_ms: 400 });
  renderSwitches(); markDirty();
});
$('#switch-token').addEventListener('input', renderSwitches);

// ---------- bridge ----------
async function loadBridge(quiet = true) {
  try {
    [S.lights, S.bridgeGroups] = await Promise.all([api('GET', '/api/bridge/lights'), api('GET', '/api/bridge/groups')]);
    S.lights.sort((a, b) => a.name.localeCompare(b.name));
  } catch (e) {
    S.lights = S.bridgeGroups = null;
    if (!quiet) toast(e.message, true);
  }
  renderLightsTable();
  if (S.cfg) renderSwitches();
}

function renderLightsTable() {
  const body = $('#lights-table tbody');
  if (!S.lights) { body.replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'muted' }, 'Bridge not reachable.'))); return; }
  body.replaceChildren(...[...S.lights].sort((a, b) => a.id - b.id).map((l) => h('tr', {},
    h('td', {}, l.id), h('td', {}, l.name), h('td', { class: 'muted' }, l.type),
    h('td', {}, h('span', { class: 'dot' + (l.on && l.reachable ? ' on' : '') }), l.reachable ? (l.on ? 'on' : 'off') : 'unreachable'))));
}

$('#bridge-test').addEventListener('click', (ev) => guarded(async () => {
  if (!$('#savebar').hidden) toast('Note: testing the saved settings, not unsaved changes');
  const i = await api('GET', '/api/bridge/info');
  $('#bridge-result').textContent = `✓ ${i.name} · ${i.modelid} · API ${i.apiversion} · SW ${i.swversion}`;
  await loadBridge(false);
}, ev.currentTarget));

$('#bridge-pair').addEventListener('click', (ev) => guarded(async () => {
  const ip = $('#bridge-ip').value.trim();
  if (!ip) throw new ApiError('Enter the bridge IP first');
  if (!confirm(`Press the link button on the bridge at ${ip} now, then click OK.`)) return;
  const cfg = await api('POST', '/api/bridge/pair', { bridge_ip: ip });
  const pending = collect();
  loadConfig(cfg);
  // keep other unsaved edits in the form
  S.cfg.rooms = pending.rooms; S.cfg.groups = pending.groups;
  toast('Paired — new API key stored');
  await loadBridge(false);
}, ev.currentTarget));

$('#lights-refresh').addEventListener('click', (ev) => guarded(() => loadBridge(false), ev.currentTarget));

// ---------- security ----------
$('#token-gen').addEventListener('click', () => {
  const b = new Uint8Array(24);
  crypto.getRandomValues(b);
  $('#switch-token').value = btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  renderSwitches(); markDirty();
});
$('#token-clear').addEventListener('click', () => { $('#switch-token').value = ''; renderSwitches(); markDirty(); });

$('#password-form').addEventListener('submit', (ev) => {
  ev.preventDefault();
  guarded(async () => {
    const r = await api('POST', '/api/password', { current: $('#pw-current').value, new: $('#pw-new').value });
    S.csrf = r.csrf;
    ev.target.reset();
    $('#pw-result').textContent = '✓ Password changed, other sessions logged out.';
  }, ev.submitter);
});

// ---------- logs ----------
async function loadLogs() {
  const r = await api('GET', '/api/logs?lines=300');
  const pre = $('#logs');
  const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
  pre.replaceChildren(...r.lines.map((l) => h('div', { class: /WARNING|ERROR/.test(l) ? 'warn' : '' }, l)));
  if (atBottom) pre.scrollTop = pre.scrollHeight;
}
$('#logs-refresh').addEventListener('click', (ev) => guarded(loadLogs, ev.currentTarget));
$('#logs-auto').addEventListener('change', (e) => {
  clearInterval(S.logTimer);
  if (e.target.checked) S.logTimer = setInterval(() => guarded(loadLogs), 3000);
});

// ---------- tabs ----------
function selectTab(name) {
  for (const b of document.querySelectorAll('[role=tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === name));
  for (const p of document.querySelectorAll('[data-panel]')) p.hidden = p.dataset.panel !== name;
  if (name === 'logs') guarded(loadLogs);
  try { sessionStorage.setItem('tab', name); } catch { /* ignore */ }
}
for (const b of document.querySelectorAll('[role=tab]')) b.addEventListener('click', () => selectTab(b.dataset.tab));

window.addEventListener('beforeunload', (e) => { if (!$('#savebar').hidden) e.preventDefault(); });

function inNet(ip, cidr) {
  const toInt = (x) => x.split('.').reduce((a, o) => a * 256 + Number(o), 0);
  const [net, bits] = cidr.split('/');
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(ip)) return false;
  const size = 2 ** (32 - Number(bits));
  return Math.floor(toInt(ip) / size) === Math.floor(toInt(net) / size);
}

function proxyHint(s) {
  const p = s.proxy;
  if (!p) return '';
  if (!p.peer_trusted) {
    return p.x_forwarded_for || p.x_real_ip
      ? `A proxy header is present, but ${p.peer_ip} is not trusted. Add ${p.peer_ip} to "Trusted proxies" and click Save.`
      : 'No proxy detected. You are connected directly.';
  }
  if (!p.x_forwarded_for && !p.x_real_ip) return 'The trusted proxy sends no X-Forwarded-For / X-Real-IP header. Check the proxy configuration.';
  if (inNet(s.client_ip, '172.16.0.0/12')) {
    return `The proxy itself only sees a Docker address (${s.client_ip}), so the real IP is already lost before the proxy. ` +
      'Usually the client connected via IPv6 (or a hairpin connection) and Docker\'s docker-proxy replaced the source IP. ' +
      'Fix it on the Nginx Proxy Manager side (see README → "Behind a reverse proxy").';
  }
  return '✓ Real client IP detected.';
}

function showIps(s) {
  $('#client-ip').textContent = s.client_ip || '?';
  const p = s.proxy;
  if (!p) return;
  const row = (k, v, cls) => h('tr', {}, h('th', {}, k), h('td', {}, h('code', { class: cls }, v || '—')));
  $('#proxy-diag').replaceChildren(
    row('Connection from', `${p.peer_ip} ${p.peer_trusted ? '(trusted proxy)' : '(not trusted)'}`),
    row('X-Forwarded-For', p.x_forwarded_for),
    row('X-Real-IP', p.x_real_ip),
    row('X-Forwarded-Proto', p.x_forwarded_proto),
    row('→ Detected client IP', s.client_ip));
  const hint = proxyHint(s);
  $('#proxy-hint').textContent = hint;
  $('#proxy-hint').className = 'hint' + (hint.startsWith('✓') ? ' ok' : hint.startsWith('No proxy') ? '' : ' warn');
}

// ---------- boot ----------
async function start() {
  const cfg = await api('GET', '/api/config');
  $('#login').hidden = true;
  $('#app').hidden = false;
  loadConfig(cfg);
  let tab = 'switches';
  try { tab = sessionStorage.getItem('tab') || tab; } catch { /* ignore */ }
  selectTab(tab);
  loadBridge();
  api('GET', '/api/session').then(showIps, () => {});
}

(async () => {
  try {
    const s = await api('GET', '/api/session');
    $('#version').textContent = 'v' + s.version;
    showIps(s);
    if (!s.authenticated) return showLogin();
    S.csrf = s.csrf;
    await start();
  } catch (e) {
    document.body.replaceChildren(h('p', { class: 'error' }, e.message));
  }
})();
