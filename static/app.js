/* ===========================================================================
   Mattermost Admin Dashboard — front-end (vanilla JS, no dependencies)
   =========================================================================== */
(function () {
  'use strict';

  var BOOT = window.__BOOT__ || {};
  var TZ = BOOT.tz || 'UTC';
  var MAX_USER_ROWS = 500;

  /* ---------------------------------------------------------------- utils */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function h(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(value) {
    var n = Number(value || 0);
    return isFinite(n) ? n : 0;
  }
  function fmtNum(value) { return num(value).toLocaleString('en-US'); }
  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms || 120);
    };
  }
  function initials(name, username) {
    var src = (name || '').trim();
    if (src) {
      var parts = src.split(/\s+/).filter(Boolean);
      if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return (username || '?').slice(0, 2).toUpperCase();
  }
  function hashString(str) {
    var hsh = 0;
    str = String(str || '');
    for (var i = 0; i < str.length; i++) { hsh = ((hsh << 5) - hsh + str.charCodeAt(i)) | 0; }
    return Math.abs(hsh);
  }
  function hue(name) { return hashString(name) % 360; }
  function gradient(name) {
    var h1 = hue(name);
    return 'linear-gradient(135deg, hsl(' + h1 + ' 68% 55%), hsl(' + ((h1 + 46) % 360) + ' 62% 44%))';
  }

  var dtCache = {};
  function fmtDate(ts) {
    var d = toDate(ts); if (!d) return '—';
    if (!dtCache.date) dtCache.date = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: '2-digit', month: 'short', year: 'numeric' });
    return dtCache.date.format(d);
  }
  function fmtTime(ts) {
    var d = toDate(ts); if (!d) return '—';
    if (!dtCache.time) dtCache.time = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
    return dtCache.time.format(d);
  }
  function fmtDateTime(ts) {
    var d = toDate(ts); if (!d) return '—';
    return fmtDate(d.getTime() / 1000) + ' · ' + fmtTime(d.getTime() / 1000);
  }
  function fmtDayKey(ts) {
    var d = toDate(ts); if (!d) return '';
    if (!dtCache.day) dtCache.day = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
    return dtCache.day.format(d);
  }
  function fmtDayLabel(ts) {
    var d = toDate(ts); if (!d) return '';
    var today = fmtDayKey(Date.now() / 1000);
    var key = fmtDayKey(ts);
    var yesterday = fmtDayKey(Date.now() / 1000 - 86400);
    if (key === today) return 'Today';
    if (key === yesterday) return 'Yesterday';
    if (!dtCache.dayLong) dtCache.dayLong = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
    return dtCache.dayLong.format(d);
  }
  function toDate(ts) {
    if (ts === null || ts === undefined || ts === '' || ts === 0) return null;
    if (typeof ts === 'number') return new Date(ts * 1000);
    var numeric = Number(ts);
    if (!isNaN(numeric) && numeric > 0) return new Date(numeric * 1000);
    var d = new Date(ts);
    return isNaN(d.getTime()) ? null : d;
  }
  function fmtRel(ts) {
    var d = toDate(ts); if (!d) return '—';
    var diff = Math.floor(Date.now() / 1000) - Math.floor(d.getTime() / 1000);
    if (diff < 45) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return fmtDate(ts);
  }
  function dur(seconds) {
    seconds = Math.max(0, Math.floor(seconds || 0));
    if (seconds < 60) return '0m';
    var d = Math.floor(seconds / 86400);
    var hh = Math.floor((seconds % 86400) / 3600);
    var mm = Math.floor((seconds % 3600) / 60);
    if (d > 0) return d + 'd ' + hh + 'h';
    if (hh > 0) return hh + 'h ' + mm + 'm';
    return mm + 'm';
  }
  function pct(part, whole) { return whole > 0 ? Math.round((part / whole) * 100) : 0; }
  function flagEmoji(cc) {
    if (!cc || String(cc).length !== 2) return '';
    try {
      return String.fromCodePoint.apply(null, String(cc).toUpperCase().split('').map(function (c) {
        return 127397 + c.charCodeAt(0);
      }));
    } catch (e) { return ''; }
  }
  function randomPassword(len) {
    var chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
    var out = '';
    var buf = new Uint32Array(len || 14);
    if (window.crypto && window.crypto.getRandomValues) { window.crypto.getRandomValues(buf); }
    else { for (var j = 0; j < buf.length; j++) buf[j] = Math.floor(Math.random() * 4294967295); }
    for (var i = 0; i < buf.length; i++) out += chars[buf[i] % chars.length];
    return out;
  }
  function slugify(text) {
    return String(text || '').toLowerCase().trim()
      .replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').slice(0, 63);
  }

  /* ---------------------------------------------------------------- icons */
  var ICON_PATHS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    teams: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    userPlus: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
    chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.6 9.6 0 0 1-3.9-.9L3 21l1.9-4.6A8.4 8.4 0 1 1 21 11.5z"/>',
    pulse: '<path d="M22 12h-4l-3 8L9 4l-3 8H2"/>',
    pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/>',
    trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>',
    key: '<path d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3"/>',
    power: '<path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><path d="M12 2v10"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    x: '<path d="M18 6L6 18M6 6l12 12"/>',
    alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14L21 3"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    terminal: '<path d="M4 17l6-6-6-6M12 19h8"/>',
    eye: '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    eyeOff: '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
    edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>'
  };
  function icon(name, size) {
    return '<svg width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (ICON_PATHS[name] || '') + '</svg>';
  }

  /* ---------------------------------------------------------------- state */
  var state = {
    view: 'overview',
    users: [],
    teams: [],
    counts: {},
    usersLoaded: false,
    chat: { userId: null, partnerId: null, channelId: null, page: 0, messages: [], participants: {}, hasMore: false, mode: null, user: null, partner: null, showDeleted: true },
    presence: { hours: 24, rows: [], selected: null, now: null },
    locations: { tab: 'live', offset: 0, total: 0, timer: null },
    settings: null,
    overview: null
  };
  var openModals = [];

  /* ---------------------------------------------------------------- api */
  function ApiError(message, status, data) {
    this.name = 'ApiError';
    this.message = message;
    this.status = status;
    this.data = data || {};
  }
  ApiError.prototype = Object.create(Error.prototype);

  function sessionExpired() {
    if ($('#session-expired')) return;
    var wrap = document.createElement('div');
    wrap.className = 'modal-overlay open';
    wrap.id = 'session-expired';
    wrap.innerHTML = '<div class="modal" style="max-width:400px"><div class="modal-head"><div><h2>Session expired</h2><p>Your Mattermost admin session is no longer valid.</p></div></div>' +
      '<div class="modal-body"><p class="small muted">Sign in again to continue. This can happen after a Mattermost restart or after your session expires.</p></div>' +
      '<div class="modal-actions"><button class="btn btn-primary" onclick="window.location.href=\'/\'">Sign in again</button></div></div>';
    document.body.appendChild(wrap);
    document.body.classList.add('modal-open');
  }

  function api(path, opts) {
    opts = opts || {};
    var method = opts.method || 'GET';
    if (path.charAt(0) !== '/') path = '/' + path;
    var url = (path.indexOf('/api/') === 0 || path.indexOf('/download/') === 0)
      ? path
      : '/api' + path;
    if (opts.params) {
      var qs = [];
      Object.keys(opts.params).forEach(function (k) {
        var v = opts.params[k];
        if (v !== undefined && v !== null && v !== '') qs.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
      });
      if (qs.length) url += (url.indexOf('?') >= 0 ? '&' : '?') + qs.join('&');
    }
    var headers = {};
    if (method !== 'GET' || opts.body) headers['Content-Type'] = 'application/json';
    if (method !== 'GET') headers['X-CSRF-Token'] = BOOT.csrf || '';
    return fetch(url, {
      method: method,
      headers: headers,
      credentials: 'same-origin',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined
    }).then(function (resp) {
      var ct = resp.headers.get('content-type') || '';
      var parse = ct.indexOf('application/json') >= 0 ? resp.json().catch(function () { return null; }) : Promise.resolve(null);
      return parse.then(function (data) {
        if (!resp.ok) {
          if (resp.status === 401 && data && data.login_required) sessionExpired();
          throw new ApiError((data && data.message) || ('Request failed (' + resp.status + ')'), resp.status, data || {});
        }
        return data;
      });
    }, function (err) {
      throw new ApiError('Cannot reach the dashboard server: ' + err.message, 0, {});
    });
  }

  /* ---------------------------------------------------------------- ui primitives */
  function toast(message, type, title, ms) {
    type = type || 'info';
    var root = $('#toast-root');
    var el = document.createElement('div');
    el.className = 'toast ' + type;
    var ic = type === 'success' ? icon('check') : type === 'error' ? icon('alert') : icon('info');
    el.innerHTML = ic + '<div>' + (title ? '<strong>' + h(title) + '</strong><br>' : '') + h(message) + '</div>';
    el.title = 'Click to dismiss';
    el.addEventListener('click', function () { el.remove(); });
    root.appendChild(el);
    var life = ms || (type === 'error' ? 7000 : type === 'warn' ? 9000 : 4200);
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transform = 'translateY(6px)';
      el.style.transition = 'all .2s ease';
      setTimeout(function () { el.remove(); }, 220);
    }, life);
  }

  function modal(opts) {
    var wrap = document.createElement('div');
    wrap.className = 'modal-overlay';
    var sizeClass = opts.size || '';
    wrap.innerHTML = '<div class="modal ' + sizeClass + '" role="dialog" aria-modal="true">' +
      '<div class="modal-head"><div><h2>' + h(opts.title || '') + '</h2>' + (opts.subtitle ? '<p>' + opts.subtitle + '</p>' : '') + '</div>' +
      '<button type="button" class="icon-btn" data-close aria-label="Close">' + icon('x') + '</button></div>' +
      '<div class="modal-body">' + (opts.body || '') + '</div>' +
      (opts.actions ? '<div class="modal-actions">' + opts.actions + '</div>' : '') +
      '</div>';
    document.getElementById('modal-root').appendChild(wrap);
    document.body.classList.add('modal-open');
    requestAnimationFrame(function () { wrap.classList.add('open'); });
    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
      wrap.classList.remove('open');
      var idx = openModals.indexOf(ctl);
      if (idx >= 0) openModals.splice(idx, 1);
      setTimeout(function () {
        wrap.remove();
        if (!document.querySelector('.modal-overlay')) document.body.classList.remove('modal-open');
      }, 170);
      if (opts.onClose) opts.onClose();
    }
    var ctl = { el: wrap, modal: wrap.querySelector('.modal'), close: close };
    openModals.push(ctl);
    var onKey = function (e) { if (e.key === 'Escape') ctl.close(); };
    var innerClose = close;
    ctl.close = function () { document.removeEventListener('keydown', onKey); innerClose(); };
    wrap.addEventListener('mousedown', function (e) { if (e.target === wrap) ctl.close(); });
    $$('[data-close]', wrap).forEach(function (b) { b.addEventListener('click', function () { ctl.close(); }); });
    document.addEventListener('keydown', onKey);
    if (opts.onMount) opts.onMount(ctl);
    return ctl;
  }
  function setModalSubtitle(m, text) {
    var p = m.modal.querySelector('.modal-head p');
    if (!p) {
      p = document.createElement('p');
      m.modal.querySelector('.modal-head > div').appendChild(p);
    }
    p.textContent = text || '';
  }

  function closeAllModals() {
    openModals.slice().reverse().forEach(function (m) { try { m.close(); } catch (e) { /* noop */ } });
  }

  function confirmDialog(opts) {
    return new Promise(function (resolve) {
      var settled = false;
      var body = (opts.note ? '<div class="callout ' + (opts.noteType || 'warn') + '" style="margin:0 0 14px">' + icon('alert') + '<div>' + opts.note + '</div></div>' : '') +
        '<p class="small" style="color:var(--muted)">' + opts.message + '</p>' +
        (opts.checkboxLabel ? '<label class="check" style="margin-top:14px"><input type="checkbox" id="cd-check"> ' + opts.checkboxLabel + '</label>' : '');
      var m = modal({
        title: opts.title,
        body: body,
        actions: '<button class="btn" data-close>Cancel</button>' +
          '<button class="btn ' + (opts.danger === false ? 'btn-primary' : 'btn-danger') + '" id="cd-ok">' + h(opts.confirmText || 'Confirm') + '</button>',
        onClose: function () {
          if (!settled) { settled = true; resolve({ ok: false, checked: false }); }
        }
      });
      m.el.querySelector('#cd-ok').addEventListener('click', function () {
        if (settled) return;
        settled = true;
        var check = m.el.querySelector('#cd-check');
        resolve({ ok: true, checked: check ? check.checked : false });
        m.close();
      });
    });
  }

  function emptyState(text, ic, sub) {
    return '<div class="empty">' + icon(ic || 'info', 34) + '<strong>' + h(text) + '</strong>' + (sub ? '<span class="tiny">' + h(sub) + '</span>' : '') + '</div>';
  }

  /* ---------------------------------------------------------------- data helpers */
  function userById(id) {
    for (var i = 0; i < state.users.length; i++) { if (state.users[i].id === id) return state.users[i]; }
    return null;
  }
  function teamById(id) {
    for (var i = 0; i < state.teams.length; i++) { if (state.teams[i].id === id) return state.teams[i]; }
    return null;
  }
  function displayName(u) {
    if (!u) return '';
    return (u.name || ((u.first_name || '') + ' ' + (u.last_name || '')).trim() || u.username || '');
  }
  function userLabel(u) { return displayName(u) || u.username || u.email || 'Unknown user'; }
  function statusPill(status, long) {
    var s = ['online', 'away', 'dnd'].indexOf(status) >= 0 ? status : 'offline';
    var label = s === 'online' ? 'Online' : s === 'away' ? 'Away' : s === 'dnd' ? (long ? 'Do not disturb' : 'DND') : 'Offline';
    return '<span class="status ' + s + '"><span class="dot"></span>' + label + '</span>';
  }
  function avatarHtml(user, cls, showPresence) {
    var name = userLabel(user);
    var pr = showPresence ? '<span class="presence" style="background:var(--' + (['online', 'away', 'dnd'].indexOf((user && user.status) || '') >= 0 ? user.status : 'offline') + ')"></span>' : '';
    return '<div class="avatar ' + (cls || '') + '" style="background:' + gradient(name) + '">' + h(initials(name, user && user.username)) + pr + '</div>';
  }
  function setAvatarEl(el, user, showPresence) {
    if (!el) return;
    var name = userLabel(user);
    el.className = 'avatar ' + (el.classList.contains('lg') ? 'lg' : 'sm');
    el.style.background = gradient(name);
    el.textContent = initials(name, user && user.username);
    if (showPresence) {
      var dot = document.createElement('span');
      dot.className = 'presence';
      dot.style.background = 'var(--' + (['online', 'away', 'dnd'].indexOf((user && user.status) || '') >= 0 ? user.status : 'offline') + ')';
      el.appendChild(dot);
    }
  }
  function teamChips(ids, max) {
    if (!ids || !ids.length) return '<span class="muted tiny">No team</span>';
    max = max || 3;
    var html = ids.slice(0, max).map(function (id) {
      var t = teamById(id);
      if (!t) return '';
      return '<span class="chip team" title="' + h(t.display_name || t.name) + '">' + h(t.display_name || t.name) + '</span>';
    }).join('');
    if (ids.length > max) html += '<span class="chip">+' + (ids.length - max) + '</span>';
    return html;
  }
  function locationText(loc, opts) {
    if (!loc) return '<span class="muted">No location</span>';
    if (loc.is_private) return '<span class="muted">Local network</span>';
    var parts = [loc.city, loc.region, loc.country].filter(Boolean);
    if (!parts.length) return '<span class="muted">Unknown</span>';
    return (loc.country_code ? '<span class="flag">' + flagEmoji(loc.country_code) + '</span> ' : '') + h(parts.join(', '));
  }
  function osmLink(lat, lon) {
    if (lat === null || lat === undefined || lon === null || lon === undefined) return '<span class="muted">—</span>';
    var url = 'https://www.openstreetmap.org/?mlat=' + encodeURIComponent(lat) + '&mlon=' + encodeURIComponent(lon) + '#map=13/' + encodeURIComponent(lat) + '/' + encodeURIComponent(lon);
    return '<a href="' + url + '" target="_blank" rel="noopener noreferrer" title="Open in OpenStreetMap">' + Number(lat).toFixed(4) + ', ' + Number(lon).toFixed(4) + ' ' + icon('external', 12) + '</a>';
  }
  var SOURCE_LABEL = { 'agent': 'Agent', 'dashboard-login': 'Dashboard login', 'audit-log': 'Login audit', 'manual': 'Manual' };
  var SOURCE_PILL = { 'agent': 'pill-violet', 'dashboard-login': 'pill-blue', 'audit-log': 'pill-amber', 'manual': 'pill-gray' };
  function sourcePill(src) {
    return '<span class="pill ' + (SOURCE_PILL[src] || 'pill-gray') + '">' + h(SOURCE_LABEL[src] || src || 'unknown') + '</span>';
  }
  var ACTION_LABEL = {
    'login': 'Signed in', 'logout': 'Signed out',
    'user.create': 'Created user', 'user.activate': 'Activated user', 'user.deactivate': 'Deactivated user',
    'user.delete_permanent': 'Deleted user permanently', 'user.reset_password': 'Reset password',
    'team.create': 'Created team', 'team.delete_permanent': 'Deleted team permanently', 'team.archive': 'Archived team',
    'team.members_add': 'Added team member', 'team.members_remove': 'Removed team member',
    'locations.sync_audits': 'Imported login locations', 'agent.download': 'Downloaded location agent'
  };
  function actionLabel(action) { return ACTION_LABEL[action] || action || '—'; }
  function actionIcon(action) {
    if (!action) return 'info';
    if (action.indexOf('user') === 0) return action.indexOf('delete') >= 0 ? 'trash' : 'users';
    if (action.indexOf('team') === 0) return 'teams';
    if (action.indexOf('location') === 0) return 'pin';
    if (action === 'login' || action === 'logout') return 'logout';
    if (action.indexOf('agent') === 0) return 'terminal';
    return 'info';
  }
  function prettyDetails(raw) {
    if (!raw) return '<span class="muted">—</span>';
    try {
      var obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
      if (obj && typeof obj === 'object') {
        var parts = Object.keys(obj).map(function (k) {
          var v = obj[k];
          if (v === null || v === '' || (Array.isArray(v) && !v.length)) return '';
          if (typeof v === 'object') v = JSON.stringify(v);
          return k + ': ' + v;
        }).filter(Boolean);
        return '<span class="tiny muted">' + h(parts.join(' · ')) + '</span>';
      }
      return h(String(obj));
    } catch (e) { return h(String(raw)); }
  }
  function statusOf(u) { return u && ['online', 'away', 'dnd'].indexOf(u.status) >= 0 ? u.status : 'offline'; }

  function copyText(text) {
    var fallback = function () {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) { /* noop */ }
      ta.remove();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(fallback);
    }
    fallback();
    return Promise.resolve();
  }

  /* ---------------------------------------------------------------- view routing */
  var VIEW_META = {
    overview: { title: 'Overview', sub: 'A live snapshot of your Mattermost server' },
    users: { title: 'Users', sub: 'Manage accounts, teams and passwords' },
    teams: { title: 'Teams', sub: 'Create teams and manage memberships' },
    chats: { title: 'Chats', sub: 'Read direct-message conversations' },
    presence: { title: 'Presence', sub: 'When users were online or offline' },
    locations: { title: 'Locations', sub: 'Where users connected from' },
    audit: { title: 'Activity', sub: 'Everything admins did in this dashboard' },
    settings: { title: 'Settings', sub: 'Server, tracking and agent configuration' }
  };
  var loaders = {
    overview: loadOverview, users: loadUsers, teams: loadTeams, chats: loadChats,
    presence: loadPresence, locations: loadLocations, audit: loadAudit, settings: loadSettings
  };
  function setSub(text) { $('#page-sub').textContent = text || ''; }

  function setView(view, opts) {
    opts = opts || {};
    if (!VIEW_META[view]) view = 'overview';
    state.view = view;
    $$('.nav-item').forEach(function (b) { b.classList.toggle('active', b.dataset.view === view); });
    $$('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + view); });
    $('#page-title').textContent = VIEW_META[view].title;
    setSub(VIEW_META[view].sub);
    if (!opts.skipHash) {
      try { history.replaceState(null, '', '#/' + view); } catch (e) { location.hash = '#/' + view; }
    }
    stopLocAuto();
    if (view === 'locations' && $('#loc-auto') && $('#loc-auto').checked) startLocAuto();
    if (loaders[view]) loaders[view](opts);
  }
  function loadCurrent(force) {
    if (loaders[state.view]) loaders[state.view]({ force: !!force });
  }
  function onHashChange() {
    var match = (location.hash || '').match(/^#\/([a-z]+)/);
    var view = match && VIEW_META[match[1]] ? match[1] : 'overview';
    if (view !== state.view) setView(view);
  }

  /* =================================================================
     OVERVIEW
     ================================================================= */
  function loadOverview() {
    setSub('Loading server snapshot…');
    api('/overview').then(function (data) {
      state.overview = data;
      state.counts = data.counts || {};
      $('#nav-user-count').textContent = fmtNum(state.counts.active_users || 0);
      $('#nav-team-count').textContent = fmtNum(state.counts.teams || 0);
      if (data.server && data.server.version) {
        $('#server-label').textContent = 'Mattermost v' + data.server.version;
      }
      renderOverview(data);
      if (state.view === 'overview') setSub('Updated ' + fmtTime(data.fetched_at) + ' · ' + (data.server.site_name || 'Mattermost server'));
    }).catch(function (err) {
      if (state.view === 'overview') setSub('Unable to load overview');
      toast(err.message, 'error', 'Overview');
    });
  }

  function statCard(opts) {
    return '<div class="stat ' + (opts.tone || '') + '"><div class="stat-icon">' + icon(opts.icon, 19) + '</div>' +
      '<div class="stat-value">' + h(opts.value) + '</div><div class="stat-label">' + h(opts.label) + '</div>' +
      (opts.sub ? '<div class="stat-sub">' + opts.sub + '</div>' : '') + '</div>';
  }

  function renderOverview(data) {
    var c = data.counts || {};
    $('#ov-stats').innerHTML = [
      statCard({ icon: 'users', value: fmtNum(c.active_users), label: 'Active users', sub: h(fmtNum(c.inactive_users)) + ' deactivated · ' + h(fmtNum(c.admins)) + ' admins' }),
      statCard({ icon: 'teams', value: fmtNum(c.teams), label: 'Teams', sub: h(fmtNum(c.total_users)) + ' total accounts', tone: 'purple' }),
      statCard({ icon: 'pulse', value: fmtNum(c.online), label: 'Online right now', sub: 'status polled from Mattermost', tone: 'green' }),
      statCard({ icon: 'pin', value: fmtNum(data.tracked_users), label: 'Tracked users', sub: h(fmtNum(data.pings_24h)) + ' location pings in 24 h', tone: 'amber' })
    ].join('');

    var online = data.online_users || [];
    $('#ov-online-count').textContent = fmtNum(data.online_total);
    if (!online.length) {
      $('#ov-online').innerHTML = emptyState('Nobody is online right now', 'pulse', 'Status is checked every ' + (BOOT.poll_seconds || 60) + ' seconds.');
    } else {
      $('#ov-online').innerHTML = '<div class="list">' + online.map(function (u) {
        return '<div class="list-row">' + avatarHtml(u, 'sm', true) +
          '<div class="grow"><div class="name">' + h(userLabel(u)) + (u.is_admin ? ' <span class="pill pill-admin" style="font-size:9.5px">ADMIN</span>' : '') + '</div>' +
          '<div class="sub">@' + h(u.username) + '</div></div>' +
          '<div class="end">' + statusPill(u.status) + '<button class="icon-btn" style="width:28px;height:28px" data-action="user-chat" data-id="' + h(u.id) + '" title="Read chats">' + icon('chat', 14) + '</button></div></div>';
      }).join('') + '</div>';
      if (data.online_total > online.length) {
        $('#ov-online').innerHTML += '<div class="tiny muted" style="padding-top:8px">+ ' + (data.online_total - online.length) + ' more online — <button class="link-btn" data-goto="presence">open presence</button></div>';
      }
    }

    var locs = data.latest_locations || [];
    if (!locs.length) {
      $('#ov-locations').innerHTML = emptyState('No location history yet', 'pin', 'Set up the location agent or import login IPs.');
    } else {
      $('#ov-locations').innerHTML = '<div class="list">' + locs.map(function (l) {
        var u = userById(l.user_id) || { username: l.username };
        return '<div class="list-row">' + avatarHtml(u, 'sm', false) +
          '<div class="grow"><div class="name">' + h(l.username || userLabel(u) || 'Unknown') + '</div>' +
          '<div class="sub">' + locationText(l) + ' · ' + h(fmtRel(l.ts)) + '</div></div>' +
          '<div class="end">' + sourcePill(l.source) + '</div></div>';
      }).join('') + '</div>';
    }

    $('#ov-audit').innerHTML = (data.audit || []).length ? '<div class="list">' + data.audit.map(function (a) {
      return '<div class="list-row">' +
        '<div class="avatar sm" style="background:' + gradient(a.action) + ';font-size:0">' + icon(actionIcon(a.action), 14) + '</div>' +
        '<div class="grow"><div class="name">' + h(actionLabel(a.action)) + (a.target ? ' <span class="muted small">· ' + h(a.target) + '</span>' : '') + '</div>' +
        '<div class="sub">' + h(a.actor || 'system') + ' · ' + h(fmtRel(a.ts)) + '</div></div></div>';
    }).join('') + '</div>' : emptyState('No admin actions yet', 'clock');

    var mode = data.chat_mode;
    $('#ov-mode-note').innerHTML = mode === 'db'
      ? icon('check') + '<div><strong>Chat reading is fully enabled.</strong> Conversations are read directly from a read-only Mattermost database connection.</div>'
      : icon('alert') + '<div><strong>Chat reading is limited.</strong> The REST API does not let System Admins read other users\' DMs. Configure <code>DATABASE_URL</code> in <code>.env</code> for full visibility. <button class="link-btn" data-goto="settings">Settings</button></div>';
    $('#ov-mode-note').className = 'callout' + (mode === 'db' ? '' : ' warn');
    loadSystemHealth();
  }

  function loadSystemHealth() {
    var box = $('#ov-health');
    if (!box) return;
    api('/system/info').then(function (info) {
      var rows = [
        ['Mattermost API', info.mm_ping === null ? '<span class="pill pill-red">unreachable</span>'
          : '<span class="pill pill-live"><span class="dot"></span>' + info.mm_ping + ' ms</span>'],
        ['Mattermost database', !info.db ? '<span class="pill pill-gray">not configured</span>'
          : (info.db < 0 ? '<span class="pill pill-red">unreachable</span>'
            : '<span class="pill pill-live"><span class="dot"></span>' + info.db + ' ms</span>')],
        ['mmctl (permanent deletes)', info.mmctl ? '<span class="pill pill-live"><span class="dot"></span>available</span>'
          : '<span class="pill pill-gray">not installed</span>']
      ];
      box.innerHTML = '<div class="section-title" style="margin-top:18px">Server health</div><dl class="kv">' +
        rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + r[1] + '</dd>'; }).join('') + '</dl>';
    }).catch(function () { box.innerHTML = ''; });
  }

  /* =================================================================
     USERS
     ================================================================= */
  function loadUsers(force) {
    if (state.view === 'users') setSub('Loading users and teams…');
    var params = force ? { refresh: 1 } : {};
    return api('/users', { params: params }).then(function (data) {
      state.users = data.users || [];
      state.teams = data.teams || [];
      state.counts = data.counts || {};
      state.usersLoaded = true;
      $('#nav-user-count').textContent = fmtNum(state.counts.active_users || 0);
      $('#nav-team-count').textContent = fmtNum(state.counts.teams || 0);
      renderUsersTable();
      if (state.view === 'teams') renderTeamsGrid();
      if (state.view === 'users') {
        setSub(fmtNum(state.counts.active_users || 0) + ' active users · ' + fmtNum(state.counts.teams || 0) + ' teams · ' + fmtNum(state.counts.online || 0) + ' online');
      }
      return data;
    }).catch(function (err) {
      if (state.view === 'users') {
        setSub('Unable to load users');
        $('#users-table tbody').innerHTML = '<tr><td colspan="7">' + emptyState('Could not load users', 'alert', err.message) + '</td></tr>';
      }
      toast(err.message, 'error', 'Users');
      throw err;
    });
  }

  function renderUsersTable() {
    var tb = $('#users-table tbody');
    if (!tb) return;
    if (!state.usersLoaded) return;
    var q = ($('#user-search').value || '').trim().toLowerCase();
    var sf = $('#user-status-filter').value;
    var showInactive = $('#user-show-inactive').checked;
    var rows = state.users.filter(function (u) { return showInactive || u.active; });
    if (q) {
      rows = rows.filter(function (u) {
        var teamNames = (u.team_ids || []).map(function (id) { var t = teamById(id); return t ? t.display_name + ' ' + t.name : ''; }).join(' ');
        var hay = [u.username, u.email, u.first_name, u.last_name, u.nickname, teamNames].join(' ').toLowerCase();
        return hay.indexOf(q) >= 0;
      });
    }
    if (sf !== 'all') {
      rows = rows.filter(function (u) {
        if (sf === 'connected') return ['online', 'away', 'dnd'].indexOf(u.status) >= 0;
        return u.status === sf;
      });
    }
    var shown = rows.slice(0, MAX_USER_ROWS);
    tb.innerHTML = shown.length ? shown.map(userRowHtml).join('') : '<tr><td colspan="7">' + emptyState('No users match your filters', 'users', 'Try clearing the search or status filter.') + '</td></tr>';
    $('#users-sub').textContent = 'Showing ' + fmtNum(shown.length) + ' of ' + fmtNum(state.users.length) + ' users · ' +
      fmtNum(state.counts.active_users || 0) + ' active · ' + fmtNum(state.counts.inactive_users || 0) + ' deactivated' +
      (state.users.length > MAX_USER_ROWS ? ' · use search to narrow down' : '');
  }

  function userRowHtml(u) {
    var lastSeen = u.active && u.status !== 'offline' ? '<span style="color:var(--success)">Online now</span>'
      : u.last_seen ? '<span title="' + h(fmtDateTime(u.last_seen)) + '">' + h(fmtRel(u.last_seen)) + '</span>'
      : '<span class="muted">—</span>';
    var loc = u.location ? locationText(u.location) : '<span class="muted">—</span>';
    var admin = u.is_admin ? ' <span class="pill pill-admin" style="font-size:9.5px">ADMIN</span>' : '';
    var guest = u.is_guest ? ' <span class="pill pill-violet" style="font-size:9.5px">GUEST</span>' : '';
    var deact = !u.active ? ' <span class="pill pill-red" style="font-size:9.5px">DEACTIVATED</span>' : '';
    var actions = '<button class="icon-btn" style="width:28px;height:28px" data-action="user-chat" data-id="' + h(u.id) + '" title="Read chats">' + icon('chat', 14) + '</button>' +
      '<button class="icon-btn" style="width:28px;height:28px" data-action="manage-teams" data-id="' + h(u.id) + '" title="Manage teams">' + icon('teams', 14) + '</button>' +
      '<button class="icon-btn" style="width:28px;height:28px" data-action="user-password" data-id="' + h(u.id) + '" title="Reset password">' + icon('key', 14) + '</button>' +
      '<button class="icon-btn" style="width:28px;height:28px" data-action="user-toggle" data-id="' + h(u.id) + '" title="' + (u.active ? 'Deactivate' : 'Activate') + '">' + icon('power', 14) + '</button>' +
      '<button class="icon-btn" style="width:28px;height:28px" data-action="user-delete" data-id="' + h(u.id) + '" title="Delete user">' + icon('trash', 14) + '</button>';
    return '<tr class="clickable' + (u.active ? '' : ' row-dim') + '" data-action="user-detail" data-id="' + h(u.id) + '">' +
      '<td><div class="cell-user">' + avatarHtml(u, 'sm', true) + '<div><div class="cell-main">' + h(userLabel(u)) + admin + guest + deact + '</div>' +
      '<div class="cell-sub">@' + h(u.username) + '</div></div></div></td>' +
      '<td class="hide-sm"><span class="small">' + h(u.email || '—') + '</span></td>' +
      '<td>' + teamChips(u.team_ids) + '</td>' +
      '<td>' + statusPill(u.status, true) + '</td>' +
      '<td class="hide-sm">' + lastSeen + '</td>' +
      '<td class="hide-sm">' + loc + '</td>' +
      '<td><div class="actions">' + actions + '</div></td>' +
      '</tr>';
  }

  function exportUsers() {
    if (!state.users.length) { toast('No users loaded yet.', 'error'); return; }
    var rows = [['username', 'email', 'first_name', 'last_name', 'roles', 'active', 'teams', 'status', 'last_seen', 'last_location']];
    state.users.forEach(function (u) {
      var teams = (u.team_ids || []).map(function (id) { var t = teamById(id); return t ? t.display_name : ''; }).filter(Boolean).join('; ');
      var loc = u.location ? [u.location.city, u.location.country].filter(Boolean).join(', ') : '';
      rows.push([u.username, u.email, u.first_name, u.last_name, u.roles, u.active ? 'yes' : 'no', teams, u.status,
        u.last_seen ? fmtDateTime(u.last_seen) : '', loc]);
    });
    downloadCsv('mattermost-users-' + new Date().toISOString().slice(0, 10) + '.csv', rows);
  }
  function downloadCsv(filename, rows) {
    var csv = rows.map(function (r) {
      return r.map(function (cell) {
        var s = cell === null || cell === undefined ? '' : String(cell);
        return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      }).join(',');
    }).join('\r\n');
    var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  /* =================================================================
     TEAMS
     ================================================================= */
  function loadTeams() {
    setSub('Loading teams…');
    return api('/users').then(function (data) {
      state.users = data.users || [];
      state.teams = data.teams || [];
      state.counts = data.counts || {};
      state.usersLoaded = true;
      $('#nav-user-count').textContent = fmtNum(state.counts.active_users || 0);
      $('#nav-team-count').textContent = fmtNum(state.counts.teams || 0);
      renderUsersTable();
      renderTeamsGrid();
      if (state.view === 'teams') setSub(fmtNum(state.teams.length) + ' teams · ' + fmtNum(state.counts.active_users || 0) + ' active users');
    }).catch(function (err) {
      setSub('Unable to load teams');
      $('#teams-grid').innerHTML = emptyState('Could not load teams', 'alert', err.message);
      toast(err.message, 'error', 'Teams');
    });
  }

  function renderTeamsGrid() {
    var grid = $('#teams-grid');
    if (!grid) return;
    var teams = state.teams.slice().sort(function (a, b) {
      return (a.display_name || a.name || '').localeCompare(b.display_name || b.name || '');
    });
    if (!teams.length) {
      grid.innerHTML = emptyState('No teams yet', 'teams', 'Create your first team to get started.');
      return;
    }
    grid.innerHTML = teams.map(function (t) {
      var memberIds = (t.member_ids || []).slice();
      var members = memberIds.map(userById).filter(Boolean);
      var avatars = members.slice(0, 6).map(function (u) { return avatarHtml(u, 'sm', true); }).join('');
      var extra = memberIds.length > 6 ? '<span class="more">+' + (memberIds.length - 6) + '</span>' : '';
      var typePill = t.type === 'I' ? '<span class="pill pill-amber">Invite only</span>' : '<span class="pill pill-blue">Open</span>';
      var label = t.display_name || t.name;
      return '<div class="team-card">' +
        '<div class="team-head"><div class="team-logo" style="background:' + gradient(label) + '">' + h(initials(label)) + '</div>' +
        '<div style="min-width:0"><div class="team-name">' + h(label) + '</div><div class="team-handle">@' + h(t.name) + '</div></div></div>' +
        '<div class="team-meta">' + typePill + '<span class="pill pill-gray">' + icon('users', 11) + ' ' + fmtNum(memberIds.length) + ' members</span></div>' +
        '<div class="team-members">' + (avatars || '<span class="tiny muted">No members</span>') + extra + '</div>' +
        '<div class="team-actions">' +
        '<button class="btn btn-sm" data-action="team-members" data-id="' + h(t.id) + '">' + icon('users', 13) + ' Manage members</button>' +
        '<button class="btn btn-sm btn-danger" data-action="team-delete" data-id="' + h(t.id) + '" title="Delete team">' + icon('trash', 13) + '</button>' +
        '</div></div>';
    }).join('');
  }

  /* =================================================================
     CHATS
     ================================================================= */
  function loadChats(opts) {
    opts = opts || {};
    setSub('Direct-message viewer');
    var prep = state.usersLoaded ? Promise.resolve() : api('/users').then(function (data) {
      state.users = data.users || [];
      state.teams = data.teams || [];
      state.usersLoaded = true;
      renderUsersTable();
    }).catch(function () {});
    return prep.then(function () {
      renderChatUserList();
      if (opts.userId) {
        selectChatUser(opts.userId);
      } else if (state.chat.userId) {
        selectChatUser(state.chat.userId, true);
      } else {
        $('#chat-partner-list').innerHTML = '<div class="empty sm">Select a user to see who they talked to.</div>';
      }
    });
  }

  function renderChatUserList() {
    var list = $('#chat-user-list');
    var q = ($('#chat-user-search').value || '').trim().toLowerCase();
    var users = state.users.slice().sort(function (a, b) {
      if (a.active !== b.active) return a.active ? -1 : 1;
      return userLabel(a).toLowerCase().localeCompare(userLabel(b).toLowerCase());
    });
    if (q) {
      users = users.filter(function (u) {
        return ([u.username, u.email, u.first_name, u.last_name, u.nickname].join(' ')).toLowerCase().indexOf(q) >= 0;
      });
    }
    users = users.slice(0, 300);
    if (!users.length) {
      list.innerHTML = '<div class="empty sm">No users found</div>';
      return;
    }
    list.innerHTML = users.map(function (u) {
      var active = state.chat.userId === u.id ? ' active' : '';
      return '<div class="chat-user' + active + '" data-action="chat-user" data-id="' + h(u.id) + '">' +
        avatarHtml(u, 'sm', true) +
        '<div class="grow"><div class="name">' + h(userLabel(u)) + (u.is_admin ? ' <span class="pill pill-admin" style="font-size:8.5px">ADMIN</span>' : '') + '</div>' +
        '<div class="sub">@' + h(u.username) + (u.active ? '' : ' · deactivated') + '</div></div>' +
        '<div class="end">' + (u.active ? '<span class="status ' + statusOf(u) + '"><span class="dot"></span></span>' : '<span class="tiny muted">inactive</span>') + '</div></div>';
    }).join('');
  }

  function setChatBanner(html, tone) {
    var el = $('#chat-banner');
    if (!html) { el.innerHTML = ''; return; }
    el.innerHTML = '<div class="callout ' + (tone || '') + '" style="margin:0">' + icon(tone === 'warn' ? 'alert' : 'info') + '<div>' + html + '</div></div>';
  }

  function selectChatUser(userId, silent) {
    var u = userById(userId);
    if (!u) {
      if (!silent) toast('User not found in the loaded list.', 'error');
      return;
    }
    state.chat.userId = userId;
    state.chat.user = u;
    state.chat.partnerId = null;
    state.chat.channelId = null;
    state.chat.messages = [];
    state.chat.participants = {};
    state.chat.page = 0;
    renderChatUserList();
    $('#chat-partner-list').innerHTML = '<div class="loading small muted" style="padding:18px">Loading conversations…</div>';
    $('#chat-partners-title').textContent = 'Conversations of @' + u.username;
    $('#chat-convo-title').textContent = 'Conversations with ' + userLabel(u);
    $('#chat-convo-sub').textContent = 'Pick one of the conversations on the left.';
    setAvatarEl($('#chat-convo-avatar'), u, true);
    setChatBanner('');
    $('#chat-messages').innerHTML = '<div class="chat-empty">' + icon('chat', 38) + '<strong>Choose a conversation</strong><span>' + h(userLabel(u)) + ' has talked to the people listed on the left. Select one to read the full history.</span></div>';
    $('#chat-foot').classList.add('hidden');
    setSub('Loading conversations of @' + u.username + '…');

    api('/chat/partners/' + encodeURIComponent(userId)).then(function (data) {
      state.chat.mode = data.mode;
      var partners = data.partners || [];
      if (data.warning) {
        setChatBanner(h(data.warning) + ' <button class="link-btn" data-goto="settings">Configure database access</button>', 'warn');
      } else if (data.mode === 'api') {
        setChatBanner('Chats are read through the Mattermost REST API. Mattermost normally blocks System Admins from reading other users\' direct messages — if conversations fail to load, switch to a database connection. <button class="link-btn" data-goto="settings">Settings</button>', 'warn');
      }
      if (!partners.length) {
        $('#chat-partner-list').innerHTML = '<div class="empty sm">No direct conversations found' + (data.mode === 'api' ? ' <br><span class="tiny">Mattermost may be blocking read access.</span>' : '') + '</div>';
      } else {
        $('#chat-partner-list').innerHTML = partners.map(function (p) {
          var partner = p.partner || {};
          var active = state.chat.partnerId === partner.id ? ' active' : '';
          var preview = p.preview ? h(p.preview) : (p.deleted_count ? 'All messages deleted' : 'No messages');
          if (p.preview && p.preview_deleted) preview = '<span class="del-preview">' + preview + '</span>';
          var delBadge = p.deleted_count
            ? '<span class="pill pill-del" title="' + p.deleted_count + ' deleted message(s) still in the database">' + p.deleted_count + ' del</span>'
            : '';
          return '<div class="chat-user' + active + '" data-action="chat-partner" data-partner="' + h(partner.id) + '" data-channel="' + h(p.channel_id) + '">' +
            avatarHtml(partner, 'sm', true) +
            '<div class="grow"><div class="name">' + h(partner.name || partner.username) + ' ' + delBadge + '</div>' +
            '<div class="sub">' + preview + '</div></div>' +
            '<div class="end"><span class="time">' + (p.last_post_at ? h(fmtRel(p.last_post_at)) : '') + '</span></div></div>';
        }).join('');
      }
      $('#chat-partners-title').textContent = 'Conversations of @' + u.username + ' (' + partners.length + ')';
      setSub('@' + u.username + ' · ' + partners.length + ' conversation' + (partners.length === 1 ? '' : 's') + (data.mode === 'db' ? ' · database mode' : ' · API mode'));
    }).catch(function (err) {
      $('#chat-partner-list').innerHTML = '<div class="empty sm">' + h(err.message) + '</div>';
      setChatBanner(h(err.message), 'warn');
      toast(err.message, 'error', 'Conversations');
    });
  }

  function openChat(partnerId, channelId) {
    var partner = userById(partnerId) || { id: partnerId, username: partnerId };
    var primary = state.chat.user;
    state.chat.partnerId = partnerId;
    state.chat.partner = partner;
    state.chat.channelId = channelId;
    state.chat.messages = [];
    state.chat.page = 0;
    state.chat.participants = {};
    $$('#chat-partner-list .chat-user').forEach(function (el) {
      el.classList.toggle('active', el.dataset.channel === channelId);
    });
    $('#chat-convo-title').textContent = userLabel(partner);
    $('#chat-convo-sub').textContent = '@' + (primary ? primary.username : '') + ' ↔ @' + (partner.username || '');
    setAvatarEl($('#chat-convo-avatar'), partner, true);
    setChatBanner('');
    $('#chat-messages').innerHTML = '<div class="chat-empty"><div class="spinner"></div><span style="margin-top:10px">Loading messages…</span></div>';
    $('#chat-foot').classList.add('hidden');
    fetchChatPage(0, false).then(function () {
      var deleted = state.chat.messages.filter(function (m) { return m.deleted; }).length;
      var line = '@' + (primary ? primary.username : '') + ' ↔ @' + partner.username +
        ' · ' + state.chat.messages.length + ' messages' +
        (deleted ? ' · ' + deleted + ' deleted' : '');
      $('#chat-convo-sub').textContent = line;
      setSub(line);
    });
  }

  function fetchChatPage(page, prepend) {
    var channelId = state.chat.channelId;
    var prevHeight = $('#chat-messages').scrollHeight;
    var prevTop = $('#chat-messages').scrollTop;
    return api('/chat/' + encodeURIComponent(channelId) + '/posts', { params: { page: page, per_page: 60 } }).then(function (data) {
      var incoming = data.posts || [];
      var existing = {};
      state.chat.messages.forEach(function (m) { existing[m.id] = true; });
      incoming = incoming.filter(function (m) { return !existing[m.id]; });
      state.chat.messages = prepend ? incoming.concat(state.chat.messages) : state.chat.messages.concat(incoming);
      state.chat.messages.sort(function (a, b) { return num(a.create_at) - num(b.create_at); });
      state.chat.participants = Object.assign({}, state.chat.participants, data.participants || {});
      state.chat.hasMore = !!data.has_more;
      state.chat.page = page;
      if (data.warning) setChatBanner(h(data.warning) + ' <button class="link-btn" data-goto="settings">Settings</button>', 'warn');
      renderMessages();
      var box = $('#chat-messages');
      if (prepend) {
        box.scrollTop = box.scrollHeight - prevHeight + prevTop;
      } else {
        box.scrollTop = box.scrollHeight;
      }
      $('#chat-foot').classList.toggle('hidden', !state.chat.hasMore);
    }).catch(function (err) {
      $('#chat-messages').innerHTML = '<div class="chat-empty">' + icon('alert', 34) + '<strong>Could not load messages</strong><span>' + h(err.message) + '</span>' +
        (err.status === 403 ? '<span class="tiny muted" style="margin-top:8px">Mattermost blocks System Admins from reading other users\' DMs over the API. Add DATABASE_URL in .env to read chats from the database.</span>' : '') + '</div>';
      if (err.status === 403 || (err.data && /database/i.test(err.message))) {
        setChatBanner(h(err.message) + ' <button class="link-btn" data-goto="settings">Settings</button>', 'warn');
      }
      toast(err.message, 'error', 'Chat');
    });
  }

  function participantName(uid) {
    var p = state.chat.participants[uid];
    if (p) return p.name || p.username || uid;
    var u = userById(uid);
    return u ? userLabel(u) : uid;
  }
  function participantUsername(uid) {
    var p = state.chat.participants[uid];
    if (p && p.username) return p.username;
    var u = userById(uid);
    return u ? u.username : '';
  }

  function fmtBytes(n) {
    n = num(n);
    if (!n) return '';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(0) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  }

  function fileLabel(f) {
    var ext = (f.ext || '').toUpperCase();
    return ext ? ext.slice(0, 5) : 'FILE';
  }

  function renderAttachments(files) {
    if (!files || !files.length) return '';
    var out = '<div class="attachments">';
    files.forEach(function (f) {
      var url = '/api/files/' + encodeURIComponent(f.id);
      var name = h(f.name || 'attachment');
      var size = f.size ? ' · ' + h(fmtBytes(f.size)) : '';
      if (f.is_image) {
        out += '<a class="attach-img" href="' + url + '" target="_blank" rel="noopener" title="' + name + '">' +
          '<img src="' + url + '" alt="' + name + '" loading="lazy">' +
          '<span class="attach-cap">' + name + size + '</span></a>';
      } else {
        out += '<a class="attach-file" href="' + url + '" target="_blank" rel="noopener" download>' +
          '<span class="attach-ext">' + h(fileLabel(f)) + '</span>' +
          '<span class="grow"><span class="attach-name">' + name + '</span>' +
          '<span class="attach-size">' + h(size.replace(' · ', '')) + '</span></span>' +
          icon('download', 13) + '</a>';
      }
    });
    return out + '</div>';
  }

  function renderMessages() {
    var box = $('#chat-messages');
    var msgs = state.chat.messages;
    if (!msgs.length) {
      box.innerHTML = '<div class="chat-empty">' + icon('chat', 36) + '<strong>No messages</strong><span>There are no messages in this conversation.</span></div>';
      return;
    }
    var primaryId = state.chat.userId;
    var html = '';
    var lastDay = '';
    var showDeleted = state.chat.showDeleted !== false;
    var hiddenDeleted = 0;
    msgs.forEach(function (m) {
      if (!m.message && !m.deleted && !(m.files && m.files.length)) return;
      if (m.deleted && !showDeleted) { hiddenDeleted++; return; }
      var day = fmtDayKey(m.create_at);
      if (day && day !== lastDay) {
        html += '<div class="chat-date">' + h(fmtDayLabel(m.create_at)) + '</div>';
        lastDay = day;
      }
      if (m.is_system && !m.deleted) {
        if (!m.message) return;
        html += '<div class="msg system"><div class="msg-bubble">' + h(m.message) + '</div></div>';
        return;
      }
      var mine = m.user_id === primaryId;
      var name = participantName(m.user_id);
      var uname = participantUsername(m.user_id);
      var meta = '<span>' + h(name) + '</span><span>@' + h(uname || '?') + '</span><span>' + h(fmtTime(m.create_at)) + '</span>';
      var body, extraClass = '';
      if (m.deleted) {
        // Deleted messages keep living in the Mattermost database: show the text
        // when the server retained it, and always show when it was deleted.
        var hasText = !!(m.message && m.message.trim());
        body = hasText ? h(m.message) : '<span class="gone">Text no longer stored by Mattermost</span>';
        extraClass = hasText ? ' deleted-text' : ' gone';
        meta += '<span class="deleted-tag">deleted</span>' +
          (m.delete_at ? '<span class="deleted-when">' + h(fmtDateTime(m.delete_at)) + '</span>' : '') +
          (m.from_props ? '<span class="deleted-when">plugin text</span>' : '');
      } else {
        body = h(m.message);
      }
      var attach = renderAttachments(m.files);
      var bubble = (body || (!m.deleted && !attach) ? '<div class="msg-bubble' + extraClass + '">' + body + '</div>' : '');
      html += '<div class="msg' + (mine ? ' mine' : '') + (m.deleted ? ' deleted' : '') + (m.is_system ? ' system-row' : '') + '">' +
        avatarHtml({ username: uname || '?', name: name }, '', false) +
        '<div class="msg-body"><div class="msg-meta">' + meta + '</div>' + bubble + attach + '</div></div>';
    });
    if (hiddenDeleted) {
      html = '<div class="chat-hidden-note">' + hiddenDeleted + ' deleted message' +
        (hiddenDeleted === 1 ? '' : 's') + ' hidden — switch “Deleted” on to show ' +
        (hiddenDeleted === 1 ? 'it' : 'them') + '.</div>' + html;
    }
    box.innerHTML = html || '<div class="chat-empty">' + icon('chat', 36) + '<strong>No messages</strong></div>';
  }

  /* =================================================================
     PRESENCE
     ================================================================= */
  function loadPresence(opts) {
    opts = opts || {};
    setSub('Loading presence history…');
    state.presence.selected = null;
    $('#presence-detail').innerHTML = '';
    return api('/presence', { params: { hours: state.presence.hours } }).then(function (data) {
      state.presence.rows = data.users || [];
      state.presence.now = data.now;
      state.presence.trackingSince = data.tracking_since;
      renderPresenceTable();
      if (state.view === 'presence') {
        setSub('Last ' + hoursLabel(state.presence.hours) + ' · tracking since ' + fmtDate(data.tracking_since) + ' · ' + state.presence.rows.length + ' active users');
      }
    }).catch(function (err) {
      $('#presence-table tbody').innerHTML = '<tr><td colspan="5">' + emptyState('Could not load presence', 'alert', err.message) + '</td></tr>';
      setSub('Unable to load presence');
      toast(err.message, 'error', 'Presence');
    });
  }
  function hoursLabel(hours) { return hours === 24 ? '24 hours' : hours === 168 ? '7 days' : '30 days'; }

  function renderTimeline(intervals, start, end, large) {
    var span = Math.max(1, end - start);
    var html = '<div class="timeline' + (large ? ' timeline-lg' : '') + '">';
    (intervals || []).forEach(function (iv) {
      var s = Math.max(num(iv.start), start);
      var e = Math.min(num(iv.end), end);
      if (e <= s) return;
      var width = ((e - s) / span) * 100;
      var st = ['online', 'away', 'dnd'].indexOf(iv.status) >= 0 ? iv.status : 'offline';
      html += '<span class="' + st + '" style="width:' + width.toFixed(4) + '%" title="' + h((st === 'offline' ? 'Offline' : st === 'online' ? 'Online' : st === 'away' ? 'Away' : 'DND') + ' · ' + dur(iv.seconds) + ' · ' + fmtDateTime(iv.start) + ' → ' + fmtTime(iv.end)) + '"></span>';
    });
    return html + '</div>';
  }
  function timelineLegend() {
    return '<div class="timeline-legend"><span><i class="legend-online"></i>Online</span><span><i class="legend-away"></i>Away</span><span><i class="legend-dnd"></i>DND</span><span><i class="legend-offline"></i>Offline</span></div>';
  }

  function renderPresenceTable() {
    var tb = $('#presence-table tbody');
    var end = state.presence.now || Math.floor(Date.now() / 1000);
    var start = end - state.presence.hours * 3600;
    var rows = state.presence.rows;
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="5">' + emptyState('No presence history yet', 'pulse', 'Status history starts being collected when the dashboard runs with a valid admin session.') + '</td></tr>';
      return;
    }
    tb.innerHTML = rows.map(function (u) {
      var total = state.presence.hours * 3600;
      var share = pct(u.online_seconds, total);
      var lastSeen = u.status !== 'offline' ? '<span style="color:var(--success)">Now</span>' : (u.last_seen ? '<span title="' + h(fmtDateTime(u.last_seen)) + '">' + h(fmtRel(u.last_seen)) + '</span>' : '<span class="muted">—</span>');
      return '<tr class="clickable" data-action="presence-detail" data-id="' + h(u.id) + '">' +
        '<td><div class="cell-user">' + avatarHtml(u, 'sm', true) + '<div><div class="cell-main">' + h(userLabel(u)) + '</div><div class="cell-sub">@' + h(u.username) + '</div></div></div></td>' +
        '<td>' + statusPill(u.status, true) + '</td>' +
        '<td><div class="cell-main">' + dur(u.online_seconds) + '</div><div class="cell-sub">' + share + '% of period</div></td>' +
        '<td class="hide-sm">' + lastSeen + '</td>' +
        '<td style="min-width:180px">' + renderTimeline(u.intervals, start, end, false) + '</td></tr>';
    }).join('');
  }

  function renderPresenceDetail(userId) {
    var u = null;
    state.presence.rows.forEach(function (row) { if (row.id === userId) u = row; });
    if (!u) return;
    state.presence.selected = userId;
    var end = state.presence.now || Math.floor(Date.now() / 1000);
    var start = end - state.presence.hours * 3600;
    var intervals = (u.intervals || []).slice().reverse();
    var detail = '<div class="card" style="margin-top:16px">' +
      '<div class="card-head">' + avatarHtml(u, 'lg', true) +
      '<div style="min-width:0"><h2 style="font-size:16px">' + h(userLabel(u)) + ' <span class="muted small">@' + h(u.username) + '</span></h2>' +
      '<p class="muted small">' + statusPill(u.status, true) + ' · ' + dur(u.online_seconds) + ' online in the last ' + hoursLabel(state.presence.hours) + '</p></div>' +
      '<div class="spacer"></div><button class="icon-btn" data-action="presence-close" title="Close">' + icon('x') + '</button></div>' +
      '<div class="timeline-wrap">' + renderTimeline(u.intervals, start, end, true) +
      '<div class="timeline-scale"><span>' + h(fmtDateTime(start)) + '</span><span>' + h(fmtDateTime(end)) + '</span></div>' + timelineLegend() + '</div>' +
      '<div class="section-title" style="margin-top:20px">Status intervals</div>' +
      (intervals.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Status</th><th>From</th><th>To</th><th>Duration</th></tr></thead><tbody>' +
        intervals.map(function (iv) {
          return '<tr><td>' + statusPill(iv.status, true) + '</td><td class="small">' + h(fmtDateTime(iv.start)) + '</td><td class="small">' + h(fmtDateTime(iv.end)) + '</td><td class="small">' + dur(iv.seconds) + '</td></tr>';
        }).join('') + '</tbody></table></div>' : '<div class="empty sm">No recorded changes in this period.</div>') +
      '<div class="modal-actions"><button class="btn btn-sm" data-action="user-chat" data-id="' + h(u.id) + '">' + icon('chat', 13) + ' Read chats</button>' +
      '<button class="btn btn-sm" data-action="user-detail" data-id="' + h(u.id) + '">' + icon('user', 13) + ' User details</button></div>' +
      '</div>';
    $('#presence-detail').innerHTML = detail;
    $('#presence-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function refreshPresenceNow() {
    var btn = $('#presence-refresh');
    btn.disabled = true;
    api('/presence/refresh', { method: 'POST' }).then(function (data) {
      toast('Polled ' + data.users + ' users · ' + data.changes + ' status change' + (data.changes === 1 ? '' : 's'), 'success');
      return loadPresence();
    }).catch(function (err) {
      toast(err.message, 'error', 'Presence');
    }).then(function () { btn.disabled = false; });
  }

  /* =================================================================
     LOCATIONS
     ================================================================= */
  function loadLocations() {
    var tab = state.locations.tab;
    if (tab === 'live') return loadLocationsLive();
    if (tab === 'history') return loadLocationsHistory(true);
    return loadAgentPane();
  }

  function ensureUsersForFilters() {
    if (state.usersLoaded) { populateLocationUserFilter(); return Promise.resolve(); }
    return api('/users').then(function (data) {
      state.users = data.users || [];
      state.teams = data.teams || [];
      state.usersLoaded = true;
      renderUsersTable();
      populateLocationUserFilter();
    }).catch(function () {});
  }

  function populateLocationUserFilter() {
    var sel = $('#loc-user-filter');
    if (!sel) return;
    var current = sel.value;
    var users = state.users.slice().sort(function (a, b) { return userLabel(a).localeCompare(userLabel(b)); });
    sel.innerHTML = '<option value="">All users</option>' + users.map(function (u) {
      return '<option value="' + h(u.id) + '">' + h(userLabel(u)) + ' (@' + h(u.username) + ')</option>';
    }).join('');
    if (current) sel.value = current;
  }

  function loadLocationsLive() {
    setSub('Loading latest locations…');
    return ensureUsersForFilters().then(function () {
      return api('/locations/latest');
    }).then(function (data) {
      var rows = data.locations || [];
      var tb = $('#loc-live-table tbody');
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="7">' + emptyState('No locations recorded yet', 'pin', 'Install the location agent on user machines, or import login IPs from Mattermost.') + '</td></tr>';
      } else {
        tb.innerHTML = rows.map(function (l) {
          var u = userById(l.user_id) || { username: l.username || 'Unknown', status: l.user_status };
          var name = userLabel(u) || l.username || (l.user_id ? 'User ' + l.user_id.slice(0, 6) : 'Unknown');
          return '<tr>' +
            '<td><div class="cell-user">' + avatarHtml(u, 'sm', true) + '<div><div class="cell-main">' + h(name) + '</div><div class="cell-sub">@' + h(u.username || l.username || '—') + '</div></div></div></td>' +
            '<td>' + locationText(l) + '</td>' +
            '<td class="hide-sm"><span class="mono tiny">' + h(l.ip || '—') + '</span></td>' +
            '<td>' + osmLink(l.lat, l.lon) + '</td>' +
            '<td class="hide-sm">' + sourcePill(l.source) + '</td>' +
            '<td><span title="' + h(fmtDateTime(l.ts)) + '">' + h(fmtRel(l.ts)) + '</span></td>' +
            '<td class="right"><button class="btn btn-sm btn-ghost" data-action="loc-history" data-id="' + h(l.user_id || '') + '" data-username="' + h(l.username || '') + '">View</button></td></tr>';
        }).join('');
      }
      var tracked = rows.length;
      $('#loc-live-sub').textContent = tracked + ' users tracked · tracking since ' + fmtDate(data.tracking_since);
      setSub(tracked + ' users with a recorded location');
      var note = '<div><strong>How locations are collected:</strong> the optional agent on a user\'s computer reports the public IP (city-level geolocation), login IPs are imported from the Mattermost audit log, and dashboard logins are recorded automatically. ' +
        'IP geolocation is approximate. For precise device location, provide GPS coordinates to the agent. <button class="link-btn" data-ltab-target="agent">Set up the agent →</button></div>';
      $('#loc-mode-note').innerHTML = icon('info') + note;
    }).catch(function (err) {
      $('#loc-live-table tbody').innerHTML = '<tr><td colspan="7">' + emptyState('Could not load locations', 'alert', err.message) + '</td></tr>';
      setSub('Unable to load locations');
      toast(err.message, 'error', 'Locations');
    });
  }

  function loadLocationsHistory(reset) {
    setSub('Loading location history…');
    return ensureUsersForFilters().then(function () {
      var userId = $('#loc-user-filter').value;
      var source = $('#loc-source-filter').value;
      var limit = Number($('#loc-limit').value || 200);
      var selectedUser = userById(userId);
      if (reset) state.locations.offset = 0;
      var params = {
        limit: limit,
        offset: state.locations.offset,
        user_id: userId,
        username: selectedUser ? selectedUser.username : '',
        source: source
      };
      var exportHref = '/api/locations/export.csv?user_id=' + encodeURIComponent(userId) + '&username=' + encodeURIComponent(params.username);
      $('#loc-export-btn').setAttribute('href', exportHref);
      return api('/locations', { params: params }).then(function (data) {
        var rows = data.locations || [];
        var tb = $('#loc-history-table tbody');
        if (reset) tb.innerHTML = '';
        if (!rows.length && reset) {
          tb.innerHTML = '<tr><td colspan="7">' + emptyState('No location records', 'pin', 'Try a different user or source filter.') + '</td></tr>';
        } else {
          tb.insertAdjacentHTML('beforeend', rows.map(function (l) {
            var u = userById(l.user_id) || { username: l.username || 'Unknown' };
            var name = userLabel(u) || l.username || 'Unknown';
            return '<tr>' +
              '<td class="small nowrap" title="' + h(fmtDateTime(l.ts)) + '">' + h(fmtDate(l.ts)) + '<div class="cell-sub">' + h(fmtTime(l.ts)) + '</div></td>' +
              '<td><span class="cell-main">' + h(name) + '</span><div class="cell-sub">@' + h(u.username || l.username || '—') + '</div></td>' +
              '<td><span class="mono tiny">' + h(l.ip || '—') + '</span>' + (l.hostname ? '<div class="cell-sub">' + h(l.hostname) + '</div>' : '') + '</td>' +
              '<td>' + locationText(l) + '</td>' +
              '<td class="hide-sm"><span class="tiny muted">' + h(l.isp || '—') + '</span></td>' +
              '<td>' + osmLink(l.lat, l.lon) + '</td>' +
              '<td class="hide-sm">' + sourcePill(l.source) + '</td></tr>';
          }).join(''));
        }
        state.locations.offset += rows.length;
        state.locations.total = data.total || 0;
        $('#loc-history-sub').textContent = 'Showing ' + state.locations.offset + ' of ' + state.locations.total + ' records';
        $('#loc-load-more').classList.toggle('hidden', state.locations.offset >= state.locations.total);
        setSub(state.locations.total + ' location records');
      });
    }).catch(function (err) {
      toast(err.message, 'error', 'Locations');
      setSub('Unable to load location history');
    });
  }

  function syncAudits() {
    toast('Importing login IPs from Mattermost…', 'info');
    api('/locations/sync-audits', { method: 'POST' }).then(function (data) {
      if (data.message) {
        toast(data.message, 'error', 'Import finished');
      } else {
        toast('Scanned ' + data.scanned + ' login events · imported ' + data.inserted + ' new location' + (data.inserted === 1 ? '' : 's') + ' (' + (data.source || 'audit') + ').', 'success');
      }
      loadLocations();
    }).catch(function (err) {
      toast(err.message, 'error', 'Import failed');
    });
  }

  function startLocAuto() {
    stopLocAuto();
    state.locations.timer = setInterval(function () {
      if (state.view === 'locations' && state.locations.tab === 'live') loadLocationsLive();
    }, 30000);
  }
  function stopLocAuto() {
    if (state.locations.timer) { clearInterval(state.locations.timer); state.locations.timer = null; }
  }

  function agentSnippet(settings) {
    var origin = window.location.origin;
    var key = (settings && settings.location_api_key) || '';
    return '<pre class="code"><span class="cmt"># 1. On the user\'s computer (Python 3 required) — download the agent above.</span>\n' +
      '<span class="cmt"># 2. Run it once to test:</span>\n' +
      'python3 mm-location-agent.py --url "' + h(origin) + '" --key "' + h(key) + '" --username "THE_MATTERMOST_USERNAME"\n\n' +
      '<span class="cmt"># 3. Or configure defaults and run it as a service:</span>\n' +
      'export DASH_URL="' + h(origin) + '"\n' +
      'export API_KEY="' + h(key) + '"\n' +
      'export USERNAME="THE_MATTERMOST_USERNAME"\n' +
      'export INTERVAL=300   <span class="cmt"># seconds between pings (5 min)</span>\n' +
      'python3 mm-location-agent.py</pre>';
  }

  function loadAgentPane() {
    setSub('Location agent setup');
    $('#loc-agent-content').innerHTML = '<div class="empty sm">Loading agent configuration…</div>';
    return api('/settings').then(function (data) {
      state.settings = data.settings;
      var s = data.settings;
      var agentUrl = '/download/agent.py';
      $('#loc-agent-content').innerHTML =
        '<div class="settings-grid">' +
        '<div class="card"><div class="card-head"><h2>What the agent does</h2></div>' +
        '<p class="small muted" style="margin-bottom:12px">The agent is a tiny Python script that runs on a user\'s computer. Every few minutes it reports the machine\'s public IP to this dashboard, which turns it into an approximate city-level location.</p>' +
        '<ul class="small muted" style="margin:0 0 0 18px;line-height:1.9">' +
        '<li>Optional — the dashboard already records dashboard logins and can import Mattermost login IPs.</li>' +
        '<li>Runs quietly in the background; no admin rights required.</li>' +
        '<li>Uses <code>ipwho.is</code> to resolve the public IP to a city.</li>' +
        '<li>Never captures screens, keystrokes or message content.</li>' +
        '<li>Pings every 5 minutes by default; can also send GPS coordinates if you extend it.</li>' +
        '</ul></div>' +
        '<div class="card"><div class="card-head"><h2>Key &amp; download</h2></div>' +
        '<label class="field"><span>Dashboard URL</span><input readonly value="' + h(window.location.origin) + '"></label>' +
        '<label class="field"><span>Location API key</span><div class="copy-row"><input id="agent-key-input" type="password" readonly value="' + h(s.location_api_key) + '">' +
        '<button class="btn btn-sm btn-ghost" data-action="toggle-key" title="Show / hide">' + icon('eye', 14) + '</button>' +
        '<button class="btn btn-sm" data-action="copy" data-copy="' + h(s.location_api_key) + '">' + icon('copy', 14) + '</button></div>' +
        '<span class="hint">Treat this key like a password — anyone with it can submit location pings.</span></label>' +
        '<a class="btn btn-primary btn-block" href="' + agentUrl + '" download>' + icon('download') + ' Download agent script</a>' +
        '<p class="tiny muted" style="margin-top:10px">The download already contains your dashboard URL and API key as defaults. Append <code>?username=jdoe</code> to pre-fill the Mattermost username.</p>' +
        '</div></div>' +
        '<div class="card"><div class="card-head"><h2>Install &amp; run</h2></div>' + agentSnippet(s) +
        '<p class="tiny muted" style="margin-top:10px">On Windows, run it with <code>python mm-location-agent.py</code> and create a Task Scheduler entry with "At log on". On Linux/macOS use a systemd unit, cron <code>@reboot</code>, or a login item.</p></div>' +
        '<div class="card"><div class="card-head"><h2>Import login IPs from Mattermost</h2></div>' +
        '<p class="small muted" style="margin-bottom:12px">If Mattermost audit logging is enabled (or the server database is connected), you can import historical login IPs for every user — no agent needed. Each login is geolocated once.</p>' +
        '<div class="toolbar" style="margin:0"><button class="btn btn-sm btn-primary" data-action="sync-audits">' + icon('refresh', 13) + ' Import now</button>' +
        '<button class="btn btn-sm btn-ghost" data-action="loc-tab" data-tab="live">Back to latest locations</button></div>' +
        '<p class="tiny muted" style="margin-top:12px">Location data is stored locally in <code>' + h('data/admin.db') + '</code>. Nothing is sent anywhere except IP lookups to the geolocation provider.</p></div>';
      setSub('Agent URL ' + window.location.origin);
    }).catch(function (err) {
      $('#loc-agent-content').innerHTML = emptyState('Could not load agent settings', 'alert', err.message);
      toast(err.message, 'error', 'Settings');
    });
  }

  /* =================================================================
     AUDIT
     ================================================================= */
  function loadAudit() {
    setSub('Loading admin activity…');
    return api('/audit', { params: { limit: 200 } }).then(function (data) {
      var rows = data.entries || [];
      var tb = $('#audit-table tbody');
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="6">' + emptyState('No admin actions yet', 'clock') + '</td></tr>';
      } else {
        tb.innerHTML = rows.map(function (a) {
          return '<tr><td class="small nowrap" title="' + h(fmtDateTime(a.ts)) + '">' + h(fmtDate(a.ts)) + '<div class="cell-sub">' + h(fmtTime(a.ts)) + '</div></td>' +
            '<td><span class="cell-main">' + h(a.actor || '—') + '</span><div class="cell-sub">' + h(a.actor_id ? a.actor_id.slice(0, 8) : '') + '</div></td>' +
            '<td><span class="pill pill-blue">' + icon(actionIcon(a.action), 12) + ' ' + h(actionLabel(a.action)) + '</span></td>' +
            '<td class="small">' + h(a.target || '—') + '</td>' +
            '<td class="hide-sm">' + prettyDetails(a.details) + '</td>' +
            '<td class="hide-sm"><span class="mono tiny">' + h(a.ip || '—') + '</span></td></tr>';
        }).join('');
      }
      setSub(rows.length + ' recorded admin actions');
    }).catch(function (err) {
      setSub('Unable to load activity');
      toast(err.message, 'error', 'Activity');
    });
  }

  /* =================================================================
     SETTINGS
     ================================================================= */
  function loadSettings() {
    setSub('Loading settings…');
    return api('/settings').then(function (data) {
      state.settings = data.settings;
      renderSettings(data.settings);
      setSub('Dashboard v' + data.settings.app_version);
    }).catch(function (err) {
      $('#settings-content').innerHTML = emptyState('Could not load settings', 'alert', err.message);
      setSub('Unable to load settings');
      toast(err.message, 'error', 'Settings');
    });
  }

  function renderSettings(s) {
    var chat = s.chat || {};
    var chatState = chat.mode === 'db'
      ? (chat.db_ok ? '<span class="pill pill-live"><span class="dot"></span>Database connected</span>' : '<span class="pill pill-red">Database configured but unreachable</span>')
      : '<span class="pill pill-amber">REST API only (limited DM access)</span>';
    var html = '<div class="settings-grid">' +
      '<div class="card"><div class="card-head"><h2>Mattermost server</h2></div><dl class="kv">' +
      '<dt>API URL</dt><dd><code>' + h(s.mm_url) + '</code></dd>' +
      '<dt>Version</dt><dd>' + h((s.server && s.server.version) || 'unknown') + '</dd>' +
      '<dt>Site name</dt><dd>' + h((s.server && s.server.site_name) || '—') + '</dd>' +
      '<dt>Dashboard</dt><dd>v' + h(s.app_version) + ' · <code>python3 app.py</code></dd>' +
      '<dt>Timezone</dt><dd>' + h(s.timezone) + '</dd>' +
      '</dl></div>' +
      '<div class="card"><div class="card-head"><h2>Tracking &amp; storage</h2></div><dl class="kv">' +
      '<dt>Presence polling</dt><dd>every ' + h(s.poll_seconds) + ' seconds</dd>' +
      '<dt>Tracking since</dt><dd>' + h(fmtDateTime(s.tracking_since)) + '</dd>' +
      '<dt>Status changes</dt><dd>' + fmtNum(s.status_events) + ' events stored</dd>' +
      '<dt>Location pings</dt><dd>' + fmtNum(s.location_pings) + ' pings stored</dd>' +
      '<dt>IP geolocation</dt><dd>' + (s.geoip_enabled ? 'Enabled (ipwho.is)' : 'Disabled') + '</dd>' +
      '<dt>Agent key</dt><dd><code>' + h((s.location_api_key || '').slice(0, 6)) + '…</code> <button class="link-btn" data-goto="locations" data-ltab-target="agent">show</button></dd>' +
      '</dl></div>' +
      '<div class="card"><div class="card-head"><h2>Chat access</h2>' + chatState + '</div>' +
      '<p class="small muted" style="margin-bottom:10px">Mattermost does not allow a System Admin to read other users\' direct messages through its API. This dashboard can read conversations directly from a <strong>read-only database connection</strong> instead.</p>' +
      '<dl class="kv"><dt>Mode</dt><dd>' + (chat.mode === 'db' ? 'Direct database (full visibility)' : 'REST API (limited)') + '</dd>' +
      '<dt>Database</dt><dd><code>' + h(s.database_url_masked || 'not configured') + '</code></dd>' +
      (chat.error ? '<dt>Error</dt><dd style="color:#ff9d9d">' + h(chat.error) + '</dd>' : '') + '</dl>' +
      '<div class="section-title">Enable full chat visibility</div>' +
      '<pre class="code">' + h('# Add to .env, then restart the dashboard:\nDATABASE_URL=postgresql://mattermost:PASSWORD@127.0.0.1:5432/mattermost\n# or: DATABASE_URL=mysql://mattermost:PASSWORD@127.0.0.1:3306/mattermost') + '</pre>' +
      '<p class="tiny muted" style="margin-top:10px">The connection is opened read-only. Use a dedicated DB user with SELECT-only rights where possible. Reading private conversations should be covered by your organisation\'s policy — inform your users.</p>' +
      '<div class="callout" style="margin-top:12px">' + icon('info') + '<div><strong>Deleted messages</strong> stay in the <code>posts</code> table with <code>DeleteAt &gt; 0</code>, and Mattermost usually keeps the original text. In database mode this dashboard shows them with a <em>deleted</em> badge and their deletion time; use the <strong>Deleted</strong> switch above a conversation to hide them. The REST API cannot provide this — a database connection is required.</div></div>' +
      '</div>' +
      '<div class="card"><div class="card-head"><h2>File storage</h2>' +
      (s.media_dir ? '<span class="pill pill-live"><span class="dot"></span>Attachments readable</span>'
                   : '<span class="pill pill-amber">Data directory not found</span>') + '</div>' +
      '<p class="small muted" style="margin-bottom:10px">Images and files sent in chats are read directly from the Mattermost data directory, so they can be shown even inside other users\' conversations.</p>' +
      '<dl class="kv"><dt>Directory</dt><dd><code>' + h(s.media_dir || 'not configured') + '</code></dd></dl>' +
      (s.media_dir ? '' : '<pre class="code">' + h('# add to .env, then restart:\nMM_DATA_DIR=/opt/mattermost/data') + '</pre>' +
        '<p class="tiny muted" style="margin-top:8px">The service user must be able to read it: <code>sudo usermod -aG mattermost mm-admin</code></p>') +
      '</div>' +
      '<div class="card"><div class="card-head"><h2>Location agent</h2></div>' +
      '<p class="small muted" style="margin-bottom:12px">Optional agent for city-level tracking of user machines (public IP based). Download the script with your key pre-filled.</p>' +
      '<a class="btn btn-sm btn-primary" href="/download/agent.py" download>' + icon('download', 13) + ' Download agent</a> ' +
      '<button class="btn btn-sm btn-ghost" data-goto="locations">Agent setup guide</button></div>' +
      '<div class="card"><div class="card-head"><h2>Security</h2></div><dl class="kv">' +
      '<dt>Login</dt><dd>Mattermost System Admin credentials only (MFA aware)</dd>' +
      '<dt>Sessions</dt><dd>12 hours · HTTP-only cookie · CSRF protected</dd>' +
      '<dt>Stored data</dt><dd>Presence events, location pings, dashboard audit log (local SQLite)</dd>' +
      '<dt>Server password</dt><dd>Never stored</dd>' +
      '</dl>' +
      '<div class="callout warn" style="margin-top:14px">' + icon('alert') + '<div>This dashboard grants powerful visibility into your users. Restrict access to the LXC, keep the port on a trusted network or behind a VPN/reverse proxy, and review who holds the System Admin role.</div></div>' +
      '</div></div>';
    $('#settings-content').innerHTML = html;
  }

  /* =================================================================
     MODALS / ACTIONS
     ================================================================= */
  function openAddUser(prefill) {
    prefill = prefill || {};
    var teams = state.teams.slice().sort(function (a, b) { return (a.display_name || '').localeCompare(b.display_name || ''); });
    var teamOptions = teams.map(function (t) { return '<option value="' + h(t.name) + '">' + h(t.display_name || t.name) + '</option>'; }).join('');
    var body = '<form id="add-user-form" novalidate>' +
      '<div id="au-error" class="form-error hidden"></div>' +
      '<div class="form-row">' +
      '<label class="field"><span>Username *</span><input id="au-username" value="' + h(prefill.username || '') + '" placeholder="jdoe" autocomplete="off"><span class="hint">Lowercase letters, numbers, dot, dash, underscore.</span></label>' +
      '<label class="field"><span>Email *</span><input id="au-email" type="email" value="' + h(prefill.email || '') + '" placeholder="jdoe@company.com"></label>' +
      '</div>' +
      '<div class="form-row">' +
      '<label class="field"><span>First name</span><input id="au-first" value="' + h(prefill.first_name || '') + '"></label>' +
      '<label class="field"><span>Last name</span><input id="au-last" value="' + h(prefill.last_name || '') + '"></label>' +
      '</div>' +
      '<label class="field"><span>Password *</span><div class="copy-row"><input id="au-password" type="text" value="' + h(prefill.password || '') + '" placeholder="At least 8 characters"><button type="button" class="btn btn-sm" id="au-gen">Generate</button></div>' +
      '<span class="hint">Share this password with the user — they can change it in Mattermost after signing in.</span></label>' +
      '<label class="field"><span>Team</span><input id="au-team" list="au-teams" value="' + h(prefill.team || '') + '" placeholder="Start typing a team name…">' +
      '<datalist id="au-teams">' + teamOptions + '</datalist>' +
      '<span class="hint">The team must already exist. Missing? <button type="button" class="link-btn" id="au-create-team">Create a new team</button></span></label>' +
      '<div class="form-row">' +
      '<label class="field"><span>Team role</span><select id="au-role"><option value="member">Member</option><option value="team_admin">Team admin</option></select></label>' +
      '<div class="field"><span>System role</span><label class="check" style="padding-top:8px"><input type="checkbox" id="au-admin" ' + (prefill.system_admin ? 'checked' : '') + '> System Admin</label></div>' +
      '</div>' +
      '<div class="modal-actions"><button type="button" class="btn" data-close>Cancel</button><button type="submit" class="btn btn-primary" id="au-submit">Create user</button></div>' +
      '</form>';

    var m = modal({
      title: 'Add a new user',
      subtitle: 'Creates the Mattermost account and adds it to the selected team.',
      body: body,
      size: 'modal-wide'
    });

    var errBox = $('#au-error', m.el);
    var teamInput = $('#au-team', m.el);

    $('#au-gen', m.el).addEventListener('click', function () {
      $('#au-password', m.el).value = randomPassword(14);
    });

    function showError(msg, extraHtml) {
      errBox.innerHTML = h(msg) + (extraHtml || '');
      errBox.classList.remove('hidden');
      errBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    $('#au-create-team', m.el).addEventListener('click', function () {
      openAddTeam({ prefill: { display_name: teamInput.value || '', name: slugify(teamInput.value || '') }, onCreated: function (team) {
        var datalist = $('#au-teams', m.el);
        var option = document.createElement('option');
        option.value = team.name;
        datalist.appendChild(option);
        teamInput.value = team.name;
        state.teams.push({ id: team.id, name: team.name, display_name: team.display_name, member_ids: [] });
        toast('Team "' + (team.display_name || team.name) + '" created — you can create the user now.', 'success');
      }});
    });

    $('#add-user-form', m.el).addEventListener('submit', function (event) {
      event.preventDefault();
      errBox.classList.add('hidden');
      var username = $('#au-username', m.el).value.trim();
      var email = $('#au-email', m.el).value.trim();
      var password = $('#au-password', m.el).value;
      var team = teamInput.value.trim();
      if (!username || !email || !password) { showError('Username, email and password are required.'); return; }
      if (password.length < 8) { showError('Password must be at least 8 characters.'); return; }
      var submit = $('#au-submit', m.el);
      submit.disabled = true;
      submit.innerHTML = '<span class="spinner"></span> Creating…';
      api('/users', {
        method: 'POST',
        body: {
          username: username, email: email, password: password,
          first_name: $('#au-first', m.el).value.trim(),
          last_name: $('#au-last', m.el).value.trim(),
          team: team,
          team_role: $('#au-role', m.el).value,
          system_admin: $('#au-admin', m.el).checked
        }
      }).then(function (data) {
        var msg = 'User @' + data.user.username + ' created' + (data.team ? ' and added to ' + (data.team.display_name || data.team.name) : '') + '.';
        if (data.warnings && data.warnings.length) toast(data.warnings.join(' '), 'error', 'Partial success');
        toast(msg, 'success');
        m.close();
        refreshAfterMutation();
      }).catch(function (err) {
        submit.disabled = false;
        submit.textContent = 'Create user';
        if (err.data && err.data.code === 'TEAM_NOT_FOUND') {
          showError(err.data.message, '<div style="margin-top:8px"><button type="button" class="btn btn-sm" id="au-make-team">' + icon('plus', 13) + ' Create team "' + h(err.data.team_query) + '"</button></div>');
          var makeBtn = $('#au-make-team', m.el);
          if (makeBtn) makeBtn.addEventListener('click', function () {
            openAddTeam({ prefill: { display_name: err.data.team_query, name: slugify(err.data.team_query) }, onCreated: function (team) {
              teamInput.value = team.name;
              var datalist = $('#au-teams', m.el);
              var option = document.createElement('option');
              option.value = team.name; datalist.appendChild(option);
              errBox.classList.add('hidden');
              toast('Team created. You can create the user now.', 'success');
            }});
          });
        } else {
          showError(err.message);
        }
      });
    });
  }

  function openAddTeam(opts) {
    opts = opts || {};
    var prefill = opts.prefill || {};
    var users = state.users.filter(function (u) { return u.active; }).sort(function (a, b) { return userLabel(a).localeCompare(userLabel(b)); });
    var pickerRows = users.map(function (u) {
      return '<label class="picker-row" data-picker-name="' + h((userLabel(u) + ' ' + u.username + ' ' + (u.email || '')).toLowerCase()) + '">' +
        '<input type="checkbox" value="' + h(u.id) + '">' + avatarHtml(u, 'sm', false) +
        '<div class="grow"><div class="name">' + h(userLabel(u)) + '</div><div class="sub">@' + h(u.username) + '</div></div></label>';
    }).join('');
    var body = '<form id="add-team-form" novalidate>' +
      '<div id="at-error" class="form-error hidden"></div>' +
      '<div class="form-row">' +
      '<label class="field"><span>Display name *</span><input id="at-display" value="' + h(prefill.display_name || '') + '" placeholder="Design Team"></label>' +
      '<label class="field"><span>Team handle *</span><input id="at-name" value="' + h(prefill.name || '') + '" placeholder="design-team"><span class="hint">Used in URLs — lowercase letters, numbers, dashes.</span></label>' +
      '</div>' +
      '<div class="field"><span>Privacy</span><div class="checks">' +
      '<label class="check"><input type="radio" name="at-type" value="O" checked> Open — anyone in the team can join</label>' +
      '<label class="check"><input type="radio" name="at-type" value="I"> Invite only</label></div></div>' +
      '<label class="field"><span>Add members (optional)</span><div class="search sm" style="margin-bottom:6px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg><input id="at-member-search" type="search" placeholder="Filter users…"></div>' +
      '<div class="picker" id="at-picker">' + (pickerRows || '<div class="empty sm">No active users</div>') + '</div>' +
      '<span class="hint" id="at-count">0 selected</span></label>' +
      '<div class="modal-actions"><button type="button" class="btn" data-close>Cancel</button><button type="submit" class="btn btn-primary" id="at-submit">Create team</button></div>' +
      '</form>';
    var m = modal({ title: 'Create a team', subtitle: 'Teams are created immediately on your Mattermost server.', body: body, size: 'modal-wide' });
    var display = $('#at-display', m.el);
    var handle = $('#at-name', m.el);
    var handleTouched = !!(prefill.name);
    handle.addEventListener('input', function () { handleTouched = true; });
    display.addEventListener('input', function () {
      if (!handleTouched) handle.value = slugify(display.value);
    });
    var picker = $('#at-picker', m.el);
    picker.addEventListener('change', function () {
      var count = picker.querySelectorAll('input:checked').length;
      $('#at-count', m.el).textContent = count + ' selected';
    });
    $('#at-member-search', m.el).addEventListener('input', debounce(function () {
      var q = this.value.toLowerCase().trim();
      $$('.picker-row', picker).forEach(function (row) {
        row.style.display = !q || row.dataset.pickerName.indexOf(q) >= 0 ? '' : 'none';
      });
    }, 100));
    function showError(msg) {
      var box = $('#at-error', m.el);
      box.textContent = msg; box.classList.remove('hidden');
    }
    $('#add-team-form', m.el).addEventListener('submit', function (event) {
      event.preventDefault();
      var name = handle.value.trim().toLowerCase();
      var displayName = display.value.trim() || name;
      if (!name || !/^[a-z0-9][a-z0-9-]{1,63}$/.test(name)) {
        showError('Team handle must be 2-64 characters: lowercase letters, numbers and dashes only.');
        return;
      }
      var memberIds = $$('input:checked', picker).map(function (i) { return i.value; });
      var type = ($('input[name="at-type"]:checked', m.el) || {}).value || 'O';
      var btn = $('#at-submit', m.el);
      btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Creating…';
      api('/teams', { method: 'POST', body: { name: name, display_name: displayName, type: type, member_ids: memberIds } })
        .then(function (data) {
          toast('Team "' + (data.team.display_name || data.team.name) + '" created' + (data.members_added ? ' with ' + data.members_added + ' member(s)' : '') + '.', 'success');
          if (data.warnings && data.warnings.length) toast(data.warnings.join(' · '), 'error', 'Some members were not added');
          m.close();
          refreshAfterMutation().then(function () {
            if (opts.onCreated) opts.onCreated(data.team);
          });
        }).catch(function (err) {
          btn.disabled = false; btn.textContent = 'Create team';
          showError(err.message);
        });
    });
  }

  function openTeamMembers(teamId) {
    var m = modal({ title: 'Team members', subtitle: 'Loading…', body: '<div class="empty sm">Loading members…</div>', size: 'modal-wide' });
    function paint() {
      var team = teamById(teamId);
      if (!team) { m.modal.querySelector('.modal-body').innerHTML = emptyState('Team not found', 'alert'); return; }
      var memberIds = team.member_ids || [];
      var members = memberIds.map(userById).filter(Boolean);
      var nonMembers = state.users.filter(function (u) { return u.active && memberIds.indexOf(u.id) < 0; });
      var roles = team.roles_by_user || {};
      var body = '<div class="toolbar" style="margin-bottom:12px">' +
        '<span class="pill pill-blue">' + icon('teams', 12) + ' ' + fmtNum(memberIds.length) + ' members</span>' +
        '<span class="pill ' + (team.type === 'I' ? 'pill-amber' : 'pill-gray') + '">' + (team.type === 'I' ? 'Invite only' : 'Open') + '</span>' +
        '<span class="muted small">@' + h(team.name) + '</span></div>' +
        '<form id="tm-add-form" class="copy-row" style="margin-bottom:14px">' +
        '<input id="tm-user" list="tm-users" placeholder="Type a username or name to add…" style="flex:1">' +
        '<datalist id="tm-users">' + nonMembers.map(function (u) { return '<option value="' + h(u.username) + '">' + h(userLabel(u)) + ' · ' + h(u.email || '') + '</option>'; }).join('') + '</datalist>' +
        '<select id="tm-role" style="width:126px"><option value="member">Member</option><option value="team_admin">Team admin</option></select>' +
        '<button class="btn btn-primary btn-sm" type="submit">Add</button></form>' +
        '<div class="table-wrap"><table class="table"><thead><tr><th>Member</th><th>Team role</th><th class="right">Action</th></tr></thead><tbody>' +
        (members.length ? members.map(function (u) {
          var isAdmin = (roles[u.id] || '').split(' ').indexOf('team_admin') >= 0;
          return '<tr><td><div class="cell-user">' + avatarHtml(u, 'sm', true) + '<div><div class="cell-main">' + h(userLabel(u)) + '</div><div class="cell-sub">@' + h(u.username) + '</div></div></div></td>' +
            '<td>' + (isAdmin ? '<span class="pill pill-admin">Team admin</span>' : '<span class="pill pill-gray">Member</span>') + '</td>' +
            '<td class="right"><button class="btn btn-sm btn-ghost" data-remove-member="' + h(u.id) + '">Remove</button></td></tr>';
        }).join('') : '<tr><td colspan="3">' + emptyState('No members yet', 'users') + '</td></tr>') +
        '</tbody></table></div>';
      m.modal.querySelector('.modal-body').innerHTML = body;
      setModalSubtitle(m, (team.display_name || team.name) + ' · ' + members.length + ' members');
      m.modal.querySelector('#tm-add-form').addEventListener('submit', function (event) {
        event.preventDefault();
        var input = m.modal.querySelector('#tm-user');
        var query = input.value.trim().toLowerCase();
        var role = m.modal.querySelector('#tm-role').value;
        if (!query) return;
        var user = null;
        for (var i = 0; i < nonMembers.length; i++) {
          var cand = nonMembers[i];
          if ((cand.username || '').toLowerCase() === query || (cand.email || '').toLowerCase() === query ||
              userLabel(cand).toLowerCase() === query || cand.id === query) { user = cand; break; }
        }
        if (!user) { toast('No matching user found. Use the exact username.', 'error'); return; }
        api('/teams/' + encodeURIComponent(teamId) + '/members', { method: 'POST', body: { user_id: user.id, role: role } })
          .then(function (data) {
            if (data.errors && data.errors.length) toast(data.errors[0].message, 'error');
            else toast('@' + user.username + ' added to the team.', 'success');
            return refreshAfterMutation();
          }).then(paint)
          .catch(function (err) { toast(err.message, 'error'); });
      });
      m.modal.querySelectorAll('[data-remove-member]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var uid = btn.dataset.removeMember;
          api('/teams/' + encodeURIComponent(teamId) + '/members/' + encodeURIComponent(uid), { method: 'DELETE' })
            .then(function () { toast('Member removed.', 'success'); return refreshAfterMutation(); })
            .then(paint)
            .catch(function (err) { toast(err.message, 'error'); });
        });
      });
    }
    paint();
  }

  function openManageTeams(userId) {
    var m = modal({ title: 'Manage teams', subtitle: 'Loading…', body: '<div class="empty sm">Loading…</div>', size: 'modal-wide' });
    function paint() {
      var u = userById(userId);
      if (!u) { m.modal.querySelector('.modal-body').innerHTML = emptyState('User not found', 'alert'); return; }
      setModalSubtitle(m, userLabel(u) + ' · @' + u.username);
      var userTeamIds = u.team_ids || [];
      var userTeams = userTeamIds.map(teamById).filter(Boolean);
      var otherTeams = state.teams.filter(function (t) { return userTeamIds.indexOf(t.id) < 0; });
      var body = '<div class="section-title">Current teams</div>' +
        (userTeams.length ? '<div class="list">' + userTeams.map(function (t) {
          return '<div class="list-row"><div class="team-logo" style="background:' + gradient(t.display_name || t.name) + ';width:32px;height:32px;border-radius:9px;font-size:12px">' + h(initials(t.display_name || t.name)) + '</div>' +
            '<div class="grow"><div class="name">' + h(t.display_name || t.name) + '</div><div class="sub">@' + h(t.name) + ' · ' + (t.member_ids || []).length + ' members</div></div>' +
            '<div class="end"><button class="btn btn-sm btn-ghost" data-remove-team="' + h(t.id) + '">Remove</button></div></div>';
        }).join('') + '</div>' : '<div class="empty sm">Not a member of any team.</div>') +
        '<div class="section-title">Add to a team</div>' +
        (otherTeams.length ? '<form id="mt-add-form" class="copy-row"><select id="mt-team" style="flex:1">' +
          otherTeams.map(function (t) { return '<option value="' + h(t.id) + '">' + h(t.display_name || t.name) + ' (@' + h(t.name) + ')</option>'; }).join('') +
          '</select><select id="mt-role" style="width:126px"><option value="member">Member</option><option value="team_admin">Team admin</option></select>' +
          '<button class="btn btn-primary btn-sm" type="submit">Add</button></form>'
          : '<div class="empty sm">This user is already in every team.</div>') +
        '<div class="form-note" style="margin-top:16px">' + icon('info', 14) + ' Removing a user from a team does not delete the account. Use the Users page to deactivate or delete the account entirely.</div>';
      m.modal.querySelector('.modal-body').innerHTML = body;
      var addForm = m.modal.querySelector('#mt-add-form');
      if (addForm) addForm.addEventListener('submit', function (event) {
        event.preventDefault();
        var teamId = m.modal.querySelector('#mt-team').value;
        var role = m.modal.querySelector('#mt-role').value;
        api('/teams/' + encodeURIComponent(teamId) + '/members', { method: 'POST', body: { user_id: userId, role: role } })
          .then(function () { toast('User added to the team.', 'success'); return refreshAfterMutation(); })
          .then(paint)
          .catch(function (err) { toast(err.message, 'error'); });
      });
      m.modal.querySelectorAll('[data-remove-team]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var teamId = btn.dataset.removeTeam;
          var team = teamById(teamId);
          api('/teams/' + encodeURIComponent(teamId) + '/members/' + encodeURIComponent(userId), { method: 'DELETE' })
            .then(function () { toast('Removed from ' + ((team && (team.display_name || team.name)) || 'team') + '.', 'success'); return refreshAfterMutation(); })
            .then(paint)
            .catch(function (err) { toast(err.message, 'error'); });
        });
      });
    }
    paint();
  }

  function openResetPassword(userId) {
    var u = userById(userId);
    if (!u) return;
    var body = '<form id="rp-form"><div id="rp-error" class="form-error hidden"></div>' +
      '<p class="small muted" style="margin-bottom:14px">Set a new password for <strong>' + h(userLabel(u)) + '</strong> (@' + h(u.username) + '). The old password will stop working immediately.</p>' +
      '<label class="field"><span>New password</span><div class="copy-row"><input id="rp-password" type="text" value="' + h(randomPassword(14)) + '">' +
      '<button type="button" class="btn btn-sm" id="rp-gen">Generate</button><button type="button" class="btn btn-sm btn-ghost" id="rp-copy" title="Copy">' + icon('copy', 14) + '</button></div>' +
      '<span class="hint">Minimum 8 characters. Copy it and share it securely with the user.</span></label>' +
      '<div class="modal-actions"><button type="button" class="btn" data-close>Cancel</button><button type="submit" class="btn btn-primary" id="rp-submit">Update password</button></div></form>';
    var m = modal({ title: 'Reset password', body: body });
    $('#rp-gen', m.el).addEventListener('click', function () { $('#rp-password', m.el).value = randomPassword(14); });
    $('#rp-copy', m.el).addEventListener('click', function () {
      copyText($('#rp-password', m.el).value); toast('Password copied to clipboard.', 'success');
    });
    $('#rp-form', m.el).addEventListener('submit', function (event) {
      event.preventDefault();
      var pw = $('#rp-password', m.el).value;
      var errBox = $('#rp-error', m.el);
      if (pw.length < 8) { errBox.textContent = 'Password must be at least 8 characters.'; errBox.classList.remove('hidden'); return; }
      var btn = $('#rp-submit', m.el);
      btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Saving…';
      api('/users/' + encodeURIComponent(userId) + '/password', { method: 'PUT', body: { password: pw } })
        .then(function () { toast('Password updated for @' + u.username + '.', 'success'); m.close(); })
        .catch(function (err) { btn.disabled = false; btn.textContent = 'Update password'; errBox.textContent = err.message; errBox.classList.remove('hidden'); });
    });
  }

  function revokeSessions(userId) {
    var u = userById(userId);
    if (!u) return;
    confirmDialog({
      title: 'Sign out everywhere',
      message: 'Revoke all active sessions of <strong>@' + h(u.username) + '</strong>? They will be logged out on every device but keep their account.',
      confirmText: 'Revoke sessions',
      danger: false
    }).then(function (res) {
      if (!res.ok) return;
      return api('/users/' + encodeURIComponent(userId) + '/revoke-sessions', { method: 'POST' })
        .then(function (data) {
          toast(data.revoked + ' session(s) revoked for @' + u.username + '.', 'success');
        });
    }).catch(function (err) { toast(err.message, 'error'); });
  }

  function toggleAdminRole(userId) {
    var u = userById(userId);
    if (!u) return;
    var promote = !u.is_admin;
    confirmDialog({
      title: promote ? 'Grant System Admin' : 'Remove System Admin',
      message: promote
        ? 'Give <strong>@' + h(u.username) + '</strong> full System Admin rights? They will be able to change any server setting.'
        : 'Remove the System Admin role from <strong>@' + h(u.username) + '</strong>? They become a regular member.',
      note: promote ? 'System Admins can also sign in to this dashboard.' : 'They will lose access to this dashboard immediately.',
      confirmText: promote ? 'Grant admin' : 'Remove admin',
      danger: !promote
    }).then(function (res) {
      if (!res.ok) return;
      return api('/users/' + encodeURIComponent(userId) + '/roles', {
        method: 'POST', body: { system_admin: promote }
      }).then(function () {
        toast('@' + u.username + (promote ? ' is now a System Admin.' : ' is no longer a System Admin.'), 'success');
        return refreshAfterMutation();
      });
    }).catch(function (err) { toast(err.message, 'error'); });
  }

  function toggleUser(userId) {
    var u = userById(userId);
    if (!u) return;
    var activating = !u.active;
    confirmDialog({
      title: activating ? 'Activate user' : 'Deactivate user',
      message: activating
        ? 'Reactivate <strong>@' + h(u.username) + '</strong>? They will be able to sign in again.'
        : 'Deactivate <strong>@' + h(u.username) + '</strong>? Their sessions are revoked and they cannot sign in. Their messages and files are kept.',
      note: activating ? null : 'Deactivation is reversible. You can activate the account again at any time.',
      confirmText: activating ? 'Activate' : 'Deactivate user',
      danger: !activating
    }).then(function (res) {
      if (!res.ok) return;
      return api('/users/' + encodeURIComponent(userId) + '/active', { method: 'PUT', body: { active: activating } })
        .then(function () {
          toast('@' + u.username + ' ' + (activating ? 'activated' : 'deactivated') + '.', 'success');
          refreshAfterMutation();
        });
    }).catch(function (err) { toast(err.message, 'error'); });
  }

  function openDeleteUser(userId) {
    var u = userById(userId);
    if (!u) return;
    var body = '<div class="callout danger">' + icon('alert') + '<div><strong>This affects the Mattermost account of @' + h(u.username) + '.</strong>' +
      '<br>Deactivation keeps all messages and files. Permanent deletion removes the user and their content and cannot be undone.</div></div>' +
      '<label class="check"><input type="checkbox" id="du-perm"> Permanently delete the account and its content (requires <code>EnableAPIUserDeletion</code> on the server)</label>';
    var m = modal({
      title: 'Delete user',
      subtitle: userLabel(u) + ' · @' + u.username + ' · ' + (u.email || ''),
      body: body,
      actions: '<button class="btn" data-close>Cancel</button>' +
        '<button class="btn btn-danger" id="du-deactivate">Deactivate</button>' +
        '<button class="btn btn-danger" id="du-permanent">Delete permanently</button>'
    });
    function run(permanent) {
      var url = '/users/' + encodeURIComponent(userId) + (permanent ? '?permanent=1' : '');
      api(url, { method: 'DELETE' }).then(function (data) {
        var result = (data && data.result) || (permanent ? 'deleted' : 'deactivated');
        m.close();
        if (result === 'deleted') {
          toast('@' + u.username + ' was permanently deleted.', 'success');
        } else if (result === 'deactivated') {
          if (permanent) {
            // Asked for a permanent delete but the server only deactivated.
            toast('@' + u.username + ' was deactivated — not permanently deleted. ' +
                  'Enable EnableAPIUserDeletion or install mmctl to delete for real.',
                  'warn', 'Only deactivated', 12000);
          } else {
            toast('@' + u.username + ' was deactivated.', 'success');
          }
        } else {
          toast('The server reported success but @' + u.username + ' is unchanged.', 'error');
        }
        refreshAfterMutation();
      }).catch(function (err) {
        toast(err.message, 'error', permanent ? 'Permanent delete failed' : 'Delete failed');
      });
    }
    $('#du-deactivate', m.el).addEventListener('click', function () { run(false); });
    $('#du-permanent', m.el).addEventListener('click', function () {
      if (!m.el.querySelector('#du-perm').checked) { toast('Tick the permanent-deletion checkbox first.', 'error'); return; }
      run(true);
    });
  }

  function openDeleteTeam(teamId) {
    var t = teamById(teamId);
    if (!t) return;
    var memberCount = (t.member_ids || []).length;
    var body = '<div class="callout warn">' + icon('alert') + '<div><strong>Archive "' + h(t.display_name || t.name) + '"?</strong><br>' +
      'The team disappears from Mattermost, but its data is kept in the database. ' + fmtNum(memberCount) + ' member(s) will lose access.</div></div>' +
      '<label class="check"><input type="checkbox" id="dt-perm"> Permanently delete the team and all of its data (requires <code>EnableAPITeamDeletion</code>)</label>';
    var m = modal({
      title: 'Delete team',
      subtitle: '@' + t.name,
      body: body,
      actions: '<button class="btn" data-close>Cancel</button><button class="btn btn-danger" id="dt-delete">Delete team</button>'
    });
    $('#dt-delete', m.el).addEventListener('click', function () {
      var permanent = m.el.querySelector('#dt-perm').checked;
      api('/teams/' + encodeURIComponent(teamId) + (permanent ? '?permanent=1' : ''), { method: 'DELETE' })
        .then(function (data) {
          var result = (data && data.result) || 'archived';
          m.close();
          if (result === 'deleted') toast('Team permanently deleted.', 'success');
          else if (result === 'archived' && permanent) {
            toast('Team was archived, not permanently deleted. Enable EnableAPITeamDeletion ' +
                  'or install mmctl to delete for real.', 'warn', 'Only archived', 12000);
          } else toast('Team archived.', 'success');
          refreshAfterMutation();
        }).catch(function (err) { toast(err.message, 'error', 'Delete failed'); });
    });
  }

  function openUserDetail(userId) {
    var m = modal({
      title: 'User details', subtitle: 'Loading…', size: 'modal-wide',
      body: '<div class="empty sm">Loading user details…</div>'
    });
    api('/users/' + encodeURIComponent(userId) + '/detail').then(function (data) {
      var u = data.user;
      var teams = data.teams || [];
      var sessions = data.sessions || [];
      var locations = data.locations || [];
      var statusEvents = data.status_history || [];
      var badges = '';
      if (u.is_admin) badges += '<span class="pill pill-admin">System Admin</span> ';
      if (!u.delete_at) badges += '<span class="pill pill-live"><span class="dot"></span>Active</span>'; else badges += '<span class="pill pill-red">Deactivated</span>';
      var html = '<div class="toolbar" style="margin-bottom:16px">' + avatarHtml({ username: u.username, first_name: u.first_name, last_name: u.last_name }, 'lg', false) +
        '<div style="min-width:0"><h2 style="font-size:17px">' + h(userLabel(u)) + '</h2><div class="muted small">@' + h(u.username) + ' · ' + h(u.email || '') + '</div>' +
        '<div style="margin-top:7px;display:flex;gap:6px;flex-wrap:wrap">' + badges + '</div></div>' +
        '<div class="spacer"></div><div style="display:flex;gap:6px;flex-wrap:wrap">' +
        '<button class="btn btn-sm" data-action="user-chat" data-id="' + h(u.id) + '">' + icon('chat', 13) + ' Chats</button>' +
        '<button class="btn btn-sm btn-ghost" data-action="user-password" data-id="' + h(u.id) + '">' + icon('key', 13) + ' Password</button>' +
        '<button class="btn btn-sm btn-ghost" data-action="user-revoke" data-id="' + h(u.id) + '">' + icon('logout', 13) + ' Sign out everywhere</button>' +
        '<button class="btn btn-sm btn-ghost" data-action="user-role" data-id="' + h(u.id) + '">' + icon('shield', 13) + ' ' + (u.is_admin ? 'Remove admin' : 'Make admin') + '</button>' +
        '</div></div>' +
        '<dl class="kv" style="margin-bottom:18px"><dt>Created</dt><dd>' + h(fmtDateTime(u.create_at)) + '</dd>' +
        '<dt>Roles</dt><dd>' + h(u.roles || '—') + '</dd>' +
        '<dt>Last activity</dt><dd>' + (data.last_activity ? h(fmtDateTime(data.last_activity)) : '<span class="muted">no active sessions</span>') + '</dd>' +
        '<dt>User ID</dt><dd><code>' + h(u.id) + '</code></dd></dl>' +
        '<div class="grid grid-2">' +
        '<div><div class="section-title">Teams (' + teams.length + ')</div>' +
        (teams.length ? '<div class="chips">' + teams.map(function (t) { return '<span class="chip team">' + h(t.display_name || t.name) + '</span>'; }).join('') + '</div>' +
          '<button class="link-btn" style="margin-top:8px" data-action="manage-teams" data-id="' + h(u.id) + '">Manage teams →</button>'
          : '<div class="empty sm">Not in any team</div>') +
        '</div>' +
        '<div><div class="section-title">Active sessions (' + sessions.length + ')</div>' +
        (sessions.length ? '<div class="list">' + sessions.slice(0, 4).map(function (s) {
          var props = s.props || {};
          var device = [props.browser, props.platform, props.os].filter(Boolean).join(' · ') || 'Client';
          return '<div class="list-row"><div class="grow"><div class="name">' + h(device) + '</div><div class="sub">active ' + h(s.last_activity_at ? fmtRel(s.last_activity_at) : '—') + '</div></div></div>';
        }).join('') + '</div>' : '<div class="empty sm">No active sessions</div>') +
        '</div></div>' +
        '<div class="section-title">Recent locations (' + locations.length + ')</div>' +
        (locations.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>IP</th><th>Location</th><th>Source</th></tr></thead><tbody>' +
          locations.slice(0, 8).map(function (l) {
            return '<tr><td class="small nowrap">' + h(fmtDateTime(l.ts)) + '</td><td class="mono tiny">' + h(l.ip || '—') + '</td><td>' + locationText(l) + '</td><td>' + sourcePill(l.source) + '</td></tr>';
          }).join('') + '</tbody></table></div>' : '<div class="empty sm">No location records for this user.</div>') +
        '<div class="section-title">Recent status changes (' + statusEvents.length + ')</div>' +
        (statusEvents.length ? '<div class="list">' + statusEvents.slice(-8).reverse().map(function (e) {
          return '<div class="list-row"><div class="grow"><div class="name">' + statusPill(e.status, true) + '</div><div class="sub">' + h(fmtDateTime(e.ts)) + '</div></div></div>';
        }).join('') + '</div>' : '<div class="empty sm">No status history recorded yet.</div>') +
        '<div class="modal-actions"><button class="btn btn-danger" data-action="user-delete" data-id="' + h(u.id) + '">' + icon('trash', 13) + ' Delete user</button>' +
        '<button class="btn ' + (u.delete_at ? 'btn-success' : 'btn-ghost') + '" data-action="user-toggle" data-id="' + h(u.id) + '">' + icon('power', 13) + ' ' + (u.delete_at ? 'Activate user' : 'Deactivate user') + '</button></div>';
      m.modal.querySelector('.modal-body').innerHTML = html;
      setModalSubtitle(m, 'Profile, teams, sessions and history');
    }).catch(function (err) {
      m.modal.querySelector('.modal-body').innerHTML = emptyState('Could not load user', 'alert', err.message);
    });
  }

  function refreshAfterMutation() {
    var p = loadUsers(true).catch(function () {});
    return p.then(function () {
      if (state.view === 'overview') loadOverview();
      else if (state.view === 'teams') renderTeamsGrid();
      else if (state.view === 'presence') loadPresence();
      else if (state.view === 'locations' && state.locations.tab === 'live') loadLocationsLive();
      else if (state.view === 'settings') loadSettings();
    });
  }

  /* ---------------------------------------------------------------- global events */
  document.addEventListener('click', function (event) {
    var goto = event.target.closest('[data-goto]');
    if (goto && !event.target.closest('[data-action]')) {
      var targetView = goto.dataset.goto;
      setView(targetView);
      if (goto.dataset.ltabTarget) {
        state.locations.tab = goto.dataset.ltabTarget;
        syncLocTabs();
        loadLocations();
      }
      return;
    }
    var viewBtn = event.target.closest('[data-view-target]');
    if (viewBtn) { setView(viewBtn.dataset.viewTarget); return; }

    var el = event.target.closest('[data-action]');
    if (!el) return;
    var action = el.dataset.action;
    var id = el.dataset.id;

    function guard(promise) {
      if (promise && promise.catch) promise.catch(function (err) { toast(err.message, 'error'); });
    }

    switch (action) {
      case 'add-user': openAddUser(); break;
      case 'add-team': openAddTeam(); break;
      case 'user-detail': closeAllModals(); openUserDetail(id); break;
      case 'user-chat': closeAllModals(); setView('chats', { userId: id }); break;
      case 'manage-teams': closeAllModals(); openManageTeams(id); break;
      case 'user-password': closeAllModals(); openResetPassword(id); break;
      case 'user-toggle': closeAllModals(); toggleUser(id); break;
      case 'user-delete': closeAllModals(); openDeleteUser(id); break;
      case 'user-revoke': revokeSessions(id); break;
      case 'user-role': toggleAdminRole(id); break;
      case 'team-members': openTeamMembers(id); break;
      case 'team-delete': closeAllModals(); openDeleteTeam(id); break;
      case 'chat-user':
        selectChatUser(el.dataset.id);
        var layout = document.querySelector('.chat-layout');
        if (layout && window.innerWidth <= 720) layout.classList.add('mobile-partners');
        break;
      case 'chat-partner':
        openChat(el.dataset.partner, el.dataset.channel);
        var l3 = document.querySelector('.chat-layout');
        if (l3 && window.innerWidth <= 720) { l3.classList.remove('mobile-users', 'mobile-partners'); l3.classList.add('mobile-convo'); }
        break;
      case 'chat-show-users': {
        var l1 = document.querySelector('.chat-layout');
        if (l1) { l1.classList.remove('mobile-partners'); l1.classList.add('mobile-users'); }
        break;
      }
      case 'chat-show-partners': {
        var l2 = document.querySelector('.chat-layout');
        if (l2) { l2.classList.remove('mobile-users', 'mobile-convo'); l2.classList.add('mobile-partners'); }
        break;
      }
      case 'presence-detail': renderPresenceDetail(id); break;
      case 'presence-close': state.presence.selected = null; $('#presence-detail').innerHTML = ''; break;
      case 'loc-history':
        state.locations.tab = 'history';
        state.locations.offset = 0;
        syncLocTabs();
        loadLocationsHistory(true).then(function () {
          var sel = $('#loc-user-filter');
          if (sel && el.dataset.id) { sel.value = el.dataset.id; loadLocationsHistory(true); }
        });
        break;
      case 'loc-tab':
        state.locations.tab = el.dataset.tab || 'live';
        syncLocTabs();
        loadLocations();
        break;
      case 'sync-audits': syncAudits(); break;
      case 'refresh-view': loadCurrent(true); break;
      case 'copy':
        copyText(el.dataset.copy || ''); toast('Copied to clipboard.', 'success');
        break;
      case 'toggle-key': {
        var input = $('#agent-key-input');
        if (!input) break;
        var showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        el.innerHTML = showing ? icon('eye', 14) : icon('eyeOff', 14);
        break;
      }
      case 'logout': logout(); break;
      default: break;
    }
  });

  $$('.nav-item').forEach(function (btn) {
    btn.addEventListener('click', function () { setView(btn.dataset.view); closeSidebar(); });
  });

  $('#logout-btn').addEventListener('click', logout);
  function logout() {
    api('/logout', { method: 'POST' }).catch(function () {}).then(function () {
      window.location.href = '/';
    });
  }
  $('#global-refresh').addEventListener('click', function () {
    var btn = this;
    btn.disabled = true;
    var svg = btn.querySelector('svg');
    if (svg) svg.classList.add('spin');
    var done = function () { btn.disabled = false; if (svg) svg.classList.remove('spin'); };
    loadCurrent(true);
    setTimeout(done, 900);
  });
  function closeSidebar() {
    var sb = $('#sidebar');
    if (!sb) return;
    sb.classList.remove('show');
    var back = $('#sidebar-backdrop');
    if (back) back.remove();
  }
  function toggleSidebar() {
    var sb = $('#sidebar');
    if (!sb) return;
    var open = sb.classList.toggle('show');
    if (open) {
      var back = document.createElement('div');
      back.id = 'sidebar-backdrop';
      back.className = 'sidebar-backdrop';
      back.addEventListener('click', closeSidebar);
      document.body.appendChild(back);
    } else {
      var existing = $('#sidebar-backdrop');
      if (existing) existing.remove();
    }
  }
  $('#menu-btn').addEventListener('click', toggleSidebar);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeSidebar(); });

  // Users filters
  $('#user-search').addEventListener('input', debounce(renderUsersTable, 140));
  $('#user-status-filter').addEventListener('change', renderUsersTable);
  $('#user-show-inactive').addEventListener('change', renderUsersTable);
  $('#export-users-btn').addEventListener('click', exportUsers);

  // Chat search
  $('#chat-user-search').addEventListener('input', debounce(renderChatUserList, 140));
  var showDeletedBox = $('#chat-show-deleted');
  if (showDeletedBox) {
    showDeletedBox.addEventListener('change', function () {
      state.chat.showDeleted = showDeletedBox.checked;
      renderMessages();
    });
  }

  $('#chat-refresh').addEventListener('click', function () {
    if (state.chat.channelId) {
      state.chat.messages = []; state.chat.page = 0;
      fetchChatPage(0, false);
    } else if (state.chat.userId) {
      selectChatUser(state.chat.userId);
    }
  });
  $('#chat-load-older').addEventListener('click', function () {
    if (!state.chat.channelId) return;
    fetchChatPage(state.chat.page + 1, true);
  });

  // Presence range
  $$('#presence-range button').forEach(function (btn) {
    btn.addEventListener('click', function () {
      state.presence.hours = Number(btn.dataset.hours);
      $$('#presence-range button').forEach(function (b) { b.classList.toggle('active', b === btn); });
      loadPresence();
    });
  });
  $('#presence-refresh').addEventListener('click', refreshPresenceNow);

  // Locations
  $$('#loc-tabs button').forEach(function (btn) {
    btn.addEventListener('click', function () {
      state.locations.tab = btn.dataset.ltab;
      state.locations.offset = 0;
      syncLocTabs();
      loadLocations();
    });
  });
  function syncLocTabs() {
    $$('#loc-tabs button').forEach(function (b) { b.classList.toggle('active', b.dataset.ltab === state.locations.tab); });
    ['live', 'history', 'agent'].forEach(function (t) {
      var pane = $('#loc-pane-' + t);
      if (pane) pane.classList.toggle('hidden', t !== state.locations.tab);
    });
  }
  ['loc-user-filter', 'loc-source-filter', 'loc-limit'].forEach(function (id) {
    var el = $('#' + id);
    if (el) el.addEventListener('change', function () { state.locations.offset = 0; loadLocationsHistory(true); });
  });
  $('#loc-load-more').addEventListener('click', function () { loadLocationsHistory(false); });
  $('#loc-auto').addEventListener('change', function () {
    if (this.checked) startLocAuto(); else stopLocAuto();
  });

  window.addEventListener('hashchange', onHashChange);

  /* ---------------------------------------------------------------- init */
  (function init() {
    var user = BOOT.user || {};
    $('#me-name').textContent = user.name || user.username || 'Administrator';
    $('#me-username').textContent = '@' + (user.username || 'admin');
    var meAvatar = $('#me-avatar');
    meAvatar.textContent = initials(user.name, user.username);
    meAvatar.style.background = gradient(user.name || user.username || 'admin');
    if ((user.roles || '').indexOf('system_admin') >= 0) $('#me-name').title = 'System Admin';
    var pollLabel = $('#presence-poll-label');
    if (pollLabel) pollLabel.textContent = BOOT.poll_seconds || 60;

    var match = (location.hash || '').match(/^#\/([a-z]+)/);
    var initial = match && VIEW_META[match[1]] ? match[1] : 'overview';
    setView(initial, { skipHash: false });
  })();
})();
