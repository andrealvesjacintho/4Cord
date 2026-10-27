'use strict';

window.addEventListener('error', (e) => {
  window.__tpError = {
    message: e && e.message,
    source: e && e.filename,
    line: e && e.lineno,
    column: e && e.colno,
    stack: e && e.error && e.error.stack,
  };
});

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};

/* ---------------- ponte com o Python ---------------- */
let seq = 0;
const pending = new Map();

function call(cmd, args = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    try {
      window.webkit.messageHandlers.tp.postMessage(JSON.stringify({ id, cmd, args }));
    } catch (e) {
      pending.delete(id);
      reject(e);
      return;
    }
    setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error('sem resposta do backend'));
      }
    }, 25000);
  });
}

window.tpReply = (p) => {
  const q = pending.get(p.id);
  if (!q) return;
  pending.delete(p.id);
  if (p.ok) q.resolve(p.data);
  else q.reject(new Error(p.error || 'erro desconhecido'));
};

/* ---------------- estado ---------------- */
const HISTORY_LIMIT = 300;
const SEEN_LIMIT = 1000;
const PAGE_SIZE = 50;
const SYNC_LIMIT = 100;

/* IDs do Discord sao snowflakes numericos; compara sem perder precisao. */
function idCmp(a, b) {
  if (a == null || b == null) return 0;
  try {
    const x = BigInt(a), y = BigInt(b);
    return x < y ? -1 : (x > y ? 1 : 0);
  } catch (e) {
    const sa = String(a), sb = String(b);
    if (/^\d+$/.test(sa) && /^\d+$/.test(sb)) {
      if (sa.length !== sb.length) return sa.length < sb.length ? -1 : 1;
      return sa < sb ? -1 : (sa > sb ? 1 : 0);
    }
    return sa < sb ? -1 : (sa > sb ? 1 : 0);
  }
}

const S = {
  user: null,
  guilds: [],
  dms: [],
  channels: [],
  roles: [],
  kind: 'guild',
  guild: null,
  channel: null,
  messages: [],
  nodes: new Map(),
  liveStick: false,
  oldest: null,
  newest: null,
  hasOlder: false,
  hasNewer: false,
  seen: new Set(),
  activeIds: new Set(),
  pendingSeen: new Set(),
  pendingLive: [],
  /* Ultimo ID conhecido por canal, inclusive fora da conversa aberta.
     Usado para recuperar mensagens perdidas durante uma desconexao. */
  lastByChannel: new Map(),
  navSeq: 0,
  readyOnce: false,
  recovering: false,
  loadingOlder: false,
  loadingChannel: false,
  syncing: false,
  sending: false,
  attaching: false,
  ramBusy: false,
  unread: {},
  mock: false,
  gateway: false,
  avatars: false,
  hiddenDMs: new Set(),
  appName: '4Cord',
  accent: '#5b6cff',
  verbose: false,
};

const NOTES_GUILD = /^notes$/i;

