// Video Clipper Studio Frontend Script

const DEFAULT_FORMATS = [
  { format_id: "best", note: "Video / Best Quality (Chất lượng gốc)", size_mb: null },
  { format_id: "1080p", note: "Video / 1080p Full HD", size_mb: null },
  { format_id: "720p", note: "Video / 720p HD", size_mb: null },
  { format_id: "480p", note: "Video / 480p SD", size_mb: null },
  { format_id: "mp3", note: "Audio / MP3 (320kbps)", size_mb: null }
];

let videoState = {
  duration: 1800.0,   // default 30 mins
  startSec: 312.000,  // 00:05:12.000
  endSec: 314.000,    // 00:05:14.000
  source: "",
  is_local: false,
  title: "Sẵn sàng cắt video",
  formats: [...DEFAULT_FORMATS]
};

let lastRunFolder = "";

// DOM Elements
const videoPlayer = document.getElementById("videoPlayer");
const videoPlaceholder = document.getElementById("videoPlaceholder");
const ytIframe = document.getElementById("ytIframe");
const sourceInput = document.getElementById("sourceInput");
const btnPaste = document.getElementById("btnPaste");
const btnBrowse = document.getElementById("btnBrowse");
const fileInput = document.getElementById("fileInput");
const btnLoad = document.getElementById("btnLoad");
const dropZone = document.getElementById("dropZone");

const tabText = document.getElementById("tabText");
const mediaTitle = document.getElementById("mediaTitle");
const mediaThumb = document.getElementById("mediaThumb");
const mediaDurationSub = document.getElementById("mediaDurationSub");
const totalDurationText = document.getElementById("totalDurationText");

const startTimeInput = document.getElementById("startTimeInput");
const endTimeInput = document.getElementById("endTimeInput");
const cutLengthBadge = document.getElementById("cutLengthBadge");
const sliderTrack = document.getElementById("sliderTrack");
const sliderRangeFill = document.getElementById("sliderRangeFill");
const startHandle = document.getElementById("startHandle");
const endHandle = document.getElementById("endHandle");

const btnSetStartCurrent = document.getElementById("btnSetStartCurrent");
const btnSetEndCurrent = document.getElementById("btnSetEndCurrent");
const btnPreviewSegment = document.getElementById("btnPreviewSegment");
const btnMainDownload = document.getElementById("btnMainDownload");

const formatsList = document.getElementById("formatsList");
const formatTabs = document.querySelectorAll(".format-tab");
const chkExtractFrames = document.getElementById("chkExtractFrames");
const framesControls = document.getElementById("framesControls");
const frameFormatSelect = document.getElementById("frameFormatSelect");
const frameFpsSelect = document.getElementById("frameFpsSelect");
const btnOpenFolder = document.getElementById("btnOpenFolder");

const processModal = document.getElementById("processModal");
const modalStatusTitle = document.getElementById("modalStatusTitle");
const modalMessage = document.getElementById("modalMessage");
const progressBarFill = document.getElementById("progressBarFill");
const resultActions = document.getElementById("resultActions");
const btnDownloadVideo = document.getElementById("btnDownloadVideo");
const btnDownloadFrames = document.getElementById("btnDownloadFrames");
const btnOpenRunFolder = document.getElementById("btnOpenRunFolder");
const framesCountText = document.getElementById("framesCountText");

