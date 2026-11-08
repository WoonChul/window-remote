/* window-remote web client. Plain JS, no build step. */
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const stage = $('#stage');
  const canvas = $('#screen');
  const ctx = canvas.getContext('2d', { alpha: false });
  const overlay = $('#overlay');
  const cursorEl = $('#cursor');
  const statusEl = $('#status');
  const winSelect = $('#winSelect');

  const LONG_PRESS_MS = 500;
  const DRAG_THRESHOLD = 8;       // css px before a touch becomes a drag
  const DOUBLE_TAP_MS = 350;
  const DOUBLE_TAP_PX = 24;

  const store = {
    get(k) { try { return localStorage.getItem('wr_' + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem('wr_' + k, v); } catch (e) { /* ignore */ } },
  };

  const st = {
    ws: null, token: null, authed: false,
    hwnd: null, frameW: 0, frameH: 0, needFit: true, fitMode: true,
    scale: 1, tx: 0, ty: 0,
    mode: store.get('mode') || 'pointer',      // 'pointer' | 'trackpad'
    cursor: { x: 0.5, y: 0.5 },
    speed: parseFloat(store.get('speed') || '1'),
    mods: new Set(),
    lastSeq: 0, frames: 0, fps: 0, rtt: null,
    pendingMove: null, moveScheduled: false,
  };

  // ------------------------------------------------------------ connection
  function getToken() {
    const url = new URL(location.href);
    let t = url.searchParams.get('token');
    if (t) {
      store.set('token', t);
      history.replaceState(null, '', location.pathname);
    } else {
      t = store.get('token');
    }
    if (!t) {
      t = (prompt('에이전트 창에 표시된 접속 토큰을 입력하세요') || '').trim();
      if (t) store.set('token', t);
    }
    return t;
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.binaryType = 'arraybuffer';
    st.ws = ws;
    setStatus('연결 중…');
    ws.onopen = () => send({ t: 'hello', token: st.token });
    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') onJson(JSON.parse(ev.data));
      else onFrame(ev.data);
    };
    ws.onclose = () => {
      st.authed = false;
      setStatus('연결 끊김 · 재연결 중');
      setTimeout(connect, 2000);
    };
  }

  function send(obj) {
    if (st.ws && st.ws.readyState === WebSocket.OPEN) st.ws.send(JSON.stringify(obj));
  }

  function onJson(m) {
    switch (m.t) {
      case 'welcome':
        st.authed = true;
        setStatus(`연결됨 · ${m.host}`);
        sendSettings();
        if (st.hwnd) send({ t: 'select', hwnd: st.hwnd });
        break;
      case 'windows': fillWindows(m.items); break;
      case 'selected':
        st.hwnd = m.hwnd; st.needFit = true; st.lastSeq = 0;
        winSelect.value = String(m.hwnd);
        document.title = `${m.title} · window-remote`;
        showOverlay('불러오는 중…');
        break;
      case 'state':
        if (m.state === 'minimized') showOverlay('창이 최소화되어 있습니다 · 화면을 누르면 복원');
        else if (m.state === 'ok') showOverlay(null);
        break;
      case 'gone':
        st.hwnd = null; showOverlay('창이 닫혔습니다 · 다른 창을 선택하세요');
        break;
      case 'pong': st.rtt = Math.round(performance.now() - m.ts); break;
      case 'error':
        if (m.code === 'auth') {
          store.set('token', '');
          st.token = getToken();
        }
        setStatus(m.msg || '오류');
        break;
    }
  }

  function fillWindows(items) {
    const cur = st.hwnd ? String(st.hwnd) : winSelect.value;
    winSelect.innerHTML = '<option value="">창 선택…</option>';
    for (const w of items) {
      const o = document.createElement('option');
      o.value = String(w.hwnd);
      o.textContent = w.exe ? `${w.title} — ${w.exe}` : w.title;
      winSelect.appendChild(o);
    }
    winSelect.value = cur;
  }

  // ---------------------------------------------------------------- frames
  function onFrame(buf) {
    const dv = new DataView(buf);
    if (dv.getUint8(0) !== 1) return;
    const seq = dv.getUint32(1, true);
    const w = dv.getUint16(5, true);
    const h = dv.getUint16(7, true);
    const blob = new Blob([new Uint8Array(buf, 9)], { type: 'image/jpeg' });
    createImageBitmap(blob).then((bmp) => {
      if (seq > st.lastSeq) {
        st.lastSeq = seq;
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w; canvas.height = h;
          if (st.fitMode || !st.frameW) st.needFit = true;
        }
        st.frameW = w; st.frameH = h;
        ctx.drawImage(bmp, 0, 0);
        if (st.needFit) { st.needFit = false; fit(); }
        st.frames++;
      }
      bmp.close();
      send({ t: 'ack', seq });
    }).catch(() => send({ t: 'ack', seq }));
  }

  // ------------------------------------------------------------ view / zoom
  function applyTransform() {
    canvas.style.transform = `translate(${st.tx}px, ${st.ty}px) scale(${st.scale})`;
    stage.classList.toggle('pixelated', st.scale >= 2);
    updateCursor();
  }

  function fit() {
    if (!st.frameW) return;
    const sw = stage.clientWidth, sh = stage.clientHeight;
    st.scale = Math.min(sw / st.frameW, sh / st.frameH);
    st.tx = (sw - st.frameW * st.scale) / 2;
    st.ty = (sh - st.frameH * st.scale) / 2;
    st.fitMode = true;
    applyTransform();
  }

  function zoomAt(factor, cx, cy) {
    const ns = Math.min(16, Math.max(0.05, st.scale * factor));
    st.tx = cx - (cx - st.tx) * (ns / st.scale);
    st.ty = cy - (cy - st.ty) * (ns / st.scale);
    st.scale = ns;
    st.fitMode = false;
    applyTransform();
  }

  function stagePoint(clientX, clientY) {
    const r = stage.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
  }

  // stage px -> normalized window coordinates (0..1)
  function toNorm(p) {
    return {
      x: (p.x - st.tx) / st.scale / st.frameW,
      y: (p.y - st.ty) / st.scale / st.frameH,
    };
  }

  function fromNorm(n) {
    return { x: st.tx + n.x * st.frameW * st.scale, y: st.ty + n.y * st.frameH * st.scale };
  }

  const inside = (n) => n.x >= 0 && n.x <= 1 && n.y >= 0 && n.y <= 1;

  // ---------------------------------------------------------- remote input
  function queueMove(n) {
    st.pendingMove = n;
    if (!st.moveScheduled) {
      st.moveScheduled = true;
      requestAnimationFrame(flushMove);
    }
  }

  function flushMove() {
    st.moveScheduled = false;
    if (st.pendingMove) {
      send({ t: 'mouse', a: 'move', x: st.pendingMove.x, y: st.pendingMove.y });
      st.pendingMove = null;
    }
  }

  function mouse(a, n, b = 'left') {
    st.pendingMove = null;
    send({ t: 'mouse', a, b, x: n.x, y: n.y });
  }

  function clickAt(n, b = 'left') { mouse('down', n, b); mouse('up', n, b); }

  function wheelAt(n, delta, horizontal = false) {
    send({ t: 'mouse', a: 'wheel', d: delta, h: horizontal, x: n.x, y: n.y });
  }

  function pressCode(code) {
    const mods = [...st.mods];
    for (const m of mods) send({ t: 'key', a: 'down', code: m });
    send({ t: 'key', a: 'press', code });
    for (const m of mods.reverse()) send({ t: 'key', a: 'up', code: m });
    clearMods();
  }

  function pressCombo(combo) {
    const parts = combo.split('+');
    const key = parts.pop();
    for (const m of parts) send({ t: 'key', a: 'down', code: m });
    send({ t: 'key', a: 'press', code: key });
    for (const m of parts.reverse()) send({ t: 'key', a: 'up', code: m });
  }

  function clearMods() {
    st.mods.clear();
    document.querySelectorAll('#keybar [data-mod]').forEach((b) => b.classList.remove('on'));
  }

  function sendText(s) {
    if (!s) return;
    // With sticky Ctrl/Alt active, a single letter becomes a shortcut (Ctrl+C ...)
    if (st.mods.size && s.length === 1 && /[a-z0-9]/i.test(s)) {
      pressCode(/\d/.test(s) ? `Digit${s}` : `Key${s.toUpperCase()}`);
      return;
    }
    send({ t: 'text', s });
  }

  // --------------------------------------------------------- trackpad cursor
  function updateCursor() {
    const show = st.mode === 'trackpad' && st.frameW > 0 && st.hwnd;
    cursorEl.hidden = !show;
    if (!show) return;
    const p = fromNorm(st.cursor);
    cursorEl.style.left = `${p.x}px`;
    cursorEl.style.top = `${p.y}px`;
  }

  function keepCursorVisible() {
    const p = fromNorm(st.cursor);
    const sw = stage.clientWidth, sh = stage.clientHeight, m = 40;
    let dx = 0, dy = 0;
    if (p.x < m) dx = m - p.x; else if (p.x > sw - m) dx = sw - m - p.x;
    if (p.y < m) dy = m - p.y; else if (p.y > sh - m) dy = sh - m - p.y;
    if (dx || dy) { st.tx += dx; st.ty += dy; st.fitMode = false; applyTransform(); }
  }

  function moveCursorBy(dx, dy) {
    // finger px -> displayed px * speed; zooming in therefore gives finer control
    st.cursor.x = Math.min(1, Math.max(0, st.cursor.x + dx * st.speed / (st.frameW * st.scale)));
    st.cursor.y = Math.min(1, Math.max(0, st.cursor.y + dy * st.speed / (st.frameH * st.scale)));
    updateCursor();
    if (st.scale * st.frameW > stage.clientWidth || st.scale * st.frameH > stage.clientHeight) keepCursorVisible();
    queueMove(st.cursor);
  }

  // ------------------------------------------------------------- pointers
  const touches = new Map();   // pointerId -> {x, y}
  let one = null;              // single-finger gesture
  let pinch = null;            // two-finger gesture
  let lastTap = { t: 0, x: 0, y: 0, n: null };
  let wheelAcc = 0;

  const btnName = (b) => (b === 2 ? 'right' : b === 1 ? 'middle' : 'left');

  stage.addEventListener('contextmenu', (e) => e.preventDefault());

  stage.addEventListener('pointerdown', (e) => {
    if (!st.hwnd || !st.frameW) return;
    stage.setPointerCapture(e.pointerId);
    if (e.pointerType === 'mouse') {
      stage.focus();
      const n = toNorm(stagePoint(e.clientX, e.clientY));
      if (inside(n)) mouse('down', n, btnName(e.button));
      e.preventDefault();
      return;
    }
    touches.set(e.pointerId, stagePoint(e.clientX, e.clientY));
    if (touches.size === 1) startOne(e);
    else if (touches.size === 2) { cancelOne(); startPinch(); }
  });

  stage.addEventListener('pointermove', (e) => {
    if (!st.hwnd || !st.frameW) return;
    if (e.pointerType === 'mouse') {
      const n = toNorm(stagePoint(e.clientX, e.clientY));
      if (inside(n) || e.buttons) queueMove(n);
      return;
    }
    if (!touches.has(e.pointerId)) return;
    touches.set(e.pointerId, stagePoint(e.clientX, e.clientY));
    if (pinch) movePinch();
    else if (one && one.id === e.pointerId) moveOne(e);
  });

  const onUp = (e) => {
    if (e.pointerType === 'mouse') {
      if (!st.hwnd || !st.frameW) return;
      mouse('up', toNorm(stagePoint(e.clientX, e.clientY)), btnName(e.button));
      return;
    }
    if (!touches.has(e.pointerId)) return;
    touches.delete(e.pointerId);
    if (pinch) {
      if (touches.size < 2) endPinch();
    } else if (one && one.id === e.pointerId) {
      endOne(e.type === 'pointercancel');
    }
  };
  stage.addEventListener('pointerup', onUp);
  stage.addEventListener('pointercancel', onUp);

  function startOne(e) {
    const p = stagePoint(e.clientX, e.clientY);
    one = { id: e.pointerId, start: p, last: p, dragging: false, long: false, held: false, timer: 0 };
    one.timer = setTimeout(() => {
      if (!one || one.dragging) return;
      one.long = true;
      if (navigator.vibrate) navigator.vibrate(20);
      if (st.mode === 'pointer') {
        clickAt(toNorm(one.start), 'right');
      } else {
        mouse('down', st.cursor);       // long press = start dragging with the left button
        one.held = true;
      }
    }, LONG_PRESS_MS);
  }

  function moveOne(e) {
    const p = stagePoint(e.clientX, e.clientY);
    const dist = Math.hypot(p.x - one.start.x, p.y - one.start.y);
    if (!one.dragging && dist > DRAG_THRESHOLD) {
      one.dragging = true;
      clearTimeout(one.timer);
      if (st.mode === 'pointer' && !one.long) {
        mouse('down', toNorm(one.start));
        one.held = true;
      }
    }
    if (one.dragging) {
      if (st.mode === 'pointer') {
        if (one.held) queueMove(toNorm(p));
      } else {
        moveCursorBy(p.x - one.last.x, p.y - one.last.y);
      }
    }
    one.last = p;
  }

  function endOne(cancelled) {
    clearTimeout(one.timer);
    const g = one;
    one = null;
    if (g.held) {
      flushMove();
      mouse('up', st.mode === 'pointer' ? toNorm(g.last) : st.cursor);
      return;
    }
    if (cancelled || g.dragging || g.long) return;
    // a tap
    let n = st.mode === 'pointer' ? toNorm(g.start) : st.cursor;
    const now = performance.now();
    if (st.mode === 'pointer' && now - lastTap.t < DOUBLE_TAP_MS &&
        Math.hypot(g.start.x - lastTap.x, g.start.y - lastTap.y) < DOUBLE_TAP_PX) {
      n = lastTap.n;   // reuse the first tap's point so the host sees a double-click
    }
    if (!inside(n)) return;
    clickAt(n);
    lastTap = { t: now, x: g.start.x, y: g.start.y, n };
  }

  function cancelOne() {
    if (!one) return;
    clearTimeout(one.timer);
    if (one.held) mouse('up', st.mode === 'pointer' ? toNorm(one.last) : st.cursor);
    one = null;
  }

  function pts() { return [...touches.values()]; }

  function startPinch() {
    const [a, b] = pts();
    pinch = {
      d0: Math.hypot(a.x - b.x, a.y - b.y) || 1,
      m0: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      lastMid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      scale0: st.scale, tx0: st.tx, ty0: st.ty,
      t0: performance.now(), moved: false, scroll: 0,
    };
  }

  function movePinch() {
    const [a, b] = pts();
    if (!b) return;
    const d = Math.hypot(a.x - b.x, a.y - b.y);
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    if (Math.abs(d - pinch.d0) > 6 || Math.hypot(mid.x - pinch.m0.x, mid.y - pinch.m0.y) > 6) pinch.moved = true;
    if (st.mode === 'trackpad') {
      // two-finger drag = scroll the remote window
      pinch.scroll += mid.y - pinch.lastMid.y;
      const notches = Math.trunc(pinch.scroll / 15);
      if (notches) {
        wheelAt(st.cursor, notches * 120);
        pinch.scroll -= notches * 15;
      }
    } else {
      const ns = Math.min(16, Math.max(0.05, pinch.scale0 * d / pinch.d0));
      st.tx = mid.x - (pinch.m0.x - pinch.tx0) * (ns / pinch.scale0);
      st.ty = mid.y - (pinch.m0.y - pinch.ty0) * (ns / pinch.scale0);
      st.scale = ns;
      st.fitMode = false;
      applyTransform();
    }
    pinch.lastMid = mid;
  }

  function endPinch() {
    const quickTap = !pinch.moved && performance.now() - pinch.t0 < 300;
    if (quickTap && st.mode === 'trackpad') clickAt(st.cursor, 'right');
    pinch = null;
    touches.clear();   // ignore the finger still down until a fresh touch
  }

  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const p = stagePoint(e.clientX, e.clientY);
    if (e.ctrlKey) {               // also what trackpad pinch produces on desktop
      zoomAt(Math.exp(-e.deltaY * 0.01), p.x, p.y);
      return;
    }
    if (!st.hwnd || !st.frameW) return;
    const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 800 : 1;
    const horizontal = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY);
    wheelAcc += (horizontal ? (e.deltaX || e.deltaY) : e.deltaY) * unit;
    const notches = Math.trunc(wheelAcc / 100);
    if (!notches) return;
    wheelAcc -= notches * 100;
    const n = toNorm(p);
    wheelAt(n, horizontal ? notches * 120 : -notches * 120, horizontal);
  }, { passive: false });

  // ------------------------------------------------------- desktop keyboard
  stage.addEventListener('keydown', (e) => {
    if (!st.hwnd) return;
    e.preventDefault();
    send({ t: 'key', a: 'down', code: e.code });
  });
  stage.addEventListener('keyup', (e) => {
    if (!st.hwnd) return;
    e.preventDefault();
    send({ t: 'key', a: 'up', code: e.code });
  });
  stage.addEventListener('blur', () => send({ t: 'release' }));
  window.addEventListener('blur', () => send({ t: 'release' }));

  // -------------------------------------------------- mobile keyboard bar
  const kbdInput = $('#kbdInput');
  kbdInput.addEventListener('compositionend', (e) => {
    sendText(e.data);
    kbdInput.value = '';
  });
  kbdInput.addEventListener('input', (e) => {
    if (e.isComposing) return;
    if (e.inputType === 'insertText' && e.data) sendText(e.data);
    else if (e.inputType === 'deleteContentBackward') pressCode('Backspace');
    else if (e.inputType === 'insertLineBreak') pressCode('Enter');
    else if (e.inputType === 'insertFromPaste') sendText(kbdInput.value);
    else return;
    kbdInput.value = '';
  });
  kbdInput.addEventListener('keydown', (e) => {
    // physical keys on a tablet keyboard (not the IME)
    if (e.isComposing || e.keyCode === 229) return;
    if (['Enter', 'Backspace', 'Tab', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Delete'].includes(e.key)) {
      e.preventDefault();
      pressCode(e.code || e.key);
    }
  });

  $('#keybar').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.mod) {
      const m = b.dataset.mod;
      if (st.mods.has(m)) { st.mods.delete(m); b.classList.remove('on'); }
      else { st.mods.add(m); b.classList.add('on'); }
    } else if (b.dataset.code) {
      pressCode(b.dataset.code);
    } else if (b.dataset.combo) {
      pressCombo(b.dataset.combo);
    }
  });

  // ------------------------------------------------------------- toolbar
  winSelect.addEventListener('change', () => {
    const v = winSelect.value;
    if (!v) return;
    st.hwnd = Number(v);
    st.frameW = 0;
    send({ t: 'select', hwnd: st.hwnd });
    stage.focus();
  });
  $('#btnRefresh').addEventListener('click', () => send({ t: 'list' }));
  $('#btnZoomIn').addEventListener('click', () => zoomAt(1.25, stage.clientWidth / 2, stage.clientHeight / 2));
  $('#btnZoomOut').addEventListener('click', () => zoomAt(0.8, stage.clientWidth / 2, stage.clientHeight / 2));
  $('#btnFit').addEventListener('click', fit);

  const btnMode = $('#btnMode');
  function setMode(mode) {
    st.mode = mode;
    store.set('mode', mode);
    btnMode.textContent = mode === 'pointer' ? '포인터' : '트랙패드';
    btnMode.classList.toggle('on', mode === 'trackpad');
    updateCursor();
  }
  btnMode.addEventListener('click', () => setMode(st.mode === 'pointer' ? 'trackpad' : 'pointer'));

  $('#btnKbd').addEventListener('click', () => {
    const bar = $('#keybar');
    bar.hidden = !bar.hidden;
    $('#btnKbd').classList.toggle('on', !bar.hidden);
    if (!bar.hidden) kbdInput.focus();
    setTimeout(() => { if (st.fitMode) fit(); }, 50);
  });

  // ------------------------------------------------------------ settings
  const settingsEl = $('#settings');
  const setFields = { fps: $('#setFps'), quality: $('#setQuality'), maxw: $('#setMaxw'), method: $('#setMethod') };
  for (const [k, el] of Object.entries(setFields)) {
    const saved = store.get(k);
    if (saved !== null && saved !== '') el.value = saved;
    el.addEventListener('change', () => { store.set(k, el.value); sendSettings(); });
  }
  const speedEl = $('#setSpeed');
  speedEl.value = String(st.speed);
  speedEl.addEventListener('input', () => { st.speed = parseFloat(speedEl.value); store.set('speed', speedEl.value); });

  function sendSettings() {
    send({
      t: 'settings',
      fps: Number(setFields.fps.value), quality: Number(setFields.quality.value),
      maxw: Number(setFields.maxw.value), method: setFields.method.value,
    });
  }
  $('#btnSettings').addEventListener('click', () => { settingsEl.hidden = !settingsEl.hidden; });
  $('#btnCloseSettings').addEventListener('click', () => { settingsEl.hidden = true; });

  // -------------------------------------------------------------- status
  function setStatus(s) { statusEl.dataset.base = s; renderStatus(); }
  function renderStatus() {
    const parts = [statusEl.dataset.base || ''];
    if (st.authed && st.rtt !== null) parts.push(`${st.rtt}ms`);
    if (st.authed && st.hwnd) parts.push(`${st.fps}fps`);
    statusEl.textContent = parts.join(' · ');
  }
  function showOverlay(text) {
    overlay.hidden = !text;
    if (text) overlay.textContent = text;
  }

  setInterval(() => {
    st.fps = st.frames; st.frames = 0;
    if (st.authed) send({ t: 'ping', ts: performance.now() });
    renderStatus();
  }, 1000);

  window.addEventListener('resize', () => { if (st.fitMode) fit(); else applyTransform(); });

  // ---------------------------------------------------------------- start
  setMode(st.mode);
  st.token = getToken();
  connect();

  // exposed for automated tests
  window.__wr = { st, toNorm, fromNorm };
})();