const store = {
  get(k, d) { try { const v = localStorage.getItem('tp:' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('tp:' + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
};

const DEFAULT_ACCENT = '#5b6cff';

function normalizeAccent(value) {
  const v = String(value || '').trim();
  return /^#[0-9a-fA-F]{6}$/.test(v) ? v.toLowerCase() : DEFAULT_ACCENT;
}

function hexToRgb(hex) {
  const h = normalizeAccent(hex).slice(1);
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function mixHex(hex, other, amount) {
  const a = hexToRgb(hex);
  const b = hexToRgb(other);
  const mix = (x, y) => Math.round(x + (y - x) * amount);
  return '#' + [mix(a.r, b.r), mix(a.g, b.g), mix(a.b, b.b)]
    .map((n) => n.toString(16).padStart(2, '0')).join('');
}

function applyAccent(value, persist = true, cache = true) {
  const hex = normalizeAccent(value);
  const { r, g, b } = hexToRgb(hex);
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const fg = lum > 0.58 ? '#101116' : '#ffffff';
  // Em fundos escuros, tons muito escuros ficam ilegiveis como texto.
  const text = lum < 0.28 ? mixHex(hex, '#ffffff', 0.52) : hex;
  const root = document.documentElement;
  root.style.setProperty('--accent', hex);
  root.style.setProperty('--accent-fg', fg);
  root.style.setProperty('--accent-soft', `rgba(${r},${g},${b},.18)`);
  root.style.setProperty('--accent-text', text);
  S.accent = hex;
  const pick = $('#accentPick');
  if (pick && document.activeElement !== pick) pick.value = hex;
  if (cache) store.set('accent', hex);
  if (persist) call('set_accent', { color: hex }).catch(() => {});
}

/* ---------------- utilidades ---------------- */
const LEAN = new URLSearchParams(location.search).get('lean') === '1';

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

function mdLite(raw) {
  let h = esc(raw);
  h = h.replace(/```([\s\S]*?)```/g, (_, c) => `<code>${c}</code>`);
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
  h = h.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<i>$2</i>');
  // Emotes externos não são baixados: viram apenas "?" (economiza rede/RAM).
  h = h.replace(/&lt;(a?):([^:&]+):(\d+)&gt;/g,
    (_, anim, name) => `<span class="emojiText customEmoji" title=":${name}:">?</span>`);
  h = h.replace(/(https?:\/\/[^\s<]+)/g, (url) => {
    const label = /gif/i.test(url) ? 'GIF' : 'LINK';
    return `<a class="linkTag" href="${url}" target="_blank" rel="noreferrer" title="${url}">${label}</a>`;
  });
  return h;
}

function mediaFormat(url, mime) {
  const ct = String(mime || '').toLowerCase().split(';')[0].trim();
  const byMime = {
    'image/png': 'PNG', 'image/jpeg': 'JPG', 'image/jpg': 'JPG',
    'image/gif': 'GIF', 'image/webp': 'WEBP', 'image/avif': 'AVIF',
    'image/svg+xml': 'SVG', 'image/bmp': 'BMP', 'image/x-icon': 'ICO',
  };
  if (byMime[ct]) return byMime[ct];
  const m = String(url || '').match(/\.([a-z0-9]+)(?:[?#]|$)/i);
  const ext = m ? m[1].toUpperCase() : '';
  if (ext === 'JPEG') return 'JPG';
  return ext || 'IMG';
}

/* A3: o CDN do Discord aceita width/height em anexos. A imagem inline usa
   uma miniatura; o visualizador sempre abre a URL original. */
function thumbUrl(url, width, height) {
  try {
    const u = new URL(url, location.href);
    const host = u.hostname.toLowerCase();
    if (!/(^|\.)discordapp\.(com|net)$/.test(host)) return null;
    if (!/\/(attachments|ephemeral-attachments)\//.test(u.pathname)) return null;
    const tw = Math.max(64, Math.min(680, Math.round((Number(width) || 220) * 2)));
    const th = Math.max(48, Math.min(480, Math.round((Number(height) || 130) * 2)));
    u.searchParams.set('width', String(tw));
    u.searchParams.set('height', String(th));
    return u.toString();
  } catch (e) {
    return null;
  }
}

/* A4: um unico IntersectionObserver para todas as midias reveladas. */
let mediaObserver = null;
function getMediaObserver() {
  if (mediaObserver) return mediaObserver;
  if (!('IntersectionObserver' in window)) return null;
  const root = $('#msgs');
  if (!root) return null;
  mediaObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const wrap = entry.target;
      if (entry.isIntersecting) return;
      if (wrap._revealed && !mediaInUse(wrap)) wrap._censor();
    });
  }, { root, rootMargin: '0px', threshold: 0 });
  return mediaObserver;
}

function mediaInUse(wrap) {
  if (typeof lb !== 'undefined' && lb && lb.classList.contains('open')) {
    // Quando a midia foi aberta pelo proprio no, apenas ele fica retido.
    // Comparar so a URL manteria duas copias identicas decodificadas.
    if (lbHasWrap) { if (lbWrap === wrap) return true; }
    else if (lbUrl === wrap._url) return true;
  }
  if (wrap.contains(document.activeElement)) return true;
  return false;
}

function censorOffscreenMedia() {
  const root = $('#msgs');
  if (!root) return;
  const rr = root.getBoundingClientRect();
  document.querySelectorAll('#msgList .mediaBox.revealed').forEach((wrap) => {
    const r = wrap.getBoundingClientRect();
    if (r.bottom < rr.top || r.top > rr.bottom) {
      if (wrap._censor && !mediaInUse(wrap)) wrap._censor();
    }
  });
}

function disposeMediaTree(root) {
  if (!root) return;
  const self = root.matches && root.matches('.mediaBox');
  if (!self && (!root.querySelector || !root.querySelector('.mediaBox'))) return;
  const boxes = self ? [root] : [...root.querySelectorAll('.mediaBox')];
  boxes.forEach((wrap) => {
    if (wrap._dispose) wrap._dispose();
  });
}

/* Capa de censura: nenhuma imagem e baixada antes do clique. */
function mediaNode(url, opts = {}) {
  const fmt = mediaFormat(url, opts.mime);
  const wrap = el('div', 'mediaBox');
  const w = Number(opts.width) || 0;
  const h = Number(opts.height) || 0;
  let baseW = 220;
  let baseH = 130;
  if (w > 0 && h > 0) {
    const scale = Math.min(340 / w, 240 / h, 1);
    baseW = Math.max(72, Math.round(w * scale));
    baseH = Math.max(48, Math.round(h * scale));
  }
  wrap._baseW = baseW;
  wrap._baseH = baseH;
  wrap._url = url;
  wrap.style.width = baseW + 'px';
  wrap.style.height = baseH + 'px';

  const im = el('img', 'mediaImg hidden');
  im.alt = fmt;
  im.draggable = false;
  im.loading = 'lazy';
  im.dataset.original = url;

  const cover = el('button', 'mediaCover');
  cover.type = 'button';
  cover.title = 'Clique para revelar';
  cover.setAttribute('aria-label', 'Revelar mídia ' + fmt);
  cover.appendChild(el('span', 'mediaFmt', fmt));

  const thumb = thumbUrl(url, baseW, baseH);
  let triedOriginal = false;

  const showFallback = () => {
    wrap._revealed = false;
    wrap._failed = true;
    const obs = getMediaObserver();
    if (obs) obs.unobserve(wrap);
    im.onerror = null;
    im.removeAttribute('src');
    im.classList.add('hidden');
    cover.classList.add('hidden');
    wrap.classList.remove('revealed');
    wrap.style.width = '';
    wrap.style.height = '';
    let fallback = wrap.querySelector('.file');
    if (!fallback) {
      fallback = el('a', 'file', '📎 ' + (opts.filename || 'mídia'));
      fallback.href = url;
      fallback.target = '_blank';
      fallback.rel = 'noreferrer';
      wrap.appendChild(fallback);
    }
  };

  const reveal = () => {
    if (wrap._failed) return;
    triedOriginal = false;
    wrap._revealed = true;
    wrap.classList.add('revealed');
    im.classList.remove('hidden');
    cover.classList.add('hidden');
    cover.blur();
    wrap.style.width = '';
    wrap.style.height = '';
    im.onerror = () => {
      if (!wrap._revealed) return;
      if (thumb && !triedOriginal) {
        triedOriginal = true;
        im.src = url;
        return;
      }
      showFallback();
    };
    im.src = thumb || url;
    const obs = getMediaObserver();
    if (obs) obs.observe(wrap);
  };

  const censor = () => {
    if (!wrap._revealed || wrap._failed) return;
    wrap._revealed = false;
    const obs = getMediaObserver();
    if (obs) obs.unobserve(wrap);
    im.onerror = null;
    im.removeAttribute('src');
    im.removeAttribute('srcset');
    im.classList.add('hidden');
    cover.classList.remove('hidden');
    wrap.classList.remove('revealed');
    wrap.style.width = wrap._baseW + 'px';
    wrap.style.height = wrap._baseH + 'px';
  };

  const dispose = () => {
    wrap._revealed = false;
    if (lbWrap === wrap) lbWrap = null;
    const obs = getMediaObserver();
    if (obs) obs.unobserve(wrap);
    im.onerror = null;
    im.onclick = null;
    cover.onclick = null;
    im.removeAttribute('src');
    im.removeAttribute('srcset');
  };

  wrap._reveal = reveal;
  wrap._censor = censor;
  wrap._dispose = dispose;
  cover.onclick = reveal;
  im.onclick = () => { if (wrap._revealed) openLightbox(url, wrap); };

  wrap.appendChild(im);
  wrap.appendChild(cover);
  return wrap;
}

const emojiLabel = (emoji) => (emoji && (emoji.name || emoji.id)) || '?';

function emojiNode(emoji, cls = 'emoji') {
  // Emote customizado: não carrega imagem, mostra só um "?".
  if (emoji && emoji.id) {
    const sp = el('span', 'emojiText customEmoji', '?');
    sp.title = emojiLabel(emoji);
    return sp;
  }
  return el('span', 'emojiText', emojiLabel(emoji));
}

const hhmm = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const cdnAvatar = (u, size = 64) =>
  u && u.avatar ? `https://cdn.discordapp.com/avatars/${u.id}/${u.avatar}.png?size=${size}` : null;

let toastTimer = 0;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 3200);
}

/* ---------------- servidor exibido ---------------- */
function isNotesGuild(g) {
  return !!(g && typeof g.name === 'string' && NOTES_GUILD.test(g.name.trim()));
}

function initialGuild() {
  const saved = store.get('serverId', null);
  return S.guilds.find((g) => g.id === saved)
    || S.guilds.find(isNotesGuild)
    || S.guilds[0]
    || null;
}

function activeGuild() {
  return S.guild || initialGuild();
}

function renderServerSelect() {
  const sel = $('#serverSel');
  if (!sel) return;
  sel.innerHTML = '';
  S.guilds.forEach((g) => {
    const opt = el('option', '', g.name);
    opt.value = g.id;
    sel.appendChild(opt);
  });
  if (S.guild) sel.value = S.guild.id;
  sel.disabled = !S.guilds.length;
}

function showNoServer() {
  S.channel = null;
  resetHistory(true);
  $('#sideTitle').textContent = 'Servidores';
  $('#sideBody').innerHTML = '';
  $('#sideBody').appendChild(el('div', 'empty',
    'Nenhum servidor disponível nesta conta.'));
  $('#chTitle').textContent = 'Sem servidor';
  $('#chHash').textContent = '#';
}

function setConn(connected) {
  S.gateway = !!connected;
  const dot = $('#conn');
  if (!dot) return;
  dot.classList.remove('on', 'off', 'wait');
  dot.classList.add(connected ? 'on' : 'off');
  dot.title = connected ? 'conectado em tempo real' : 'sem conexão em tempo real';
}

function setConnWait() {
  const dot = $('#conn');
  if (!dot) return;
  dot.classList.remove('on', 'off');
  dot.classList.add('wait');
  dot.title = 'conectando em tempo real...';
}

/* ---------------- indicadores de carregamento ---------------- */
function setMsgLoading(on) {
  const row = $('#msgLoading');
  if (row) row.classList.toggle('hidden', !on);
}

function setSyncBusy(on) {
  S.syncing = !!on;
  const spin = $('#syncSpin');
  if (spin) spin.classList.toggle('hidden', !on);
}

function setLoadOlderBusy(on) {
  S.loadingOlder = !!on;
  const btn = $('#loadOlder');
  const spin = $('#loadOlderSpin');
  if (btn) btn.disabled = !!on;
  if (spin) spin.classList.toggle('hidden', !on);
}

function updateHistoryControls() {
  const hasChannel = !!S.channel;
  const older = hasChannel && S.hasOlder;
  const newer = hasChannel && S.hasNewer;
  const wrap = $('#loadOlderWrap');
  const oldBtn = $('#loadOlder');
  const newBtn = $('#loadNewer');
  if (wrap) wrap.classList.toggle('hidden', !(older || newer));
  if (oldBtn) oldBtn.classList.toggle('hidden', !older);
  if (newBtn) newBtn.classList.toggle('hidden', !newer);
}

/* ---------------- sidebar ---------------- */
function renderMe() {
  const u = S.user || {};
  const av = $('#meAvatar');
  const url = S.avatars ? cdnAvatar(u) : null;
  if (url) { av.src = url; av.classList.remove('hidden'); }
  else { av.removeAttribute('src'); av.classList.add('hidden'); }
  $('#meName').textContent = u.global_name || u.username || '—';
  $('#meTag').textContent = u.username ? '@' + u.username : '—';
}

function renderChannels() {
  const body = $('#sideBody');
  body.innerHTML = '';
  const cats = S.channels.filter((c) => c.type === 4).sort((a, b) => a.position - b.position);
  const texts = S.channels.filter((c) => c.type === 0 || c.type === 5)
    .sort((a, b) => a.position - b.position);

  const addChan = (c) => {
    const b = el('button', 'chan');
    b.innerHTML = `<span class="hash">#</span><span>${esc(c.name)}</span>`;
    const badge = S.unread[c.id];
    if (badge) b.appendChild(el('span', 'badge', String(badge)));
    if (S.channel && S.channel.id === c.id) b.classList.add('active');
    b.dataset.id = c.id;
    b.onclick = () => openChannel(c, b);
    body.appendChild(b);
  };

  if (cats.length) {
    cats.forEach((cat) => {
      body.appendChild(el('div', 'cat', cat.name));
      texts.filter((t) => t.parent_id === cat.id).forEach(addChan);
    });
    const loose = texts.filter((t) => !t.parent_id || !cats.some((c) => c.id === t.parent_id));
    if (loose.length) { body.appendChild(el('div', 'cat', 'sem categoria')); loose.forEach(addChan); }
  } else {
    texts.forEach(addChan);
  }
  if (!texts.length) body.appendChild(el('div', 'cat', 'sem canais de texto'));
}

function dmDisplayName(ch) {
  const u = (ch.recipients && ch.recipients[0]) || {};
  return u.global_name || u.username || 'DM';
}

function sortedDMs() {
  const top = store.get('dmTop', []) || [];
  const pos = new Map(top.map((id, i) => [id, i]));
  const rank = (id) => (pos.has(id) ? pos.get(id) : 1e9);
  return S.dms
    .filter((ch) => !S.hiddenDMs.has(ch.id))
    .slice()
    .sort((a, b) => rank(a.id) - rank(b.id));
}

function pinDM(id) {
  const top = (store.get('dmTop', []) || []).filter((x) => x !== id);
  top.unshift(id);
  store.set('dmTop', top.slice(0, 50));
}

function renderDMs() {
  const body = $('#sideBody');
  body.innerHTML = '';
  const dms = sortedDMs();
  if (!dms.length) {
    body.appendChild(el('div', 'cat', 'nenhuma DM'));
    return;
  }
  dms.forEach((ch) => {
    const u = (ch.recipients && ch.recipients[0]) || { username: 'DM' };
    const b = el('button', 'chan dm');
    b.appendChild(el('span', 'hash', '@'));
    b.appendChild(el('span', 'chanName', dmDisplayName(ch)));
    const badge = S.unread[ch.id];
    if (badge) b.appendChild(el('span', 'badge', String(badge)));
    const rm = el('button', 'dmRemove', '×');
    rm.title = 'Remover DM da lista';
    rm.setAttribute('aria-label', 'Remover DM ' + dmDisplayName(ch));
    rm.onclick = (e) => { e.stopPropagation(); removeDM(ch); };
    b.appendChild(rm);
    if (S.channel && S.channel.id === ch.id) b.classList.add('active');
    b.dataset.id = ch.id;
    b.onclick = () => openChannel({ id: ch.id, name: dmDisplayName(ch), dm: true }, b);
    body.appendChild(b);
  });
}

function removeDM(ch) {
  S.hiddenDMs.add(ch.id);
  store.set('hiddenDMs', [...S.hiddenDMs]);
  store.set('dmTop', (store.get('dmTop', []) || []).filter((id) => id !== ch.id));
  S.dms = S.dms.filter((c) => c.id !== ch.id);
  if (S.channel && S.channel.id === ch.id) {
    S.channel = null;
    resetHistory(true);
    $('#chTitle').textContent = '—';
    $('#chHash').textContent = '@';
    $('#input').placeholder = 'Mensagem em @—';
  }
  renderDMs();
  toast('DM removida da lista.');
}

async function addDM(friend) {
  const user = friend && (friend.user || friend);
  if (!user || !user.id) return;
  try {
    const ch = await call('open_dm', { user: user.id });
    if (!ch || !ch.id) return;
    if (!ch.recipients || !ch.recipients.length) ch.recipients = [user];
    S.hiddenDMs.delete(ch.id);
    store.set('hiddenDMs', [...S.hiddenDMs]);
    S.dms = [ch, ...S.dms.filter((c) => c.id !== ch.id)];
    pinDM(ch.id);
    $('#friends').classList.add('hidden');
    renderDMs();
    const node = document.querySelector(`#sideBody .chan[data-id="${ch.id}"]`);
    await openChannel({ id: ch.id, name: dmDisplayName(ch), dm: true }, node);
    toast('DM adicionada ao topo.');
  } catch (e) { toast('Falha ao abrir DM: ' + e.message); }
}

/* ---------------- amigos ---------------- */
let friendsCache = null;

function friendUser(rel) {
  return (rel && (rel.user || rel)) || {};
}

function renderFriendList() {
  const box = $('#friendList');
  if (!box) return;
  const q = ($('#friendSearch').value || '').trim().toLowerCase();
  const list = (friendsCache || []).filter((rel) => {
    const u = friendUser(rel);
    const name = (u.global_name || u.username || '').toLowerCase();
    return !q || name.includes(q) || (u.username || '').toLowerCase().includes(q);
  });
  box.innerHTML = '';
  if (!list.length) {
    box.appendChild(el('div', 'empty', friendsCache ? 'Nenhum amigo encontrado.' : 'Carregando amigos...'));
    return;
  }
  list.forEach((rel) => {
    const u = friendUser(rel);
    const b = el('button', 'friend');
    b.appendChild(el('span', 'hash', '@'));
    b.appendChild(el('span', 'chanName', u.global_name || u.username || 'Amigo'));
    if (u.bot) b.appendChild(el('span', 'authorTag bot', 'BOT'));
    b.title = u.username ? '@' + u.username : '';
    b.onclick = () => addDM(rel);
    box.appendChild(b);
  });
}

async function openFriends() {
  const pop = $('#friends');
  pop.classList.remove('hidden');
  $('#friendSearch').value = '';
  $('#friendList').innerHTML = '<div class="empty">Carregando amigos...</div>';
  try {
    const rels = await call('friends');
    friendsCache = (rels || []).filter((r) => (r.type === undefined || r.type === 1) && friendUser(r).id);
    renderFriendList();
    $('#friendSearch').focus();
  } catch (e) {
    friendsCache = [];
    $('#friendList').innerHTML = '';
    $('#friendList').appendChild(el('div', 'empty', 'Falha ao carregar amigos: ' + e.message));
  }
}

/* ---------------- navegacao ---------------- */
function markNav(kind) {
  const dm = $('#dmBtn');
  const add = $('#addDMBtn');
  const g = activeGuild();
  if (dm) {
    dm.classList.toggle('active', kind === 'dm');
    dm.title = kind === 'dm'
      ? `Voltar para ${g ? g.name : 'servidor'}`
      : 'Mensagens diretas';
    dm.setAttribute('aria-label', dm.title);
  }
  if (add) add.classList.toggle('hidden', kind !== 'dm');
  if (kind !== 'dm') $('#friends').classList.add('hidden');
}

/* ---------------- janela de historico (A1/A2) ---------------- */
function pruneSeen() {
  if (S.seen.size <= SEEN_LIMIT) return;
  for (const id of S.seen) {
    if (S.seen.size <= SEEN_LIMIT) break;
    if (!S.activeIds.has(id) && !S.pendingSeen.has(id)) S.seen.delete(id);
  }
}

function markSeen(id) {
  if (!id) return;
  S.seen.add(id);
  pruneSeen();
}

function noteChannelLast(channelId, messageId) {
  if (!channelId || !messageId) return;
  const prev = S.lastByChannel.get(channelId);
  if (!prev || idCmp(messageId, prev) > 0) {
    S.lastByChannel.set(channelId, messageId);
  }
}

function noteMessageIfPresent(m) {
  if (m && m.channel_id && m.id) noteChannelLast(m.channel_id, m.id);
}

function bumpUnread(channelId, amount = 1) {
  if (!channelId || amount <= 0) return;
  S.unread[channelId] = (S.unread[channelId] || 0) + amount;
}

function queueLive(m) {
  if (!m || !m.id) return;
  if (S.seen.has(m.id) || S.pendingLive.some((x) => x.id === m.id)) return;
  S.pendingLive.push(m);
}

function flushPendingLive() {
  if (!S.pendingLive.length) return;
  const queued = S.pendingLive.splice(0);
  queued.forEach((m) => {
    // Uma mensagem enfileirada que ja ficou para tras da janela atual
    // pertence ao historico; nao deve ser anexada no fim fora de ordem.
    if (S.newest && idCmp(m.id, S.newest) <= 0) { markSeen(m.id); return; }
    appendMessage(m, true);
  });
}

function messageNodeFor(id) {
  return S.nodes.get(id) || document.querySelector(`#msgList .msg[data-id="${id}"]`);
}

function setWindowMeta() {
  S.oldest = S.messages.length ? S.messages[0].id : null;
  S.newest = S.messages.length ? S.messages[S.messages.length - 1].id : null;
}

function resetHistory(clearSeen = true) {
  disposeMediaTree($('#msgList'));
  $('#msgList').innerHTML = '';
  S.messages = [];
  S.nodes.clear();
  S.activeIds.clear();
  S.pendingSeen.clear();
  S.pendingLive = [];
  if (clearSeen) S.seen.clear();
  S.oldest = null;
  S.newest = null;
  S.hasOlder = false;
  S.hasNewer = false;
  S.liveStick = false;
  S.loadingChannel = false;
  setLoadOlderBusy(false);
  setSyncBusy(false);
  setMsgLoading(false);
  updateHistoryControls();
}

function isGroupedWith(prev, m) {
  if (!prev || !m || !prev.author || !m.author) return false;
  if (prev.author.id !== m.author.id) return false;
  const a = new Date(prev.timestamp).getTime();
  const b = new Date(m.timestamp).getTime();
  return isFinite(a) && isFinite(b) && (b - a) < 7 * 60 * 1000;
}

function refreshGrouping() {
  let prev = null;
  S.messages.forEach((m, i) => {
    const node = messageNodeFor(m.id);
    if (node) node.classList.toggle('grp', i === 0 || !isGroupedWith(prev, m));
    prev = m;
  });
}

function replaceWindow(msgs, atLatest) {
  disposeMediaTree($('#msgList'));
  $('#msgList').innerHTML = '';
  S.messages = [];
  S.nodes.clear();
  S.activeIds.clear();
  const list = $('#msgList');
  const unique = [];
  const local = new Set();
  (msgs || []).forEach((m) => {
    if (!m || !m.id || local.has(m.id)) return;
    local.add(m.id);
    unique.push(m);
  });
  const windowMsgs = unique.slice(-HISTORY_LIMIT);
  windowMsgs.forEach((m, i) => {
    S.messages.push(m);
    S.activeIds.add(m.id);
    markSeen(m.id);
    noteMessageIfPresent(m);
    list.appendChild(messageNode(m, i === 0 ? false : isGroupedWith(windowMsgs[i - 1], m)));
  });
  S.hasNewer = !atLatest;
  S.liveStick = !!atLatest;
  setWindowMeta();
  refreshGrouping();
  updateHistoryControls();
}

function trimWindow(side, preserveScroll = false) {
  const box = $('#msgs');
  let changed = false;
  while (S.messages.length > HISTORY_LIMIT) {
    changed = true;
    if (side === 'top') {
      const m = S.messages.shift();
      const node = S.nodes.get(m.id);
      if (node) {
        const height = preserveScroll ? node.offsetHeight : 0;
        disposeMediaTree(node);
        node.remove();
        S.nodes.delete(m.id);
        if (preserveScroll && box) {
          box.scrollTop = Math.max(0, box.scrollTop - height);
        }
      }
      S.activeIds.delete(m.id);
      S.hasOlder = true;
    } else {
      const m = S.messages.pop();
      const node = S.nodes.get(m.id);
      if (node) {
        disposeMediaTree(node);
        node.remove();
        S.nodes.delete(m.id);
      }
      S.activeIds.delete(m.id);
      S.hasNewer = true;
    }
  }
  if (changed) {
    // Remover do topo so muda o agrupamento do novo primeiro item. Evita
    // varrer 300 nos a cada mensagem recebida.
    if (side === 'top' && S.messages.length) {
      const first = S.nodes.get(S.messages[0].id);
      if (first) first.classList.add('grp');
    }
    setWindowMeta();
    updateHistoryControls();
  }
}

async function selectGuild(g, _btn) {
  const seq = ++S.navSeq;
  S.kind = 'guild';
  S.guild = g;
  store.set('serverId', g.id);
  renderServerSelect();
  markNav('guild');
  $('#sideTitle').textContent = g.name;
  S.channels = [];
  S.roles = [];
  S.channel = null;
  resetHistory(true);
  $('#chTitle').textContent = '—';
  try {
    const [channels, roles] = await Promise.all([
      call('channels', { guild: g.id, kind: 'guild' }),
      call('roles', { guild: g.id }).catch(() => []),
    ]);
    if (seq !== S.navSeq) return;
    S.channels = channels || [];
    S.roles = roles || [];
    renderChannels();
    const texts = S.channels.filter((c) => c.type === 0 || c.type === 5)
      .sort((a, b) => a.position - b.position);
    for (const c of texts) {
      const node = document.querySelector(`#sideBody .chan[data-id="${c.id}"]`);
      if (await openChannel(c, node)) break;
    }
  } catch (e) { toast('Falha ao carregar canais: ' + e.message); }
}

async function selectDMs() {
  S.kind = 'dm';
  S.guild = activeGuild();
  S.roles = [];
  markNav('dm');
  $('#sideTitle').textContent = 'Mensagens diretas';
  S.channels = [];
  S.channel = null;
  resetHistory(true);
  $('#chTitle').textContent = '—';
  renderDMs();
  for (const first of sortedDMs()) {
    const node = document.querySelector(`#sideBody .chan[data-id="${first.id}"]`);
    if (await openChannel({ id: first.id, name: dmDisplayName(first), dm: true }, node)) break;
  }
}

async function openChannel(ch, node) {
  const seq = ++S.navSeq;
  S.channel = ch;
  document.querySelectorAll('#sideBody .chan').forEach((b) => b.classList.remove('active'));
  if (node) {
    node.classList.add('active');
    const badge = node.querySelector('.badge');
    if (badge) badge.remove();
  }
  S.unread[ch.id] = 0;
  $('#chHash').textContent = ch.dm ? '@' : '#';
  $('#chTitle').textContent = ch.name;
  $('#input').placeholder = `Mensagem em ${ch.dm ? '@' : '#'}${ch.name}`;
  resetHistory(true);
  setMsgLoading(true);
  S.loadingChannel = true;
  if (window.innerWidth <= 760) document.body.classList.remove('side-open');
  try {
    const raw = await call('messages', { channel: ch.id });
    if (seq !== S.navSeq || !S.channel || S.channel.id !== ch.id) return false;
    replaceWindow((raw || []).slice().reverse(), true);
    S.hasOlder = (raw || []).length >= PAGE_SIZE;
    updateHistoryControls();
    if (!S.messages.length) {
      $('#msgList').appendChild(el('div', 'empty', 'Nenhuma mensagem ainda.'));
    }
    scrollBottom();
    return true;
  } catch (e) {
    if (seq !== S.navSeq || !S.channel || S.channel.id !== ch.id) return false;
    window.__tpCatch = (window.__tpCatch || []).concat(String(e && (e.stack || e)));
    const denied = /\(403\)/.test(e.message);
    $('#msgList').appendChild(el('div', 'empty',
      denied ? 'Sem acesso a este canal.' : 'Falha ao carregar mensagens: ' + e.message));
    if (!denied) toast('Falha ao carregar mensagens: ' + e.message);
    return false;
  } finally {
    if (seq === S.navSeq) {
      S.loadingChannel = false;
      setMsgLoading(false);
      flushPendingLive();
    }
  }
}

async function loadOlder() {
  if (!S.channel || !S.oldest || !S.hasOlder || S.loadingOlder || S.syncing) return;
  const ch = S.channel;
  const seq = S.navSeq;
  const pending = [];
  setLoadOlderBusy(true);
  try {
    const raw = await call('messages', { channel: ch.id, before: S.oldest });
    if (seq !== S.navSeq || !S.channel || S.channel.id !== ch.id) return;
    const asc = (raw || []).slice().reverse();
    asc.forEach((m) => { if (m && m.id) { pending.push(m.id); S.pendingSeen.add(m.id); } });
    const seenLocal = new Set();
    const fresh = asc.filter((m) => {
      if (!m || !m.id || seenLocal.has(m.id) || S.activeIds.has(m.id)) return false;
      seenLocal.add(m.id);
      return true;
    });
    if (!asc.length) {
      S.hasOlder = false;
      updateHistoryControls();
      return;
    }
    const box = $('#msgs');
    const list = $('#msgList');
    const oldFirst = list.firstElementChild;
    const topBefore = oldFirst ? oldFirst.getBoundingClientRect().top : 0;
    const combined = fresh.concat(S.messages);
    const frag = document.createDocumentFragment();
    fresh.forEach((m, i) => {
      const prev = i > 0 ? combined[i - 1] : null;
      frag.appendChild(messageNode(m, i === 0 ? false : isGroupedWith(prev, m)));
    });
    list.insertBefore(frag, list.firstChild);
    S.messages = combined;
    fresh.forEach((m) => { S.activeIds.add(m.id); markSeen(m.id); });
    S.hasOlder = asc.length >= PAGE_SIZE;
    // A partir daqui o usuario esta lendo o passado: mensagens ao vivo nao
    // devem empurrar a janela; "voltar ao recente" recarrega a pagina atual.
    if (fresh.length) S.hasNewer = true;
    S.liveStick = false;
    if (oldFirst) {
      box.scrollTop += oldFirst.getBoundingClientRect().top - topBefore;
    }
    trimWindow('bottom');
    setWindowMeta();
    refreshGrouping();
    updateHistoryControls();
  } catch (e) {
    if (seq === S.navSeq) toast('Falha ao carregar anteriores: ' + e.message);
  } finally {
    pending.forEach((id) => S.pendingSeen.delete(id));
    if (seq === S.navSeq) {
      setLoadOlderBusy(false);
      updateHistoryControls();
      flushPendingLive();
    }
  }
}

async function goLatest() {
  if (!S.channel || S.syncing || S.loadingOlder) return;
  const ch = S.channel;
  const seq = S.navSeq;
  setSyncBusy(true);
  try {
    const raw = await call('messages', { channel: ch.id, limit: PAGE_SIZE });
    if (seq !== S.navSeq || !S.channel || S.channel.id !== ch.id) return;
    replaceWindow((raw || []).slice().reverse(), true);
    S.hasOlder = (raw || []).length >= PAGE_SIZE;
    updateHistoryControls();
    if (!S.messages.length) {
      $('#msgList').appendChild(el('div', 'empty', 'Nenhuma mensagem ainda.'));
    }
    scrollBottom();
  } catch (e) {
    if (seq === S.navSeq) toast('Falha ao voltar ao recente: ' + e.message);
  } finally {
    if (seq === S.navSeq) setSyncBusy(false);
  }
}

/* ---------------- mensagens ---------------- */
const roleColor = (role) => {
  const c = role && Number(role.color);
  return c ? '#' + c.toString(16).padStart(6, '0') : null;
};

function topRole(m) {
  const ids = (m.member && m.member.roles) || [];
  if (!ids.length || !S.roles.length) return null;
  const set = new Set(ids);
  return S.roles
    .filter((r) => set.has(r.id) && r.name && r.name !== '@everyone')
    .sort((a, b) => (b.position || 0) - (a.position || 0))[0] || null;
}

function authorNode(m) {
  const author = m.author || {};
  const member = m.member || {};
  const wrap = el('span', 'author');
  const role = topRole(m);
  const color = roleColor(role);
  const name = member.nick || author.global_name || author.username || '?';
  const who = el('span', 'who', name);
  who.title = author.username ? (author.global_name ? `${author.global_name} (@${author.username})` : '@' + author.username) : name;
  if (color) who.style.color = color;
  wrap.appendChild(who);

  const clan = author.primary_guild || author.clan;
  if (clan && clan.tag) {
    const tag = el('span', 'authorTag');
    tag.title = 'Tag do servidor';
    const shield = el('span', 'tagShield');
    shield.innerHTML = '<svg viewBox="0 0 12 12" width="9" height="9" fill="currentColor"><path d="M6 .8 10.6 2.4v3.3c0 2.7-1.8 4.6-4.6 5.5C3.2 10.3 1.4 8.4 1.4 5.7V2.4z"/></svg>';
    tag.appendChild(shield);
    tag.appendChild(el('span', '', clan.tag));
    wrap.appendChild(tag);
  }
  if (author.bot) wrap.appendChild(el('span', 'authorTag bot', 'BOT'));
  if (author.system) wrap.appendChild(el('span', 'authorTag system', 'SISTEMA'));
  if (role && (!clan || !clan.tag || clan.tag !== role.name)) {
    const badge = el('span', 'authorTag role', role.name);
    badge.title = 'Cargo: ' + role.name;
    if (color) {
      badge.style.color = color;
      badge.style.borderColor = color + '66';
      badge.style.background = color + '1f';
    }
    wrap.appendChild(badge);
  }
  return wrap;
}

function reactionsNode(m) {
  const host = el('div', 'reactions');
  (m.reactions || []).forEach((r) => {
    const b = el('button', 'reaction' + (r.me ? ' me' : ''));
    b.title = (r.me ? 'Remover reação ' : 'Reagir com ') + emojiLabel(r.emoji);
    b.appendChild(emojiNode(r.emoji));
    b.appendChild(el('span', 'count', String(r.count || 0)));
    b.onclick = () => toggleReaction(m, r, host);
    host.appendChild(b);
  });
  return host;
}

async function toggleReaction(m, reaction, host) {
  const remove = !!reaction.me;
  try {
    await call('react', {
      channel: m.channel_id || (S.channel && S.channel.id),
      message: m.id,
      emoji: reaction.emoji && reaction.emoji.id
        ? `${reaction.emoji.name}:${reaction.emoji.id}`
        : (reaction.emoji && reaction.emoji.name),
      remove,
    });
    reaction.me = !remove;
    reaction.count = Math.max(0, (reaction.count || 0) + (remove ? -1 : 1));
    if (remove && reaction.count === 0) {
      m.reactions = (m.reactions || []).filter((x) => x !== reaction);
    }
    const fresh = reactionsNode(m);
    if (fresh.children.length) host.replaceWith(fresh);
    else host.remove();
  } catch (e) { toast('Falha na reação: ' + e.message); }
}

async function interact(m, c, values) {
  if (c.style === 5 && c.url) {
    call('open_url', { url: c.url }).catch(() => window.open(c.url, '_blank'));
    return;
  }
  if (c.disabled) return;
  try {
    await call('interact', {
      channel: m.channel_id || (S.channel && S.channel.id),
      message: m.id,
      guild: S.kind === 'guild' && S.guild ? S.guild.id : null,
      application_id: m.application_id || null,
      component_type: c.type,
      custom_id: c.custom_id || null,
      values: values || null,
    });
    toast('Interação enviada.');
  } catch (e) { toast('Componente indisponível: ' + e.message); }
}

function componentNode(m, c) {
  if (!c) return null;
  if (c.type === 2) {
    const styles = { 1: 'primary', 2: '', 3: 'success', 4: 'danger', 5: 'link' };
    const b = el('button', 'compBtn ' + (styles[c.style] || ''));
    b.disabled = !!c.disabled;
    if (c.emoji) b.appendChild(emojiNode(c.emoji));
    b.appendChild(el('span', '', c.label || 'Botão'));
    if (c.style === 5) b.title = c.url || 'Abrir link';
    else b.title = c.custom_id || 'Componente';
    b.onclick = () => interact(m, c);
    return b;
  }
  if (c.type === 3) {
    const sel = el('select', 'compSelect');
    const head = el('option', '', c.placeholder || 'Selecionar...');
    head.value = '';
    sel.appendChild(head);
    (c.options || []).forEach((o) => {
      const opt = el('option', '', o.label || o.value);
      opt.value = o.value;
      if (o.default) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.disabled = !!c.disabled;
    sel.onchange = () => {
      if (!sel.value) return;
      interact(m, c, [sel.value]);
      sel.value = '';
    };
    return sel;
  }
  if (c.type === 5 || c.type === 6 || c.type === 7 || c.type === 8) {
    const sel = el('select', 'compSelect');
    const ph = el('option', '', c.placeholder || 'Selecionar...');
    ph.value = '';
    sel.appendChild(ph);
    sel.disabled = true;
    sel.title = 'Seletor do Discord';
    return sel;
  }
  if (c.type === 10) return el('div', 'compText', c.content || '');
  if (c.type === 11) {
    const wrap = el('div', 'compMedia');
    const url = c.media && (c.media.url || c.media.proxy_url);
    if (url) wrap.appendChild(mediaNode(url, {
      mime: c.media.content_type,
      width: c.media.width,
      height: c.media.height,
    }));
    return wrap;
  }
  if (c.type === 12) {
    const wrap = el('div', 'compMedia');
    (c.items || []).forEach((it) => {
      const url = it.media && (it.media.url || it.media.proxy_url);
      if (url) wrap.appendChild(mediaNode(url, {
        mime: it.media.content_type,
        width: it.media.width,
        height: it.media.height,
      }));
    });
    return wrap;
  }
  return null;
}

function componentsNode(m) {
  const host = el('div', 'components');
  const addRow = (comps) => {
    const row = el('div', 'componentRow');
    (comps || []).forEach((c) => {
      const n = componentNode(m, c);
      if (n) row.appendChild(n);
    });
    if (row.children.length) host.appendChild(row);
  };
  const add = (c) => {
    if (!c) return;
    if (c.type === 1) { addRow(c.components); return; }
    if (c.type === 17) { (c.components || []).forEach(add); return; }
    const n = componentNode(m, c);
    if (n) {
      const row = el('div', 'componentRow');
      row.appendChild(n);
      host.appendChild(row);
    }
  };
  (m.components || []).forEach(add);
  return host;
}

function messageNode(m, grouped) {
  const node = el('div', 'msg' + (grouped ? '' : ' grp'));
  node.dataset.id = m.id;
  const row = el('div', 'mrow');

  row.appendChild(el('span', 'when', hhmm(m.timestamp))).title = m.timestamp || '';
  row.appendChild(authorNode(m));

  const body = el('div', 'body');
  if (m.content) {
    const text = el('span', 'text');
    text.innerHTML = mdLite(m.content);
    body.appendChild(text);
  }
  if (m.edited_timestamp) body.appendChild(el('span', 'edited', '(editado)'));

  (m.attachments || []).forEach((a) => {
    const wrap = el('div', 'att');
    const isImg = (a.content_type || '').startsWith('image/') || /\.(png|jpe?g|gif|webp|avif)$/i.test(a.filename || a.url || '');
    if (isImg) {
      wrap.appendChild(mediaNode(a.url, {
        mime: a.content_type,
        filename: a.filename,
        width: a.width,
        height: a.height,
      }));
    } else {
      const link = el('a', 'file', '📎 ' + (a.filename || 'arquivo'));
      link.href = a.url; link.target = '_blank'; link.rel = 'noreferrer';
      wrap.appendChild(link);
    }
    body.appendChild(wrap);
  });

  if ((m.reactions || []).length) body.appendChild(reactionsNode(m));
  if ((m.components || []).length) {
    const comps = componentsNode(m);
    if (comps.children.length) body.appendChild(comps);
  }

  row.appendChild(body);
  node.appendChild(row);
  S.nodes.set(m.id, node);
  return node;
}

function appendMessage(m, live = true) {
  if (!m || !m.id) return;
  noteMessageIfPresent(m);
  if (!S.channel) return;
  if (m.channel_id && m.channel_id !== S.channel.id) {
    if (live) {
      bumpUnread(m.channel_id);
      if (S.kind === 'guild') renderChannels(); else renderDMs();
    }
    return;
  }
  if ((S.loadingOlder || S.loadingChannel) && !S.hasNewer) {
    queueLive(m);
    return;
  }
  if (S.seen.has(m.id)) return;
  // Lendo historico antigo: nao desloca a janela; oferece "voltar ao recente".
  if (S.hasNewer) {
    markSeen(m.id);
    S.hasNewer = true;
    updateHistoryControls();
    return;
  }
  const box = $('#msgs');
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  const mine = S.user && m.author && m.author.id === S.user.id;
  if (nearBottom || mine) S.liveStick = true;
  const stick = S.liveStick;
  const list = $('#msgList');
  const placeholder = list.querySelector('.empty');
  if (placeholder) placeholder.remove();
  const prev = S.messages[S.messages.length - 1];
  const grouped = isGroupedWith(prev, m);
  S.messages.push(m);
  S.activeIds.add(m.id);
  markSeen(m.id);
  list.appendChild(messageNode(m, grouped));
  trimWindow('top', !stick);
  setWindowMeta();
  if (live && stick) scrollBottom();
}

function appendLiveBatch(msgs) {
  if (!S.channel) return false;
  if ((S.loadingOlder || S.loadingChannel) && !S.hasNewer) {
    (msgs || []).forEach(queueLive);
    return false;
  }
  const box = $('#msgs');
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  if (nearBottom) S.liveStick = true;
  const list = $('#msgList');
  const placeholder = list.querySelector('.empty');
  let added = false;
  (msgs || []).forEach((m) => {
    if (!m || !m.id || S.seen.has(m.id)) return;
    if (m.channel_id && m.channel_id !== S.channel.id) return;
    noteMessageIfPresent(m);
    if (placeholder) placeholder.remove();
    const prev = S.messages[S.messages.length - 1];
    const grouped = isGroupedWith(prev, m);
    S.messages.push(m);
    S.activeIds.add(m.id);
    markSeen(m.id);
    list.appendChild(messageNode(m, grouped));
    added = true;
  });
  if (added) {
    trimWindow('top', !S.liveStick);
    setWindowMeta();
    refreshGrouping();
    if (S.liveStick) scrollBottom();
  }
  return added;
}

let bottomRaf = 0;
function scrollBottom() {
  if (bottomRaf) return;
  const box = $('#msgs');
  const go = () => { box.scrollTop = box.scrollHeight; };
  bottomRaf = requestAnimationFrame(() => {
    bottomRaf = 0;
    go();
    requestAnimationFrame(go);
  });
}

/* ---------------- envio ---------------- */
async function send() {
  const input = $('#input');
  const content = input.value.trim();
  if (!content || !S.channel || S.sending) return;
  const ch = S.channel.id;
  S.sending = true;
  const btn = $('#sendBtn');
  if (btn) btn.disabled = true;
  input.value = '';
  autosize();
  try {
    const m = await call('send', { channel: ch, content });
    if (m && S.channel && S.channel.id === ch) appendMessage(m);
  } catch (e) {
    input.value = content;
    autosize();
    toast('Não foi possível enviar: ' + e.message);
  } finally {
    S.sending = false;
    if (btn) btn.disabled = false;
  }
}

async function attach() {
  if (!S.channel || S.attaching) return;
  const ch = S.channel.id;
  const content = $('#input').value.trim();
  S.attaching = true;
  const btn = $('#attachBtn');
  if (btn) btn.disabled = true;
  try {
    const m = await call('upload', { channel: ch, content });
    if (m && S.channel && S.channel.id === ch) {
      $('#input').value = '';
      autosize();
      appendMessage(m);
    }
  } catch (e) { toast('Falha no anexo: ' + e.message); }
  finally {
    S.attaching = false;
    if (btn) btn.disabled = false;
  }
}

/* ---------------- lightbox ---------------- */
let lbScale = 1, lbX = 0, lbY = 0, lbUrl = '', lbWrap = null, lbHasWrap = false;
const lb = $('#lightbox'), lbImg = $('#lbImg'), lbError = $('#lbError');

function paintLb() {
  lbImg.style.transform = `translate(${lbX}px,${lbY}px) scale(${lbScale})`;
  lbImg.style.cursor = lbScale > 1 ? 'grab' : 'default';
}
function openLightbox(url, wrap = null) {
  if (!url) return;
  lbUrl = url;
  lbWrap = wrap || null;
  lbHasWrap = !!wrap;
  lbScale = 1; lbX = lbY = 0; paintLb();
  lb.classList.add('open');
  lbError.classList.add('hidden');
  lbImg.classList.remove('hidden');
  lbImg.onload = () => {
    lbError.classList.add('hidden');
    lbImg.classList.remove('hidden');
  };
  lbImg.onerror = () => {
    if (!lbUrl) return;
    lbImg.classList.add('hidden');
    lbError.classList.remove('hidden');
  };
  lbImg.src = url;
}
function closeLightbox() {
  lbUrl = '';
  lbWrap = null;
  lbHasWrap = false;
  lb.classList.remove('open');
  lbImg.onload = null;
  lbImg.onerror = null;
  lbImg.src = '';
  lbImg.classList.remove('hidden');
  lbError.classList.add('hidden');
  // Depois de fechar, midias reveladas que estao fora da tela podem voltar
  // para a capa e liberar a decodificacao.
  censorOffscreenMedia();
}
function zoomLb(f) {
  lbScale = Math.min(8, Math.max(.15, lbScale * f));
  if (lbScale <= 1) { lbX = lbY = 0; }
  paintLb();
}

/* ---------------- configuracoes ---------------- */
function applyTheme(t, persist = true, cache = true) {
  const theme = (t === 'amoled' || t === 'auto') ? t : 'dark';
  document.documentElement.dataset.theme = theme;
  if (cache) store.set('theme', theme);
  const sel = $('#themeSel');
  if (sel) sel.value = theme;
  // Mantem a barra de titulo/controles GTK alinhados ao tema do app.
  if (persist) call('set_theme', { theme }).catch(() => {});
}
function applyAvatars(on) {
  S.avatars = !!on && !LEAN;
  store.set('avatars', !!on);
  const chk = $('#avatarsChk');
  if (chk) chk.checked = S.avatars;
  renderMe();
  if (S.kind === 'dm') renderDMs();
}

function applyAppName(name) {
  S.appName = (name || '').trim() || '4Cord';
  document.title = S.appName;
  const title = $('#appTitle');
  if (title) title.textContent = S.appName;
  const input = $('#appNameInput');
  if (input && document.activeElement !== input) input.value = S.appName;
}

function applyVerbose(on, persist = false) {
  S.verbose = !!on;
  const chk = $('#verboseChk');
  if (chk) chk.checked = S.verbose;
  if (persist) call('set_verbose', { enabled: S.verbose }).catch(() => {});
}

async function refreshRam() {
  if (S.ramBusy) return;
  S.ramBusy = true;
  const info = $('#ramInfo');
  try {
    const r = await call('ram');
    if (!info) return;
    if (!r || !r.ok || r.mb == null) {
      info.textContent = 'RAM —';
      info.title = 'Não foi possível ler o consumo em /proc.';
      return;
    }
    const rounded = Math.round(r.mb);
    const prefix = r.method === 'PSS' ? 'RAM' : 'RAM ~';
    const label = `${prefix} ${rounded} MB`;
    if (info.textContent !== label) info.textContent = label;
    const method = r.method === 'PSS'
      ? 'PSS agregado'
      : 'PSS agregado (RSS nos processos sem smaps_rollup)';
    info.title = `${method} de ${r.processes} processo(s) do 4Cord`;
  } catch (e) {
    if (info) {
      info.textContent = 'RAM —';
      info.title = 'Falha ao consultar /proc.';
    }
  } finally {
    S.ramBusy = false;
  }
}

function setIconPreview(path) {
  const im = $('#iconPreview');
  if (!im) return;
  if (path) {
    im.src = 'file://' + encodeURI(path).replace(/#/g, '%23');
    im.classList.remove('hidden');
  } else {
    im.removeAttribute('src');
    im.classList.add('hidden');
  }
}

async function saveAppName() {
  const val = $('#appNameInput').value;
  try {
    const name = await call('set_app_name', { name: val });
    applyAppName(name);
    toast('Nome do aplicativo atualizado.');
  } catch (e) { toast('Falha ao renomear: ' + e.message); }
}

async function chooseIcon() {
  try {
    const res = await call('pick_icon');
    if (res && res.icon) {
      setIconPreview(res.icon);
      toast('Ícone atualizado.');
    }
  } catch (e) { toast('Falha ao mudar o ícone: ' + e.message); }
}

function toggleSide() {
  if (window.innerWidth <= 760) {
    document.body.classList.toggle('side-open');
  } else {
    document.body.classList.toggle('side-collapsed');
    const btn = $('#sideToggle');
    if (btn) {
      const label = document.body.classList.contains('side-collapsed')
        ? 'Expandir canais (Ctrl+B)' : 'Recolher canais (Ctrl+B)';
      btn.title = label;
      btn.setAttribute('aria-label', label);
    }
  }
}

function resetWidths() {
  document.body.classList.remove('side-collapsed');
  store.set('sideW', 224);
  document.documentElement.style.setProperty('--side-w', '224px');
}

/* ---------------- central de informacoes ---------------- */
const INFO_TABS = ['about', 'steps', 'tech'];
let infoTab = 'about';
let infoLastFocus = null;

function infoPanelEl() {
  return $('#info');
}

function showInfoTab(name) {
  if (!INFO_TABS.includes(name)) name = 'about';
  infoTab = name;
  INFO_TABS.forEach((tab) => {
    const sec = $('#info' + tab.charAt(0).toUpperCase() + tab.slice(1));
    const btn = document.querySelector(`[data-info-tab="${tab}"]`);
    const active = tab === name;
    if (sec) sec.classList.toggle('hidden', !active);
    if (btn) {
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.tabIndex = active ? 0 : -1;
    }
  });
  const adv = $('#infoAdvanced');
  if (adv) adv.classList.add('hidden');
  const tabs = $('#infoTabs');
  if (tabs) tabs.classList.remove('hidden');
  const more = $('#infoAdvancedBtn');
  if (more) more.classList.remove('hidden');
  const back = $('#infoBack');
  if (back) back.classList.add('hidden');
  const body = $('#infoBody');
  if (body) body.scrollTop = 0;
}

function showInfoAdvanced() {
  INFO_TABS.forEach((tab) => {
    const sec = $('#info' + tab.charAt(0).toUpperCase() + tab.slice(1));
    if (sec) sec.classList.add('hidden');
  });
  const adv = $('#infoAdvanced');
  if (adv) adv.classList.remove('hidden');
  const tabs = $('#infoTabs');
  if (tabs) tabs.classList.add('hidden');
  const more = $('#infoAdvancedBtn');
  if (more) more.classList.add('hidden');
  const back = $('#infoBack');
  if (back) back.classList.remove('hidden');
  const body = $('#infoBody');
  if (body) body.scrollTop = 0;
  if (back) back.focus();
}

function openInfo() {
  const panel = infoPanelEl();
  if (!panel) return;
  infoLastFocus = document.activeElement;
  $('#settings').classList.add('hidden');
  $('#friends').classList.add('hidden');
  panel.classList.remove('hidden');
  showInfoTab('about');
  const close = $('#infoClose');
  if (close) close.focus();
}

function closeInfo() {
  const panel = infoPanelEl();
  if (!panel || panel.classList.contains('hidden')) return;
  panel.classList.add('hidden');
  if (infoLastFocus && document.contains(infoLastFocus)) {
    try { infoLastFocus.focus(); } catch (e) { /* ignore */ }
  }
}

function infoKeydown(e) {
  const panel = infoPanelEl();
  if (!panel || panel.classList.contains('hidden')) return;
  if (e.key !== 'Tab') return;
  const focusables = [...panel.querySelectorAll(
    'button:not(:disabled):not(.hidden), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )].filter((n) => n.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

/* ---------------- redimensionamento ---------------- */
function initResizers() {
  const root = document.documentElement;
  const sideW = store.get('sideW', 224);
  root.style.setProperty('--side-w', sideW + 'px');

  const handle = $('#r2');
  handle.addEventListener('pointerdown', (ev) => {
    if (window.innerWidth <= 760) return;
    ev.preventDefault();
    handle.classList.add('drag');
    const startX = ev.clientX;
    const startSide = parseInt(getComputedStyle(root).getPropertyValue('--side-w'));
    const move = (e) => {
      const v = Math.max(176, Math.min(360, startSide + (e.clientX - startX)));
      root.style.setProperty('--side-w', v + 'px');
    };
    const up = () => {
      handle.classList.remove('drag');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      store.set('sideW', parseInt(getComputedStyle(root).getPropertyValue('--side-w')));
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up, { once: true });
  });
}

/* ---------------- eventos do gateway ---------------- */
async function syncLatest() {
  if (!S.channel || S.syncing || S.loadingOlder) return false;
  const ch = S.channel;
  const seq = S.navSeq;
  setSyncBusy(true);
  try {
    // Busca duas paginas para detectar sobreposicao com a janela atual.
    // Uma unica pagina pode nao alcancar o historico exibido apos uma
    // reconexao longa, criando um buraco no meio da lista.
    const raw = await call('messages', { channel: ch.id, limit: SYNC_LIMIT });
    if (seq !== S.navSeq || !S.channel || S.channel.id !== ch.id) return false;
    const asc = (raw || []).slice().reverse().filter((m) => m && m.id);
    if (asc.length) noteChannelLast(ch.id, asc[asc.length - 1].id);
    if (!asc.length) return true;
    if (S.hasNewer) {
      // O usuario esta lendo historico antigo: nao desloca a janela.
      asc.forEach((m) => markSeen(m.id));
      S.hasNewer = true;
      updateHistoryControls();
      return true;
    }
    const newest = S.newest;
    const gap = !!newest && idCmp(asc[0].id, newest) > 0;
    if (gap) {
      const box = $('#msgs');
      const atBottom = S.liveStick ||
        (box.scrollHeight - box.scrollTop - box.clientHeight < 120);
      if (atBottom) {
        // Recomeca pela pagina mais recente em vez de anexar e deixar um
        // intervalo inacessivel entre a janela antiga e a nova.
        replaceWindow(asc, true);
        S.hasOlder = asc.length >= PAGE_SIZE;
        setWindowMeta();
        updateHistoryControls();
        scrollBottom();
      } else {
        asc.forEach((m) => markSeen(m.id));
        S.hasNewer = true;
        updateHistoryControls();
      }
      return true;
    }
    // Sem buraco: acrescenta somente o que e mais novo que a janela atual.
    const fresh = newest ? asc.filter((m) => idCmp(m.id, newest) > 0) : asc;
    appendLiveBatch(fresh);
    if (asc.length >= PAGE_SIZE) S.hasOlder = true;
    updateHistoryControls();
    return true;
  } catch (e) {
    /* sem acesso ou offline: o historico que ja esta na tela permanece */
    return false;
  } finally {
    if (seq === S.navSeq) setSyncBusy(false);
  }
}

/* Junta DMs recebidas do REST/READY sem perder a ordem escolhida pelo
   usuario nem reapresentar DMs que ele removeu da lista. */
function mergeDMs(list) {
  if (!Array.isArray(list)) return false;
  const incoming = list.filter((ch) => ch && ch.id &&
    (ch.type === 1 || ch.type === 3) && !S.hiddenDMs.has(ch.id));
  const byId = new Map(S.dms.map((ch) => [ch.id, ch]));
  incoming.forEach((ch) => {
    byId.set(ch.id, Object.assign(byId.get(ch.id) || {}, ch));
  });
  const merged = incoming.map((ch) => byId.get(ch.id));
  S.dms.forEach((ch) => {
    if (!S.hiddenDMs.has(ch.id) && !merged.some((x) => x.id === ch.id)) {
      merged.push(ch);
    }
  });
  S.dms = merged;
  if (S.kind === 'dm') renderDMs();
  return true;
}

async function refreshDMs() {
  try {
    return mergeDMs(await call('dms'));
  } catch (e) {
    return false;
  }
}

async function recoverChannelMessages(ch, last) {
  if (!ch || !last || !ch.id) return 0;
  if (S.channel && S.channel.id === ch.id) return 0;
  const raw = await call('messages', {
    channel: ch.id,
    after: last,
    limit: SYNC_LIMIT,
  });
  const asc = (raw || []).slice().reverse().filter((m) => m && m.id);
  if (!asc.length) return 0;
  let fresh = 0;
  asc.forEach((m) => {
    if (!S.seen.has(m.id)) {
      fresh += 1;
      markSeen(m.id);
    }
  });
  noteChannelLast(ch.id, asc[asc.length - 1].id);
  if (fresh) {
    bumpUnread(ch.id, fresh);
    if (S.kind === 'dm') renderDMs();
    else renderChannels();
  }
  return fresh;
}

/* Recupera a conversa aberta e as DMs conhecidas depois de uma reconexao.
   A busca "after" usa o ultimo ID visto e e limitada a uma pagina por DM. */
async function recoverAfterReconnect() {
  if (S.recovering || S.loadingChannel) return false;
  S.recovering = true;
  let found = false;
  try {
    await refreshDMs();
    const active = S.channel;
    if (active) {
      found = await syncLatest() || found;
    } else {
      setSyncBusy(true);
    }
    const targets = S.dms
      .filter((ch) => {
        if (active && ch.id === active.id) return false;
        const last = S.lastByChannel.get(ch.id);
        if (!last) return false;
        return !ch.last_message_id || idCmp(ch.last_message_id, last) > 0;
      })
      .slice(0, 10);
    for (const ch of targets) {
      const last = S.lastByChannel.get(ch.id);
      setSyncBusy(true);
      try {
        const n = await recoverChannelMessages(ch, last);
        found = found || n > 0;
      } catch (e) {
        /* rede indisponivel: a conversa sera atualizada ao ser aberta */
      } finally {
        setSyncBusy(false);
      }
    }
    return found;
  } finally {
    S.recovering = false;
    setSyncBusy(false);
  }
}

async function reloadMessages() {
  if (S.loadingChannel || S.loadingOlder || S.syncing || S.recovering) return;
  const hasChannel = !!S.channel;
  await recoverAfterReconnect();
  toast(hasChannel ? 'Mensagens sincronizadas.' : 'Lista de DMs atualizada.');
}

window.tpEvent = (ev) => {
  if (!ev) return;
  const d = ev.data || {};
  if (ev.type === 'gateway') { setConn(!!d.connected); return; }
  if (ev.type === 'ready') {
    if (d.user) { S.user = d.user; renderMe(); }
    if (Array.isArray(d.private_channels) && d.private_channels.length) {
      mergeDMs(d.private_channels);
    }
    setConn(true);
    // READY depois de uma sessao invalidada nao reenvia eventos perdidos:
    // sincroniza a conversa atual e as DMs conhecidas.
    if (S.readyOnce) recoverAfterReconnect();
    S.readyOnce = true;
    return;
  }
  if (ev.type === 'resumed') {
    setConn(true);
    S.readyOnce = true;
    recoverAfterReconnect();
    return;
  }
  if (ev.type === 'message_create') { appendMessage(d); return; }
  if (ev.type === 'message_update') {
    const idx = S.messages.findIndex((m) => m.id === d.id);
    const node = messageNodeFor(d.id);
    if (idx >= 0) {
      Object.assign(S.messages[idx], d);
      if (node) {
        disposeMediaTree(node);
        node.replaceWith(messageNode(S.messages[idx], false));
        refreshGrouping();
      }
    } else if (node) {
      const text = node.querySelector('.text');
      if (text) text.innerHTML = mdLite(d.content || '');
    }
    return;
  }
  if (ev.type === 'message_delete') {
    const node = messageNodeFor(d.id);
    if (node) {
      disposeMediaTree(node);
      node.remove();
      S.nodes.delete(d.id);
    }
    S.messages = S.messages.filter((m) => m.id !== d.id);
    S.activeIds.delete(d.id);
    S.seen.delete(d.id);
    setWindowMeta();
    refreshGrouping();
    updateHistoryControls();
    return;
  }
  if (ev.type === 'channel_create') {
    if ((d.type === 1 || d.type === 3) && !S.dms.some((c) => c.id === d.id)) {
      S.dms.unshift(d);
      if (S.kind === 'dm') renderDMs();
    }
  }
};

/* ---------------- boot ---------------- */
function autosize() {
  const i = $('#input');
  i.style.height = 'auto';
  i.style.height = Math.min(140, i.scrollHeight) + 'px';
}

async function boot() {
  applyTheme(store.get('theme', 'dark'), false, false);
  applyAccent(store.get('accent', null) || DEFAULT_ACCENT, false, false);
  applyAvatars(store.get('avatars', false));
  initResizers();

  try {
    const init = await call('init');
    S.user = init.user;
    S.guilds = init.guilds || [];
    S.dms = init.dms || [];
    S.hiddenDMs = new Set(store.get('hiddenDMs', []) || []);
    S.mock = !!init.mock;
    if (init.gateway) setConn(true); else setConnWait();
    $('#ver').textContent = 'v' + init.version;
    const infoVer = $('#infoVersion');
    if (infoVer) infoVer.textContent = 'v' + init.version;
    applyAppName(init.app_name || '4Cord');
    applyTheme(init.theme || store.get('theme', 'dark'), false, true);
    // O backend e a fonte de verdade; o localStorage e apenas cache visual.
    applyAccent(init.accent || store.get('accent', null) || DEFAULT_ACCENT, false, true);
    applyVerbose(!!init.verbose_logs, false);
    setIconPreview(init.icon);
    refreshRam();
    if (S.mock) $('#mockHint').textContent = 'modo demonstração (dados falsos)';
    renderServerSelect();
    renderMe();
    const g = initialGuild();
    if (g) await selectGuild(g);
    else showNoServer();
  } catch (e) {
    toast('Falha ao iniciar: ' + e.message);
  }
}

/* ---------------- ligacoes ---------------- */
$('#dmBtn').onclick = () => {
  if (S.kind === 'dm') {
    const g = activeGuild();
    if (g) selectGuild(g);
    else showNoServer();
  } else {
    selectDMs();
  }
};
$('#addDMBtn').onclick = openFriends;
$('#friendsClose').onclick = () => $('#friends').classList.add('hidden');
$('#friendSearch').addEventListener('input', renderFriendList);
$('#msgs').addEventListener('scroll', () => {
  const b = $('#msgs');
  S.liveStick = b.scrollHeight - b.scrollTop - b.clientHeight < 120;
}, { passive: true });
$('#serverSel').onchange = async (e) => {
  const g = S.guilds.find((x) => x.id === e.target.value);
  if (!g) return;
  $('#settings').classList.add('hidden');
  await selectGuild(g);
  toast('Servidor exibido: ' + g.name);
};
$('#appNameSave').onclick = saveAppName;
$('#appNameInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); saveAppName(); }
});
$('#iconBtn').onclick = chooseIcon;
$('#settingsBtn').onclick = () => {
  renderServerSelect();
  $('#settings').classList.toggle('hidden');
};
$('#sideToggle').onclick = toggleSide;
$('#sideOpen').onclick = toggleSide;
$('#sideScrim').onclick = () => document.body.classList.remove('side-open');
$('#sendBtn').onclick = send;
$('#reloadBtn').onclick = reloadMessages;
$('#attachBtn').onclick = attach;
$('#loadOlder').onclick = loadOlder;
$('#loadNewer').onclick = goLatest;
$('#input').addEventListener('input', autosize);
$('#input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
$('#themeSel').onchange = (e) => applyTheme(e.target.value, true, true);
$('#accentPick').addEventListener('input', (e) => applyAccent(e.target.value, false, false));
$('#accentPick').addEventListener('change', (e) => applyAccent(e.target.value, true));
$('#accentReset').onclick = () => applyAccent(DEFAULT_ACCENT, true);
$('#avatarsChk').onchange = (e) => applyAvatars(e.target.checked);
$('#verboseChk').onchange = (e) => applyVerbose(e.target.checked, true);
$('#themeBtn').onclick = () => {
  const order = ['dark', 'amoled', 'auto'];
  const cur = document.documentElement.dataset.theme;
  applyTheme(order[(order.indexOf(cur) + 1) % order.length]);
};
$('#resetWidths').onclick = resetWidths;
$('#logoutBtn').onclick = () => call('logout').catch(() => {});
$('#ver').textContent = '';

$('#helpBtn').onclick = openInfo;
$('#infoClose').onclick = closeInfo;
$('#infoAdvancedBtn').onclick = showInfoAdvanced;
$('#infoBack').onclick = () => {
  showInfoTab(infoTab);
  const tab = document.querySelector(`[data-info-tab="${infoTab}"]`);
  if (tab) tab.focus();
};
$('#info').addEventListener('click', (e) => {
  if (e.target === $('#info')) closeInfo();
});
$('#info').addEventListener('keydown', infoKeydown);
document.querySelectorAll('.infoTab').forEach((btn) => {
  btn.onclick = () => showInfoTab(btn.dataset.infoTab);
  btn.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.infoTab')];
    const i = tabs.indexOf(btn);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    if (next) {
      next.focus();
      next.click();
    }
  });
});

lb.addEventListener('click', (e) => { if (e.target === lb) closeLightbox(); });
$('#lbClose').onclick = closeLightbox;
$('#lbPlus').onclick = () => zoomLb(1.25);
$('#lbMinus').onclick = () => zoomLb(.8);
$('#lbReset').onclick = () => { lbScale = 1; lbX = lbY = 0; paintLb(); };
$('#lbOpen').onclick = () => {
  if (!lbUrl) return;
  call('open_url', { url: lbUrl }).catch(() => window.open(lbUrl, '_blank'));
};
lb.addEventListener('wheel', (e) => { e.preventDefault(); zoomLb(e.deltaY < 0 ? 1.12 : .89); }, { passive: false });
lbImg.addEventListener('pointerdown', (e) => {
  const sx = e.clientX - lbX, sy = e.clientY - lbY;
  const mv = (ev) => { lbX = ev.clientX - sx; lbY = ev.clientY - sy; paintLb(); };
  const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); };
  window.addEventListener('pointermove', mv);
  window.addEventListener('pointerup', up, { once: true });
});
lbImg.addEventListener('dblclick', () => { lbScale = 1; lbX = lbY = 0; paintLb(); });

document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
    e.preventDefault();
    toggleSide();
  }
  if (e.key === 'Escape') {
    if (!$('#info').classList.contains('hidden')) closeInfo();
    else if (lb.classList.contains('open')) closeLightbox();
    else if (!document.querySelector('#friends').classList.contains('hidden')) {
      document.querySelector('#friends').classList.add('hidden');
    }
    else if (document.body.classList.contains('side-open')) document.body.classList.remove('side-open');
    else $('#settings').classList.add('hidden');
  }
  if (lb.classList.contains('open')) {
    if (e.key === '+' || e.key === '=') zoomLb(1.2);
    if (e.key === '-') zoomLb(.83);
  }
});

boot();
setInterval(refreshRam, 12000);