// Helper: Format seconds to HH:MM:SS.mmm
function formatTime(totalSec, includeMs = true) {
  const s = Math.max(0, parseFloat(totalSec) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.min(999, Math.round((s - Math.floor(s)) * 1000));
  const base = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  if (includeMs) {
    return `${base}.${String(ms).padStart(3, '0')}`;
  }
  return base;
}

// Helper: Parse HH:MM:SS.mmm or MM:SS.mmm or seconds
function parseTime(str) {
  if (!str) return 0;
  str = String(str).trim();
  const parts = str.split(":");
  if (parts.length === 3) {
    return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
  }
  if (parts.length === 2) {
    return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
  }
  return parseFloat(str) || 0;
}

// Update UI from startSec and endSec
function updateSliderUI() {
  const dur = Math.max(0.1, videoState.duration);
  const startPct = (videoState.startSec / dur) * 100;
  const endPct = (videoState.endSec / dur) * 100;

  startHandle.style.left = `${Math.min(100, Math.max(0, startPct))}%`;
  endHandle.style.left = `${Math.min(100, Math.max(0, endPct))}%`;
  sliderRangeFill.style.left = `${Math.min(100, Math.max(0, startPct))}%`;
  sliderRangeFill.style.width = `${Math.max(0, endPct - startPct)}%`;

  startTimeInput.value = formatTime(videoState.startSec, true);
  endTimeInput.value = formatTime(videoState.endSec, true);

  const cutDuration = Math.max(0, videoState.endSec - videoState.startSec);
  cutLengthBadge.textContent = `Độ dài cắt: ${formatTime(cutDuration, true)} (${cutDuration.toFixed(3)}s)`;
}

// Nudge Buttons (-100ms, +100ms)
document.querySelectorAll(".btn-nudge").forEach(btn => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.target;
    const delta = parseFloat(btn.dataset.delta) || 0;
    if (target === "start") {
      videoState.startSec = Math.max(0, Math.min(videoState.endSec - 0.01, videoState.startSec + delta));
      seekVideo(videoState.startSec);
    } else if (target === "end") {
      videoState.endSec = Math.min(videoState.duration, Math.max(videoState.startSec + 0.01, videoState.endSec + delta));
      seekVideo(videoState.endSec);
    }
    updateSliderUI();
  });
});

// Slider Dragging Logic
let activeDrag = null;

function handleSliderMove(e) {
  if (!activeDrag) return;
  const rect = sliderTrack.getBoundingClientRect();
  const clientX = e.clientX || (e.touches && e.touches[0].clientX);
  let pct = (clientX - rect.left) / rect.width;
  pct = Math.max(0, Math.min(1, pct));
  const targetSec = pct * videoState.duration;

  if (activeDrag === "start") {
    videoState.startSec = Math.min(targetSec, videoState.endSec - 0.05);
    seekVideo(videoState.startSec);
  } else if (activeDrag === "end") {
    videoState.endSec = Math.max(targetSec, videoState.startSec + 0.05);
    seekVideo(videoState.endSec);
  }
  updateSliderUI();
}

function stopSliderDrag() {
  activeDrag = null;
  window.removeEventListener("mousemove", handleSliderMove);
  window.removeEventListener("mouseup", stopSliderDrag);
  window.removeEventListener("touchmove", handleSliderMove);
  window.removeEventListener("touchend", stopSliderDrag);
}

startHandle.addEventListener("mousedown", (e) => {
  e.preventDefault();
  activeDrag = "start";
  window.addEventListener("mousemove", handleSliderMove);
  window.addEventListener("mouseup", stopSliderDrag);
});
startHandle.addEventListener("touchstart", (e) => {
  activeDrag = "start";
  window.addEventListener("touchmove", handleSliderMove);
  window.addEventListener("touchend", stopSliderDrag);
});

endHandle.addEventListener("mousedown", (e) => {
  e.preventDefault();
  activeDrag = "end";
  window.addEventListener("mousemove", handleSliderMove);
  window.addEventListener("mouseup", stopSliderDrag);
});
endHandle.addEventListener("touchstart", (e) => {
  activeDrag = "end";
  window.addEventListener("touchmove", handleSliderMove);
  window.addEventListener("touchend", stopSliderDrag);
});

sliderTrack.addEventListener("click", (e) => {
  if (e.target === startHandle || e.target === endHandle) return;
  const rect = sliderTrack.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  const targetSec = Math.max(0, Math.min(videoState.duration, pct * videoState.duration));

  const distStart = Math.abs(targetSec - videoState.startSec);
  const distEnd = Math.abs(targetSec - videoState.endSec);
  if (distStart < distEnd) {
    videoState.startSec = Math.min(targetSec, videoState.endSec - 0.05);
    seekVideo(videoState.startSec);
  } else {
    videoState.endSec = Math.max(targetSec, videoState.startSec + 0.05);
    seekVideo(videoState.endSec);
  }
  updateSliderUI();
});

