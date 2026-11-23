// Galvor Social Studio — shared UI helpers
function toast(msg, ms) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => (t.style.display = 'none'), ms || 2600);
}
function toggleTheme() {
  const r = document.documentElement;
  const next = r.dataset.theme === 'dark' ? 'light' : 'dark';
  r.dataset.theme = next;
  try { localStorage.setItem('gss-theme', next); } catch (e) {}
}
async function api(url, body) {
  let r;
  try { r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); }
  catch (e) { return { ok: false, error: "Can't reach the Studio. It may have stopped: start it with start_studio.bat, then try again." }; }
  let j = {};
  try { j = await r.json(); } catch (e) { j = { ok: false, error: 'Server error (' + r.status + ')' }; }
  if (!r.ok && j.ok === undefined) j.ok = false;
  return j;
}
async function copyText(text, label) {
  try { await navigator.clipboard.writeText(text); toast((label || 'Copied') + ' ✓'); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove(); toast((label || 'Copied') + ' ✓');
  }
}
async function setStatus(id, status, extra) {
  const j = await api('/api/post/' + encodeURIComponent(id) + '/status', Object.assign({ status }, extra || {}));
  if (!j.ok) { toast(j.error || 'Failed', 6000); return false; }
  toast(j.message || ('Marked ' + status.replace('_', ' ') + (j.notified ? ' · ' + j.notified + ' notified' : '')), j.message ? 4000 : 2600);
  setTimeout(() => location.reload(), j.message ? 1800 : 600);
  return true;
}
// "Send for review": pick approvers (pre-ticked with the routing rule's picks), add a note, send.
function sendForReview(id, defaults, before) {
  const m = document.getElementById('reviewm');
  const want = (defaults || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  m.querySelectorAll('#reviewlist input').forEach(c => { c.checked = want.includes(c.value.toLowerCase()); });
  document.getElementById('reviewnote').value = '';
  document.getElementById('reviewgo').onclick = async () => {
    const reviewers = [...m.querySelectorAll('#reviewlist input:checked')].map(c => c.value);
    if (!reviewers.length) { toast('Pick at least one approver'); return; }
    if (before && !(await before())) return;
    m.classList.remove('on');
    setStatus(id, 'in_review', { reviewers, note: document.getElementById('reviewnote').value });
  };
  m.classList.add('on');
}
async function markPublished(id) {
  const url = prompt('Paste the live post URL (optional):', '');
  if (url === null) return;
  setStatus(id, 'published', { url });
}
function openAsk() { document.getElementById('askm').classList.add('on'); setTimeout(() => document.getElementById('askq').focus(), 50); }
async function askGo(e) {
  e.preventDefault();
  const q = document.getElementById('askq').value.trim(); if (!q) return false;
  const a = document.getElementById('aska'); a.innerHTML = '<span class="spinner"></span> Thinking…';
  const j = await api('/api/ask', { q });
  a.textContent = j.ok ? j.a : (j.error || 'Failed');
  return false;
}
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); const q = document.getElementById('q'); q && q.focus(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); openAsk(); }
  if (e.key === 'Escape') { document.getElementById('askm').classList.remove('on'); const r = document.getElementById('reviewm'); r && r.classList.remove('on'); }
});
