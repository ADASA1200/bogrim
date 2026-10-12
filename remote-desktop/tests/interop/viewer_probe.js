// צופה בדפדפן (libwebrtc של Chromium - אותו מנוע כמו באנדרואיד) שמיישם את פרוטוקול RDesk
// בדיוק כמו אפליקציית ה-Kotlin. משמש לבדיקת תאימות מול המארח האמיתי (aiortc).
// שימוש: node viewer_probe.js <pageUrl> <wsUrl> <hostId> [password]
const { chromium } = require('playwright');

(async () => {
  const [pageUrl, wsUrl, hostId, password = ''] = process.argv.slice(2);
  const browser = await chromium.launch({
    args: ['--no-sandbox', '--disable-features=WebRtcHideLocalIpsWithMdns'],
  });
  const page = await browser.newPage();
  page.on('console', (m) => process.stderr.write('[page] ' + m.text() + '\n'));
  await page.goto(pageUrl);
  const result = await page.evaluate(async ({ wsUrl, hostId, password }) => {
    const enc = new TextEncoder();
    const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    async function deriveKey(pw) {
      const k = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveBits']);
      return new Uint8Array(await crypto.subtle.deriveBits(
        { name: 'PBKDF2', salt: enc.encode('rdesk-v1'), iterations: 200000, hash: 'SHA-256' }, k, 256));
    }
    async function authTag(key, nonce, role, sdp) {
      const k = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
      return hex(await crypto.subtle.sign('HMAC', k, enc.encode(`${role}\n${nonce}\n${sdp}`)));
    }
    async function sha256(s) { return new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(s))); }
    const fp = (sdp) => { const m = /a=fingerprint:sha-256 ([0-9A-Fa-f:]+)/.exec(sdp); return m ? m[1].toUpperCase() : ''; };
    async function sessionCode(o, a) {
      const h = await sha256(fp(o) + '|' + fp(a));
      const n = ((h[0] * 2 ** 24) + (h[1] << 16) + (h[2] << 8) + h[3]) % 1000000;
      const s = String(n).padStart(6, '0');
      return s.slice(0, 3) + ' ' + s.slice(3);
    }

    const out = { steps: [] };
    const inbox = [];
    let waiter = null;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (e) => { const m = JSON.parse(e.data); if (waiter) { const w = waiter; waiter = null; w(m); } else inbox.push(m); };
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws error')); });
    const next = (ms = 15000) => new Promise((res, rej) => {
      if (inbox.length) return res(inbox.shift());
      const t = setTimeout(() => { waiter = null; rej(new Error('timeout')); }, ms);
      waiter = (m) => { clearTimeout(t); res(m); };
    });
    const relayTo = (payload) => ws.send(JSON.stringify({ type: 'relay', to: hostId, payload }));

    ws.send(JSON.stringify({ type: 'register', id: 'v' + Math.random().toString(16).slice(2, 14) }));
    if ((await next()).type !== 'registered') throw new Error('register failed');
    relayTo({ kind: 'hello' });
    let m = await next();
    if (m.type === 'unreachable') { out.error = 'host not found / offline'; return out; }
    if (m.payload.kind === 'reject') { out.error = m.payload.reason; return out; }
    const nonce = m.payload.nonce;
    out.steps.push('challenge');
    const key = password ? await deriveKey(password) : null;

    const pc = new RTCPeerConnection({ iceServers: [] });
    pc.addTransceiver('video', { direction: 'recvonly' });
    const control = pc.createDataChannel('control');
    const files = pc.createDataChannel('files');
    const helloP = new Promise((res) => { control.onmessage = (e) => handleControl(JSON.parse(e.data), res); });
    out.chat = []; out.clip = null;
    function handleControl(msg, helloRes) {
      if (msg.t === 'hello') { out.hello = msg; helloRes(msg); }
      else if (msg.t === 'chat') out.chat.push(msg.text);
      else if (msg.t === 'clip') out.clip = msg.text;
      else if (msg.t === 'perms') out.perms = msg.perms;
      else if (msg.t === 'bye') out.bye = true;
    }
    out.files = { text: [], bin: 0 };
    files.binaryType = 'arraybuffer';
    files.onmessage = (e) => { if (typeof e.data === 'string') out.files.text.push(JSON.parse(e.data)); else out.files.bin += e.data.byteLength; };

    await pc.setLocalDescription(await pc.createOffer());
    if (pc.iceGatheringState !== 'complete') {
      await new Promise((res) => { pc.onicegatheringstatechange = () => pc.iceGatheringState === 'complete' && res(); setTimeout(res, 8000); });
    }
    const offerSdp = pc.localDescription.sdp;
    relayTo({ kind: 'offer', sdp: offerSdp, auth: key ? await authTag(key, nonce, 'viewer', offerSdp) : null });
    out.steps.push('offer-sent');

    m = await next(60000);
    const ans = m.payload;
    if (ans.kind === 'reject') { out.error = ans.reason; return out; }
    out.mode = 'interactive';
    if (ans.auth !== null && ans.auth !== undefined) {
      if (!key || (await authTag(key, nonce, 'host', ans.sdp)) !== ans.auth) { out.error = 'host authentication failed'; return out; }
      out.mode = 'unattended';
    }
    out.code = await sessionCode(offerSdp, ans.sdp);
    await pc.setRemoteDescription({ type: 'answer', sdp: ans.sdp });
    out.steps.push('answer-ok');
    await Promise.race([helloP, sleep(20000).then(() => { throw new Error('no hello'); })]);
    ws.close();

    // וידאו: מחכים לפריימים מפוענחים
    let frames = 0;
    for (let i = 0; i < 100 && frames < 5; i++) {
      await sleep(100);
      for (const r of (await pc.getStats()).values()) if (r.type === 'inbound-rtp' && r.kind === 'video') frames = r.framesDecoded || 0;
    }
    out.frames = frames;

    // קלט ושליחות
    const send = (o) => control.send(JSON.stringify(o));
    send({ t: 'mm', x: 0.5, y: 0.25 });
    send({ t: 'md', b: 'left', x: 0.5, y: 0.25 }); send({ t: 'mu', b: 'left', x: 0.5, y: 0.25 });
    send({ t: 'ms', dx: 0, dy: 1 });
    send({ t: 'kd', k: 'a' }); send({ t: 'ku', k: 'a' });
    send({ t: 'chat', text: 'שלום מהדפדפן' });
    send({ t: 'clip', text: 'clip from probe' });
    send({ t: 'cfg', fps: 10, scale: 0.5 });

    // קובץ (ערוץ files): JSON start -> בינארי -> end
    const payload = new Uint8Array(40000).map((_, i) => i % 251);
    files.send(JSON.stringify({ op: 'start', name: 'probe.bin', size: payload.length }));
    for (let o = 0; o < payload.length; o += 16384) files.send(payload.slice(o, o + 16384));
    files.send(JSON.stringify({ op: 'end' }));

    await sleep(2500);
    out.chatEchoed = out.chat.length;
    send({ t: 'bye' });
    await sleep(300);
    pc.close();
    return out;
  }, { wsUrl, hostId, password });
  console.log(JSON.stringify(result));
  await browser.close();
})().catch((e) => { console.log(JSON.stringify({ error: 'probe crashed: ' + e.message })); process.exit(0); });