// Manual Input Changes
startTimeInput.addEventListener("change", () => {
  let sec = parseTime(startTimeInput.value);
  sec = Math.max(0, Math.min(sec, videoState.endSec - 0.01));
  videoState.startSec = sec;
  seekVideo(sec);
  updateSliderUI();
});

endTimeInput.addEventListener("change", () => {
  let sec = parseTime(endTimeInput.value);
  sec = Math.min(videoState.duration, Math.max(sec, videoState.startSec + 0.01));
  videoState.endSec = sec;
  seekVideo(sec);
  updateSliderUI();
});

// Video Sync & Controls
function seekVideo(sec) {
  if (videoPlayer.style.display !== "none" && !isNaN(videoPlayer.duration)) {
    videoPlayer.currentTime = sec;
  }
}

btnSetStartCurrent.addEventListener("click", () => {
  if (videoPlayer.style.display !== "none") {
    videoState.startSec = Math.min(videoPlayer.currentTime, videoState.endSec - 0.01);
    updateSliderUI();
  }
});

btnSetEndCurrent.addEventListener("click", () => {
  if (videoPlayer.style.display !== "none") {
    videoState.endSec = Math.max(videoPlayer.currentTime, videoState.startSec + 0.01);
    updateSliderUI();
  }
});

let previewTimer = null;
btnPreviewSegment.addEventListener("click", () => {
  if (videoPlayer.style.display !== "none") {
    videoPlayer.currentTime = videoState.startSec;
    videoPlayer.play();
    if (previewTimer) clearInterval(previewTimer);
    previewTimer = setInterval(() => {
      if (videoPlayer.currentTime >= videoState.endSec) {
        videoPlayer.pause();
        clearInterval(previewTimer);
      }
    }, 50);
  }
});

// Frame Extraction Toggle
chkExtractFrames.addEventListener("change", () => {
  framesControls.style.display = chkExtractFrames.checked ? "flex" : "none";
});

// Clipboard Paste Button
btnPaste.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      sourceInput.value = text.trim();
      videoState.source = text.trim();
      loadSource(text.trim());
    }
  } catch (err) {
    alert("Vui lòng dán trực tiếp link vào ô nhập URL!");
  }
});

// Browse File Button
btnBrowse.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    uploadLocalFile(fileInput.files[0]);
  }
});

// Drag and Drop
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length > 0) {
    uploadLocalFile(e.dataTransfer.files[0]);
  } else {
    const text = e.dataTransfer.getData("text");
    if (text) {
      sourceInput.value = text.trim();
      videoState.source = text.trim();
      loadSource(text.trim());
    }
  }
});

btnLoad.addEventListener("click", () => {
  const val = sourceInput.value.trim();
  if (val) {
    videoState.source = val;
    loadSource(val);
  } else {
    alert("Vui lòng nhập link YouTube hoặc chọn file video!");
  }
});

sourceInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const val = sourceInput.value.trim();
    if (val) {
      videoState.source = val;
      loadSource(val);
    }
  }
});

sourceInput.addEventListener("input", () => {
  const val = sourceInput.value.trim();
  if (val) {
    videoState.source = val;
  }
});

// Upload local file to backend
async function uploadLocalFile(file) {
  showModal("Đang tải file lên...", "Đang chuẩn bị file video từ máy tính...");
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    applyVideoData(data);
    closeModal();
  } catch (err) {
    showError(err.message);
  }
}

// Load source from URL or local path
async function loadSource(source) {
  showModal("Đang lấy thông tin video...", `Đang kết nối: ${source}`);
  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source })
    });
    const data = await res.json();
    if (data.error) {
      console.warn("Lỗi lấy thông tin:", data.error);
      videoState.source = source;
      videoState.formats = DEFAULT_FORMATS;
      renderFormatCards("video");
      closeModal();
      return;
    }

    applyVideoData(data);
    closeModal();
  } catch (err) {
    console.warn("Network error:", err);
    videoState.source = source;
    videoState.formats = DEFAULT_FORMATS;
    renderFormatCards("video");
    closeModal();
  }
}

