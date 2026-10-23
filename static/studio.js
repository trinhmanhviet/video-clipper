import { clampTrimHandle } from './trim-range.mjs';
const $ = id => document.getElementById(id);
let media = null, currentJob = null, polling = null, previewEnd = null;
let uploadBusy = false, jobActive = false;
let lastMediaTouch = -Infinity;

function message(error) {
  $('error').textContent = String(error.message || error);
  $('error').hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw Error('Máy xử lý chưa trả lời. Thử lại sau vài giây.'); }
  if (!response.ok) {
    const error = Error(data.error || 'Yêu cầu lỗi (' + response.status + ')');
    error.status = response.status;
    throw error;
  }
  return data;
}
function post(path, data) {
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
}
async function keepMediaAlive() {
  if (!media || uploadBusy || jobActive || document.visibilityState !== 'visible') return;
  if (performance.now() - lastMediaTouch < 30000) return;
  lastMediaTouch = performance.now();
  const ident = media.id;
  try { await post('/api/media/' + ident + '/touch', {}); }
  catch (error) {
    if (error.status === 410 && media && media.id === ident && !jobActive && !uploadBusy) {
      clearMedia(); message(error);
    }
  }
}
function format(value) {
  let ms = Math.round(Math.max(0, Number(value) || 0) * 1000);
  const h = Math.floor(ms / 3600000); ms %= 3600000;
  const m = Math.floor(ms / 60000); ms %= 60000;
  const s = Math.floor(ms / 1000);
  return [h,m,s].map(n => String(n).padStart(2,'0')).join(':') + '.' + String(ms % 1000).padStart(3,'0');
}
function parse(value) {
  const parts = String(value).trim().split(':').map(Number);
  if (parts.some(n => !Number.isFinite(n)) || parts.length > 3)
    throw Error('Mốc thời gian không hợp lệ. Dùng dạng 00:01:23.456.');
  return parts.reduce((a,b) => a*60+b, 0);
}
function selection() {
  const start = parse($('start').value), end = parse($('end').value);
  if (!media || start < 0 || end <= start || end > media.duration + .01)
    throw Error('Mốc kết thúc phải sau mốc bắt đầu và nằm trong video.');
  return {start,end};
}
function syncControls() {
  const unavailable = !media || uploadBusy;
  for (const id of ['start','end','start-range','end-range','back-frame','next-frame','set-start','set-end','preview','format','height','frames','frame-format','fps'])
    $(id).disabled = unavailable;
  $('export').disabled = unavailable || jobActive;
  for (const id of ['file','choose-video','import','remove-video'])
    $(id).disabled = uploadBusy || jobActive;
  $('remove-video').hidden = !media;
}
function update() {
  if (!media) return;
  try {
    const {start,end} = selection();
    $('export-duration').textContent = (end-start).toFixed(3) + ' giây';
    $('start-range').value = start; $('end-range').value = end;
    $('range-fill').style.left = (100*start/media.duration) + '%';
    $('range-fill').style.width = (100*(end-start)/media.duration) + '%';
    $('start-range').setAttribute('aria-valuetext', format(start));
    $('end-range').setAttribute('aria-valuetext', format(end));
    $('range-caption').textContent = format(start) + ' – ' + format(end);
    $('selection').textContent = 'Độ dài đoạn: ' + (end-start).toFixed(3) + ' giây';
    $('estimate').textContent = $('frames').checked
      ? 'Khoảng ' + Math.ceil((end-start)*($('fps').value ? Number($('fps').value) : media.fps)) + ' ảnh frame. JPG nhẹ hơn PNG.' : '';
    localStorage.setItem('clip-v2-selection', JSON.stringify({media_id:media.id,start:$('start').value,end:$('end').value}));
  } catch (error) {
    $('selection').textContent = error.message;
    $('export-duration').textContent = '—';
  }
}
function applyMedia(data, restore = false) {
  media = data; previewEnd = null;
  document.body.classList.add('has-media');
  $('empty-picker').hidden = true; $('video').hidden = false;
  $('video').src = data.stream_url;
  $('media-name').textContent = data.name;
  $('media-info').textContent = data.width + ' × ' + data.height + ' · ' + data.fps.toFixed(2) + ' fps · ' + format(data.duration);
  for (const id of ['start-range','end-range']) $(id).max = data.duration;
  $('start').value = format(0); $('end').value = format(data.duration);
  if (restore) {
    try {
      const saved = JSON.parse(localStorage.getItem('clip-v2-selection'));
      if (saved && saved.media_id === data.id) { $('start').value = saved.start; $('end').value = saved.end; }
    } catch {}
  }
  localStorage.setItem('clip-v2-media', data.id);
  update(); syncControls();
}
function clearMedia() {
  if (uploadBusy || jobActive) return;
  $('video').pause(); $('video').removeAttribute('src'); $('video').load();
  $('result-video').pause(); $('result-video').removeAttribute('src'); $('result-video').load();
  media = null; previewEnd = null; currentJob = null; clearTimeout(polling);
  document.body.classList.remove('has-media');
  $('video').hidden = true; $('empty-picker').hidden = false;
  $('media-name').textContent = 'Chưa chọn video';
  $('media-info').textContent = 'MP4, MOV, MKV, WebM · Tối đa 2 GB';
  $('file').value = ''; $('current-time').textContent = format(0);
  $('start').value = format(0); $('end').value = format(0);
  for (const id of ['start-range','end-range']) $(id).max = 1;
  $('start-range').value = 0; $('end-range').value = 1;
  $('range-caption').textContent = '—'; $('range-fill').style.left = '0%'; $('range-fill').style.width = '0%';
  $('export-duration').textContent = '—'; $('selection').textContent = 'Độ dài đoạn: —';
  $('upload-note').textContent = ''; $('upload-progress').hidden = true;
  $('job-card').hidden = true; $('error').hidden = true; $('estimate').textContent = '';
  for (const key of ['clip-v2-media','clip-v2-selection','clip-v2-job','clip-v2-upload']) localStorage.removeItem(key);
  syncControls(); $('choose-video').focus();
}
async function upload(file) {
  if (!file || uploadBusy || jobActive) return;
  uploadBusy = true; syncControls();
  $('error').hidden = true; $('upload-progress').hidden = false; $('upload-progress').value = 0;
  try {
    const key = file.name + ':' + file.size + ':' + file.lastModified;
    let item;
    try {
      const previous = JSON.parse(localStorage.getItem('clip-v2-upload'));
      if (previous && previous.key === key) {
        const state = await api('/api/uploads/' + previous.id);
        if (state.media_id) { applyMedia(await api('/api/media/' + state.media_id)); return; }
        item = {id:previous.id,offset:state.offset};
      }
    } catch {}
    if (!item) item = await post('/api/uploads', {name:file.name,size:file.size});
    localStorage.setItem('clip-v2-upload', JSON.stringify({key,id:item.id}));
    let offset = item.offset;
    const begun = performance.now();
    while (offset < file.size) {
      const end = Math.min(file.size, offset + 4*1024*1024);
      let sent = false;
      for (let attempt=0; attempt<3 && !sent; attempt++) {
        try {
          const r = await fetch('/api/uploads/' + item.id + '?offset=' + offset,
            {method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file.slice(offset,end)});
          const data = await r.json();
          if (r.status === 409 || r.ok) { offset=data.offset; sent=true; }
          else throw Error(data.error || 'Tải lên không thành công');
        } catch (error) {
          if (attempt === 2) throw error;
          await new Promise(resolve => setTimeout(resolve,1000));
        }
      }
      const pct = offset/file.size*100;
      $('upload-progress').value = pct;
      $('upload-note').textContent = 'Đang tải: ' + pct.toFixed(0) + '% · ' + (offset/1048576).toFixed(1)
        + ' / ' + (file.size/1048576).toFixed(1) + ' MB · ' + ((performance.now()-begun)/1000).toFixed(0) + ' giây';
    }
    applyMedia(await post('/api/uploads/' + item.id + '/complete', {}));
    $('upload-note').textContent = ''; $('upload-progress').hidden = true;
    localStorage.removeItem('clip-v2-upload');
  } catch (error) {
    message(error);
    $('upload-note').textContent = 'Tải lên bị gián đoạn. Chọn lại cùng file để tiếp tục từ phần đã tải.';
  } finally {
    uploadBusy = false; syncControls(); $('file').value = '';
  }
}
async function follow(id) {
  currentJob = id; jobActive = true; syncControls();
  localStorage.setItem('clip-v2-job',id);
  $('job-card').hidden = false; $('result').hidden = true; clearTimeout(polling);
  async function tick() {
    try {
      const job = await api('/api/jobs/' + id);
      const titles = {queued:'Đang chờ tới lượt',completed:'Đã hoàn thành',error:'Xử lý không thành công',cancelled:'Đã hủy',processing:'Đang xử lý',expired:'File đã tự dọn'};
      $('job-title').textContent = titles[job.status] || 'Đang xử lý';
      $('job-progress').value = job.progress;
      $('percent').textContent = Math.round(job.progress) + '%';
      $('elapsed').textContent = 'Đã chạy ' + Math.max(0,job.elapsed || 0).toFixed(0) + ' giây';
      $('job-message').textContent = job.error || job.message;
      $('cancel').hidden = !['queued','processing'].includes(job.status);
      if (job.status === 'completed') {
        if (job.kind === 'import') {
          applyMedia(await api('/api/media/' + job.result.media_id),true);
          $('job-message').textContent = 'Đã tải video từ liên kết. Chọn đoạn cần xuất bên trên.';
        } else {
          const r = job.result; $('result').hidden = false;
          $('download-video').href = r.video_url + '?download=1';
          $('download-video').textContent = r.video.endsWith('.mp3') ? 'Tải MP3' : 'Tải MP4';
          $('download-frames').hidden = !r.frames_url;
          if (r.frames_url) {
            $('download-frames').href = r.frames_url + '?download=1';
            $('download-frames').textContent = 'Tải ' + r.frames_count + ' frame (ZIP)';
          }
          $('result-video').hidden = r.video.endsWith('.mp3');
          if (!r.video.endsWith('.mp3')) $('result-video').src = r.video_url;
        }
      }
      if (['completed','error','cancelled','expired'].includes(job.status)) { jobActive=false; syncControls(); return; }
      polling = setTimeout(tick,1000);
    } catch {
      $('job-message').textContent = 'Đang kết nối lại máy xử lý…';
      polling = setTimeout(tick,3000);
    }
  }
  await tick();
}
$('choose-video').onclick = () => $('file').click();
$('remove-video').onclick = clearMedia;
$('file').addEventListener('change',e => upload(e.target.files[0]));
$('drop').addEventListener('dragover',e => { e.preventDefault(); if (!uploadBusy && !jobActive) $('drop').classList.add('drag'); });
$('drop').addEventListener('dragleave',e => { if (!$('drop').contains(e.relatedTarget)) $('drop').classList.remove('drag'); });
$('drop').addEventListener('drop',e => { e.preventDefault(); $('drop').classList.remove('drag'); upload(e.dataTransfer.files[0]); });
$('import').onclick = async () => {
  if (uploadBusy || jobActive) return;
  try {
    $('error').hidden=true; jobActive=true; syncControls();
    const job = await post('/api/import',{url:$('url').value.trim()}); await follow(job.id);
  } catch (error) { jobActive=false; syncControls(); message(error); }
};
for (const id of ['start','end']) {
  $(id).addEventListener('input',update); $(id).addEventListener('change',update);
}
for (const edge of ['start','end']) {
  $(edge+'-range').addEventListener('input',() => {
    if (!media) return;
    const other = edge === 'start' ? 'end' : 'start';
    const otherValue = Number($(other+'-range').value);
    $(other).value = format(otherValue);
    const value = clampTrimHandle(edge,Number($(edge+'-range').value),otherValue,media.duration,media.fps);
    $(edge).value = format(value); $('video').currentTime=value; update();
  });
  $('set-'+edge).onclick = () => { $(edge).value=format($('video').currentTime); update(); };
}
$('back-frame').onclick = () => { if (media) { $('video').pause(); $('video').currentTime=Math.max(0,$('video').currentTime-1/media.fps); } };
$('next-frame').onclick = () => { if (media) { $('video').pause(); $('video').currentTime=Math.min(media.duration,$('video').currentTime+1/media.fps); } };
$('video').ontimeupdate = () => {
  $('current-time').textContent=format($('video').currentTime);
  if (!$('video').paused) keepMediaAlive();
  if (previewEnd !== null && $('video').currentTime >= previewEnd) { $('video').pause(); previewEnd=null; }
};
$('preview').onclick = () => {
  try { const {start,end}=selection(); $('video').currentTime=start; previewEnd=end; $('video').play().catch(message); }
  catch (error) { message(error); }
};
$('frames').onchange = () => { $('frame-options').hidden=!$('frames').checked; update(); };
$('fps').onchange = update;
$('export').onclick = async () => {
  if (uploadBusy || jobActive) return;
  try {
    $('error').hidden=true; const {start,end}=selection(); update(); jobActive=true; syncControls();
    const job = await post('/api/jobs',{media_id:media.id,start,end,format:$('format').value,
      height:$('height').value ? Number($('height').value) : null,frames:$('frames').checked,
      frame_format:$('frame-format').value,fps:$('fps').value ? Number($('fps').value) : null});
    await follow(job.id);
  } catch (error) { jobActive=false; syncControls(); message(error); }
};
$('cancel').onclick = async () => { try { if (currentJob) await post('/api/jobs/'+currentJob+'/cancel',{}); } catch (error) { message(error); } };
syncControls();
document.addEventListener('pointerdown', keepMediaAlive, {passive:true});
document.addEventListener('keydown', keepMediaAlive, {passive:true});
(async () => {
  try {
    const health = await api('/api/health');
    $('health').textContent = health.backend === 'pc-v2' ? '● Máy xử lý đã kết nối' : 'Đang kết nối';
  } catch { $('health').textContent='Máy xử lý chưa kết nối'; }
  const mid=localStorage.getItem('clip-v2-media'), job=localStorage.getItem('clip-v2-job');
  if (mid) {
    try { applyMedia(await api('/api/media/'+mid),true); }
    catch (error) { if (error.status === 410) { clearMedia(); message(error); } }
  }
  if (job) await follow(job);
})();
