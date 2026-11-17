// Post editor: tabs, slide editor, scenes, save / render / AI / metrics
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let SLIDES = JSON.parse(JSON.stringify((POST.creative && POST.creative.slides) || []));
let SCENES = JSON.parse(JSON.stringify((POST.script && POST.script.scenes) || []));
let dirty = false;

// ---------- tabs
document.querySelectorAll('#tabs button').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('#tabs button').forEach((x) => x.classList.remove('on'));
  document.querySelectorAll('.tab').forEach((x) => x.classList.remove('on'));
  b.classList.add('on'); $('t-' + b.dataset.t).classList.add('on');
}));
document.addEventListener('input', () => { dirty = true; });
window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

// ---------- caption counter + feed preview
function count() {
  const c = $('caption'); if (!c) return;
  const v = c.value, first = (v.split('\n')[0] || '');
  const el = $('capcount');
  el.textContent = `${v.length.toLocaleString()} / ${LIMIT.toLocaleString()} chars` + (SEE ? ` · first line ${first.length}/${SEE}` : '');
  el.classList.toggle('over', v.length > LIMIT || (SEE && first.length > SEE));
  const fp = $('feedprev');
  if (fp) {
    const cut = SEE ? v.slice(0, SEE) : v;
    const tags = $('hashtags').value.trim();
    fp.innerHTML = '<b>' + esc(POST.voice === 'company' ? 'Galvor' : ({ sunil: 'Sunil Humne', raj: 'Raj Dhakad', shrutik: 'Shrutik Rathod', kc: 'KC' }[POST.voice] || 'Galvor')) + '</b>\n' +
      esc(cut) + (v.length > SEE && SEE ? '<span style="color:var(--muted)">… see more</span>' : '') +
      (v.length <= SEE && tags ? '\n\n<span style="color:var(--li)">' + esc(tags) + '</span>' : '');
  }
}
count();

// ---------- slide editor
const FIELDS = {
  cover: ['kicker', 'headline', 'sub', 'play'], statement: ['headline', 'sub'], text: ['kicker', 'headline', 'body'],
  stat: ['kicker', 'stat', 'headline', 'sub', 'source'], list: ['kicker', 'headline', 'items'],
  compare: ['kicker', 'headline', 'left_title', 'left', 'right_title', 'right'], poll: ['kicker', 'headline', 'options', 'sub'],
  festival: ['motif', 'kicker', 'greeting', 'headline', 'sub'], cta: ['headline', 'sub', 'actions'],
};
const ARRAYS = ['items', 'options', 'left', 'right', 'actions'];
const BIG = ['headline', 'body', 'sub', 'items', 'left', 'right', 'options', 'actions'];