// Apply Video Data into UI
function applyVideoData(data) {
  videoState.duration = data.duration || 1800.0;
  const currentStart = parseTime(startTimeInput.value);
  const currentEnd = parseTime(endTimeInput.value);
  if (currentEnd > currentStart && currentEnd <= videoState.duration) {
    videoState.startSec = currentStart;
    videoState.endSec = currentEnd;
  } else {
    videoState.startSec = 0.0;
    videoState.endSec = Math.min(videoState.duration, 10.0);
  }

  videoState.title = data.title || "Video";
  videoState.source = data.local_path || data.url || sourceInput.value.trim();
  videoState.is_local = !!data.is_local;
  videoState.formats = (data.formats && data.formats.length > 0) ? data.formats : DEFAULT_FORMATS;

  tabText.textContent = videoState.title;
  mediaTitle.textContent = videoState.title;
  mediaDurationSub.textContent = data.duration_str || formatTime(videoState.duration, true);
  totalDurationText.textContent = data.duration_str || formatTime(videoState.duration, true);
  if (data.thumbnail) mediaThumb.src = data.thumbnail;

  // Video preview setup
  if (data.is_local && (data.stream_url || data.local_path)) {
    videoPlayer.src = data.stream_url || `/stream/${encodeURIComponent(data.title)}`;
    videoPlayer.style.display = "block";
    videoPlaceholder.style.display = "none";
    ytIframe.style.display = "none";
  } else if (data.url && (data.url.includes("youtube.com") || data.url.includes("youtu.be"))) {
    const match = data.url.match(/(?:v=|\/)([0-9A-Za-z_-]{11})/);
    if (match) {
      ytIframe.src = `https://www.youtube.com/embed/${match[1]}?enablejsapi=1`;
      ytIframe.style.display = "block";
      videoPlayer.style.display = "none";
      videoPlaceholder.style.display = "none";
    }
  }

  updateSliderUI();
  renderFormatCards("video");
}

// Render Format Cards
function renderFormatCards(filterType) {
  formatsList.innerHTML = "";
  const sourceList = (videoState.formats && videoState.formats.length > 0) ? videoState.formats : DEFAULT_FORMATS;
  const list = sourceList.filter(f => {
    if (filterType === "audio") return f.format_id === "mp3";
    return f.format_id !== "mp3";
  });

  list.forEach(item => {
    const card = document.createElement("div");
    card.className = "format-card";
    const sizeLabel = item.size_mb ? `${item.size_mb} MB` : (item.format_id === 'mp3' ? 'MP3 320k' : 'Chất lượng cao');
    card.innerHTML = `
      <div class="format-name">${item.note}</div>
      <div class="format-size">${sizeLabel}</div>
      <button class="btn-download" title="Cắt và Tải về">
        <span>Tải về</span> <span class="dl-icon">⬇</span>
      </button>
    `;

    card.querySelector(".btn-download").addEventListener("click", () => {
      triggerCut(item.format_id);
    });

    formatsList.appendChild(card);
  });
}

formatTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    formatTabs.forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    renderFormatCards(tab.dataset.type);
  });
});

// Big Primary CTA Button
if (btnMainDownload) {
  btnMainDownload.addEventListener("click", () => {
    triggerCut("best");
  });
}

// Trigger Video Cut & Processing
async function triggerCut(formatId) {
  let targetSource = videoState.source || sourceInput.value.trim();
  if (!targetSource) {
    alert("Vui lòng dán link YouTube hoặc đường dẫn file video vào ô tìm kiếm!");
    sourceInput.focus();
    return;
  }

  const payload = {
    source: targetSource,
    is_local: videoState.is_local,
    title: videoState.title || "clip",
    start_time: startTimeInput.value.trim() || "00:05:12.000",
    end_time: endTimeInput.value.trim() || "00:05:14.000",
    format_id: formatId || "best",
    extract_frames: chkExtractFrames.checked,
    frame_format: frameFormatSelect.value,
    frame_fps: frameFpsSelect.value
  };

  showModal("Đang bắt đầu cắt video...", `Cắt đoạn từ ${payload.start_time} đến ${payload.end_time}`);
  resultActions.style.display = "none";

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    pollStatus(data.task_id);
  } catch (err) {
    showError(err.message);
  }
}

// Poll Background Status
function pollStatus(taskId) {
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${taskId}`);
      const task = await res.json();

      modalMessage.textContent = task.message;

      if (task.status === "completed") {
        clearInterval(timer);
        modalStatusTitle.textContent = "✅ Hoàn tất thành công!";
        modalMessage.textContent = `Kết quả đã được lưu gọn gàng vào thư mục riêng: outputs/${task.result.run_folder}/`;
        progressBarFill.style.animation = "none";
        progressBarFill.style.width = "100%";

        resultActions.style.display = "flex";
        btnDownloadVideo.href = task.result.video_url;
        btnDownloadVideo.download = task.result.video_file;

        lastRunFolder = task.result.run_folder || "";
        if (btnOpenRunFolder) {
          btnOpenRunFolder.onclick = () => openOutputFolder(lastRunFolder);
          btnOpenRunFolder.textContent = `📂 Mở thư mục riêng: ${lastRunFolder}`;
        }

        if (task.result.frames_zip) {
          btnDownloadFrames.href = task.result.frames_url;
          btnDownloadFrames.download = task.result.frames_zip;
          btnDownloadFrames.style.display = "block";
          framesCountText.textContent = task.result.frames_count;
        } else {
          btnDownloadFrames.style.display = "none";
        }

      } else if (task.status === "error") {
        clearInterval(timer);
        showError(task.message);
      }
    } catch (e) {
      clearInterval(timer);
      showError("Lỗi kết nối khi cập nhật tiến độ.");
    }
  }, 1000);
}

// Modal functions
function showModal(title, msg) {
  modalStatusTitle.textContent = title;
  modalMessage.textContent = msg;
  progressBarFill.style.animation = "progressPulse 1.5s infinite";
  progressBarFill.style.width = "30%";
  progressBarFill.style.backgroundColor = "";
  resultActions.style.display = "none";
  processModal.style.display = "flex";
}

function showError(msg) {
  modalStatusTitle.textContent = "❌ Lỗi";
  modalMessage.textContent = msg;
  progressBarFill.style.animation = "none";
  progressBarFill.style.backgroundColor = "#ef4444";
  progressBarFill.style.width = "100%";
}

function closeModal() {
  processModal.style.display = "none";
}

// Open Output Directory in Windows Explorer
async function openOutputFolder(folderName = "") {
  try {
    await fetch("/api/open_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folderName })
    });
  } catch (e) {
    alert("Không thể mở thư mục tự động.");
  }
}

btnOpenFolder.addEventListener("click", () => openOutputFolder(""));

function resetApp() {
  sourceInput.value = "";
  videoPlayer.pause();
  videoPlayer.src = "";
  videoPlayer.style.display = "none";
  ytIframe.src = "";
  ytIframe.style.display = "none";
  videoPlaceholder.style.display = "flex";
  videoState = {
    duration: 1800.0,
    startSec: 312.000,
    endSec: 314.000,
    source: "",
    is_local: false,
    title: "Sẵn sàng cắt video",
    formats: [...DEFAULT_FORMATS]
  };
  tabText.textContent = "Video Clipper";
  mediaTitle.textContent = "Sẵn sàng tải & cắt video";
  totalDurationText.textContent = "00:30:00.000";
  mediaDurationSub.textContent = "Điền link hoặc chọn file bên trên";
  updateSliderUI();
  renderFormatCards("video");
}

// Live Log Drawer Logic
const logDrawer = document.getElementById("logDrawer");
const logContent = document.getElementById("logContent");
const btnToggleLogPanel = document.getElementById("btnToggleLogPanel");
const btnToggleConsole = document.getElementById("btnToggleConsole");
const btnClearLogs = document.getElementById("btnClearLogs");
const btnCopyLogs = document.getElementById("btnCopyLogs");

let logPollingTimer = null;
let isConsoleVisible = true;

function toggleLogPanel() {
  if (!logDrawer) return;
  const isHidden = logDrawer.style.display === "none";
  logDrawer.style.display = isHidden ? "flex" : "none";
  if (btnToggleLogPanel) btnToggleLogPanel.classList.toggle("active", isHidden);
  if (isHidden) {
    fetchLogs();
    if (!logPollingTimer) logPollingTimer = setInterval(fetchLogs, 1000);
  } else {
    if (logPollingTimer) {
      clearInterval(logPollingTimer);
      logPollingTimer = null;
    }
  }
}

async function fetchLogs() {
  try {
    const res = await fetch("/api/logs");
    const data = await res.json();
    if (data.logs && logContent) {
      logContent.textContent = data.logs.join("\n") || "Chưa có log mới...";
      logContent.scrollTop = logContent.scrollHeight;
    }
  } catch (e) {}
}

if (btnToggleLogPanel) btnToggleLogPanel.addEventListener("click", toggleLogPanel);

if (btnClearLogs) {
  btnClearLogs.addEventListener("click", async () => {
    try {
      await fetch("/api/clear_logs", { method: "POST" });
      if (logContent) logContent.textContent = "Đã xóa toàn bộ log.";
    } catch (e) {}
  });
}

if (btnCopyLogs) {
  btnCopyLogs.addEventListener("click", () => {
    if (logContent) {
      navigator.clipboard.writeText(logContent.textContent);
      alert("Đã sao chép nội dung log!");
    }
  });
}

// Toggle Windows CMD Console Window
if (btnToggleConsole) {
  btnToggleConsole.addEventListener("click", async () => {
    isConsoleVisible = !isConsoleVisible;
    try {
      await fetch("/api/toggle_console", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show: isConsoleVisible })
      });
      btnToggleConsole.classList.toggle("active", isConsoleVisible);
      btnToggleConsole.textContent = isConsoleVisible ? "🖥️ Console Window" : "🖥️ Console: ĐÃ ẨN";
    } catch (e) {}
  });
}

// Phone Remote Modal Logic
const btnPhoneRemote = document.getElementById("btnPhoneRemote");
const qrModal = document.getElementById("qrModal");
const qrImg = document.getElementById("qrImg");
const tunnelUrlInput = document.getElementById("tunnelUrlInput");
const btnCopyTunnelUrl = document.getElementById("btnCopyTunnelUrl");

function closeQrModal() {
  if (qrModal) qrModal.style.display = "none";
}

async function checkTunnelStatus() {
  try {
    const res = await fetch("/api/tunnel");
    const data = await res.json();
    if (data.url) {
      if (tunnelUrlInput) tunnelUrlInput.value = data.url;
      if (qrImg && data.qr) qrImg.src = data.qr;
      if (btnPhoneRemote) {
        btnPhoneRemote.classList.add("active");
        btnPhoneRemote.textContent = "📱 Link ĐT: Sẵn sàng";
      }
    } else {
      if (tunnelUrlInput) tunnelUrlInput.value = "Đang kết nối Cloudflare Tunnel...";
    }
  } catch (e) {}
}

if (btnPhoneRemote) {
  btnPhoneRemote.addEventListener("click", () => {
    if (qrModal) qrModal.style.display = "flex";
    checkTunnelStatus();
  });
}

if (btnCopyTunnelUrl) {
  btnCopyTunnelUrl.addEventListener("click", () => {
    if (tunnelUrlInput && tunnelUrlInput.value.startsWith("http")) {
      navigator.clipboard.writeText(tunnelUrlInput.value);
      alert("Đã sao chép link Remote! Bạn có thể gửi qua Zalo / Telegram để mở trên điện thoại.");
    }
  });
}

// Auto check tunnel status in the background
let tunnelCheckCount = 0;
const tunnelTimer = setInterval(async () => {
  await checkTunnelStatus();
  tunnelCheckCount++;
  if (tunnelCheckCount > 12 || (tunnelUrlInput && tunnelUrlInput.value.startsWith("http"))) {
    clearInterval(tunnelTimer);
  }
}, 2500);

// Initial setup on page load
updateSliderUI();
renderFormatCards("video");