function drawSlides() {
  const box = $('slides'); if (!box) return;
  box.innerHTML = SLIDES.map((s, i) => {
    const fields = FIELDS[s.layout] || ['headline'];
    const inputs = fields.map((f) => {
      let v = s[f]; if (ARRAYS.includes(f)) v = (v || []).map((x) => (typeof x === 'object' ? (x.title + (x.detail ? ' — ' + x.detail : '')) : x)).join('\n');
      const tag = BIG.includes(f) ? `<textarea class="in" style="min-height:${ARRAYS.includes(f) || f === 'body' ? 100 : 56}px" data-i="${i}" data-f="${f}">${esc(v)}</textarea>`
        : `<input class="in" data-i="${i}" data-f="${f}" value="${esc(v)}">`;
      return `<div><label class="f">${f.replace('_', ' ')}${ARRAYS.includes(f) ? ' <small>(one per line)</small>' : ''}</label>${tag}</div>`;
    }).join('');
    return `<div class="slide-ed"><div class="hd"><b>Slide ${i + 1}</b>
      <select class="in" style="width:auto" data-i="${i}" data-layout>${LAYOUTS.map((l) => `<option ${l === s.layout ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <button class="btn sm" onclick="mv(${i},-1)">↑</button><button class="btn sm" onclick="mv(${i},1)">↓</button><button class="btn sm danger" onclick="rm(${i})">✕</button></div>
      <div class="two">${inputs}</div></div>`;
  }).join('') || '<div class="empty">No slides yet.</div>';
  box.querySelectorAll('[data-f]').forEach((el) => el.addEventListener('input', () => {
    const s = SLIDES[+el.dataset.i], f = el.dataset.f;
    s[f] = ARRAYS.includes(f) ? el.value.split('\n').map((x) => x.trim()).filter(Boolean) : el.value;
  }));
  box.querySelectorAll('[data-layout]').forEach((el) => el.addEventListener('change', () => { SLIDES[+el.dataset.i].layout = el.value; drawSlides(); }));
}
function addSlide() { SLIDES.push({ layout: SLIDES.length ? 'list' : 'cover', headline: '' }); drawSlides(); dirty = true; }
function mv(i, d) { const j = i + d; if (j < 0 || j >= SLIDES.length) return; [SLIDES[i], SLIDES[j]] = [SLIDES[j], SLIDES[i]]; drawSlides(); dirty = true; }
function rm(i) { if (confirm('Remove slide ' + (i + 1) + '?')) { SLIDES.splice(i, 1); drawSlides(); dirty = true; } }
drawSlides();

// ---------- scenes
function drawScenes() {
  const box = $('scenes'); if (!box) return;
  box.innerHTML = SCENES.map((s, i) => `<div class="scene">
    <input class="in" data-s="${i}" data-k="time" value="${esc(s.time)}">
    <textarea class="in" data-s="${i}" data-k="visual">${esc(s.visual)}</textarea>
    <textarea class="in" data-s="${i}" data-k="voiceover">${esc(s.voiceover)}</textarea>
    <textarea class="in" data-s="${i}" data-k="on_screen">${esc(s.on_screen)}</textarea>
    <button class="btn sm danger" onclick="SCENES.splice(${i},1);drawScenes()">✕</button></div>`).join('');
  box.querySelectorAll('[data-s]').forEach((el) => el.addEventListener('input', () => { SCENES[+el.dataset.s][el.dataset.k] = el.value; }));
}
function addScene() { SCENES.push({ time: '', visual: '', voiceover: '', on_screen: '' }); drawScenes(); }
drawScenes();

// ---------- collect + save
function collect() {
  const val = (id) => ($(id) ? $(id).value : undefined);
  const d = {
    caption: val('caption'), hashtags: val('hashtags'), first_comment: val('first_comment'), alt_text: val('alt_text'), cta: val('cta'),
    date: val('date'), time: val('time'), format: val('format'), pillar: val('pillar'), job: val('job'), series: val('series'),
    festival: val('festival') || null, topic_ref: val('topic_ref'), title: val('title'), hook: val('hook'), notes: val('notes'),
    creative: { size: val('csize') || 'feed', slides: SLIDES },
  };
  if ($('voice') && !$('voice').disabled) d.voice = val('voice');
  if ($('scenes')) d.script = { duration: val('sc_duration'), music: val('sc_music'), setup: val('sc_setup'), notes: val('sc_notes'), scenes: SCENES };
  if ($('poll_q')) d.poll = { question: val('poll_q'), options: val('poll_o').split('\n').map((x) => x.trim()).filter(Boolean), duration: val('poll_d') };
  if ($('nl_draft')) d.newsletter = Object.assign({}, POST.newsletter || {}, { draft_markdown: val('nl_draft') });
  return d;
}
function showIssues(issues) {
  $('issues').innerHTML = issues.length ? issues.map((i) => `<li class="${i.severity}"><b>${esc(i.field)}</b> — ${esc(i.message)}</li>`).join('') : '<li class="ok">All checks pass.</li>';
}
async function saveAll() {
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/save', collect());
  if (!j.ok) { toast(j.error || 'Save failed', 5000); return false; }
  dirty = false; showIssues(j.issues);
  if (j.message) { toast(j.message, 6000); setTimeout(() => (location.href = '/post/' + j.id), 1500); return true; }
  if (j.id !== PID) { location.href = '/post/' + j.id; return true; }
  toast('Saved'); return true;
}
async function renderImgs() {
  const b = $('renderBtn'); b.disabled = true; b.innerHTML = '<span class="spinner"></span> Rendering…';
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/render', collect());
  b.disabled = false; b.textContent = 'Render images';
  if (!j.ok) { toast(j.error || 'Render failed', 6000); return; }
  dirty = false; toast('Rendered ' + j.images.length + ' file(s)');
  setTimeout(() => (location.href = '/post/' + j.id), 400);
}
function copyCaption() {
  const tags = $('hashtags').value.trim();
  copyText($('caption').value.trim() + (tags ? '\n\n' + tags : ''), 'Caption copied');
}
async function aiRun(ins, mode) {
  if (!ins && mode !== 'draft') { toast('Write an instruction first'); return; }
  if (!(await saveAll())) return;
  $('aispin').innerHTML = '<span class="spinner"></span> Writing…';
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/ai', { instruction: ins, mode: mode || 'edit' });
  $('aispin').textContent = '';
  if (!j.ok) { toast(j.error || 'AI failed', 7000); return; }
  dirty = false; location.href = '/post/' + j.id;
}
async function publishNow() {
  if (!confirm('Publish this post to ' + POST.platform + ' now?')) return;
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/publish');
  if (!j.ok) { toast(j.error || 'Publish failed', 8000); return; }
  toast('Published ✓'); setTimeout(() => location.reload(), 800);
}
async function saveMetrics() {
  const m = {}; document.querySelectorAll('#metrics [data-k]').forEach((el) => (m[el.dataset.k] = el.value));
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/metrics', m);
  const u = await api('/api/post/' + encodeURIComponent(PID) + '/save', { published_url: $('published_url').value });
  toast(j.ok && u.ok ? 'Results saved' : 'Save failed');
}
async function dup(platform) {
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/duplicate', { platform });
  if (j.ok) location.href = '/post/' + j.id; else toast('Failed');
}
async function del() {
  if (!confirm('Delete this post and its folder? This cannot be undone.')) return;
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/delete');
  if (j.ok) { dirty = false; location.href = '/content/' + POST.platform; }
}
document.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveAll(); } });

async function repurpose(kind) {
  if (!(await saveAll())) return;
  toast('Repurposing with AI… (20–40 s)', 40000);
  const j = await api('/api/post/' + encodeURIComponent(PID) + '/repurpose', { kind });
  if (!j.ok) { toast(j.error || 'Failed', 6000); return; }
  if (j.message) alert(j.message);
  location.href = '/post/' + encodeURIComponent(j.id);
}
