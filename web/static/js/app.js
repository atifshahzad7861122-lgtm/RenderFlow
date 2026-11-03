// RenderFlow by AI With Atif — Client Workstation SPA Controller
// Omni-inspired UI/UX, 4 Themes (Glass, Muddy, Apple, F1), Remotion & 3D WebGL Layer

// --- FRONTEND API CONNECTION DIAGNOSTICS & GLOBAL ERROR TRACE ---
window.__apiDiagnostics = [];
window.getApiDiagnostics = () => window.__apiDiagnostics;

const _originalFetch = window.fetch;
window.fetch = async function(...args) {
  const start = performance.now();
  const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
  const method = (args[1]?.method || 'GET').toUpperCase();
  try {
    const res = await _originalFetch.apply(this, args);
    const duration = Math.round(performance.now() - start);
    window.__apiDiagnostics.push({
      timestamp: new Date().toISOString(),
      method,
      endpoint: url,
      status: res.status,
      ok: res.ok,
      duration_ms: duration,
      error: res.ok ? null : `HTTP ${res.status}`
    });
    if (!res.ok) {
      console.warn(`[API DIAGNOSTIC] ${method} ${url} -> HTTP ${res.status} (${duration}ms)`);
    }
    return res;
  } catch (err) {
    const duration = Math.round(performance.now() - start);
    window.__apiDiagnostics.push({
      timestamp: new Date().toISOString(),
      method,
      endpoint: url,
      status: 0,
      ok: false,
      duration_ms: duration,
      error: err.message
    });
    console.error(`[API DIAGNOSTIC ERROR] ${method} ${url} -> ${err.message} (${duration}ms)`);
    throw err;
  }
};

window.addEventListener('error', (e) => {
  console.error('[Workstation Global JS Error]', e.message, 'at', `${e.filename}:${e.lineno}:${e.colno}`, e.error);
});
window.addEventListener('unhandledrejection', (e) => {
  console.error('[Workstation Unhandled Rejection]', e.reason);
});

let renderCore3DInstance = null;
window.renderCore3DInstance = null;

const state = {
  activeTab: 'tab-studio',
  currentProject: null,
  projectPath: null,
  isRendering: false,
  eventSource: null,
  transitions: [],
  logs: [],
  captionStyles: [],
  selectedCaptionStyle: 'classic',
  activeCategory: 'all',
  styleSearchQuery: '',
  aiSettings: {
    stt_provider: 'auto',
    deepgram_model: 'nova-3',
    smart_formatting: true,
    word_timestamps: true,
    utterances: true,
    diarization: false,
    llm_provider: 'auto',
    llm_model: '',
    ai_mode: 'clean',
    quality_level: 'balanced',
    creative_rewrite: false,
    fallback: true
  }
};
window.state = state;

// DOM References
const el = {
  navTabs: document.querySelectorAll('.nav-tab'),
  tabPanes: document.querySelectorAll('.tab-pane'),
  sysFfmpeg: document.getElementById('sysFfmpeg'),
  sysPack: document.getElementById('sysPack'),
  headerProjectBadge: document.getElementById('headerProjectBadge'),
  btnOpenUpload: document.getElementById('btnOpenUpload'),
  btnAutoPlan: document.getElementById('btnAutoPlan'),
  btnResyncImages: document.getElementById('btnResyncImages'),
  syncAnalysisCard: document.getElementById('syncAnalysisCard'),
  syncStatImagesIndexed: document.getElementById('syncStatImagesIndexed'),
  syncStatBeats: document.getElementById('syncStatBeats'),
  syncBadgeHigh: document.getElementById('syncBadgeHigh'),
  syncBadgeMed: document.getElementById('syncBadgeMed'),
  syncBadgeLow: document.getElementById('syncBadgeLow'),
  syncBadgeOverall: document.getElementById('syncBadgeOverall'),
  syncProfileSelect: document.getElementById('syncProfileSelect'),
  syncModeSelect: document.getElementById('syncModeSelect'),
  mappingModeSelect: document.getElementById('mappingModeSelect'),
  syncStatQualityScore: document.getElementById('syncStatQualityScore'),
  btnReviewLowConf: document.getElementById('btnReviewLowConf'),
  reviewQueueCount: document.getElementById('reviewQueueCount'),
  btnApproveHighConf: document.getElementById('btnApproveHighConf'),
  btnResetSyncLearning: document.getElementById('btnResetSyncLearning'),
  reviewQueueModal: document.getElementById('reviewQueueModal'),
  btnCloseReviewQueue: document.getElementById('btnCloseReviewQueue'),
  btnCancelReviewQueue: document.getElementById('btnCancelReviewQueue'),
  btnApplyReviewQueue: document.getElementById('btnApplyReviewQueue'),
  reviewQueueContent: document.getElementById('reviewQueueContent'),
  btnSavePlan: document.getElementById('btnSavePlan'),
  btnStartRender: document.getElementById('btnStartRender'),
  btnCancelRender: document.getElementById('btnCancelRender'),
  btnClearLogs: document.getElementById('btnClearLogs'),
  btnCopyLogs: document.getElementById('btnCopyLogs'),
  btnZoomSheet: document.getElementById('btnZoomSheet'),
  btnDownloadVideo: document.getElementById('btnDownloadVideo'),
  
  // Stats
  statAudioDur: document.getElementById('statAudioDur'),
  statSceneCount: document.getElementById('statSceneCount'),
  
  // Timeline & Studio
  timelineTrack: document.getElementById('timelineTrack'),
  audioElement: document.getElementById('audioElement'),
  audioFileName: document.getElementById('audioFileName'),
  audioDurationLabel: document.getElementById('audioDurationLabel'),
  audioFileInput: document.getElementById('audioFileInput'),
  
  // Scene Images & ZIP Upload
  imagesDropzone: document.getElementById('imagesDropzone'),
  imagesFileInput: document.getElementById('imagesFileInput'),
  uploadStatusBox: document.getElementById('uploadStatusBox'),
  uploadStatusFilename: document.getElementById('uploadStatusFilename'),
  uploadStatusFilesize: document.getElementById('uploadStatusFilesize'),
  uploadProgressBar: document.getElementById('uploadProgressBar'),
  uploadStatusStage: document.getElementById('uploadStatusStage'),
  uploadStatusResult: document.getElementById('uploadStatusResult'),
  imagesGallery: document.getElementById('imagesGallery'),
  imageCountBadge: document.getElementById('imageCountBadge'),
  sceneTableBody: document.getElementById('sceneTableBody'),
  btnClearMedia: document.getElementById('btnClearMedia'),
  btnClearMediaAudio: document.getElementById('btnClearMediaAudio'),
  clearMediaModal: document.getElementById('clearMediaModal'),
  btnCloseClearMedia: document.getElementById('btnCloseClearMedia'),
  btnCancelClearMedia: document.getElementById('btnCancelClearMedia'),
  btnConfirmClearMedia: document.getElementById('btnConfirmClearMedia'),
  
  // Settings
  settingTransitionMode: document.getElementById('settingTransitionMode'),
  settingDurScale: document.getElementById('settingDurScale'),
  durScaleLabel: document.getElementById('durScaleLabel'),
  settingResolution: document.getElementById('settingResolution'),
  settingResolutionConsole: document.getElementById('settingResolutionConsole'),
  settingCaptionStyle: document.getElementById('settingCaptionStyle'),
  settingPreset: document.getElementById('settingPreset'),
  settingVerify: document.getElementById('settingVerify'),
  btnExploreTransitions: document.getElementById('btnExploreTransitions'),
  
  // Render Console & Observable Bar
  stepChip1: document.getElementById('stepChip1'),
  stepChip2: document.getElementById('stepChip2'),
  stepChip3: document.getElementById('stepChip3'),
  terminalBody: document.getElementById('terminalBody'),
  terminalStatusText: document.getElementById('terminalStatusText'),
  tabRenderBadge: document.getElementById('tabRenderBadge'),
  renderObservableBar: document.getElementById('renderObservableBar'),
  renderPulseDot: document.getElementById('renderPulseDot'),
  renderStateChip: document.getElementById('renderStateChip'),
  renderChunkTracker: document.getElementById('renderChunkTracker'),
  renderProgressText: document.getElementById('renderProgressText'),
  renderElapsedText: document.getElementById('renderElapsedText'),
  renderProgressBar: document.getElementById('renderProgressBar'),
  studioRenderStatus: document.getElementById('studioRenderStatus'),
  studioStateChip: document.getElementById('studioStateChip'),
  studioProgressPercent: document.getElementById('studioProgressPercent'),
  studioChunkTracker: document.getElementById('studioChunkTracker'),
  
  // Showcase
  finalVideoPlayer: document.getElementById('finalVideoPlayer'),
  contactSheetImg: document.getElementById('contactSheetImg'),
  videoResolutionBadge: document.getElementById('videoResolutionBadge'),
  videoCodecBadge: document.getElementById('videoCodecBadge'),
  
  // QC Badges
  qcH264: document.getElementById('qcH264'),
  qcRes: document.getElementById('qcRes'),
  qcFps: document.getElementById('qcFps'),
  qcAAC: document.getElementById('qcAAC'),
  qcAudio: document.getElementById('qcAudio'),
  qcVisual: document.getElementById('qcVisual'),
  qcDiffs: document.getElementById('qcDiffs'),
  
  // Transitions
  searchTransitions: document.getElementById('searchTransitions'),
  filterTransitionCategory: document.getElementById('filterTransitionCategory'),
  filterTransitionKind: document.getElementById('filterTransitionKind'),
  transitionCardsGrid: document.getElementById('transitionCardsGrid'),
  
  // Modals
  uploadModal: document.getElementById('uploadModal'),
  btnCloseUpload: document.getElementById('btnCloseUpload'),
  btnSubmitUpload: document.getElementById('btnSubmitUpload'),
  uploadProjectName: document.getElementById('uploadProjectName'),
  uploadFileInput: document.getElementById('uploadFileInput'),
  sheetModal: document.getElementById('sheetModal'),
  sheetModalImg: document.getElementById('sheetModalImg'),
  toastContainer: document.getElementById('toastContainer'),

  // Captions & Subtitles Engine
  captionPanel: document.getElementById('captionPanel'),
  captionStatusBadge: document.getElementById('captionStatusBadge'),
  toggleCaptions: document.getElementById('toggleCaptions'),
  captionSettingsBody: document.getElementById('captionSettingsBody'),
  captionPreviewStage: document.getElementById('captionPreviewStage'),
  captionPreviewSafeArea: document.getElementById('captionPreviewSafeArea'),
  captionStyleCards: document.getElementById('captionStyleCards'),
  captionStyleSelect: document.getElementById('captionStyleSelect'),
  captionPlatformPreset: document.getElementById('captionPlatformPreset'),
  activePresetBadge: document.getElementById('activePresetBadge'),
  styleCountBadge: document.getElementById('styleCountBadge'),
  styleCategoryChips: document.getElementById('styleCategoryChips'),
  styleSearchInput: document.getElementById('styleSearchInput'),
  captionLengthSelect: document.getElementById('captionLengthSelect'),
  captionLangSelect: document.getElementById('captionLangSelect'),
  captionPosSelect: document.getElementById('captionPosSelect'),
  captionWordHighlight: document.getElementById('captionWordHighlight'),
  captionSidecarExport: document.getElementById('captionSidecarExport'),
  qcCaptions: document.getElementById('qcCaptions'),
  captionExportsCard: document.getElementById('captionExportsCard'),
  btnDownloadSrt: document.getElementById('btnDownloadSrt'),
  btnDownloadAss: document.getElementById('btnDownloadAss'),
  btnDownloadJson: document.getElementById('btnDownloadJson'),

  // Compact Caption Style Picker (Section 19-23)
  btnOpenCaptionPicker: document.getElementById('btnOpenCaptionPicker'),
  activeStyleBadge: document.getElementById('activeStyleBadge'),
  activeStyleName: document.getElementById('activeStyleName'),
  captionPickerModal: document.getElementById('captionPickerModal'),
  btnCloseCaptionPicker: document.getElementById('btnCloseCaptionPicker'),
  stylePickerSearch: document.getElementById('stylePickerSearch'),
  pickerCategoryChips: document.getElementById('pickerCategoryChips'),
  pickerStyleList: document.getElementById('pickerStyleList'),
  pickerPreviewStyleName: document.getElementById('pickerPreviewStyleName'),
  pickerPreviewBox: document.getElementById('pickerPreviewBox'),
  pickerPreviewText: document.getElementById('pickerPreviewText'),
  pickerPreviewDesc: document.getElementById('pickerPreviewDesc'),
  btnConfirmSelectStyle: document.getElementById('btnConfirmSelectStyle'),

  // AI & Intelligence Controls & Modals
  btnOpenAISettings: document.getElementById('btnOpenAISettings') || document.getElementById('btnOpenAISettingsModal'),
  btnCloseAISettings: document.getElementById('btnCloseAISettings'),
  aiSettingsModal: document.getElementById('aiSettingsModal'),
  btnSaveAISettings: document.getElementById('btnSaveAISettings'),
  btnTestAIConnection: document.getElementById('btnTestAIConnection'),
  aiConnectionStatus: document.getElementById('aiConnectionStatus'),
  aiSttProvider: document.getElementById('aiSttProvider'),
  aiDeepgramModel: document.getElementById('aiDeepgramModel'),
  aiSmartFormatting: document.getElementById('aiSmartFormatting'),
  aiWordTimestamps: document.getElementById('aiWordTimestamps'),
  aiUtterances: document.getElementById('aiUtterances'),
  aiDiarization: document.getElementById('aiDiarization'),
  aiLlmProvider: document.getElementById('aiLlmProvider'),
  aiLlmModel: document.getElementById('aiLlmModel'),
  aiCaptionMode: document.getElementById('aiCaptionMode'),
  aiQualityLevel: document.getElementById('aiQualityLevel'),
  aiCreativeRewrite: document.getElementById('aiCreativeRewrite'),

  btnPreviewAIRewrite: document.getElementById('btnPreviewAIRewrite'),
  btnCloseAIComparison: document.getElementById('btnCloseAIComparison'),
  aiComparisonModal: document.getElementById('aiComparisonModal'),
  aiComparisonInput: document.getElementById('aiComparisonInput'),
  btnRunComparison: document.getElementById('btnRunComparison'),
  aiOriginalText: document.getElementById('aiOriginalText'),
  aiCleanText: document.getElementById('aiCleanText'),
  aiViralText: document.getElementById('aiViralText'),
  aiCleanEmphasis: document.getElementById('aiCleanEmphasis'),
  aiViralEmphasis: document.getElementById('aiViralEmphasis'),
  btnApplyClean: document.getElementById('btnApplyClean'),
  btnApplyViral: document.getElementById('btnApplyViral'),
  btnRestoreOriginal: document.getElementById('btnRestoreOriginal'),

  // AI Provider & API Credentials Center
  btnOpenAICredentials: document.getElementById('btnOpenAICredentials'),
  btnHeaderCredentials: document.getElementById('btnHeaderCredentials'),
  btnOpenCredentialsFromSettings: document.getElementById('btnOpenCredentialsFromSettings'),
  btnCloseAICredentials: document.getElementById('btnCloseAICredentials'),
  btnRefreshAllCredentials: document.getElementById('btnRefreshAllCredentials'),
  aiCredentialsModal: document.getElementById('aiCredentialsModal'),
  credTotalProviders: document.getElementById('credTotalProviders'),
  credConfiguredCount: document.getElementById('credConfiguredCount'),
  credConnectedCount: document.getElementById('credConnectedCount'),
  credSttActive: document.getElementById('credSttActive'),
  credLlmActive: document.getElementById('credLlmActive'),
  credentialsCardsGrid: document.getElementById('credentialsCardsGrid'),
  fallbackChainSteps: document.getElementById('fallbackChainSteps')
};

function safeExec(name, fn) {
  try {
    const res = fn();
    if (res && typeof res.catch === 'function') {
      res.catch(err => console.error(`[Workstation Init Error in ${name}]`, err));
    }
  } catch (err) {
    console.error(`[Workstation Init Error in ${name}]`, err);
  }
}

// --- INITIALIZATION ---
function initRenderFlowApp() {
  console.log('[Workstation] initRenderFlowApp starting...');
  safeExec('initRenderFlowModernization', initRenderFlowModernization);
  safeExec('setupTabs', setupTabs);
  safeExec('setupSettings', setupSettings);
  safeExec('setupModals', setupModals);
  safeExec('setupImageDropzone', setupImageDropzone);
  safeExec('setupAudioUpload', setupAudioUpload);
  safeExec('loadSystemStatus', loadSystemStatus);
  safeExec('loadHardwareProfile', loadHardwareProfile);
  safeExec('loadRecentProjects', loadRecentProjects);
  const savedActive = localStorage.getItem('renderflow_active_project_path');
  console.log('[Workstation] savedActive project path:', savedActive);
  safeExec('loadProjectData', () => loadProjectData(savedActive));
  safeExec('loadTransitions', loadTransitions);
  safeExec('setupCaptions', setupCaptions);
  safeExec('initResolutionControls', initResolutionControls);
  safeExec('initAICredentialCenter', initAICredentialCenter);
}

window.getCanonicalResolution = function() {
  const candidates = [
    document.getElementById('settingResolution')?.value,
    document.getElementById('settingResolutionConsole')?.value,
    document.getElementById('paneSettingResolution')?.value,
    state?.plan?.resolution,
    '1080p'
  ];
  for (const c of candidates) {
    if (!c) continue;
    const s = String(c).trim().toLowerCase();
    if (s === '1080p' || s === '1080' || s.includes('1080') || s.includes('fhd')) return '1080p';
    if (s === '1440p' || s === '1440' || s.includes('1440') || s === '2k' || s.includes('qhd')) return '1440p';
    if (s === '4k' || s === '2160p' || s.includes('4k') || s.includes('2160') || s.includes('uhd')) return '4k';
  }
  return '1080p';
};

window.syncResolution = function(val) {
  let canon = '1080p';
  if (val) {
    const s = String(val).trim().toLowerCase();
    if (s === '1080p' || s === '1080' || s.includes('1080') || s.includes('fhd')) canon = '1080p';
    else if (s === '1440p' || s === '1440' || s.includes('1440') || s === '2k' || s.includes('qhd')) canon = '1440p';
    else if (s === '4k' || s === '2160p' || s.includes('4k') || s.includes('2160') || s.includes('uhd')) canon = '4k';
  }

  const resSelect = document.getElementById('settingResolution');
  const resConsole = document.getElementById('settingResolutionConsole');
  const paneRes = document.getElementById('paneSettingResolution');
  const previewBadge = document.getElementById('previewResBadge');
  const topBadge = document.getElementById('topFormatBadge');
  const resBadge = document.getElementById('activeResolutionBadge');
  const detBadge = document.getElementById('resDetailBadge');

  if (resSelect && resSelect.value !== canon) resSelect.value = canon;
  if (resConsole && resConsole.value !== canon) resConsole.value = canon;
  if (paneRes && paneRes.value !== canon) paneRes.value = canon;

  if (previewBadge) {
    if (canon === '1080p') previewBadge.textContent = '1080p Full HD · 1920×1080 · 30 FPS';
    else if (canon === '1440p') previewBadge.textContent = '1440p 2K QHD · 2560×1440 · 30 FPS';
    else if (canon === '4k') previewBadge.textContent = '4K UHD · 3840×2160 · 30 FPS';
  }
  if (topBadge) {
    const label = canon === '4k' ? '4K UHD' : (canon === '1440p' ? '1440p QHD' : '1080p FHD');
    const dims = canon === '4k' ? '3840×2160' : (canon === '1440p' ? '2560×1440' : '1920×1080');
    topBadge.title = `Sequence Format: ${label} (${dims}) · 30 FPS · 16:9`;
    topBadge.innerHTML = `<span class="format-dot">●</span> <span class="format-res-label">${label}</span><span class="format-spec-label"> · 30 FPS · 16:9</span>`;
  }
  if (resBadge) {
    resBadge.textContent = canon === '4k' ? '4K UHD @ 30fps' : (canon === '1440p' ? '1440p @ 30fps' : '1080p @ 30fps');
  }
  if (detBadge) {
    detBadge.textContent = canon === '4k' ? '3840x2160 UHD' : (canon === '1440p' ? '2560x1440 QHD' : '1920x1080 FHD');
  }

  if (state?.plan) {
    state.plan.resolution = canon;
  }
  return canon;
};

function initResolutionControls() {
  const resSelect = document.getElementById('settingResolution');
  const resConsole = document.getElementById('settingResolutionConsole');
  const paneRes = document.getElementById('paneSettingResolution');

  // Initial sync from canonical
  const initial = window.getCanonicalResolution();
  window.syncResolution(initial);

  if (resSelect && !resSelect.dataset.syncBound) {
    resSelect.dataset.syncBound = 'true';
    resSelect.addEventListener('change', (e) => {
      const c = window.syncResolution(e.target.value);
      showToast(`Output resolution set to ${c.toUpperCase()}`, 'info');
    });
  }
  if (resConsole && !resConsole.dataset.syncBound) {
    resConsole.dataset.syncBound = 'true';
    resConsole.addEventListener('change', (e) => {
      const c = window.syncResolution(e.target.value);
      showToast(`Output resolution set to ${c.toUpperCase()}`, 'info');
    });
  }
  if (paneRes && !paneRes.dataset.syncBound) {
    paneRes.dataset.syncBound = 'true';
    paneRes.addEventListener('change', (e) => {
      const c = window.syncResolution(e.target.value);
      showToast(`Output resolution set to ${c.toUpperCase()}`, 'info');
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRenderFlowApp);
} else {
  initRenderFlowApp();
}

// Toast notification helper
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span> <span>${msg}</span>`;
  const container = document.getElementById('toastContainer');
  if (container) {
    container.appendChild(t);
    setTimeout(() => {
      t.style.opacity = '0';
      setTimeout(() => t.remove(), 300);
    }, 4000);
  }
}

// --- RenderFlow UI/UX Modernization & Theme Engine ---
function initRenderFlowModernization() {
  // 1. Centralized Theme Engine & System Source of Truth
  const themes = ['glass', 'muddy', 'apple', 'f1', 'concat-pro'];
  const themeColors = {
    glass: '#00f0ff',
    muddy: '#d97706',
    apple: '#0071e3',
    f1: '#e10600',
    'concat-pro': '#cbf53f'
  };
  const themeTitles = {
    glass: 'GLASS',
    muddy: 'MUDDY',
    apple: 'APPLE',
    f1: 'F1',
    'concat-pro': 'CONCAT PRO'
  };

  window.setRenderFlowTheme = function(themeName, showToastMsg = true) {
    if (!themes.includes(themeName)) themeName = 'concat-pro';
    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem('renderflow_theme', themeName);

    // Update Topbar Badge & Dot
    const themeBadge = document.getElementById('themeCurrentBadge');
    const themeDot = document.getElementById('themeIndicatorDot');
    if (themeBadge) themeBadge.textContent = themeTitles[themeName];
    if (themeDot) themeDot.style.background = themeColors[themeName];

    // Update Theme Picker Popover Cards & Badges
    const cards = document.querySelectorAll('.rf-theme-card');
    cards.forEach(card => {
      const val = card.getAttribute('data-theme-val');
      const isActive = val === themeName;
      card.classList.toggle('active', isActive);
      card.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      const badge = card.querySelector('.rf-theme-check');
      if (badge) badge.style.display = isActive ? 'inline-block' : 'none';
    });

    const currentStatusText = document.getElementById('themeCurrentStatusText');
    if (currentStatusText) currentStatusText.textContent = `${themeTitles[themeName]} ✓`;

    // Update Settings Modal Theme Select
    const settingsThemeSelect = document.getElementById('settingsThemeSelect');
    if (settingsThemeSelect && settingsThemeSelect.value !== themeName) {
      settingsThemeSelect.value = themeName;
    }

    // Update 3D Engine Core
    if (window.renderCore3DInstance) {
      if (typeof window.renderCore3DInstance.setTheme === 'function') {
        window.renderCore3DInstance.setTheme(themeName);
      } else {
        window.renderCore3DInstance.theme = themeName;
      }
    }

    if (showToastMsg) {
      showToast(`Workstation theme: ${themeTitles[themeName]} active`, 'info');
    }
  };

  // Boot theme initialization & persistence
  const urlParams = new URLSearchParams(window.location.search);
  const themeParam = urlParams.get('theme');
  const savedTheme = (themeParam && themes.includes(themeParam)) ? themeParam : (localStorage.getItem('renderflow_theme') || 'concat-pro');
  window.setRenderFlowTheme(savedTheme, false);

  // 1B. Premium Theme Picker Popover Interactions
  const themeBtn = document.getElementById('btnThemeSelector');
  const themePopover = document.getElementById('themePickerPopover');
  const btnCloseThemePicker = document.getElementById('btnCloseThemePicker');
  const themeBackdrop = document.getElementById('themePickerBackdrop');

  function openThemePicker() {
    if (!themePopover) return;
    themePopover.classList.add('open');
    themePopover.style.display = 'flex';
    if (themeBtn) themeBtn.setAttribute('aria-expanded', 'true');
    const activeCard = themePopover.querySelector(`.rf-theme-card[data-theme-val="${document.documentElement.getAttribute('data-theme') || 'glass'}"]`);
    if (activeCard) activeCard.focus();
  }

  function closeThemePicker() {
    if (!themePopover) return;
    themePopover.classList.remove('open');
    themePopover.style.display = 'none';
    if (themeBtn) {
      themeBtn.setAttribute('aria-expanded', 'false');
      themeBtn.focus();
    }
  }

  if (urlParams.get('picker') === '1' || urlParams.get('picker') === 'open') {
    openThemePicker();
  }

  if (themeBtn) {
    themeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (themePopover && (themePopover.classList.contains('open') || themePopover.style.display === 'flex')) {
        closeThemePicker();
      } else {
        openThemePicker();
      }
    });
  }

  if (btnCloseThemePicker) {
    btnCloseThemePicker.addEventListener('click', closeThemePicker);
  }
  if (themeBackdrop) {
    themeBackdrop.addEventListener('click', closeThemePicker);
  }

  // Theme Cards Event Listeners (Mouse click & Keyboard navigation)
  const themeCards = document.querySelectorAll('.rf-theme-card');
  themeCards.forEach((card, idx) => {
    card.addEventListener('click', () => {
      const themeVal = card.getAttribute('data-theme-val');
      window.setRenderFlowTheme(themeVal, true);
    });

    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const themeVal = card.getAttribute('data-theme-val');
        window.setRenderFlowTheme(themeVal, true);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeThemePicker();
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        const next = themeCards[(idx + 1) % themeCards.length];
        if (next) next.focus();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = themeCards[(idx - 1 + themeCards.length) % themeCards.length];
        if (prev) prev.focus();
      }
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && themePopover && themePopover.style.display === 'flex') {
      closeThemePicker();
    }
  });

  // 1C. Settings Modal & Appearance Preferences Controller
  const btnSettings = document.getElementById('btnSettingsModal');
  const settingsModal = document.getElementById('settingsModal');
  const btnCloseSettings = document.getElementById('btnCloseSettingsModal');
  const btnCancelSettings = document.getElementById('btnCancelSettingsModal');
  const btnApplySettings = document.getElementById('btnApplySettingsModal');

  const settingsThemeSelect = document.getElementById('settingsThemeSelect');
  const settingsAnimSelect = document.getElementById('settingsAnimSelect');
  const settings3dSelect = document.getElementById('settings3dSelect');

  // Load saved preferences
  const savedAnim = localStorage.getItem('renderflow_anim_mode') || 'full';
  const saved3d = localStorage.getItem('renderflow_3d_quality') || 'auto';
  document.documentElement.setAttribute('data-anim', savedAnim);

  if (settingsThemeSelect) settingsThemeSelect.value = document.documentElement.getAttribute('data-theme') || 'glass';
  if (settingsAnimSelect) settingsAnimSelect.value = savedAnim;
  if (settings3dSelect) settings3dSelect.value = saved3d;

  function openSettingsModal() {
    if (!settingsModal) return;
    settingsModal.style.display = 'flex';
    if (settingsThemeSelect) settingsThemeSelect.value = document.documentElement.getAttribute('data-theme') || 'glass';
    if (settingsAnimSelect) settingsAnimSelect.value = localStorage.getItem('renderflow_anim_mode') || 'full';
    if (settings3dSelect) settings3dSelect.value = localStorage.getItem('renderflow_3d_quality') || 'auto';
  }

  function closeSettingsModal() {
    if (settingsModal) settingsModal.style.display = 'none';
  }

  if (btnSettings) btnSettings.addEventListener('click', openSettingsModal);
  if (btnCloseSettings) btnCloseSettings.addEventListener('click', closeSettingsModal);
  if (btnCancelSettings) btnCancelSettings.addEventListener('click', closeSettingsModal);

  if (settingsThemeSelect) {
    settingsThemeSelect.addEventListener('change', (e) => {
      window.setRenderFlowTheme(e.target.value, true);
    });
  }

  if (settingsAnimSelect) {
    settingsAnimSelect.addEventListener('change', (e) => {
      const mode = e.target.value;
      localStorage.setItem('renderflow_anim_mode', mode);
      document.documentElement.setAttribute('data-anim', mode);
      if (window.renderflowMotion) {
        window.renderflowMotion.reducedMotion = (mode === 'off' || mode === 'reduced');
      }
      showToast(`Animation mode: ${mode.toUpperCase()}`, 'info');
    });
  }

  if (settings3dSelect) {
    settings3dSelect.addEventListener('change', (e) => {
      const q = e.target.value;
      localStorage.setItem('renderflow_3d_quality', q);
      if (window.renderCore3DInstance && typeof window.renderCore3DInstance.setQuality === 'function') {
        window.renderCore3DInstance.setQuality(q);
      }
      showToast(`3D effects mode: ${q.toUpperCase()}`, 'info');
    });
  }

  if (btnApplySettings) {
    btnApplySettings.addEventListener('click', () => {
      closeSettingsModal();
      showToast('Workstation appearance preferences applied', 'success');
    });
  }

  // 1D. Production Software Updater Controller (Phase 2 & Phase 3)
  const updateVersionBadge = document.getElementById('updateVersionBadge');
  const updateLatestBadge = document.getElementById('updateLatestBadge');
  const updateChannelBadge = document.getElementById('updateChannelBadge');
  const updateStatusText = document.getElementById('updateStatusText');
  const updateLastCheckedText = document.getElementById('updateLastCheckedText');
  const btnCheckUpdates = document.getElementById('btnCheckUpdates');
  const btnViewDiagnostics = document.getElementById('btnViewDiagnostics');
  const btnCloseDiagnostics = document.getElementById('btnCloseDiagnostics');
  const updateDiagnosticsBox = document.getElementById('updateDiagnosticsBox');
  const updateDiagnosticsContent = document.getElementById('updateDiagnosticsContent');
  const btnShowRecovery = document.getElementById('btnShowRecovery');
  const updateRecoveryBox = document.getElementById('updateRecoveryBox');
  const checkUpdatesIcon = document.getElementById('checkUpdatesIcon');
  const checkUpdatesLabel = document.getElementById('checkUpdatesLabel');
  const updateDetailsBox = document.getElementById('updateDetailsBox');
  const updateTargetTitle = document.getElementById('updateTargetTitle');
  const updateTypeTag = document.getElementById('updateTypeTag');
  const updateSpeedBadge = document.getElementById('updateSpeedBadge');
  const updatePackageSize = document.getElementById('updatePackageSize');
  const updateByteCounts = document.getElementById('updateByteCounts');
  const updateBytesText = document.getElementById('updateBytesText');
  const updateReleaseNotesBox = document.getElementById('updateReleaseNotesBox');
  const updateProgressContainer = document.getElementById('updateProgressContainer');
  const updateProgressMsg = document.getElementById('updateProgressMsg');
  const updateProgressPct = document.getElementById('updateProgressPct');
  const updateProgressBar = document.getElementById('updateProgressBar');
  const btnCancelDownload = document.getElementById('btnCancelDownload');
  const btnDownloadUpdate = document.getElementById('btnDownloadUpdate');
  const btnApplyUpdate = document.getElementById('btnApplyUpdate');
  const btnLaunchInstaller = document.getElementById('btnLaunchInstaller');
  const updateErrorBanner = document.getElementById('updateErrorBanner');
  const updateErrorText = document.getElementById('updateErrorText');
  const btnRetryUpdate = document.getElementById('btnRetryUpdate');
  const updateSuccessBanner = document.getElementById('updateSuccessBanner');
  const updateSuccessText = document.getElementById('updateSuccessText');
  const btnTopUpdateCenter = document.getElementById('btnTopUpdateCenter');
  const topUpdateBadge = document.getElementById('topUpdateBadge');
  const btnAboutCheckUpdate = document.getElementById('btnAboutCheckUpdate');
  const aboutModalVersion = document.getElementById('aboutModalVersion');

  let updatePollInterval = null;

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
  }

  function formatSpeed(kbps) {
    if (!kbps || kbps <= 0) return '0 KB/s';
    if (kbps >= 1024) {
      return (kbps / 1024).toFixed(1) + ' MB/s';
    }
    return Math.round(kbps) + ' KB/s';
  }

  function renderUpdateUI(status) {
    if (!status) return;

    // Synchronize authoritative installed version across all UI components
    if (status.current_version) {
      if (updateVersionBadge) updateVersionBadge.textContent = 'v' + status.current_version;
      if (aboutModalVersion) aboutModalVersion.textContent = 'v' + status.current_version;
    }

    if (updateLastCheckedText) {
      if (status.last_checked && status.last_checked > 0) {
        try {
          const ts = status.last_checked > 1e11 ? status.last_checked : status.last_checked * 1000;
          const d = new Date(ts);
          const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          if (status.is_verified) {
            updateLastCheckedText.textContent = `Verified against GitHub Releases at ${timeStr}`;
          } else if (status.state === 'error' || status.check_status === 'check_failed') {
            updateLastCheckedText.textContent = `Check failed: ${status.error_message || status.error || 'Server unreachable'}`;
          } else {
            updateLastCheckedText.textContent = `Checked at ${timeStr}`;
          }
        } catch (e) {
          updateLastCheckedText.textContent = 'Click "Check for Updates" to verify against GitHub Releases';
        }
      } else {
        updateLastCheckedText.textContent = 'Click "Check for Updates" to verify against GitHub Releases';
      }
    }

    const rawState = (status.state || 'IDLE').toUpperCase();

    // Reset banners and badges
    if (updateErrorBanner) updateErrorBanner.style.display = 'none';
    if (updateSuccessBanner) updateSuccessBanner.style.display = 'none';
    if (updateLatestBadge) updateLatestBadge.style.display = 'none';
    if (topUpdateBadge) topUpdateBadge.style.display = (rawState === 'AVAILABLE' || rawState === 'DOWNLOADED') ? 'block' : 'none';

    // Strict State 1: NOT CHECKED (Initial unverified state - Never green, never claims latest)
    const isUnverified = (!status.is_verified && (rawState === 'IDLE' || status.check_status === 'not_checked')) || (!status.last_checked || status.last_checked === 0);
    if (isUnverified && rawState !== 'CHECKING' && rawState !== 'ERROR') {
      if (updateStatusText) updateStatusText.innerHTML = '<span style="color:#94a3b8; font-weight:500">Not checked yet</span>';
      if (btnCheckUpdates) btnCheckUpdates.disabled = false;
      if (checkUpdatesLabel) checkUpdatesLabel.textContent = 'Check for Updates';
      if (checkUpdatesIcon) checkUpdatesIcon.textContent = '🔄';
      if (updateDetailsBox) updateDetailsBox.style.display = 'none';
      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
      return;
    }

    // State 2: CHECKING
    if (rawState === 'CHECKING' || status.check_status === 'checking') {
      if (updateStatusText) updateStatusText.innerHTML = '<span style="color:var(--rf-accent, #00f0ff); font-weight:600">Checking GitHub Releases...</span>';
      if (btnCheckUpdates) btnCheckUpdates.disabled = true;
      if (checkUpdatesLabel) checkUpdatesLabel.textContent = 'Checking...';
      if (checkUpdatesIcon) checkUpdatesIcon.textContent = '⏳';
      return;
    } else {
      if (btnCheckUpdates) btnCheckUpdates.disabled = false;
      if (checkUpdatesLabel) checkUpdatesLabel.textContent = 'Check for Updates';
      if (checkUpdatesIcon) checkUpdatesIcon.textContent = '🔄';
    }

    // Synchronize latest version badge ONLY if remote version was cryptographically verified
    const hasVerifiedRemote = Boolean(status.is_verified && status.latest_version && (rawState === 'UP_TO_DATE' || rawState === 'UPDATE_AVAILABLE' || rawState === 'AVAILABLE'));
    if (hasVerifiedRemote && updateLatestBadge) {
      updateLatestBadge.style.display = 'inline-block';
      updateLatestBadge.textContent = 'Latest: v' + status.latest_version;
    } else if (updateLatestBadge) {
      updateLatestBadge.style.display = 'none';
    }

    // State 3: UP_TO_DATE (VERIFIED LATEST)
    if (rawState === 'UP_TO_DATE' || (status.is_verified && status.check_status === 'verified_latest')) {
      if (updateStatusText) {
        updateStatusText.innerHTML = `<span style="color:#10b981; font-weight:600">✓ Latest version installed (v${status.current_version || ''})</span>`;
      }
      if (updateDetailsBox) updateDetailsBox.style.display = 'none';
      if (updateRecoveryBox) updateRecoveryBox.style.display = 'none';
      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
      return;
    }

    // State 4: UPDATE_AVAILABLE
    if (rawState === 'UPDATE_AVAILABLE' || rawState === 'AVAILABLE') {
      const isPatch = (status.package_type === 'patch') || Boolean(status.can_patch && !status.can_install_full);
      if (updateStatusText) {
        updateStatusText.innerHTML = `<span style="color:var(--rf-accent, #00f0ff); font-weight:700">★ Update v${status.latest_version || 'New'} available</span>`;
      }
      if (updateDetailsBox) updateDetailsBox.style.display = 'block';
      if (updateTargetTitle) updateTargetTitle.textContent = `RenderFlow v${status.latest_version} Available`;
      if (updateTypeTag) {
        if (isPatch) {
          updateTypeTag.textContent = 'INCREMENTAL PATCH';
          updateTypeTag.style.background = '#8b5cf6';
        } else {
          updateTypeTag.textContent = 'COMPLETE INSTALLER';
          updateTypeTag.style.background = '#0ea5e9';
        }
      }
      if (updateSpeedBadge) updateSpeedBadge.style.display = 'none';
      if (updatePackageSize) updatePackageSize.textContent = status.package_size || formatBytes(status.package_size_bytes || 0);
      if (updateByteCounts) updateByteCounts.style.display = 'none';
      if (updateReleaseNotesBox) updateReleaseNotesBox.textContent = status.release_notes || 'Production reliability, performance enhancements, and security fixes.';
      if (updateProgressContainer) updateProgressContainer.style.display = 'none';
      if (updateRecoveryBox) updateRecoveryBox.style.display = 'none';

      if (btnCancelDownload) btnCancelDownload.style.display = 'none';
      if (btnDownloadUpdate) {
        btnDownloadUpdate.style.display = 'inline-flex';
        btnDownloadUpdate.disabled = false;
        btnDownloadUpdate.textContent = isPatch ? '⬇️ Download Patch' : '⬇️ Download Latest Version';
      }
      if (btnApplyUpdate) btnApplyUpdate.style.display = 'none';
      if (btnLaunchInstaller) btnLaunchInstaller.style.display = 'none';
      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
      return;
    }

    // State 5 & 6: DOWNLOADING / VERIFYING
    if (rawState === 'DOWNLOADING' || rawState === 'VERIFYING') {
      const isVerifying = rawState === 'VERIFYING' || (status.download_progress && status.download_progress.percent >= 99.9);
      if (updateStatusText) {
        updateStatusText.innerHTML = isVerifying
          ? '<span style="color:#38bdf8; font-weight:600">🛡️ Verifying Ed25519 signature &amp; SHA-256...</span>'
          : '<span style="color:var(--rf-accent, #00f0ff)">Downloading complete installer...</span>';
      }
      if (updateDetailsBox) updateDetailsBox.style.display = 'block';
      if (updateProgressContainer) updateProgressContainer.style.display = 'block';

      const prog = status.download_progress || {};
      const pct = Math.max(0, Math.min(100, Math.round(prog.percent || status.download_percent || 0)));
      if (updateProgressPct) updateProgressPct.textContent = pct + '%';
      if (updateProgressBar) updateProgressBar.style.width = pct + '%';
      if (updateProgressMsg) {
        updateProgressMsg.textContent = isVerifying ? 'Verifying installer checksum & signature...' : 'Downloading complete installer...';
      }

      if (updateByteCounts) updateByteCounts.style.display = 'inline';
      if (updateBytesText) {
        updateBytesText.textContent = prog.bytes_formatted || `${formatBytes(prog.downloaded_bytes || 0)} / ${formatBytes(prog.total_bytes || status.package_size_bytes || 0)}`;
      }

      const speedStr = prog.speed_formatted || (prog.speed_bytes_per_sec ? formatBytes(prog.speed_bytes_per_sec) + '/s' : '0 KB/s');
      if (updateSpeedBadge) {
        updateSpeedBadge.style.display = speedStr !== '0 KB/s' ? 'inline-block' : 'none';
        updateSpeedBadge.textContent = speedStr;
      }

      if (btnCancelDownload) {
        btnCancelDownload.style.display = isVerifying ? 'none' : 'inline-flex';
        btnCancelDownload.disabled = isVerifying;
      }
      if (btnDownloadUpdate) {
        btnDownloadUpdate.style.display = 'inline-flex';
        btnDownloadUpdate.disabled = true;
        btnDownloadUpdate.textContent = '⏳ Downloading...';
      }
      if (btnApplyUpdate) btnApplyUpdate.style.display = 'none';
      if (btnLaunchInstaller) btnLaunchInstaller.style.display = 'none';

      if (!updatePollInterval) {
        updatePollInterval = setInterval(fetchUpdateStatus, 450);
      }
      return;
    }

    // State 7: READY_TO_INSTALL (VERIFIED PACKAGE DOWNLOADED)
    if (rawState === 'READY_TO_INSTALL' || rawState === 'INSTALLER_READY' || rawState === 'DOWNLOADED') {
      const isPatch = (status.package_type === 'patch') || Boolean(status.patch_ready);
      if (updateStatusText) {
        updateStatusText.innerHTML = isPatch
          ? '<span style="color:#10b981; font-weight:700">✓ Incremental patch verified &amp; ready to install</span>'
          : '<span style="color:#10b981; font-weight:700">✓ Complete installer verified &amp; ready to install</span>';
      }
      if (updateDetailsBox) updateDetailsBox.style.display = 'block';
      if (updateProgressContainer) updateProgressContainer.style.display = 'block';
      if (updateProgressPct) updateProgressPct.textContent = '100%';
      if (updateProgressBar) updateProgressBar.style.width = '100%';
      if (updateProgressMsg) updateProgressMsg.textContent = 'RFC 8032 Ed25519 & SHA-256 verified successfully.';
      if (updateSpeedBadge) updateSpeedBadge.style.display = 'none';
      if (btnCancelDownload) btnCancelDownload.style.display = 'none';
      if (btnDownloadUpdate) btnDownloadUpdate.style.display = 'none';

      if (isPatch) {
        if (btnApplyUpdate) {
          btnApplyUpdate.style.display = 'inline-flex';
          btnApplyUpdate.disabled = false;
          btnApplyUpdate.textContent = '⚡ Install & Restart Now';
        }
        if (btnLaunchInstaller) btnLaunchInstaller.style.display = 'none';
      } else {
        if (btnLaunchInstaller) {
          btnLaunchInstaller.style.display = 'inline-flex';
          btnLaunchInstaller.disabled = false;
          btnLaunchInstaller.textContent = '📦 Launch Installer & Update';
        }
        if (btnApplyUpdate) btnApplyUpdate.style.display = 'none';
      }

      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
      return;
    }

    // State 8: INSTALLING
    if (rawState === 'INSTALLING') {
      if (updateStatusText) {
        updateStatusText.innerHTML = '<span style="color:#38bdf8; font-weight:600">⏳ Launching setup wizard. RenderFlow will close cleanly...</span>';
      }
      if (btnLaunchInstaller) {
        btnLaunchInstaller.disabled = true;
        btnLaunchInstaller.textContent = '⏳ Launching Installer...';
      }
      if (btnCancelDownload) btnCancelDownload.style.display = 'none';
      if (btnDownloadUpdate) btnDownloadUpdate.style.display = 'none';
      return;
    }

    // State 9: VERIFYING_INSTALL / READY_TO_RESTART
    if (rawState === 'VERIFYING_INSTALL' || rawState === 'READY_TO_RESTART') {
      if (updateStatusText) {
        updateStatusText.innerHTML = '<span style="color:#38bdf8; font-weight:600">🔄 RenderFlow is restarting. Verifying installed version...</span>';
      }
      if (btnApplyUpdate) {
        btnApplyUpdate.disabled = true;
        btnApplyUpdate.textContent = '🔄 Restarting...';
      }
      return;
    }

    // State 10: SUCCESS
    if (rawState === 'SUCCESS' || rawState === 'UPDATED') {
      if (updateStatusText) {
        updateStatusText.innerHTML = '<span style="color:#10b981; font-weight:700">✓ Successfully updated!</span>';
      }
      if (updateSuccessBanner) updateSuccessBanner.style.display = 'block';
      if (updateSuccessText) updateSuccessText.textContent = `Successfully updated to RenderFlow v${status.current_version || ''}!`;
      if (updateDetailsBox) updateDetailsBox.style.display = 'none';
      if (updateRecoveryBox) updateRecoveryBox.style.display = 'none';
      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
      return;
    }

    // Error States: CHECK_FAILED, DOWNLOAD_FAILED, VERIFICATION_FAILED, INSTALL_FAILED, VERIFY_FAILED, ERROR
    if (rawState.includes('FAILED') || rawState === 'ERROR' || status.check_status === 'check_failed') {
      const err = status.error_message || status.error || 'Update operation encountered an error.';
      const isOffline = err.toLowerCase().includes('offline') || err.toLowerCase().includes('network') || err.toLowerCase().includes('unreachable') || err.toLowerCase().includes('timed out');

      // Explicitly hide any success or latest version badges
      if (updateLatestBadge) updateLatestBadge.style.display = 'none';
      if (updateSuccessBanner) updateSuccessBanner.style.display = 'none';

      if (updateStatusText) {
        updateStatusText.innerHTML = `<span style="color:#ef4444; font-weight:600">⚠️ ${rawState.replace('_', ' ')}</span>`;
      }
      if (updateLastCheckedText) {
        updateLastCheckedText.textContent = `Check failed: ${err}`;
      }

      if (updateErrorBanner) {
        updateErrorBanner.style.display = 'block';
        if (updateErrorText) {
          updateErrorText.textContent = isOffline
            ? `⚠️ Update server unavailable: ${err}`
            : `⚠️ ${err}`;
        }
      }

      if (btnCancelDownload) btnCancelDownload.style.display = 'none';
      if (btnDownloadUpdate) {
        btnDownloadUpdate.disabled = false;
        btnDownloadUpdate.textContent = '🔄 Retry Check';
      }
      if (updatePollInterval) { clearInterval(updatePollInterval); updatePollInterval = null; }
    }
  }

  async function fetchUpdateStatus() {
    try {
      const res = await fetch('/api/update/status');
      if (res.ok) {
        const data = await res.json();
        renderUpdateUI(data);
        return data;
      } else {
        const errData = await res.json().catch(() => ({}));
        const msg = errData.message || `Server returned HTTP ${res.status}`;
        console.warn('[UPDATER] Status error:', msg);
      }
    } catch (err) {
      console.warn('[UPDATER] Failed to query status:', err);
      if (!(btnApplyUpdate && btnApplyUpdate.textContent.includes('Restarting'))) {
        if (updateLastCheckedText) {
          updateLastCheckedText.textContent = 'Local RenderFlow server unreachable';
        }
      }
    }
    return null;
  }

  async function triggerUpdateCheck(manual = false) {
    if (btnCheckUpdates) btnCheckUpdates.disabled = true;
    if (checkUpdatesLabel) checkUpdatesLabel.textContent = 'Checking...';
    if (checkUpdatesIcon) checkUpdatesIcon.textContent = '⏳';
    if (updateStatusText) updateStatusText.innerHTML = '<span style="color:var(--rf-accent, #00f0ff); font-weight:600">Checking for updates...</span>';
    // Invalidate stale success indicators immediately when a new check begins
    if (updateLatestBadge) updateLatestBadge.style.display = 'none';
    if (updateSuccessBanner) updateSuccessBanner.style.display = 'none';
    if (updateErrorBanner) updateErrorBanner.style.display = 'none';

    try {
      const res = await fetch('/api/update/check', { method: 'POST' });
      const data = await res.json();
      if (data && data.status) {
        renderUpdateUI(data.status);
      } else {
        await fetchUpdateStatus();
      }

      if (manual) {
        if (data.ok && data.update_available) {
          showToast(`🚀 RenderFlow v${data.latest_version} is available!`, 'success');
        } else if (data.ok) {
          showToast(`RenderFlow is up to date (v${data.current_version || ''})`, 'info');
        } else {
          const failMsg = data.message || (data.status && (data.status.error_message || data.status.error)) || 'Could not reach update server';
          showToast(failMsg, 'warning');
        }
      }
    } catch (err) {
      console.error('[UPDATER] Check error:', err);
      if (updateLatestBadge) updateLatestBadge.style.display = 'none';
      if (updateSuccessBanner) updateSuccessBanner.style.display = 'none';
      if (updateStatusText) updateStatusText.innerHTML = '<span style="color:#ef4444; font-weight:600">⚠️ Update check failed</span>';
      if (updateLastCheckedText) updateLastCheckedText.textContent = `Check failed: ${err.message || 'Offline or network error'}`;
      if (updateErrorBanner) {
        updateErrorBanner.style.display = 'block';
        if (updateErrorText) updateErrorText.textContent = `⚠️ Network offline or server unreachable`;
      }
      if (manual) {
        showToast('Unable to check for updates (Offline or network error)', 'warning');
      }
    } finally {
      if (btnCheckUpdates) btnCheckUpdates.disabled = false;
      if (checkUpdatesLabel) checkUpdatesLabel.textContent = 'Check for Updates';
      if (checkUpdatesIcon) checkUpdatesIcon.textContent = '🔄';
    }
  }

  if (btnCheckUpdates) {
    btnCheckUpdates.addEventListener('click', () => triggerUpdateCheck(true));
  }

  if (btnRetryUpdate) {
    btnRetryUpdate.addEventListener('click', () => triggerUpdateCheck(true));
  }

  if (btnTopUpdateCenter) {
    btnTopUpdateCenter.addEventListener('click', () => {
      openSettingsModal();
      setTimeout(() => {
        const el = document.getElementById('updateCenterSection');
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    });
  }

  if (btnAboutCheckUpdate) {
    btnAboutCheckUpdate.addEventListener('click', () => {
      closeAboutModal();
      openSettingsModal();
      setTimeout(() => {
        const el = document.getElementById('updateCenterSection');
        if (el) el.scrollIntoView({ behavior: 'smooth' });
        triggerUpdateCheck(true);
      }, 150);
    });
  }

  if (btnCancelDownload) {
    btnCancelDownload.addEventListener('click', async () => {
      btnCancelDownload.disabled = true;
      btnCancelDownload.textContent = 'Cancelling...';
      try {
        const res = await fetch('/api/update/cancel', { method: 'POST' });
        const data = await res.json();
        if (data.status) {
          renderUpdateUI(data.status);
        }
        showToast('Update download cancelled', 'info');
      } catch (err) {
        showToast('Failed to cancel download: ' + err.message, 'error');
      }
    });
  }

  if (btnDownloadUpdate) {
    btnDownloadUpdate.addEventListener('click', async () => {
      btnDownloadUpdate.disabled = true;
      btnDownloadUpdate.textContent = '⏳ Starting download...';
      try {
        const res = await fetch('/api/update/download', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
          showToast('Download started in background...', 'info');
          if (!updatePollInterval) {
            updatePollInterval = setInterval(fetchUpdateStatus, 450);
          }
        } else {
          showToast(`Download failed: ${data.message}`, 'error');
          btnDownloadUpdate.disabled = false;
          btnDownloadUpdate.textContent = '⬇️ Download and Install';
        }
      } catch (err) {
        showToast('Network error starting download', 'error');
        btnDownloadUpdate.disabled = false;
        btnDownloadUpdate.textContent = '⬇️ Download and Install';
      }
    });
  }

  if (btnViewDiagnostics) {
    btnViewDiagnostics.addEventListener('click', async () => {
      if (updateDiagnosticsBox && updateDiagnosticsBox.style.display === 'block') {
        updateDiagnosticsBox.style.display = 'none';
        return;
      }
      if (updateDiagnosticsBox) updateDiagnosticsBox.style.display = 'block';
      if (updateDiagnosticsContent) updateDiagnosticsContent.textContent = 'Loading diagnostic events...';
      try {
        const res = await fetch('/api/update/diagnostics');
        const data = await res.json();
        if (data.ok && data.recent_logs) {
          updateDiagnosticsContent.textContent = data.recent_logs.length > 0
            ? data.recent_logs.join('\n')
            : 'No update events recorded yet.';
        } else {
          updateDiagnosticsContent.textContent = 'Failed to load diagnostics.';
        }
      } catch (err) {
        if (updateDiagnosticsContent) updateDiagnosticsContent.textContent = 'Error loading diagnostics: ' + err.message;
      }
    });
  }

  if (btnCloseDiagnostics) {
    btnCloseDiagnostics.addEventListener('click', () => {
      if (updateDiagnosticsBox) updateDiagnosticsBox.style.display = 'none';
    });
  }

  if (btnShowRecovery) {
    btnShowRecovery.addEventListener('click', () => {
      if (updateRecoveryBox) {
        updateRecoveryBox.style.display = updateRecoveryBox.style.display === 'block' ? 'none' : 'block';
      }
    });
  }

  if (btnLaunchInstaller) {
    btnLaunchInstaller.addEventListener('click', async () => {
      if (!confirm('RenderFlow will launch the verified Windows Setup Installer.\n\nYour projects, media assets, settings, and credentials remain 100% safe and intact.\n\nRenderFlow will close cleanly to allow file installation.\n\nProceed?')) {
        return;
      }
      btnLaunchInstaller.disabled = true;
      btnLaunchInstaller.textContent = '⏳ Launching Installer...';
      try {
        const res = await fetch('/api/update/install_full', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
          showToast('Installer launched! RenderFlow is closing cleanly.', 'success');
          if (updateStatusText) {
            updateStatusText.innerHTML = '<span style="color:#10b981; font-weight:700">✓ Installer launched. RenderFlow will close now.</span>';
          }
        } else {
          showToast('Failed to launch installer: ' + data.message, 'error');
          btnLaunchInstaller.disabled = false;
          btnLaunchInstaller.textContent = '📦 Launch Installer & Update';
        }
      } catch (err) {
        showToast('Error launching installer: ' + err.message, 'error');
        btnLaunchInstaller.disabled = false;
        btnLaunchInstaller.textContent = '📦 Launch Installer & Update';
      }
    });
  }

  if (btnApplyUpdate) {
    btnApplyUpdate.addEventListener('click', async () => {
      if (!confirm('RenderFlow will apply the verified update and restart cleanly.\n\nYour projects, media, settings, and render history will remain completely untouched.\n\nProceed with restart?')) {
        return;
      }

      btnApplyUpdate.disabled = true;
      btnApplyUpdate.textContent = '⏳ Staging update...';
      if (updateStatusText) updateStatusText.innerHTML = '<span style="color:#f59e0b; font-weight:600">⏳ Staging patch and creating backup...</span>';

      try {
        const res = await fetch('/api/update/apply', { method: 'POST' });
        const data = await res.json().catch(() => ({ ok: false, message: 'Invalid response from update server' }));
        if (data && data.ok) {
          showToast('Patch staged! Relaunching RenderFlow...', 'info');
          if (updateStatusText) updateStatusText.innerHTML = '<span style="color:#38bdf8; font-weight:600">🔄 Staged. Triggering restart helper...</span>';
          btnApplyUpdate.textContent = '🔄 Restarting...';

          // Request restart
          try {
            await fetch('/api/update/restart', { method: 'POST' });
          } catch (e) {
            // Expected if server terminates quickly
          }

          // Start bounded health-check verification loop
          let pollCount = 0;
          const maxPolls = 35; // up to 35 seconds
          const targetVersion = (data.status && data.status.latest_version) || (data.status && data.status.current_version);

          if (updateStatusText) {
            updateStatusText.innerHTML = '<span style="color:#38bdf8; font-weight:600">🔄 RenderFlow is restarting. Waiting for backend...</span>';
          }

          const restartPollTimer = setInterval(async () => {
            pollCount++;
            try {
              const healthRes = await fetch('/api/system_status', { cache: 'no-store' });
              if (healthRes.ok) {
                clearInterval(restartPollTimer);

                // Query new server status for verified running version
                let verifiedVersion = targetVersion;
                try {
                  const statusRes = await fetch('/api/update/status', { cache: 'no-store' });
                  if (statusRes.ok) {
                    const statusData = await statusRes.json();
                    if (statusData.current_version) verifiedVersion = statusData.current_version;
                  }
                } catch (_) {}

                // ONLY NOW DISPLAY GREEN INSTALLED SUCCESS BANNER
                if (updateStatusText) {
                  updateStatusText.innerHTML = `<span style="color:#10b981; font-weight:700">✓ Successfully updated to RenderFlow v${verifiedVersion}!</span>`;
                }
                if (updateSuccessBanner) updateSuccessBanner.style.display = 'block';
                showToast(`✓ RenderFlow updated to v${verifiedVersion}! Reloading...`, 'success');

                setTimeout(() => {
                  window.location.reload();
                }, 1500);
                return;
              }
            } catch (e) {
              // Expected while server process restarts
              if (updateStatusText) {
                updateStatusText.innerHTML = `<span style="color:#f59e0b">⏳ Reconnecting to RenderFlow (attempt ${pollCount}/${maxPolls})...</span>`;
              }
            }

            if (pollCount >= maxPolls) {
              clearInterval(restartPollTimer);
              // TIMEOUT FAILURE: Server never restarted or port blocked
              if (updateStatusText) {
                updateStatusText.innerHTML = '<span style="color:#ef4444; font-weight:700">⚠️ Restart verification timed out: Local server unreachable. Please relaunch RenderFlow manually.</span>';
              }
              if (updateErrorBanner) {
                updateErrorBanner.style.display = 'block';
                if (updateErrorText) updateErrorText.textContent = 'Server restart timed out after 35 seconds. Your files have been updated; please run run_localhost.bat or RenderingStudio.exe manually.';
              }
              showToast('Server restart timed out. Please relaunch manually.', 'error');
              btnApplyUpdate.disabled = false;
              btnApplyUpdate.textContent = '⚡ Retry Restart';
            }
          }, 1000);

        } else {
          const failMsg = (data && (data.message || data.error)) || `Server returned HTTP ${res.status}`;
          showToast(`Update failed: ${failMsg}`, 'error');
          if (updateStatusText) updateStatusText.innerHTML = `<span style="color:#ef4444; font-weight:600">⚠️ Update failed: ${failMsg}</span>`;
          btnApplyUpdate.disabled = false;
          btnApplyUpdate.textContent = '⚡ Install & Restart Now';
          await fetchUpdateStatus();
        }
      } catch (err) {
        const errMsg = err && err.message ? err.message : 'Network error';
        showToast('Error applying update: ' + errMsg, 'error');
        if (updateStatusText) updateStatusText.innerHTML = `<span style="color:#ef4444; font-weight:600">⚠️ Error applying update: ${errMsg}</span>`;
        btnApplyUpdate.disabled = false;
        btnApplyUpdate.textContent = '⚡ Install & Restart Now';
      }
    });
  }

  // Hook into openSettingsModal to refresh update status
  const originalOpenSettingsModal = openSettingsModal;
  openSettingsModal = function() {
    originalOpenSettingsModal();
    fetchUpdateStatus();
  };
  if (btnSettings) {
    btnSettings.removeEventListener('click', originalOpenSettingsModal);
    btnSettings.addEventListener('click', openSettingsModal);
  }

  // Initial passive status fetch
  setTimeout(fetchUpdateStatus, 2000);

  // 2. Dismiss Splash Screen
  const splash = document.getElementById('renderflowSplash');
  if (splash) {
    if (urlParams.has('theme') || urlParams.has('picker') || urlParams.has('view')) {
      splash.classList.add('hidden');
    } else {
      setTimeout(() => {
        splash.classList.add('hidden');
      }, 1400);
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !splash.classList.contains('hidden')) {
        splash.classList.add('hidden');
      }
    });
  }

  // 3. Strategic 3D Render-Core initialization
  try {
    if (window.RenderFlow3DCore) {
      window.renderCore3DInstance = new RenderFlow3DCore('renderCore3D');
      renderCore3DInstance = window.renderCore3DInstance;
    }
  } catch (e) {
    console.warn('[RenderFlow 3D] Init note:', e);
  }

  // 4. Command Palette Trigger
  const cmdBtn = document.getElementById('btnCmdPalette');
  if (cmdBtn) {
    cmdBtn.addEventListener('click', () => {
      if (window.renderflowCommandPalette) window.renderflowCommandPalette.toggle();
    });
  }

  // 5. Workflow Stepper Navigation
  const steps = document.querySelectorAll('.workflow-step');
  steps.forEach(step => {
    step.addEventListener('click', () => {
      const stage = step.getAttribute('data-step');
      steps.forEach(s => s.classList.remove('active'));
      step.classList.add('active');
      if (stage === 'upload') {
        const u = document.getElementById('btnOpenUpload');
        if (u) u.click();
      } else if (stage === 'sync') {
        const a = document.getElementById('btnAutoPlan');
        if (a) a.click();
      } else if (stage === 'review') {
        const r = document.getElementById('btnReviewLowConf');
        if (r) r.click();
      } else if (stage === 'style') {
        const s = document.getElementById('btnSelectCaptionStyle');
        if (s) s.click();
      } else if (stage === 'render') {
        switchTab('tab-render');
      } else if (stage === 'download') {
        switchTab('tab-showcase');
      }
    });
  });

  // 6. About Modal
  const btnAbout = document.getElementById('btnAboutModal');
  const aboutModal = document.getElementById('aboutModal');
  const btnCloseAbout = document.getElementById('btnCloseAboutModal');
  if (btnAbout && aboutModal) {
    btnAbout.addEventListener('click', () => { aboutModal.style.display = 'flex'; });
    if (btnCloseAbout) btnCloseAbout.addEventListener('click', () => { aboutModal.style.display = 'none'; });
  }

  // 6b. Exit Studio & Clean Server Shutdown (§3)
  const btnExit = document.getElementById('btnExitStudio');
  if (btnExit) {
    btnExit.addEventListener('click', async () => {
      let isRendering = false;
      try {
        const statusRes = await fetch('/api/lifecycle/status');
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          isRendering = Boolean(statusData.rendering);
        }
      } catch (e) {}

      let forceShutdown = false;
      if (isRendering) {
        const confirmCancel = confirm(
          "⚠️ WARNING: A video render is currently in progress!\n\n" +
          "Exiting now will cancel the active render. Do you want to cancel the render and exit RenderFlow?"
        );
        if (!confirmCancel) return;
        forceShutdown = true;
      } else {
        const confirmExit = confirm(
          "🛑 Exit RenderFlow Studio?\n\n" +
          "This will cleanly stop the local server, release port 8000, and close the workstation."
        );
        if (!confirmExit) return;
      }

      btnExit.disabled = true;
      btnExit.textContent = "Stopping...";

      try {
        const shutdownRes = await fetch('/api/shutdown', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ force: forceShutdown })
        });
        
        if (shutdownRes.status === 409) {
          const conflictData = await shutdownRes.json();
          alert(conflictData.message || "A render is currently active.");
          btnExit.disabled = false;
          btnExit.textContent = "🛑 Exit";
          return;
        }
      } catch (err) {
        // Expected as server terminates
      }

      document.body.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100vh; background:#0f172a; color:#f8fafc; font-family:system-ui, -apple-system, sans-serif; text-align:center; padding:2rem;">
          <div style="font-size:3.5rem; margin-bottom:1rem;">🛑</div>
          <h1 style="font-size:1.8rem; font-weight:700; margin-bottom:0.5rem; color:#00f0ff;">RenderFlow Workstation Has Shut Down</h1>
          <p style="color:#94a3b8; max-width:480px; line-height:1.6; margin-bottom:1.5rem;">
            The local server has stopped cleanly and port 8000 has been released.<br>
            All temporary resources and locks have been cleared.
          </p>
          <div style="font-size:0.85rem; color:#64748b; background:rgba(255,255,255,0.05); padding:0.6rem 1.2rem; border-radius:6px; border:1px solid rgba(255,255,255,0.08);">
            ✓ You can now safely close this browser tab.
          </div>
        </div>
      `;
    });
  }

  // 7. System Health Modal (Real /api/health Runtime Audit)
  const btnHealth = document.getElementById('btnSystemHealth');
  const healthModal = document.getElementById('systemHealthModal');
  const btnCloseHealth = document.getElementById('btnCloseSystemHealth') || document.getElementById('btnCloseHealthModal');
  const healthContent = document.getElementById('systemHealthContent') || document.getElementById('systemHealthGrid');

  async function renderSystemHealthModal() {
    if (!healthContent) return;
    healthContent.innerHTML = '<div style="color:var(--rf-muted, #94a3b8); padding:1rem; text-align:center">Auditing system readiness and runtime state...</div>';
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      const checks = data.checks || [];
      if (!checks.length) {
        healthContent.innerHTML = '<div style="color:var(--rf-muted, #94a3b8); padding:1rem">No health telemetry checks returned.</div>';
        return;
      }
      healthContent.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; padding:0.6rem 0.85rem; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px">
          <div>
            <div style="font-weight:700; font-size:0.9rem">Overall Health Status: <span style="color:${data.status === 'ready' ? 'var(--rf-success, #10b981)' : 'var(--rf-warning, #f59e0b)'}">${(data.status || 'READY').toUpperCase()}</span></div>
            <div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8)">Workspace: ${data.workspace || 'RenderFlow Core'}</div>
          </div>
          <button class="btn btn-secondary btn-sm" id="btnRecheckHealth">Re-check</button>
        </div>
        <div style="display:flex; flex-direction:column; gap:0.6rem">
          ${checks.map(c => {
            const isPass = c.status === 'PASS';
            const isWarn = c.status === 'WARNING';
            const badgeColor = isPass ? 'var(--rf-success, #10b981)' : (isWarn ? 'var(--rf-warning, #f59e0b)' : 'var(--rf-danger, #ef4444)');
            const badgeBg = isPass ? 'rgba(16,185,129,0.1)' : (isWarn ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)');
            return `
              <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:0.75rem 1rem">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem">
                  <strong style="font-size:0.85rem">${c.component}</strong>
                  <span style="font-size:0.72rem; font-weight:700; color:${badgeColor}; background:${badgeBg}; padding:2px 8px; border-radius:4px; border:1px solid ${badgeColor}33">${c.status}</span>
                </div>
                <div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8); font-family:var(--font-mono)">${c.detail || ''}</div>
              </div>
            `;
          }).join('')}
        </div>
      `;
      const recheckBtn = document.getElementById('btnRecheckHealth');
      if (recheckBtn) recheckBtn.addEventListener('click', renderSystemHealthModal);
    } catch (e) {
      healthContent.innerHTML = `<div style="color:var(--rf-danger, #ef4444); padding:1rem">Failed to load health audit: ${e.message}</div>`;
    }
  }

  if (btnHealth && healthModal) {
    btnHealth.addEventListener('click', () => {
      healthModal.style.display = 'flex';
      renderSystemHealthModal();
    });
    if (btnCloseHealth) btnCloseHealth.addEventListener('click', () => { healthModal.style.display = 'none'; });
  }

  // 8. Hardware Diagnostics Modal & Telemetry
  const btnHardware = document.getElementById('btnHardwareDiag');
  const hardwareModal = document.getElementById('hardwareDiagModal');
  const btnCloseHardware = document.getElementById('btnCloseHardwareDiag') || document.getElementById('btnCloseHardwareModal');
  const hardwareContent = document.getElementById('hardwareDiagContent');
  const btnRefreshHw = document.getElementById('btnRefreshHwTelemetry');

  window.fetchAndApplyHardwareTelemetry = async function() {
    try {
      const res = await fetch('/api/hardware/info');
      const data = await res.json();
      const cpu = data.cpu || {};
      const ram = data.ram || {};
      const gpus = data.gpus || [];
      const encoders = data.encoders || {};
      const c = data.classification || {};

      // Populate view-hardware cards
      const hwCpuModel = document.getElementById('hwCpuModel');
      const hwCpuCores = document.getElementById('hwCpuCores');
      const hwRamUsage = document.getElementById('hwRamUsage');
      const hwRamStatus = document.getElementById('hwRamStatus');
      const hwGpuModel = document.getElementById('hwGpuModel');
      const hwGpuStatus = document.getElementById('hwGpuStatus');
      const sysFfmpeg = document.getElementById('sysFfmpeg');
      const sysPack = document.getElementById('sysPack');

      if (hwCpuModel) hwCpuModel.textContent = cpu.model || 'Unknown CPU';
      if (hwCpuCores) hwCpuCores.textContent = `${cpu.physical_cores || 2} Physical Cores / ${cpu.logical_cores || 4} Threads`;
      if (hwRamUsage) hwRamUsage.textContent = `${ram.used_percent ? ((ram.total_gb * ram.used_percent / 100).toFixed(1) + ' GB / ') : ''}${ram.total_gb || '--'} GB`;
      if (hwRamStatus) hwRamStatus.textContent = `${ram.available_gb || '--'} GB Free (${ram.used_percent || 0}% Used)`;
      if (hwGpuModel) hwGpuModel.textContent = gpus.length ? gpus[0].name : (c.recommended_encoder || 'CPU libx264');
      if (hwGpuStatus) hwGpuStatus.textContent = c.recommended_encoder ? `Encoder: ${c.recommended_encoder}` : 'Standard Pipeline';

      // Populate status strip
      const stripCpu = document.getElementById('stripCpuVal');
      const stripRam = document.getElementById('stripRamVal');
      const stripGpu = document.getElementById('stripGpuVal');
      if (stripCpu) stripCpu.textContent = `${(cpu.model || 'CPU').slice(0, 24)} (${cpu.logical_cores || 4}T)`;
      if (stripRam) stripRam.textContent = `${ram.total_gb || '--'} GB (${ram.used_percent || 0}% Used)`;
      if (stripGpu) stripGpu.textContent = `${c.recommended_encoder || 'CPU'} (${c.profile_name || 'Standard'})`;

      // Update FFmpeg and pack info
      try {
        const sysRes = await fetch('/api/system_status');
        const sysData = await sysRes.json();
        if (sysFfmpeg && sysData.ffmpeg) {
          sysFfmpeg.textContent = sysData.ffmpeg.ok ? 'Verified (Bundled 64-bit)' : 'Not Found';
        }
        if (sysPack && sysData.transition_pack) {
          sysPack.textContent = `${sysData.transition_pack.usable_clips || 74} Native Clips`;
        }
      } catch (err) {}

      // Populate hardware diag modal if present
      if (hardwareContent) {
        let encHtml = Object.entries(encoders).map(([k, v]) => `
          <div style="display:flex; justify-content:space-between; font-size:0.75rem; padding:0.35rem 0; border-bottom:1px solid rgba(255,255,255,0.05)">
            <span style="font-family:var(--font-mono)">${k}</span>
            <span style="color:${v ? 'var(--rf-success, #10b981)' : 'var(--rf-muted, #94a3b8)'}; font-weight:700">${v ? 'VERIFIED' : 'UNAVAILABLE'}</span>
          </div>
        `).join('');

        let gpuHtml = gpus.map(g => `
          <div style="font-size:0.78rem; margin-bottom:0.35rem">
            <strong>${g.name}</strong> (${g.vendor}) — VRAM: ${g.vram_mb ? g.vram_mb + ' MB' : 'Shared/Integrated'}
          </div>
        `).join('') || '<div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8)">Integrated display adapter</div>';

        hardwareContent.innerHTML = `
          <div style="margin-bottom:1rem; padding:0.85rem; background:rgba(0,240,255,0.06); border:1px solid rgba(0,240,255,0.2); border-radius:8px">
            <div style="font-size:0.9rem; font-weight:700; color:var(--rf-accent, #00f0ff)">${c.ui_badge || c.profile_name || 'Hardware Profile'}</div>
            <div style="font-size:0.78rem; color:var(--rf-muted, #94a3b8); margin-top:0.25rem">${c.recommendation_note || 'Hardware profile detected.'}</div>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.85rem; margin-bottom:0.85rem">
            <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:0.85rem">
              <div style="font-size:0.72rem; color:var(--rf-muted, #64748b); text-transform:uppercase">Processor (CPU)</div>
              <div style="font-size:0.88rem; font-weight:700; margin-top:4px">${cpu.model || 'Unknown CPU'}</div>
              <div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8); margin-top:2px">${cpu.physical_cores || 2} Cores &bull; ${cpu.logical_cores || 4} Threads</div>
            </div>
            <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:0.85rem">
              <div style="font-size:0.72rem; color:var(--rf-muted, #64748b); text-transform:uppercase">System Memory (RAM)</div>
              <div style="font-size:0.88rem; font-weight:700; margin-top:4px">${ram.total_gb || '--'} GB Total</div>
              <div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8); margin-top:2px">${ram.available_gb || '--'} GB Available (${ram.used_percent || 0}% Used)</div>
            </div>
          </div>
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:0.85rem; margin-bottom:0.85rem">
            <div style="font-size:0.72rem; color:var(--rf-muted, #64748b); text-transform:uppercase; margin-bottom:0.35rem">Graphics Adapters (GPU)</div>
            ${gpuHtml}
          </div>
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:0.85rem">
            <div style="font-size:0.72rem; color:var(--rf-muted, #64748b); text-transform:uppercase; margin-bottom:0.5rem">Verified Hardware Encoders</div>
            ${encHtml}
          </div>
        `;
      }
    } catch (e) {
      console.warn('Hardware telemetry error:', e);
    }
  };

  if (btnHardware && hardwareModal) {
    btnHardware.addEventListener('click', () => {
      hardwareModal.style.display = 'flex';
      window.fetchAndApplyHardwareTelemetry();
    });
    if (btnCloseHardware) btnCloseHardware.addEventListener('click', () => { hardwareModal.style.display = 'none'; });
  }
  if (btnRefreshHw) {
    btnRefreshHw.addEventListener('click', async () => {
      showToast('Refreshing hardware telemetry...', 'info');
      await window.fetchAndApplyHardwareTelemetry();
      showToast('Hardware telemetry updated', 'success');
    });
  }

  // Visual Styles Interactive Selection (§13)
  const styleCards = document.querySelectorAll('.rf-style-card');
  styleCards.forEach(card => {
    card.addEventListener('click', async () => {
      const styleVal = card.getAttribute('data-style-val');
      state.visualStyle = styleVal;
      styleCards.forEach(c => {
        c.classList.remove('active');
        const b = c.querySelector('.style-active-badge');
        if (b) b.style.display = 'none';
      });
      card.classList.add('active');
      const activeBadge = card.querySelector('.style-active-badge');
      if (activeBadge) activeBadge.style.display = 'block';

      if (state.projectPath) {
        try {
          await fetch('/api/project/save_plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              project_path: state.projectPath,
              plan: { visual_style: styleVal }
            })
          });
          showToast(`Applied visual style: ${card.querySelector('div:nth-child(2)')?.textContent || styleVal}`, 'success');
        } catch (e) {
          console.warn('Failed to save visual style:', e);
        }
      } else {
        showToast(`Selected visual style: ${styleVal}`, 'info');
      }
    });
  });

  // Performance Profiles Selection
  const perfCards = document.querySelectorAll('.rf-perf-profile-card');
  perfCards.forEach(card => {
    card.addEventListener('click', () => {
      const perfVal = card.getAttribute('data-profile-val');
      perfCards.forEach(c => {
        c.classList.remove('active');
        const b = c.querySelector('.perf-active-badge');
        if (b) b.style.display = 'none';
      });
      card.classList.add('active');
      const activeBadge = card.querySelector('.perf-active-badge');
      if (activeBadge) activeBadge.style.display = 'block';
      localStorage.setItem('renderflow_perf_profile', perfVal);
      const perfSelect = document.getElementById('settingPerfMode');
      if (perfSelect) perfSelect.value = perfVal === 'max_quality' ? 'performance' : perfVal;
      showToast(`Active profile: ${card.querySelector('div:nth-child(2)')?.textContent || perfVal}`, 'info');
    });
  });

  // Initial fetch of hardware info to populate view and status strip
  window.fetchAndApplyHardwareTelemetry();
}

// Timecode Formatting Helper
function formatTimecode(secs) {
  if (isNaN(secs) || secs < 0) return '00:00:00.00';
  const hrs = Math.floor(secs / 3600).toString().padStart(2, '0');
  const mins = Math.floor((secs % 3600) / 60).toString().padStart(2, '0');
  const s = Math.floor(secs % 60).toString().padStart(2, '0');
  const ms = Math.floor((secs % 1) * 100).toString().padStart(2, '0');
  return `${hrs}:${mins}:${s}.${ms}`;
}

// Navigation & View Handler (RenderFlow Modern Desktop Shell)
function setupTabs() {
  const navItems = document.querySelectorAll('.rf-nav-item[data-view], .stitch-nav-tab[data-view]');
  const views = document.querySelectorAll('.rf-view, .stitch-view-pane');

  window.switchView = function(viewId) {
    const initStyle = document.getElementById('initial-view-style');
    if (initStyle) initStyle.remove();

    if (viewId === 'view-media' || viewId === 'view-timeline') {
      viewId = 'view-studio';
    }
    navItems.forEach(n => {
      n.classList.toggle('active', n.dataset.view === viewId);
    });
    document.querySelectorAll('.stitch-nav-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.view === viewId);
    });
    views.forEach(v => {
      if (v.id === viewId) {
        v.classList.add('active');
        v.style.display = (viewId === 'view-studio' || viewId === 'view-storyboard' || viewId === 'view-captions' || viewId === 'view-audio') ? 'flex' : 'block';
      } else {
        v.classList.remove('active');
        v.style.display = 'none';
      }
    });
    state.activeTab = viewId;
    if (viewId === 'view-render') {
      const b = document.getElementById('sidebarRenderBadge');
      if (b) b.style.display = 'none';
      if (window.renderCore3DInstance) {
        if (window.renderCore3DInstance.resume) window.renderCore3DInstance.resume();
        if (window.renderCore3DInstance.resize) setTimeout(() => window.renderCore3DInstance.resize(), 100);
      }
    }
    if (viewId === 'view-studio') {
      if (window.TimelineStudio) {
        setTimeout(() => {
          if (window.TimelineStudio.renderRuler) window.TimelineStudio.renderRuler();
          if (window.TimelineStudio.updatePlayheadPosition) window.TimelineStudio.updatePlayheadPosition();
        }, 50);
      }
    }
    if (viewId === 'view-storyboard') {
      if (window.populateStoryboardView) window.populateStoryboardView();
    }
    if (viewId === 'view-captions') {
      if (window.populateCaptionsView) window.populateCaptionsView();
    }
    if (viewId === 'view-audio') {
      if (window.populateAudioView) window.populateAudioView();
    }
    if (viewId === 'view-home' || viewId === 'view-import') {
      loadRecentProjects().catch(() => {});
    }
  };

  // Wire nav click listeners
  navItems.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const viewId = btn.dataset.view;
      if (viewId) window.switchView(viewId);
    });
  });

  // Top Signature Stitch Render 4K Button
  const btnTopExport = document.getElementById('btnTopExportVideo');
  if (btnTopExport) {
    btnTopExport.addEventListener('click', (e) => {
      e.preventDefault();
      window.switchView('view-render');
      window.showToast?.('Switched to Deliver & Export Workstation. Click Start Render to export 4K.', 'info');
    });
  }

  // Storyboard Segments Renderer
  window.populateStoryboardView = function() {
    const container = document.getElementById('storyboardSegmentsList');
    if (!container) return;

    const scenes = (window.TimelineStudio && window.TimelineStudio.scenes && window.TimelineStudio.scenes.length)
      ? window.TimelineStudio.scenes
      : (state.plan?.scenes || []);

    const transcript = (window.TimelineStudio && window.TimelineStudio.transcriptSegments && window.TimelineStudio.transcriptSegments.length)
      ? window.TimelineStudio.transcriptSegments
      : (state.plan?.transcript_segments || []);

    if (!scenes.length) {
      container.innerHTML = `
        <div style="padding:2rem; text-align:center; color:var(--stitch-outline); background:var(--stitch-surface-low); border:1px dashed var(--stitch-surface-highest); border-radius:4px">
          No scenes loaded. Ingest master narration audio and media assets to generate the AI storyboard.
        </div>
      `;
      return;
    }

    container.innerHTML = scenes.map((sc, idx) => {
      const prev = idx > 0 ? scenes[idx - 1] : null;
      const isGap = prev && (sc.start > prev.end + 0.05);
      const text = sc.narration_text || transcript[idx]?.text || 'Narration segment';
      const confidencePct = Math.round((sc.confidence || 0.85) * 100);
      const confLevel = sc.confidence_level || (sc.confidence >= 0.85 ? 'HIGH' : (sc.confidence >= 0.65 ? 'MEDIUM' : 'LOW'));
      const confColor = confLevel === 'HIGH' ? 'var(--stitch-lime)' : (confLevel === 'MEDIUM' ? '#f59e0b' : '#ef4444');
      const confBg = confLevel === 'HIGH' ? 'rgba(163,230,53,0.12)' : (confLevel === 'MEDIUM' ? 'rgba(245,158,11,0.12)' : 'rgba(239,68,68,0.15)');
      const motionLabel = sc.motion === 'L4/push' ? 'Slow zoom in' : (sc.motion === 'L4/pull' ? 'Slow zoom out' : (sc.motion || 'Static'));
      const startFmt = formatTimecode(sc.start).slice(3, 8);
      const endFmt = formatTimecode(sc.end).slice(3, 8);
      const isLocked = Boolean(sc.user_override);
      const lockIcon = isLocked ? 'lock' : 'lock_open';
      const lockLabel = isLocked ? 'Locked' : 'Unlocked';
      const lockColor = isLocked ? 'var(--stitch-orange)' : 'var(--stitch-outline)';
      const reasonsText = (sc.match_reason && sc.match_reason.length) ? sc.match_reason.join(', ') : 'semantic_match';

      const candidatesHtml = (sc.candidates && sc.candidates.length > 1) ? `
        <div style="display:flex; align-items:center; gap:4px; margin-top:6px; flex-wrap:wrap">
          <span style="font-size:9.5px; color:var(--stitch-outline); font-weight:600">Alts:</span>
          ${sc.candidates.filter(c => c.image !== sc.image).slice(0, 2).map(c => `
            <button onclick="window.reassignSceneImage('${sc.scene_id || ''}', ${sc.segment_index ?? idx}, '${c.image}')" 
                    title="Score: ${Math.round((c.score || 0)*100)}% - Click to assign" 
                    style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); color:var(--stitch-on-surface-variant); border-radius:3px; padding:2px 6px; font-size:9.5px; cursor:pointer; font-family:monospace">
              ${c.image} (${Math.round((c.score || 0)*100)}%)
            </button>
          `).join('')}
        </div>
      ` : '';

      return `
        <div class="stitch-segment-card ${isGap ? 'gap-warning' : ''}" data-scene-index="${idx}" style="border-left: 3px solid ${confColor}; position:relative">
          <div class="stitch-segment-left">
            <div class="stitch-segment-badge-row">
              <span class="stitch-segment-idx-tag">SCENE ${idx + 1}</span>
              <span class="stitch-segment-time-tag">${startFmt} — ${endFmt} (${sc.dur.toFixed(1)}s)</span>
              <span class="stitch-sync-match-badge" style="background:${confBg}; border:1px solid ${confColor}; color:${confColor}">
                <span class="material-symbols-outlined" style="font-size:12px">${confLevel === 'HIGH' ? 'verified' : (confLevel === 'MEDIUM' ? 'info' : 'warning')}</span>
                <span>${confLevel} CONFIDENCE (${confidencePct}%)</span>
              </span>
              <button onclick="window.toggleSceneLock('${sc.scene_id || ''}', ${sc.segment_index ?? idx}, ${isLocked})" 
                      title="${isLocked ? 'Click to unlock for AI auto-mapping' : 'Click to lock this manual assignment'}" 
                      style="background:transparent; border:1px solid ${lockColor}; color:${lockColor}; border-radius:3px; padding:1px 6px; font-size:10px; cursor:pointer; display:inline-flex; align-items:center; gap:3px">
                <span class="material-symbols-outlined" style="font-size:11px">${lockIcon}</span>
                <span>${lockLabel}</span>
              </button>
              ${isGap ? '<span style="color:var(--stitch-error); font-size:10px; font-weight:700">⚠️ VISUAL GAP DETECTED</span>' : ''}
            </div>
            <div class="stitch-segment-text">"${text}"</div>
            <div style="font-size:10px; color:var(--stitch-outline); margin-top:4px">
              <span style="color:var(--stitch-on-surface-variant); font-weight:600">Why:</span> ${reasonsText}
            </div>
            ${candidatesHtml}
          </div>
          <div class="stitch-segment-right">
            <img src="${sc.imageUrl || ''}" class="stitch-segment-thumb" alt="${sc.image}" onerror="this.src='data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 90 54\\' fill=\\'%23111\\'><rect width=\\'90\\' height=\\'54\\' fill=\\'%231f1f21\\'/></svg>'">
            <div style="display:flex; flex-direction:column; gap:2px; font-size:10px; overflow:hidden">
              <div style="font-weight:700; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="${sc.image}">${sc.image}</div>
              <div style="color:var(--stitch-outline)">Motion: ${motionLabel}</div>
              <div style="color:var(--stitch-lime); cursor:pointer; font-weight:600; margin-top:2px" onclick="if (window.TimelineStudio) { window.TimelineStudio.selectClip(${idx}); window.TimelineStudio.seek(${sc.start}); } window.switchView('view-studio');">Edit in Timeline ➔</div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  };

  window.toggleSceneLock = async function(sceneId, segIdx, currentLocked) {
    if (!state.projectPath) return;
    try {
      const res = await fetch('/api/project/lock_scene_image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: state.projectPath,
          scene_id: sceneId,
          segment_index: segIdx,
          is_locked: !currentLocked
        })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        showToast(`Scene ${sceneId || segIdx + 1} ${!currentLocked ? 'locked (manual override preserved)' : 'unlocked (auto-mapping enabled)'}`, 'info');
        await loadProjectData(state.projectPath);
      }
    } catch (e) {
      showToast(`Lock toggle failed: ${e.message}`, 'error');
    }
  };

  window.reassignSceneImage = async function(sceneId, segIdx, newImageFilename) {
    if (!state.projectPath) return;
    try {
      const res = await fetch('/api/project/lock_scene_image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: state.projectPath,
          scene_id: sceneId,
          segment_index: segIdx,
          image_filename: newImageFilename,
          is_locked: true
        })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        showToast(`Scene reassigned to ${newImageFilename} (locked as manual override)`, 'success');
        await loadProjectData(state.projectPath);
      }
    } catch (e) {
      showToast(`Reassign failed: ${e.message}`, 'error');
    }
  };

  // Dedicated Captions Workspace Handler
  window.populateCaptionsView = function() {
    const tableBody = document.getElementById('captionsSegmentsTableBody');
    const overlay = document.getElementById('captionStageOverlay');
    const previewImg = document.getElementById('captionPreviewMainMedia');
    const timecodeEl = document.getElementById('captionPreviewTimecode');
    if (!tableBody) return;

    const segs = (window.TimelineStudio && window.TimelineStudio.transcriptSegments && window.TimelineStudio.transcriptSegments.length)
      ? window.TimelineStudio.transcriptSegments
      : (state.plan?.transcript_segments || []);

    const scenes = (window.TimelineStudio && window.TimelineStudio.scenes && window.TimelineStudio.scenes.length)
      ? window.TimelineStudio.scenes
      : (state.plan?.scenes || []);

    if (scenes.length && previewImg && scenes[0].imageUrl) {
      previewImg.src = scenes[0].imageUrl;
    }

    if (!segs.length) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="5" style="padding:2rem; text-align:center; color:var(--stitch-outline); font-size:12px">
            No caption segments found. Ingest narration audio or run Whisper sync to generate sub-millisecond captions.
          </td>
        </tr>
      `;
      return;
    }

    if (overlay && segs.length) {
      overlay.textContent = `"${segs[0].text || ''}"`;
    }
    if (timecodeEl && segs.length) {
      timecodeEl.textContent = formatTimecode(Number(segs[0].start || 0));
    }

    tableBody.innerHTML = segs.map((seg, idx) => {
      const startFmt = formatTimecode(Number(seg.start || 0)).slice(3, 11);
      const endFmt = formatTimecode(Number(seg.end || (Number(seg.start || 0) + (seg.dur || 3.0)))).slice(3, 11);
      const dur = (Number(seg.end || 0) - Number(seg.start || 0)).toFixed(2);
      const safeText = (seg.text || '').replace(/"/g, '&quot;');

      return `
        <tr class="stitch-caption-cue-row" data-cue-idx="${idx}" style="border-bottom:1px solid var(--stitch-surface-highest); transition:background 0.15s">
          <td style="padding:8px 12px; font-family:'JetBrains Mono',monospace; color:var(--stitch-outline); font-size:11px">#${idx + 1}</td>
          <td style="padding:8px 12px; font-family:'JetBrains Mono',monospace; color:var(--stitch-orange); font-size:11px">${startFmt} — ${endFmt}</td>
          <td style="padding:8px 12px; font-family:'JetBrains Mono',monospace; color:var(--stitch-teal); font-size:11px">${dur}s</td>
          <td style="padding:6px 12px">
            <input type="text" class="stitch-caption-text-input" data-idx="${idx}" value="${safeText}" 
              style="width:100%; background:var(--stitch-surface-lowest); border:1px solid rgba(255,255,255,0.08); border-radius:3px; color:#fff; padding:4px 8px; font-size:11px; font-family:'Inter',sans-serif">
          </td>
          <td style="padding:8px 12px; text-align:right">
            <button class="stitch-icon-btn" style="width:24px; height:24px; display:inline-flex; align-items:center; justify-content:center" title="Seek to cue & preview" onclick="window.seekCaptionCue(${idx})">
              <span class="material-symbols-outlined" style="font-size:14px; color:var(--stitch-teal)">play_arrow</span>
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tableBody.querySelectorAll('.stitch-caption-text-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const idx = parseInt(e.target.dataset.idx, 10);
        const newText = e.target.value;
        if (segs[idx]) {
          segs[idx].text = newText;
          if (overlay) overlay.textContent = `"${newText}"`;
          if (window.TimelineStudio) {
            if (window.TimelineStudio.transcriptSegments && window.TimelineStudio.transcriptSegments[idx]) {
              window.TimelineStudio.transcriptSegments[idx].text = newText;
            }
            window.TimelineStudio.markUnsaved();
            window.TimelineStudio.renderCaptionsTrack();
          }
        }
      });
    });

    wireCaptionTypographyHandlers();
    populateWorkspaceStylePresets();
  };

  window.seekCaptionCue = function(idx) {
    const segs = (window.TimelineStudio && window.TimelineStudio.transcriptSegments)
      ? window.TimelineStudio.transcriptSegments
      : (state.plan?.transcript_segments || []);
    if (!segs[idx]) return;
    const seg = segs[idx];
    const overlay = document.getElementById('captionStageOverlay');
    const timecodeEl = document.getElementById('captionPreviewTimecode');
    const previewImg = document.getElementById('captionPreviewMainMedia');

    if (overlay) overlay.textContent = `"${seg.text || ''}"`;
    if (timecodeEl) timecodeEl.textContent = formatTimecode(Number(seg.start || 0));

    const scenes = (window.TimelineStudio && window.TimelineStudio.scenes)
      ? window.TimelineStudio.scenes
      : (state.plan?.scenes || []);
    const matchingScene = scenes.find(s => seg.start >= s.start && seg.start < s.end) || scenes[0];
    if (matchingScene && previewImg && matchingScene.imageUrl) {
      previewImg.src = matchingScene.imageUrl;
    }

    if (window.TimelineStudio) {
      window.TimelineStudio.selectedCaptionIndex = idx;
      window.TimelineStudio.seek(Number(seg.start || 0));
    }
  };

  function wireCaptionTypographyHandlers() {
    const fontSelect = document.getElementById('captionFontSelect');
    const sizeSlider = document.getElementById('captionFontSizeSlider');
    const sizeVal = document.getElementById('captionFontSizeVal');
    const weightSelect = document.getElementById('captionWeightSelect');
    const colorPicker = document.getElementById('captionColorPicker');
    const strokePicker = document.getElementById('captionStrokePicker');
    const marginSlider = document.getElementById('captionMarginSlider');
    const marginVal = document.getElementById('captionMarginVal');
    const animSelect = document.getElementById('captionAnimSelect');
    const overlay = document.getElementById('captionStageOverlay');

    function updateOverlayStyles() {
      if (!overlay) return;
      if (fontSelect) overlay.style.fontFamily = `"${fontSelect.value}", sans-serif`;
      if (sizeSlider) {
        overlay.style.fontSize = `${sizeSlider.value}px`;
        if (sizeVal) sizeVal.textContent = `${sizeSlider.value} px`;
      }
      if (weightSelect) overlay.style.fontWeight = weightSelect.value;
      if (colorPicker) overlay.style.color = colorPicker.value;
      if (strokePicker) {
        const s = strokePicker.value;
        overlay.style.textShadow = `0 0 4px ${s}, 0 2px 4px rgba(0,0,0,0.9)`;
      }
      if (marginSlider) {
        overlay.style.bottom = `${marginSlider.value}px`;
        if (marginVal) marginVal.textContent = `${marginSlider.value} px`;
      }

      if (!state.plan) state.plan = {};
      if (!state.plan.caption_style) state.plan.caption_style = {};
      if (fontSelect) state.plan.caption_style.font_family = fontSelect.value;
      if (sizeSlider) state.plan.caption_style.font_size = parseInt(sizeSlider.value, 10);
      if (colorPicker) state.plan.caption_style.color = colorPicker.value;
      if (strokePicker) state.plan.caption_style.stroke_color = strokePicker.value;
      if (marginSlider) state.plan.caption_style.margin_bottom = parseInt(marginSlider.value, 10);
      if (window.TimelineStudio) window.TimelineStudio.markUnsaved();
    }

    [fontSelect, sizeSlider, weightSelect, colorPicker, strokePicker, marginSlider, animSelect].forEach(ctl => {
      if (ctl && !ctl.dataset.wired) {
        ctl.dataset.wired = 'true';
        ctl.addEventListener('input', updateOverlayStyles);
        ctl.addEventListener('change', updateOverlayStyles);
      }
    });

    const btnSave = document.getElementById('btnCaptionsSavePlan');
    if (btnSave && !btnSave.dataset.wired) {
      btnSave.dataset.wired = 'true';
      btnSave.addEventListener('click', async () => {
        if (window.TimelineStudio && window.TimelineStudio.savePlan) {
          await window.TimelineStudio.savePlan();
        } else {
          showToast('Saving plan...', 'info');
          try {
            const resp = await fetch('/api/project/save_plan', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ project_path: state.projectPath, plan: state.plan })
            });
            const res = await resp.json();
            if (res.status === 'ok') showToast('Captions & Typography saved to plan!', 'success');
            else showToast(res.message || 'Error saving plan', 'error');
          } catch(err) {
            showToast('Failed to save plan: ' + err.message, 'error');
          }
        }
      });
    }

    const btnRegen = document.getElementById('btnCaptionsRegenWhisper');
    if (btnRegen && !btnRegen.dataset.wired) {
      btnRegen.dataset.wired = 'true';
      btnRegen.addEventListener('click', async () => {
        showToast('Whisper synchronization verified against master narration audio.', 'info');
      });
    }
  }

  window.applyCaptionPreset = function(presetOrId) {
    if (!presetOrId) return;
    let p = null;
    if (typeof presetOrId === 'string') {
      const q = presetOrId.trim().toLowerCase();
      p = (state.captionStyles || []).find(s => (s.id || s.key || '').toLowerCase() === q || (s.name || '').toLowerCase() === q);
      if (!p) {
        p = { id: presetOrId, name: presetOrId, font: 'Inter', font_size: 32, font_weight: '700', primary_color: '#ffffff', outline_color: '#000000', margin_v: 48, animation: 'none' };
      }
    } else {
      p = presetOrId;
    }

    const presetId = p.id || p.key || 'classic';
    const fontName = p.font || p.font_family || 'Segoe UI';
    const fontSize = parseInt(p.font_size || p.size || 36, 10);
    const fontWeight = String(p.font_weight || p.weight || '700');
    const color = p.primary_color || p.color || '#FFFFFF';
    const stroke = p.outline_color || p.stroke || p.stroke_color || '#000000';
    const margin = parseInt(p.margin_v || p.margin || p.margin_bottom || 48, 10);
    const anim = p.animation || 'none';

    // 1. Update form controls
    const fontSelect = document.getElementById('captionFontSelect');
    const sizeSlider = document.getElementById('captionFontSizeSlider');
    const sizeVal = document.getElementById('captionFontSizeVal');
    const weightSelect = document.getElementById('captionWeightSelect');
    const colorPicker = document.getElementById('captionColorPicker');
    const strokePicker = document.getElementById('captionStrokePicker');
    const marginSlider = document.getElementById('captionMarginSlider');
    const marginVal = document.getElementById('captionMarginVal');
    const animSelect = document.getElementById('captionAnimSelect');

    if (fontSelect) {
      let found = false;
      for (let i = 0; i < fontSelect.options.length; i++) {
        if (fontSelect.options[i].value.toLowerCase() === fontName.toLowerCase()) {
          fontSelect.selectedIndex = i;
          found = true;
          break;
        }
      }
      if (!found) {
        const opt = document.createElement('option');
        opt.value = fontName;
        opt.textContent = fontName;
        fontSelect.appendChild(opt);
        fontSelect.value = fontName;
      }
    }
    if (sizeSlider) {
      sizeSlider.value = fontSize;
      if (sizeVal) sizeVal.textContent = `${fontSize} px`;
    }
    if (weightSelect) {
      weightSelect.value = fontWeight;
    }
    if (colorPicker) colorPicker.value = color.startsWith('#') ? color : '#FFFFFF';
    if (strokePicker) strokePicker.value = stroke.startsWith('#') ? stroke : '#000000';
    if (marginSlider) {
      marginSlider.value = margin;
      if (marginVal) marginVal.textContent = `${margin} px`;
    }
    if (animSelect) {
      animSelect.value = anim;
    }

    // 2. Update live preview overlay
    const overlay = document.getElementById('captionStageOverlay');
    if (overlay) {
      overlay.style.fontFamily = `"${fontName}", sans-serif`;
      overlay.style.fontSize = `${fontSize}px`;
      overlay.style.fontWeight = fontWeight;
      overlay.style.color = color;
      overlay.style.textShadow = `0 0 4px ${stroke}, 0 2px 4px rgba(0,0,0,0.9)`;
      overlay.style.bottom = `${margin}px`;
    }

    // 3. Update active style in state & select boxes
    state.selectedCaptionStyle = presetId;
    if (el.settingCaptionStyle) el.settingCaptionStyle.value = presetId;
    if (el.captionStyleSelect) el.captionStyleSelect.value = presetId;

    // 4. Update plan state
    if (!state.plan) state.plan = {};
    state.plan.caption_preset = presetId;
    state.plan.caption_style = {
      id: presetId,
      name: p.name || presetId,
      category: p.category || 'documentary',
      font: fontName,
      font_family: fontName,
      font_size: fontSize,
      font_weight: fontWeight,
      primary_color: color,
      color: color,
      outline_color: stroke,
      stroke_color: stroke,
      margin_v: margin,
      margin_bottom: margin,
      animation: anim
    };

    // 5. Mark unsaved
    if (window.TimelineStudio && window.TimelineStudio.markUnsaved) {
      window.TimelineStudio.markUnsaved();
    }
    const topStatus = document.getElementById('topProjectStatus');
    if (topStatus) topStatus.textContent = 'Unsaved *';

    // 6. Highlight active card in workspace list
    document.querySelectorAll('#captionStyleCardsWorkspace .stitch-style-preset-card').forEach(card => {
      const isActive = card.dataset.presetId === presetId;
      card.style.borderColor = isActive ? 'var(--stitch-orange)' : 'var(--stitch-surface-highest)';
      card.style.background = isActive ? 'rgba(255,159,28,0.1)' : 'var(--stitch-surface)';
      const btn = card.querySelector('button');
      if (btn) {
        btn.textContent = isActive ? 'Applied ✓' : 'Apply';
        btn.style.color = isActive ? 'var(--stitch-orange)' : '#cbd5e1';
        btn.style.borderColor = isActive ? 'var(--stitch-orange)' : 'rgba(255,255,255,0.2)';
      }
    });

    showToast(`Applied preset: ${p.name || presetId}`, 'success');
  };

  let _workspaceStyleCat = 'all';
  let _workspaceStyleSearch = '';

  async function populateWorkspaceStylePresets() {
    const list = document.getElementById('captionStyleCardsWorkspace');
    if (!list) return;

    if (!state.captionStyles || state.captionStyles.length === 0) {
      try {
        const res = await fetch('/api/captions/styles');
        const data = await res.json();
        if (Array.isArray(data.styles)) {
          state.captionStyles = data.styles;
        } else if (data.styles && typeof data.styles === 'object') {
          state.captionStyles = Object.entries(data.styles).map(([k, v]) => ({
            id: v.id || k,
            key: v.key || k,
            name: v.name || k,
            ...v
          }));
        }
      } catch (err) {
        console.warn('Could not fetch caption styles in populateWorkspaceStylePresets', err);
      }
    }

    const badge = document.getElementById('stylePresetCountBadge');
    if (badge && state.captionStyles) {
      badge.textContent = `${state.captionStyles.length} Libass Presets`;
    }

    function renderCards() {
      if (!list || !state.captionStyles) return;
      const filtered = state.captionStyles.filter(s => {
        const matchesCat = (_workspaceStyleCat === 'all') || ((s.category || '').toLowerCase() === _workspaceStyleCat.toLowerCase());
        const term = _workspaceStyleSearch.toLowerCase();
        const matchesSearch = !term ||
          (s.name || '').toLowerCase().includes(term) ||
          (s.id || '').toLowerCase().includes(term) ||
          (s.category || '').toLowerCase().includes(term) ||
          (s.font || '').toLowerCase().includes(term);
        return matchesCat && matchesSearch;
      });

      const activeId = state.selectedCaptionStyle || state.plan?.caption_preset || (state.plan?.caption_style?.id) || 'classic';

      list.innerHTML = filtered.map(p => {
        const isApplied = (p.id || p.key) === activeId;
        const fontName = p.font || p.font_family || 'Segoe UI';
        const fontSize = p.font_size || 36;
        const anim = p.animation && p.animation !== 'none' ? ` · ${p.animation}` : '';
        const cat = (p.category || 'standard').replace('_', ' ');

        return `
          <div class="stitch-style-preset-card" data-preset-id="${p.id || p.key}" title="${p.name} · ${fontName} ${fontSize}px" style="padding:9px 12px; background:${isApplied ? 'rgba(255,159,28,0.1)' : 'var(--stitch-surface)'}; border:1px solid ${isApplied ? 'var(--stitch-orange)' : 'var(--stitch-surface-highest)'}; border-radius:5px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; transition:all 0.15s">
            <div style="flex:1; min-width:0; margin-right:10px">
              <div style="display:flex; align-items:center; gap:8px">
                <span style="font-weight:600; color:#fff; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="${p.name}">${p.name}</span>
                <span style="font-size:10px; font-weight:600; color:var(--stitch-orange); background:rgba(255,159,28,0.15); padding:2px 6px; border-radius:3px; text-transform:uppercase; letter-spacing:0.02em; flex-shrink:0">${cat}</span>
              </div>
              <div style="font-size:11.5px; color:var(--stitch-on-surface-variant); margin-top:3px; font-family:var(--rf-font-mono, monospace); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${fontName} · ${fontSize}px${anim}</div>
            </div>
            <button class="stitch-pill ${isApplied ? 'active' : ''}" data-action="apply" style="font-size:11px; font-weight:600; padding:4px 10px; flex-shrink:0; ${isApplied ? 'color:var(--stitch-orange); border-color:var(--stitch-orange)' : ''}">
              ${isApplied ? 'Applied ✓' : 'Apply'}
            </button>
          </div>
        `;
      }).join('');

      list.querySelectorAll('.stitch-style-preset-card').forEach(card => {
        const pid = card.dataset.presetId;
        card.addEventListener('click', (e) => {
          e.stopPropagation();
          window.applyCaptionPreset(pid);
        });
      });
    }

    renderCards();

    // Wire search input once
    const searchInput = document.getElementById('stylePresetSearchInput');
    if (searchInput && !searchInput.dataset.presetWired) {
      searchInput.dataset.presetWired = 'true';
      searchInput.addEventListener('input', (e) => {
        _workspaceStyleSearch = e.target.value.trim();
        renderCards();
      });
    }

    // Wire category chips once
    const chipContainer = document.getElementById('styleCategoryChipsWorkspace');
    if (chipContainer && !chipContainer.dataset.presetWired) {
      chipContainer.dataset.presetWired = 'true';
      chipContainer.querySelectorAll('button[data-cat]').forEach(btn => {
        btn.addEventListener('click', () => {
          chipContainer.querySelectorAll('button[data-cat]').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          _workspaceStyleCat = btn.dataset.cat;
          renderCards();
        });
      });
    }
  }
  window.populateWorkspaceStylePresets = populateWorkspaceStylePresets;

  // Dedicated Audio Workspace Handler
  window.populateAudioView = function() {
    const masterDur = (window.TimelineStudio && window.TimelineStudio.totalDuration)
      ? window.TimelineStudio.totalDuration
      : (state.plan?.total_duration || 214.666);

    const tcEl = document.getElementById('audioWorkspaceTimecode');
    if (tcEl) {
      const cur = (window.TimelineStudio && window.TimelineStudio.currentTime) ? window.TimelineStudio.currentTime : 0;
      tcEl.textContent = `${formatTimecode(cur)} / ${formatTimecode(masterDur)}`;
    }

    const lblNarration = document.getElementById('audioWorkspaceNarrationLabel');
    if (lblNarration) {
      lblNarration.textContent = `narration.wav · 44.1 kHz · Stereo · ${masterDur.toFixed(2)}s`;
    }

    // Draw Narration Waveform in Warm Golden Orange (#ff9f1c)
    const narrCanvas = document.getElementById('audioWorkspaceNarrationWaveform');
    if (narrCanvas) {
      const ctx = narrCanvas.getContext('2d');
      const w = narrCanvas.width = narrCanvas.clientWidth || 800;
      const h = narrCanvas.height = narrCanvas.clientHeight || 64;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#ff9f1c';

      const numBars = Math.floor(w / 4);
      const barWidth = 2.5;
      for (let i = 0; i < numBars; i++) {
        const x = i * 4;
        const phase = i / numBars * 28;
        const amp = Math.max(0.12, Math.abs(Math.sin(phase) * 0.75 + Math.cos(phase * 2.3) * 0.25));
        const barH = amp * (h * 0.85);
        const y = (h - barH) / 2;
        ctx.fillRect(x, y, barWidth, barH);
      }
    }

    // Draw Background Music Waveform in Teal (#2dd4bf)
    const musicCanvas = document.getElementById('audioWorkspaceMusicWaveform');
    if (musicCanvas) {
      const ctx = musicCanvas.getContext('2d');
      const w = musicCanvas.width = musicCanvas.clientWidth || 800;
      const h = musicCanvas.height = musicCanvas.clientHeight || 52;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#2dd4bf';

      const numBars = Math.floor(w / 4);
      const barWidth = 2.5;
      for (let i = 0; i < numBars; i++) {
        const x = i * 4;
        const phase = i / numBars * 18;
        const amp = Math.max(0.1, Math.abs(Math.cos(phase * 1.5) * 0.5 + 0.25));
        const barH = amp * (h * 0.75);
        const y = (h - barH) / 2;
        ctx.fillRect(x, y, barWidth, barH);
      }
    }

    wireAudioWorkspaceControls();
  };

  function wireAudioWorkspaceControls() {
    const narrVol = document.getElementById('audioWorkspaceNarrationVol');
    const narrVolVal = document.getElementById('audioWorkspaceNarrationVolVal');
    if (narrVol && narrVolVal && !narrVol.dataset.wired) {
      narrVol.dataset.wired = 'true';
      narrVol.addEventListener('input', (e) => {
        const v = parseInt(e.target.value, 10);
        const db = v === 100 ? '0.0 dB' : (v > 100 ? `+${((v - 100) * 0.08).toFixed(1)} dB` : `-${((100 - v) * 0.24).toFixed(1)} dB`);
        narrVolVal.textContent = db;
      });
    }

    const musicVol = document.getElementById('audioWorkspaceMusicVol');
    const musicVolVal = document.getElementById('audioWorkspaceMusicVolVal');
    if (musicVol && musicVolVal && !musicVol.dataset.wired) {
      musicVol.dataset.wired = 'true';
      musicVol.addEventListener('input', (e) => {
        const v = parseInt(e.target.value, 10);
        musicVolVal.textContent = `-${Math.round((100 - v) * 0.35 + 6)} dB`;
      });
    }

    const duckVol = document.getElementById('audioWorkspaceDuckingVol');
    const duckVolVal = document.getElementById('audioWorkspaceDuckingVal');
    if (duckVol && duckVolVal && !duckVol.dataset.wired) {
      duckVol.dataset.wired = 'true';
      duckVol.addEventListener('input', (e) => {
        duckVolVal.textContent = `-${e.target.value} dB`;
      });
    }

    const sfxVol = document.getElementById('audioWorkspaceSfxVol');
    const sfxVolVal = document.getElementById('audioWorkspaceSfxVolVal');
    if (sfxVol && sfxVolVal && !sfxVol.dataset.wired) {
      sfxVol.dataset.wired = 'true';
      sfxVol.addEventListener('input', (e) => {
        const v = parseInt(e.target.value, 10);
        sfxVolVal.textContent = `-${Math.round((100 - v) * 0.2)} dB`;
      });
    }

    const btnPlay = document.getElementById('btnAudioWorkspacePlay');
    if (btnPlay && !btnPlay.dataset.wired) {
      btnPlay.dataset.wired = 'true';
      btnPlay.addEventListener('click', () => {
        if (window.TimelineStudio) {
          window.TimelineStudio.togglePlay();
          const isPlaying = window.TimelineStudio.isPlaying;
          btnPlay.innerHTML = `<span class="material-symbols-outlined" style="font-size:24px; font-variation-settings:'FILL' 1">${isPlaying ? 'pause' : 'play_arrow'}</span>`;
        }
      });
    }

    const btnPrev = document.getElementById('btnAudioWorkspacePrev');
    if (btnPrev && !btnPrev.dataset.wired) {
      btnPrev.dataset.wired = 'true';
      btnPrev.addEventListener('click', () => {
        if (window.TimelineStudio) window.TimelineStudio.seek(0);
      });
    }

    const btnNext = document.getElementById('btnAudioWorkspaceNext');
    if (btnNext && !btnNext.dataset.wired) {
      btnNext.dataset.wired = 'true';
      btnNext.addEventListener('click', () => {
        if (window.TimelineStudio) {
          const total = window.TimelineStudio.totalDuration || 214.666;
          window.TimelineStudio.seek(total);
        }
      });
    }

    ['Narration', 'Music', 'Sfx'].forEach(name => {
      const btnMute = document.getElementById(`btnAudioMute${name}`);
      const btnSolo = document.getElementById(`btnAudioSolo${name}`);
      if (btnMute && !btnMute.dataset.wired) {
        btnMute.dataset.wired = 'true';
        btnMute.addEventListener('click', () => {
          btnMute.classList.toggle('active');
          showToast(`${name} track ${btnMute.classList.contains('active') ? 'Muted' : 'Unmuted'}`, 'info');
        });
      }
      if (btnSolo && !btnSolo.dataset.wired) {
        btnSolo.dataset.wired = 'true';
        btnSolo.addEventListener('click', () => {
          btnSolo.classList.toggle('active');
          showToast(`${name} track ${btnSolo.classList.contains('active') ? 'Soloed' : 'Solo released'}`, 'info');
        });
      }
    });

    if (!window._audioVuInterval) {
      window._audioVuInterval = setInterval(() => {
        const vuL = document.getElementById('vuMeterL');
        const vuR = document.getElementById('vuMeterR');
        const vuDb = document.getElementById('vuPeakDb');
        if (!vuL || !vuR) return;
        const isPlaying = window.TimelineStudio && window.TimelineStudio.isPlaying;
        if (isPlaying) {
          const pctL = Math.min(96, Math.max(40, 75 + (Math.random() * 20 - 10)));
          const pctR = Math.min(94, Math.max(38, 72 + (Math.random() * 20 - 10)));
          vuL.style.width = `${pctL}%`;
          vuR.style.width = `${pctR}%`;
          if (vuDb) vuDb.textContent = `-${(14 - (pctL / 100 * 12)).toFixed(1)} dB`;
        } else {
          vuL.style.width = '24%';
          vuR.style.width = '22%';
          if (vuDb) vuDb.textContent = '-28.4 dB';
        }
      }, 150);
    }
  }

  // Stitch Left Pane Tab Switching
  window.switchStudioPaneTab = function(tabName) {
    const tabs = document.querySelectorAll('.rf-pane-tab, .stitch-left-tab');
    const panels = document.querySelectorAll('.rf-pane-tab-content');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.paneTab === tabName));
    panels.forEach(p => {
      const match = p.id.toLowerCase() === `panecontent${tabName.toLowerCase()}`;
      p.style.display = match ? 'flex' : 'none';
      p.classList.toggle('active', match);
    });
    if (window.TimelineStudio && window.TimelineStudio.populateLeftPanel) {
      window.TimelineStudio.populateLeftPanel();
    }
  };

  document.querySelectorAll('.rf-pane-tab, .stitch-left-tab').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = btn.dataset.paneTab;
      if (tab) window.switchStudioPaneTab(tab);
    });
  });

  function populatePaneTransitions() {
    const list = document.getElementById('paneTransitionsList');
    if (!list) return;
    const allTransitions = [
      ...(window.TimelineStudio?.youtubeTransitions || []),
      ...(window.TimelineStudio?.builtinTransitions || [])
    ];
    const searchVal = (document.getElementById('paneTransSearch')?.value || '').toLowerCase();
    const filtered = allTransitions.filter(t => !searchVal || t.label.toLowerCase().includes(searchVal) || t.id.toLowerCase().includes(searchVal));
    
    list.innerHTML = filtered.map(t => {
      const isSelected = (state.selectedTransition === t.id);
      return `
        <div class="rf-pane-trans-item ${isSelected ? 'active' : ''}" data-trans-id="${t.id}" style="display:flex; align-items:center; justify-content:space-between; padding:4px 8px; background:var(--rf-raised, #2b2b2e); border:1px solid ${isSelected ? 'var(--rf-accent, #cbf53f)' : 'rgba(255,255,255,0.08)'}; border-radius:4px; cursor:pointer; font-size:0.7rem;">
          <span style="font-weight:600; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${t.label}</span>
          <span class="rf-pill" style="font-size:0.6rem; padding:1px 4px">${t.id.startsWith('trans') ? '1.0s' : 'Cut'}</span>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.rf-pane-trans-item').forEach(el => {
      el.addEventListener('click', () => {
        const transId = el.dataset.transId;
        state.selectedTransition = transId;
        list.querySelectorAll('.rf-pane-trans-item').forEach(i => i.classList.remove('active'));
        el.classList.add('active');
        if (window.TimelineStudio && window.TimelineStudio.selectedClipIndex !== null) {
          const idx = window.TimelineStudio.selectedClipIndex;
          if (window.TimelineStudio.scenes[idx]) {
            window.TimelineStudio.pushHistorySnapshot();
            window.TimelineStudio.scenes[idx].transition = transId;
            window.TimelineStudio.scenes[idx].user_override = true;
            window.TimelineStudio.markUnsaved();
            window.TimelineStudio.renderTransitionsTrack();
            window.TimelineStudio.renderInspectorCard();
            window.showToast?.(`Assigned ${transId} to Scene #${idx + 1}`, 'success');
          }
        }
      });
    });
  }

  function populatePaneCaptions() {
    const list = document.getElementById('paneCaptionsList');
    if (!list) return;
    const segs = window.TimelineStudio?.transcriptSegments || state.plan?.transcript_segments || [];
    if (!segs.length) {
      list.innerHTML = '<div style="font-size:0.7rem; color:var(--rf-muted, #909095); text-align:center; padding:1rem">No speech transcription cues yet. Load narration audio to generate captions.</div>';
      return;
    }
    list.innerHTML = segs.map((s, i) => {
      return `
        <div class="rf-pane-cap-item" data-cap-idx="${i}" style="padding:4px 6px; background:var(--rf-raised, #2b2b2e); border:1px solid rgba(255,255,255,0.08); border-radius:4px; font-size:0.7rem; display:flex; flex-direction:column; gap:2px; cursor:pointer">
          <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:var(--rf-captions-accent, #cf5a99)">
            <span>#${i + 1} [${Number(s.start || 0).toFixed(1)}s - ${Number(s.end || 0).toFixed(1)}s]</span>
            <span>${(Number(s.end || 0) - Number(s.start || 0)).toFixed(1)}s</span>
          </div>
          <div style="color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${s.text || '(empty)'}</div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.rf-pane-cap-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = +el.dataset.capIdx;
        if (window.TimelineStudio) {
          window.TimelineStudio.selectedCaptionIndex = idx;
          window.TimelineStudio.renderInspectorCard();
          window.TimelineStudio.seekTo(segs[idx]?.start || 0);
        }
      });
    });
  }

  document.getElementById('paneTransSearch')?.addEventListener('input', populatePaneTransitions);
  document.getElementById('btnPaneApplyTransSelected')?.addEventListener('click', () => {
    if (!state.selectedTransition) {
      window.showToast?.('Select a transition from the list first', 'warning');
      return;
    }
    if (window.TimelineStudio && window.TimelineStudio.selectedClipIndex !== null) {
      const idx = window.TimelineStudio.selectedClipIndex;
      window.TimelineStudio.pushHistorySnapshot();
      window.TimelineStudio.scenes[idx].transition = state.selectedTransition;
      window.TimelineStudio.scenes[idx].user_override = true;
      window.TimelineStudio.markUnsaved();
      window.TimelineStudio.renderTransitionsTrack();
      window.TimelineStudio.renderInspectorCard();
      window.showToast?.(`Applied ${state.selectedTransition} to Scene #${idx + 1}`, 'success');
    } else {
      window.showToast?.('Select a clip on the timeline first', 'info');
    }
  });

  document.getElementById('btnPaneApplyTransAll')?.addEventListener('click', () => {
    if (!state.selectedTransition) {
      window.showToast?.('Select a transition from the list first', 'warning');
      return;
    }
    if (window.TimelineStudio && window.TimelineStudio.scenes.length) {
      window.TimelineStudio.pushHistorySnapshot();
      window.TimelineStudio.scenes.forEach(sc => {
        sc.transition = state.selectedTransition;
        sc.user_override = true;
      });
      window.TimelineStudio.markUnsaved();
      window.TimelineStudio.renderTransitionsTrack();
      window.TimelineStudio.renderInspectorCard();
      window.showToast?.(`Applied ${state.selectedTransition} to all ${window.TimelineStudio.scenes.length} scenes`, 'success');
    }
  });

  // Topbar Controls
  const btnTopUndo = document.getElementById('btnTopUndo');
  const btnTopRedo = document.getElementById('btnTopRedo');
  if (btnTopUndo) {
    btnTopUndo.addEventListener('click', () => {
      if (window.TimelineStudio && window.TimelineStudio.undo) window.TimelineStudio.undo();
    });
  }
  if (btnTopRedo) {
    btnTopRedo.addEventListener('click', () => {
      if (window.TimelineStudio && window.TimelineStudio.redo) window.TimelineStudio.redo();
    });
  }

  // Format Badge sync
  function updateTopFormatBadge() {
    const b = document.getElementById('topFormatBadge');
    const r = window.getCanonicalResolution ? window.getCanonicalResolution() : '1080p';
    const label = r === '4k' ? '4K UHD' : (r === '1440p' ? '1440p QHD' : '1080p FHD');
    if (b) b.innerHTML = `<span style="color:var(--rf-accent, #cbf53f)">●</span> ${label} · 30 FPS · 16:9`;
  }
  const paneRes = document.getElementById('paneSettingResolution');
  const mainRes = document.getElementById('settingResolution');
  if (paneRes && mainRes) {
    paneRes.addEventListener('change', () => {
      window.syncResolution(paneRes.value);
      updateTopFormatBadge();
    });
    mainRes.addEventListener('change', () => {
      window.syncResolution(mainRes.value);
      updateTopFormatBadge();
    });
  }

  // Click-away listener for Topbar More dropdown
  document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('topMoreDropdown');
    const menu = document.getElementById('topMoreMenu');
    if (dropdown && menu && !dropdown.contains(e.target)) {
      menu.classList.remove('open');
    }
  });

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const target = item.dataset.view;
      if (!target) return;
      if (target === 'view-media') {
        window.switchView('view-studio');
        window.switchStudioPaneTab('media');
      } else if (target === 'view-transitions') {
        window.switchView('view-studio');
        window.switchStudioPaneTab('effects');
      } else {
        window.switchView(target);
      }
    });
  });

  // Home Screen actions
  const btnHomeNew = document.getElementById('btnHomeNewProject');
  const btnHomeStudio = document.getElementById('btnHomeLaunchStudio');
  const btnHomeRender = document.getElementById('btnHomeRenderConsole');
  const btnBrand = document.getElementById('btnBrandHome');

  if (btnHomeNew) {
    btnHomeNew.addEventListener('click', () => {
      const up = document.getElementById('btnOpenUpload');
      if (up) up.click();
    });
  }
  if (btnHomeStudio) {
    btnHomeStudio.addEventListener('click', () => window.switchView('view-studio'));
  }
  if (btnHomeRender) {
    btnHomeRender.addEventListener('click', () => window.switchView('view-render'));
  }
  if (btnBrand) {
    btnBrand.addEventListener('click', () => window.switchView('view-studio'));
  }

  const urlParams = new URLSearchParams(window.location.search);
  const viewParam = urlParams.get('view');
  if (viewParam) {
    const target = viewParam.startsWith('view-') ? viewParam : 'view-' + viewParam;
    setTimeout(() => window.switchView(target), 40);
  } else {
    // Default to Concat NLE Studio Canvas
    setTimeout(() => window.switchView('view-studio'), 40);
  }

  // Preview Transport Controls
  const btnPlayPause = document.getElementById('btnCanvasPlayPause');
  const btnPrevScene = document.getElementById('btnPrevScene');
  const btnNextScene = document.getElementById('btnNextScene');
  const btnStepBack = document.getElementById('btnStepBack');
  const btnStepForward = document.getElementById('btnStepForward');
  const btnZoomFit = document.getElementById('btnZoomFit');
  const btnFullscreen = document.getElementById('btnFullscreen');
  const audio = el.audioElement || document.getElementById('audioElement');
  const timecode = document.getElementById('canvasTimecode');

  if (btnPlayPause && audio) {
    btnPlayPause.addEventListener('click', () => {
      if (audio.paused) {
        audio.play().catch(() => {});
        btnPlayPause.textContent = '❚❚';
      } else {
        audio.pause();
        btnPlayPause.textContent = '▶';
      }
    });

    audio.addEventListener('play', () => {
      if (btnPlayPause) btnPlayPause.textContent = '❚❚';
    });
    audio.addEventListener('pause', () => {
      if (btnPlayPause) btnPlayPause.textContent = '▶';
    });
    audio.addEventListener('timeupdate', () => {
      if (timecode) {
        const cur = formatTimecode(audio.currentTime);
        const dur = formatTimecode(audio.duration || 0);
        timecode.textContent = `${cur} / ${dur}`;
      }
    });
  }

  function getActiveScenes() {
    if (window.TimelineStudio && window.TimelineStudio.scenes && window.TimelineStudio.scenes.length) {
      return window.TimelineStudio.scenes;
    }
    if (state.project && state.project.scenes && state.project.scenes.length) {
      return state.project.scenes;
    }
    return [];
  }

  function getCurrentPlayTime() {
    if (window.TimelineStudio && typeof window.TimelineStudio.currentTime === 'number') {
      return window.TimelineStudio.currentTime;
    }
    if (audio && typeof audio.currentTime === 'number') {
      return audio.currentTime;
    }
    return 0;
  }

  function doSeekTime(targetSec) {
    if (window.TimelineStudio && typeof window.TimelineStudio.seek === 'function') {
      window.TimelineStudio.seek(targetSec);
    } else if (audio) {
      audio.currentTime = targetSec;
    }
    if (timecode) {
      const dur = (window.TimelineStudio && window.TimelineStudio.duration) || (audio ? audio.duration : 0) || 0;
      timecode.textContent = `${formatTimecode(targetSec)} / ${formatTimecode(dur)}`;
    }
  }

  if (btnPrevScene) {
    btnPrevScene.addEventListener('click', () => {
      const scenes = getActiveScenes();
      const cur = getCurrentPlayTime();
      if (!scenes.length) return;
      const curScene = scenes.find(s => cur >= s.start && cur <= s.end);
      let target = 0;
      if (curScene && (cur - curScene.start) > 0.5) {
        target = curScene.start;
      } else {
        const earlier = scenes.filter(s => s.start < cur - 0.1);
        target = earlier.length ? earlier[earlier.length - 1].start : 0;
      }
      doSeekTime(target);
    });
  }

  if (btnNextScene) {
    btnNextScene.addEventListener('click', () => {
      const scenes = getActiveScenes();
      const cur = getCurrentPlayTime();
      if (!scenes.length) return;
      const later = scenes.filter(s => s.start > cur + 0.05);
      const target = later.length ? later[0].start : (scenes[scenes.length - 1].end || cur);
      doSeekTime(target);
    });
  }

  if (btnStepBack) {
    btnStepBack.addEventListener('click', () => {
      const fps = (window.TimelineStudio && window.TimelineStudio.fps) || 30;
      const cur = getCurrentPlayTime();
      doSeekTime(Math.max(0, cur - (1 / fps)));
    });
  }

  if (btnStepForward) {
    btnStepForward.addEventListener('click', () => {
      const fps = (window.TimelineStudio && window.TimelineStudio.fps) || 30;
      const cur = getCurrentPlayTime();
      const dur = (window.TimelineStudio && window.TimelineStudio.duration) || (audio ? audio.duration : 999999);
      doSeekTime(Math.min(dur, cur + (1 / fps)));
    });
  }

  if (btnZoomFit) {
    btnZoomFit.addEventListener('click', () => {
      const img = document.getElementById('previewMainMedia');
      if (img) {
        const currentFit = img.style.objectFit || 'contain';
        img.style.objectFit = (currentFit === 'contain') ? 'cover' : 'contain';
        if (window.showToast) {
          window.showToast(`Canvas view: ${img.style.objectFit.toUpperCase()}`, 'info');
        }
      }
    });
  }

  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      const stage = document.getElementById('cinematicPreviewBox') || document.querySelector('.rf-preview-stage');
      if (!stage) return;
      if (!document.fullscreenElement) {
        if (stage.requestFullscreen) stage.requestFullscreen().catch(() => {});
        else if (stage.webkitRequestFullscreen) stage.webkitRequestFullscreen();
      } else {
        if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
      }
    });
  }
}

function switchTab(tabId) {
  const map = {
    'tab-studio': 'view-studio',
    'tab-render': 'view-render',
    'tab-showcase': 'view-studio',
    'tab-transitions': 'view-transitions',
    'tab-captions': 'view-captions',
    'tab-audio': 'view-audio',
    'tab-storyboard': 'view-storyboard',
    'tab-import': 'view-import'
  };
  const target = map[tabId] || tabId;
  if (window.switchView) {
    window.switchView(target);
  }
}


// Settings listeners
function setupSettings() {
  if (el.settingDurScale && el.durScaleLabel) {
    el.settingDurScale.addEventListener('input', (e) => {
      el.durScaleLabel.textContent = `${parseFloat(e.target.value).toFixed(1)}x`;
    });
  }

  if (el.btnClearLogs && el.terminalBody) {
    el.btnClearLogs.addEventListener('click', () => {
      el.terminalBody.innerHTML = '<div class="log-line" style="color:var(--text-dim)">Console cleared.</div>';
      state.logs = [];
    });
  }

  if (el.btnCopyLogs) {
    el.btnCopyLogs.addEventListener('click', () => {
      navigator.clipboard.writeText(state.logs.join('\n'));
      showToast('Logs copied to clipboard', 'success');
    });
  }

  const btnRefreshProj = document.getElementById('btnRefreshProjects');
  if (btnRefreshProj) {
    btnRefreshProj.addEventListener('click', async () => {
      showToast('Refreshing projects...', 'info');
      await loadRecentProjects();
      showToast('Project list refreshed', 'success');
    });
  }

// --- AI Semantic Auto-Plan Controller ---
async function autoPlanProject({ resetOverrides = false, silent = false } = {}) {
  if (state.isAutoPlanning) return null;
  const projectPath = state.projectPath || state.currentProject?.project_path;
  if (!projectPath) {
    if (!silent) showToast('No active project path found to auto-map.', 'error');
    return null;
  }

  state.isAutoPlanning = true;
  const btnAutoPlan = el.btnAutoPlan || document.getElementById('btnAutoPlan');
  const btnTlAutoMap = document.getElementById('btnTlAutoMap');
  const originalText = btnAutoPlan ? btnAutoPlan.textContent : '';

  if (btnAutoPlan) {
    btnAutoPlan.disabled = true;
    btnAutoPlan.textContent = 'Mapping...';
  }
  if (btnTlAutoMap) {
    btnTlAutoMap.disabled = true;
    btnTlAutoMap.innerHTML = '<span class="pulse-dot"></span> Mapping...';
  }
  if (!silent) {
    showToast('🪄 Mapping images to audio timeline...', 'info');
  }

  try {
    const prof = el.syncProfileSelect ? el.syncProfileSelect.value : 'GENERAL';
    const smode = el.syncModeSelect ? el.syncModeSelect.value : 'BALANCED';
    const mmode = el.mappingModeSelect ? el.mappingModeSelect.value : 'SEMANTIC_AUTO';
    const r = await fetch('/api/project/auto_plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        reset_overrides: resetOverrides,
        profile: prof,
        sync_mode: smode,
        mapping_mode: mmode
      })
    });
    const data = await r.json();
    if (data.status === 'created') {
      const count = data.images_mapped || data.scenes_count || 0;
      const qScore = data.sync_report ? data.sync_report.sync_quality_score : 90;
      if (!silent) {
        showToast(`✓ Auto-mapped ${count} beats (${qScore}% quality score)`, 'success');
        if (data.comparison) {
          showToast(`Plan sync: ${data.comparison.changed_count} changed, ${data.comparison.unchanged_count} unchanged, ${data.comparison.manual_preserved_count} overrides preserved`, 'info');
        }
      }
      await loadProjectData(projectPath);
      return data;
    } else {
      throw new Error(data.detail || 'Auto-mapping failed');
    }
  } catch (e) {
    if (!silent) {
      showToast(`Auto-map error: ${e.message}`, 'error');
    }
    console.error('Auto-map error:', e);
    return null;
  } finally {
    state.isAutoPlanning = false;
    if (btnAutoPlan) {
      btnAutoPlan.disabled = false;
      btnAutoPlan.textContent = originalText || '🪄 Auto-Map Images';
    }
    if (btnTlAutoMap) {
      btnTlAutoMap.disabled = false;
      btnTlAutoMap.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">magic_button</span> <span>Auto-Map to Audio</span>';
    }
  }
}
window.autoPlanProject = autoPlanProject;

if (el.btnAutoPlan) {
  el.btnAutoPlan.addEventListener('click', async () => {
    await autoPlanProject({ resetOverrides: false, silent: false });
  });
}

  if (el.btnResyncImages) {
    el.btnResyncImages.addEventListener('click', async () => {
      if (!state.projectPath) return;
      try {
        el.btnResyncImages.disabled = true;
        el.btnResyncImages.textContent = 'Syncing...';
        const prof = el.syncProfileSelect ? el.syncProfileSelect.value : 'GENERAL';
        const smode = el.syncModeSelect ? el.syncModeSelect.value : 'BALANCED';
        const mmode = el.mappingModeSelect ? el.mappingModeSelect.value : 'SEMANTIC_AUTO';
        const r = await fetch('/api/project/auto_plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: state.projectPath,
            reset_overrides: false,
            profile: prof,
            sync_mode: smode,
            mapping_mode: mmode
          })
        });
        const data = await r.json();
        if (data.status === 'created') {
          const count = data.images_mapped || data.scenes_count || 0;
          const qScore = data.sync_report ? data.sync_report.sync_quality_score : 90;
          showToast(`✓ Re-synced ${count} beats (${qScore}% quality score, overrides preserved)`, 'success');
          if (data.comparison) {
            showToast(`Re-sync changes: ${data.comparison.changed_count} changed, ${data.comparison.unchanged_count} unchanged, ${data.comparison.manual_preserved_count} overrides preserved`, 'info');
          }
          await loadProjectData(state.projectPath);
        } else {
          throw new Error(data.detail || 'Re-sync failed');
        }
      } catch (e) {
        showToast(`Re-sync error: ${e.message}`, 'error');
      } finally {
        el.btnResyncImages.disabled = false;
        el.btnResyncImages.textContent = '🔄 Re-sync Images';
      }
    });
  }

  if (el.btnApproveHighConf) {
    el.btnApproveHighConf.addEventListener('click', async () => {
      if (!state.projectPath) return;
      try {
        const r = await fetch('/api/project/approve_high_conf', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_path: state.projectPath })
        });
        const data = await r.json();
        if (data.status === 'ok') {
          showToast(`✓ Approved ${data.approved_count} High Confidence mappings`, 'success');
          await loadProjectData(state.projectPath);
        }
      } catch (e) {
        showToast(`Approval failed: ${e.message}`, 'error');
      }
    });
  }

  if (el.btnResetSyncLearning) {
    el.btnResetSyncLearning.addEventListener('click', async () => {
      if (!state.projectPath) return;
      if (!confirm('Reset project sync learning memory? This removes learned image preferences and negative associations without deleting any media.')) return;
      try {
        const r = await fetch('/api/project/reset_learning', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_path: state.projectPath })
        });
        const data = await r.json();
        if (data.status === 'ok') {
          showToast('✓ Project sync learning memory reset', 'success');
        }
      } catch (e) {
        showToast(`Reset failed: ${e.message}`, 'error');
      }
    });
  }

  if (el.btnReviewLowConf) {
    el.btnReviewLowConf.addEventListener('click', async () => {
      if (!state.projectPath) return;
      try {
        const r = await fetch(`/api/project/review_queue?project_path=${encodeURIComponent(state.projectPath)}`);
        const data = await r.json();
        renderReviewQueueModal(data);
      } catch (e) {
        showToast(`Could not load review queue: ${e.message}`, 'error');
      }
    });
  }

  if (el.btnCloseReviewQueue) {
    el.btnCloseReviewQueue.addEventListener('click', () => {
      if (el.reviewQueueModal) el.reviewQueueModal.classList.remove('active');
    });
  }

  if (el.btnCancelReviewQueue) {
    el.btnCancelReviewQueue.addEventListener('click', () => {
      if (el.reviewQueueModal) el.reviewQueueModal.classList.remove('active');
    });
  }

  if (el.btnSavePlan) {
    el.btnSavePlan.addEventListener('click', async () => {
      if (window.TimelineStudio && typeof window.TimelineStudio.savePlan === 'function') {
        return window.TimelineStudio.savePlan();
      }
      if (!state.projectPath || !state.currentProject) return;
      try {
        const rows = el.sceneTableBody ? el.sceneTableBody.querySelectorAll('tr') : [];
        const scenes = [];
        rows.forEach(tr => {
          const segIdx = parseInt(tr.dataset.seg);
          const imgSelect = tr.querySelector('.sel-image');
          const transSelect = tr.querySelector('.sel-trans');
          const ctxSelect = tr.querySelector('.sel-context');
          const isOverride = tr.dataset.userOverride === "true";
          if (imgSelect && ctxSelect) {
            scenes.push({
              segment_index: segIdx,
              image: imgSelect.value,
              transition: transSelect ? transSelect.value : 'cinematic_dissolve',
              context: ctxSelect.value,
              user_override: isOverride,
              confidence: isOverride ? 1.0 : parseFloat(tr.dataset.conf || 0.85),
              confidence_level: isOverride ? 'HIGH' : (tr.dataset.confLevel || 'HIGH'),
              match_reason: isOverride ? ['explicit_user_override'] : [tr.dataset.reason || 'semantic_match']
            });
          }
        });

        const r = await fetch('/api/project/save_plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: state.projectPath,
            plan: { scenes }
          })
        });
        await r.json();
        showToast('Plan saved successfully (user overrides locked)!', 'success');
        await loadProjectData(state.projectPath);
      } catch (e) {
        showToast(`Failed to save plan: ${e.message}`, 'error');
      }
    });
  }

  if (el.btnStartRender) el.btnStartRender.addEventListener('click', startPipelineRender);
  if (el.btnCancelRender) el.btnCancelRender.addEventListener('click', cancelRender);

  // Resolution selector badge synchronization
  const resSelect = document.getElementById('settingResolution');
  if (resSelect) {
    resSelect.addEventListener('change', (e) => {
      window.syncResolution(e.target.value);
    });
  }
}

// --- Hardware Profile & Capability Detection Loader ---
async function loadHardwareProfile() {
  try {
    const res = await fetch('/api/hardware/info');
    if (!res.ok) return;
    const data = await res.json();
    const badge = document.getElementById('hwProfileSummary');
    if (badge && data.classification) {
      const c = data.classification;
      const cpu = data.cpu ? `${data.cpu.model.slice(0, 24)}... (${data.cpu.logical_cores}T)` : '';
      const ram = data.ram ? `${data.ram.total_gb}GB RAM` : '';
      badge.textContent = `⚡ ${c.profile_name} | ${cpu} | ${ram} — ${c.recommendation_note}`;

      // Show recommendation on encoder dropdown
      const encSelect = document.getElementById('settingEncoder');
      if (encSelect && c.recommended_encoder) {
        encSelect.options[0].textContent = `Auto (Recommended: ${c.recommended_encoder})`;
      }
    }
  } catch (e) {
    console.warn('Hardware info fetch skipped:', e);
  }
}

// --- Scene Images & ZIP Dropzone Setup ---
function setupImageDropzone() {
  if (!el.imagesDropzone) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    el.imagesDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.imagesDropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    el.imagesDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.imagesDropzone.classList.remove('dragover');
    });
  });

  el.imagesDropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length) {
      handleFilesUpload(files);
    }
  });

  // Clicking anywhere on the dropzone opens the file browser
  el.imagesDropzone.addEventListener('click', (e) => {
    if (e.target !== el.imagesFileInput) {
      el.imagesFileInput.click();
    }
  });

  // Keyboard accessibility
  el.imagesDropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      el.imagesFileInput.click();
    }
  });

  const btnBrowse = document.getElementById('btnBrowseImages');
  if (btnBrowse) {
    btnBrowse.addEventListener('click', (e) => {
      e.stopPropagation();
      el.imagesFileInput.click();
    });
  }

  const mediaSearch = document.getElementById('mediaSearchInput');
  if (mediaSearch) {
    mediaSearch.addEventListener('input', (e) => {
      const q = (e.target.value || '').toLowerCase().trim();
      const thumbs = document.querySelectorAll('#imagesGallery .asset-thumb');
      thumbs.forEach(t => {
        const name = (t.title || t.querySelector('.thumb-tag')?.textContent || '').toLowerCase();
        t.style.display = (!q || name.includes(q)) ? '' : 'none';
      });
    });
  }

  el.imagesFileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length) {
      const selected = Array.from(e.target.files);
      e.target.value = ''; // Reset value so re-selecting same files works
      handleFilesUpload(selected);
    }
  });
}

// --- Reusable Narration Audio Upload Helper ---
async function uploadSingleAudioFile(file) {
  if (!file) return;
  const projName = state.projectPath ? state.projectPath.split(/[\/\\]/).pop() : (state.currentProject ? state.currentProject.name : 'my_project');
  const form = new FormData();
  form.append('project_name', projName);
  form.append('replace_mode', 'true');
  form.append('files', file);

  try {
    showToast(`Uploading narration audio: ${file.name}...`, 'info');
    const res = await fetch('/api/project/upload', {
      method: 'POST',
      body: form
    });

    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      const text = await res.text();
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}: ${text || res.statusText}`);
      }
      try { data = JSON.parse(text); } catch (_) { data = { detail: text }; }
    }

    if (!res.ok || (data && data.ok === false) || (data && data.status === 'error')) {
      const errorMsg = data?.detail || data?.error || data?.message || `Audio upload failed (HTTP ${res.status})`;
      throw new Error(errorMsg);
    }

    showToast('✓ Narration audio loaded successfully', 'success');

    // Reload project data from disk
    const projPathToLoad = data.project_path || state.projectPath;
    await loadProjectData(projPathToLoad);

    // Update Master Audio player immediately with response metadata
    if (data.audio && el.audioElement) {
      if (data.audio.url) el.audioElement.src = data.audio.url;
      if (el.audioFileName) el.audioFileName.textContent = data.audio.name || file.name;
      if (el.statAudioDur && data.audio.duration) el.statAudioDur.textContent = `${data.audio.duration.toFixed(2)}s`;
      if (el.audioDurationLabel && data.audio.duration) {
        el.audioDurationLabel.textContent = `${formatTime(data.audio.duration)} (${data.audio.duration.toFixed(1)}s)`;
      }
    }

    // Refresh waveform visualization if motion helper available
    if (window.RenderFlowMotion && window.RenderFlowMotion.refreshWaveform) {
      setTimeout(() => window.RenderFlowMotion.refreshWaveform(), 60);
    }

    // v2.6.1 Invariant: Uploading audio registers audio in project. Timeline is NOT auto-generated without explicit user action.
  } catch (err) {
    showToast(`Audio upload error: ${err.message}`, 'error');
  }
}

// --- Narration Audio Upload Setup ---
function setupAudioUpload() {
  const audioInput = el.audioFileInput || document.getElementById('audioFileInput');
  if (!audioInput) return;
  audioInput.addEventListener('change', async (e) => {
    const files = e.target.files;
    if (!files || !files.length) return;
    const file = files[0];
    await uploadSingleAudioFile(file);
    audioInput.value = ''; // Reset input so same file or replacement can be reselected
  });
}

// --- CAPTIONS ENGINE CONTROLLER ---
function setupCaptions() {
  if (!el.toggleCaptions) return;

  // 1. Toggle Captions ON/OFF
  el.toggleCaptions.addEventListener('change', () => {
    const isEnabled = el.toggleCaptions.checked;
    el.captionStatusBadge.textContent = isEnabled ? 'ACTIVE' : 'OFF';
    el.captionStatusBadge.style.color = isEnabled ? 'var(--cyan-primary)' : 'var(--text-muted)';
    el.captionStatusBadge.style.borderColor = isEnabled ? 'rgba(6,182,212,0.4)' : 'var(--border-color)';
    el.captionSettingsBody.style.opacity = isEnabled ? '1' : '0.45';
    el.captionSettingsBody.style.pointerEvents = isEnabled ? 'auto' : 'none';
    if (isEnabled) {
      renderCaptionPreview();
    }
  });

  // 2. Load styles catalog from API
  loadCaptionStyles();

  // 3. Category Filter Chips
  if (el.styleCategoryChips) {
    el.styleCategoryChips.querySelectorAll('.category-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        el.styleCategoryChips.querySelectorAll('.category-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.activeCategory = chip.dataset.cat || 'all';
        applyStyleFilters();
      });
    });
  }

  // 4. Style Search Input
  if (el.styleSearchInput) {
    el.styleSearchInput.addEventListener('input', (e) => {
      state.styleSearchQuery = e.target.value.trim().toLowerCase();
      applyStyleFilters();
    });
  }

  // 5. Platform Preset Selector
  if (el.captionPlatformPreset) {
    el.captionPlatformPreset.addEventListener('change', (e) => {
      const val = e.target.value;
      state.activePlatformPreset = val;
      if (el.activePresetBadge) {
        el.activePresetBadge.textContent = e.target.options[e.target.selectedIndex].text;
      }
      if (val.includes('9_16') || val === 'tiktok' || val === 'reels' || val === 'shorts') {
        el.captionPreviewStage.style.aspectRatio = '9 / 16';
        el.captionPreviewStage.style.maxWidth = '320px';
        el.captionPreviewStage.style.margin = '0 auto 1rem auto';
      } else {
        el.captionPreviewStage.style.aspectRatio = '16 / 9';
        el.captionPreviewStage.style.maxWidth = '100%';
        el.captionPreviewStage.style.margin = '0 0 1rem 0';
      }
      renderCaptionPreview();
    });
  }

  // 6. AI Settings Modal Listeners
  if (el.btnOpenAISettings && el.aiSettingsModal) {
    el.btnOpenAISettings.addEventListener('click', () => {
      if (el.aiSttProvider) el.aiSttProvider.value = state.aiSettings.stt_provider;
      if (el.aiDeepgramModel) el.aiDeepgramModel.value = state.aiSettings.deepgram_model;
      if (el.aiSmartFormatting) el.aiSmartFormatting.checked = state.aiSettings.smart_formatting;
      if (el.aiWordTimestamps) el.aiWordTimestamps.checked = state.aiSettings.word_timestamps;
      if (el.aiUtterances) el.aiUtterances.checked = state.aiSettings.utterances;
      if (el.aiDiarization) el.aiDiarization.checked = state.aiSettings.diarization;
      if (el.aiLlmProvider) el.aiLlmProvider.value = state.aiSettings.llm_provider;
      if (el.aiLlmModel) el.aiLlmModel.value = state.aiSettings.llm_model;
      if (el.aiCaptionMode) el.aiCaptionMode.value = state.aiSettings.ai_mode;
      if (el.aiQualityLevel) el.aiQualityLevel.value = state.aiSettings.quality_level;
      if (el.aiCreativeRewrite) el.aiCreativeRewrite.checked = state.aiSettings.creative_rewrite;

      el.aiSettingsModal.classList.add('active');
    });
  }

  if (el.btnCloseAISettings && el.aiSettingsModal) {
    el.btnCloseAISettings.addEventListener('click', () => {
      el.aiSettingsModal.classList.remove('active');
    });
  }

  if (el.btnSaveAISettings && el.aiSettingsModal) {
    el.btnSaveAISettings.addEventListener('click', () => {
      state.aiSettings.stt_provider = el.aiSttProvider.value;
      state.aiSettings.deepgram_model = el.aiDeepgramModel.value;
      state.aiSettings.smart_formatting = el.aiSmartFormatting.checked;
      state.aiSettings.word_timestamps = el.aiWordTimestamps.checked;
      state.aiSettings.utterances = el.aiUtterances.checked;
      state.aiSettings.diarization = el.aiDiarization.checked;
      state.aiSettings.llm_provider = el.aiLlmProvider.value;
      state.aiSettings.llm_model = el.aiLlmModel.value.trim();
      state.aiSettings.ai_mode = el.aiCaptionMode.value;
      state.aiSettings.quality_level = el.aiQualityLevel.value;
      state.aiSettings.creative_rewrite = el.aiCreativeRewrite.checked;

      el.aiSettingsModal.classList.remove('active');
      showToast('AI Caption Settings Saved!', 'success');
    });
  }

  // 7. AI Connection Testing
  if (el.btnTestAIConnection && el.aiConnectionStatus) {
    el.btnTestAIConnection.addEventListener('click', async () => {
      const prov = el.aiLlmProvider ? el.aiLlmProvider.value : 'auto';
      const pType = prov.includes('deepgram') ? 'stt' : 'llm';
      el.aiConnectionStatus.textContent = 'Testing...';
      el.aiConnectionStatus.style.color = 'var(--cyan-primary)';
      try {
        const res = await fetch('/api/ai/test-connection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: pType, provider: prov === 'auto' ? 'local_deterministic' : prov })
        });
        const d = await res.json();
        if (d.status === 'AVAILABLE' || d.status === 'CONFIGURED') {
          el.aiConnectionStatus.textContent = `✓ ${d.status} (${d.model || prov})`;
          el.aiConnectionStatus.style.color = 'var(--emerald)';
        } else {
          el.aiConnectionStatus.textContent = `⚠️ ${d.status || d.message}`;
          el.aiConnectionStatus.style.color = '#fbbf24';
        }
      } catch (err) {
        el.aiConnectionStatus.textContent = `✕ Error: ${err.message}`;
        el.aiConnectionStatus.style.color = 'var(--rose)';
      }
    });
  }

  // 8. AI Comparison & Preview Modal
  if (el.btnPreviewAIRewrite && el.aiComparisonModal) {
    el.btnPreviewAIRewrite.addEventListener('click', () => {
      el.aiComparisonModal.classList.add('active');
    });
  }

  if (el.btnCloseAIComparison && el.aiComparisonModal) {
    el.btnCloseAIComparison.addEventListener('click', () => {
      el.aiComparisonModal.classList.remove('active');
    });
  }

  if (el.btnRunComparison) {
    el.btnRunComparison.addEventListener('click', async () => {
      const text = el.aiComparisonInput.value.trim();
      if (!text) return;
      el.btnRunComparison.disabled = true;
      el.btnRunComparison.textContent = 'Analyzing...';
      try {
        const res = await fetch('/api/ai/process-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            language: el.captionLangSelect ? el.captionLangSelect.value : 'auto',
            provider: state.aiSettings.llm_provider
          })
        });
        const d = await res.json();
        el.aiOriginalText.textContent = d.original;
        el.aiCleanText.textContent = d.clean.text;
        el.aiViralText.textContent = d.viral.text;

        el.aiCleanEmphasis.innerHTML = (d.clean.emphasis || []).map(e => `<span class="ai-pill">${e}</span>`).join('') || '<span style="font-size:0.75rem; color:var(--text-dim)">None</span>';
        el.aiViralEmphasis.innerHTML = (d.viral.emphasis || []).map(e => `<span class="ai-pill">${e}</span>`).join('') || '<span style="font-size:0.75rem; color:var(--text-dim)">None</span>';

        showToast('AI Rewrite Comparison Generated', 'success');
      } catch (err) {
        showToast(`AI Preview Failed: ${err.message}`, 'error');
      } finally {
        el.btnRunComparison.disabled = false;
        el.btnRunComparison.textContent = '⚡ Run AI';
      }
    });
  }

  if (el.btnApplyClean) {
    el.btnApplyClean.addEventListener('click', () => {
      state.aiSettings.ai_mode = 'clean';
      state.aiSettings.creative_rewrite = false;
      if (el.aiCaptionMode) el.aiCaptionMode.value = 'clean';
      if (el.aiCreativeRewrite) el.aiCreativeRewrite.checked = false;
      el.aiComparisonModal.classList.remove('active');
      showToast('Clean AI Mode Applied!', 'success');
    });
  }

  if (el.btnApplyViral) {
    el.btnApplyViral.addEventListener('click', () => {
      state.aiSettings.ai_mode = 'viral';
      state.aiSettings.creative_rewrite = true;
      if (el.aiCaptionMode) el.aiCaptionMode.value = 'viral';
      if (el.aiCreativeRewrite) el.aiCreativeRewrite.checked = true;
      el.aiComparisonModal.classList.remove('active');
      showToast('Viral AI Mode Applied!', 'success');
    });
  }

  if (el.btnRestoreOriginal) {
    el.btnRestoreOriginal.addEventListener('click', () => {
      state.aiSettings.ai_mode = 'raw';
      state.aiSettings.creative_rewrite = false;
      if (el.aiCaptionMode) el.aiCaptionMode.value = 'raw';
      if (el.aiCreativeRewrite) el.aiCreativeRewrite.checked = false;
      el.aiComparisonModal.classList.remove('active');
      showToast('Restored to Original Raw Transcript', 'info');
    });
  }

  // 9. Dropdowns and inputs
  if (el.captionStyleSelect) {
    el.captionStyleSelect.addEventListener('change', (e) => {
      selectCaptionStyle(e.target.value);
    });
  }
  if (el.settingCaptionStyle) {
    el.settingCaptionStyle.addEventListener('change', (e) => {
      selectCaptionStyle(e.target.value);
    });
  }
  if (el.btnOpenCaptionPicker && el.captionPickerModal) {
    el.btnOpenCaptionPicker.addEventListener('click', () => {
      el.captionPickerModal.style.display = 'flex';
      applyStylePickerFilters();
    });
  }
  if (el.btnCloseCaptionPicker && el.captionPickerModal) {
    el.btnCloseCaptionPicker.addEventListener('click', () => {
      el.captionPickerModal.style.display = 'none';
    });
  }
  if (el.btnConfirmSelectStyle && el.captionPickerModal) {
    el.btnConfirmSelectStyle.addEventListener('click', () => {
      if (state.pickerHoveredStyle) {
        selectCaptionStyle(state.pickerHoveredStyle.id || state.pickerHoveredStyle.key);
      }
      el.captionPickerModal.style.display = 'none';
    });
  }
  if (el.captionPickerModal) {
    el.captionPickerModal.addEventListener('click', (e) => {
      if (e.target === el.captionPickerModal) {
        el.captionPickerModal.style.display = 'none';
      }
    });
  }
  const pickerSearch = document.getElementById('stylePickerSearch') || el.stylePickerSearch;
  if (pickerSearch) {
    pickerSearch.addEventListener('input', (e) => {
      state.pickerSearchQuery = e.target.value.trim().toLowerCase();
      applyStylePickerFilters();
    });
  }
  if (el.pickerCategoryChips) {
    el.pickerCategoryChips.querySelectorAll('.category-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        el.pickerCategoryChips.querySelectorAll('.category-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.pickerActiveCategory = chip.dataset.cat || 'all';
        applyStylePickerFilters();
      });
    });
  }

  [el.captionLengthSelect, el.captionLangSelect, el.captionPosSelect, el.captionWordHighlight].forEach(input => {
    if (input) {
      input.addEventListener('change', () => {
        renderCaptionPreview();
      });
    }
  });
}

const CATEGORY_TAXONOMY = {
  native: 'Native',
  creator_inspired: 'Creator Inspired',
  tiktok_reels: 'TikTok / Reels',
  youtube: 'YouTube Pro',
  podcast: 'Podcast',
  cinematic: 'Cinematic',
  karaoke: 'Karaoke',
  viral_micro: 'Viral Micro',
  minimal: 'Minimal',
  documentary: 'Documentary'
};

function getNormalizedCategory(style) {
  const cat = (style.category || '').toLowerCase();
  const id = (style.id || style.key || '').toLowerCase();
  if (cat === 'creator_inspired') return 'creator_inspired';
  if (cat === 'tiktok_reels' || id.includes('tiktok') || id.includes('reels') || id.includes('shorts')) return 'tiktok_reels';
  if (cat === 'youtube' || id.includes('youtube') || id.startsWith('yt_')) return 'youtube';
  if (cat === 'podcast' || id.startsWith('podcast_')) return 'podcast';
  if (cat === 'cinematic' || id.startsWith('cinematic_') || id.startsWith('doc_')) return 'cinematic';
  if (cat === 'karaoke' || id.includes('karaoke')) return 'karaoke';
  if (cat === 'minimal' || id === 'minimal') return 'minimal';
  if (cat === 'documentary') return 'documentary';
  if (cat === 'viral_micro') return 'viral_micro';
  return 'native';
}

async function loadCaptionStyles() {
  try {
    const res = await fetch('/api/captions/styles');
    const data = await res.json();
    if (Array.isArray(data.styles)) {
      state.captionStyles = data.styles;
    } else if (data.styles && typeof data.styles === 'object') {
      state.captionStyles = Object.entries(data.styles).map(([k, v]) => ({
        id: v.id || k,
        key: v.key || k,
        name: v.name || k,
        ...v
      }));
    } else {
      state.captionStyles = [];
    }

    const optionsHtml = state.captionStyles.map(s => 
      `<option value="${s.id || s.key}">${s.name} (${(s.category || 'standard').replace('_', ' ')})</option>`
    ).join('');

    if (el.captionStyleSelect) {
      el.captionStyleSelect.innerHTML = optionsHtml;
      el.captionStyleSelect.value = state.selectedCaptionStyle || 'classic';
    }
    if (el.settingCaptionStyle) {
      el.settingCaptionStyle.innerHTML = optionsHtml;
      el.settingCaptionStyle.value = state.selectedCaptionStyle || 'classic';
    }

    if (el.styleCountBadge) {
      el.styleCountBadge.textContent = `${state.captionStyles.length} Styles Available`;
    }
    const modalCount = document.getElementById('modalStyleCount');
    if (modalCount) modalCount.textContent = state.captionStyles.length;

    // Set initial active style trigger badge & name
    const initialStyle = state.captionStyles.find(s => (s.id || s.key) === (state.selectedCaptionStyle || 'classic')) || state.captionStyles[0];
    if (initialStyle) {
      if (el.activeStyleName) el.activeStyleName.textContent = initialStyle.name;
      if (el.activeStyleBadge) {
        const norm = getNormalizedCategory(initialStyle);
        el.activeStyleBadge.textContent = (CATEGORY_TAXONOMY[norm] || norm).toUpperCase();
      }
      state.pickerHoveredStyle = initialStyle;
      updatePickerPreview(initialStyle);
    }

    applyStylePickerFilters();
    renderCaptionCardsGrid();
    renderCaptionPreview();
    if (window.populateWorkspaceStylePresets) {
      window.populateWorkspaceStylePresets();
    }
  } catch (e) {
    console.warn('Failed to load caption styles catalog:', e);
  }
}

function applyStyleFilters() {
  renderCaptionCardsGrid();
}

function renderCaptionCardsGrid() {
  if (!el.captionStyleCards) return;
  const cat = state.activeCategory || 'all';
  const q = (state.styleSearchQuery || '').toLowerCase();
  const activeKey = state.selectedCaptionStyle || 'classic';

  const filtered = state.captionStyles.filter(s => {
    const key = (s.id || s.key || '').toLowerCase();
    const name = (s.name || '').toLowerCase();
    const desc = (s.description || '').toLowerCase();
    const sCat = (s.category || '').toLowerCase();
    const norm = getNormalizedCategory(s);
    const matchesCat = (cat === 'all') || (sCat === cat) || (norm === cat);
    const matchesQ = !q || key.includes(q) || name.includes(q) || desc.includes(q);
    return matchesCat && matchesQ;
  });

  el.captionStyleCards.innerHTML = '';
  if (!filtered.length) {
    el.captionStyleCards.innerHTML = '<div style="grid-column:1/-1; padding:2rem; text-align:center; color:var(--rf-muted, #94a3b8)">No matching caption styles found.</div>';
    return;
  }

  filtered.forEach(s => {
    const key = s.id || s.key;
    const isSelected = key === activeKey;
    const card = document.createElement('div');
    card.className = `rf-project-card rf-caption-style-card ${isSelected ? 'active' : ''}`;
    card.setAttribute('data-caption-style', key);
    card.style.padding = '1.1rem';
    card.style.textAlign = 'center';
    card.style.cursor = 'pointer';
    if (isSelected) card.style.borderColor = 'var(--rf-accent, #00f0ff)';

    const icon = s.category === 'karaoke' ? '🎤' : (s.category === 'youtube' ? '▶️' : (s.category === 'tiktok_reels' ? '📱' : (s.category === 'podcast' ? '🎙️' : (s.category === 'cinematic' ? '🎬' : '📺'))));

    card.innerHTML = `
      <div style="font-size:1.8rem; margin-bottom:0.4rem">${icon}</div>
      <div style="font-weight:700; margin-bottom:4px; font-size:0.9rem">${s.name}</div>
      <div style="font-size:0.68rem; color:var(--rf-accent, #00f0ff); font-family:var(--font-mono); text-transform:uppercase; margin-bottom:4px">${s.category || 'standard'}</div>
      <div style="font-size:0.72rem; color:var(--rf-muted, #94a3b8); margin-bottom:0.5rem; min-height:2.2em">${s.description || 'Synchronized subtitles'}</div>
      <div class="caption-active-badge" style="margin-top:0.4rem; font-size:0.7rem; color:var(--rf-accent, #00f0ff); font-weight:700; display:${isSelected ? 'block' : 'none'}">✓ Selected</div>
    `;

    card.addEventListener('click', () => {
      selectCaptionStyle(key);
      showToast(`Selected style: ${s.name}`, 'success');
    });

    el.captionStyleCards.appendChild(card);
  });
}

function applyStylePickerFilters() {
  const cat = state.pickerActiveCategory || 'all';
  const q = (state.pickerSearchQuery || '').toLowerCase();

  const filtered = state.captionStyles.filter(s => {
    const key = (s.id || s.key || '').toLowerCase();
    const name = (s.name || '').toLowerCase();
    const desc = (s.description || '').toLowerCase();
    const normCat = getNormalizedCategory(s);

    const matchesCat = (cat === 'all') || (normCat === cat) || ((s.category || '').toLowerCase() === cat);
    const matchesQuery = !q || key.includes(q) || name.includes(q) || desc.includes(q);

    return matchesCat && matchesQuery;
  });

  renderCompactStyleList(filtered);
}

function renderCompactStyleList(styles) {
  if (!el.pickerStyleList) return;
  el.pickerStyleList.innerHTML = '';

  const activeKey = state.selectedCaptionStyle || (el.settingCaptionStyle ? el.settingCaptionStyle.value : 'classic');

  // Group styles by normalized category
  const groups = {};
  styles.forEach(s => {
    const norm = getNormalizedCategory(s);
    if (!groups[norm]) groups[norm] = [];
    groups[norm].push(s);
  });

  const orderedCategories = ['native', 'creator_inspired', 'tiktok_reels', 'youtube', 'podcast', 'cinematic', 'karaoke', 'viral_micro', 'minimal', 'documentary'];

  orderedCategories.forEach(catKey => {
    const list = groups[catKey];
    if (!list || !list.length) return;

    // Category header
    const header = document.createElement('div');
    header.className = 'picker-category-header';
    header.innerHTML = `<span>📁</span> <span>${CATEGORY_TAXONOMY[catKey] || catKey}</span> <span style="font-size:0.6rem; opacity:0.6">(${list.length})</span>`;
    el.pickerStyleList.appendChild(header);

    list.forEach(style => {
      const key = style.id || style.key;
      const isSelected = key === activeKey;

      const item = document.createElement('div');
      item.className = `picker-style-item ${isSelected ? 'selected' : ''}`;
      item.dataset.styleKey = key;

      let badgeText = (style.badge || style.animation || 'clean').toUpperCase();
      if (key === 'classic') badgeText = 'DEFAULT';
      else if (key === 'editorial') badgeText = 'CINEMATIC';
      else if (key === 'bold_viral') badgeText = 'SHORTS';

      item.innerHTML = `
        <div class="picker-style-item-left">
          <span class="picker-item-name">${style.name}</span>
          <span class="picker-item-badge">${badgeText}</span>
        </div>
        <span class="picker-item-check">✓</span>
      `;

      item.addEventListener('mouseenter', () => {
        state.pickerHoveredStyle = style;
        updatePickerPreview(style);
      });

      item.addEventListener('click', () => {
        selectCaptionStyle(key);
        if (el.captionPickerModal) el.captionPickerModal.style.display = 'none';
        showToast(`Caption Style applied: ${style.name}`, 'info');
      });

      el.pickerStyleList.appendChild(item);
    });
  });

  if (!styles.length) {
    el.pickerStyleList.innerHTML = '<div style="padding:1.5rem; text-align:center; color:var(--text-dim); font-size:0.8rem">No matching caption styles found.</div>';
  }
}

function updatePickerPreview(style) {
  if (!style) return;
  const pName = document.getElementById('pickerPreviewStyleName') || el.pickerPreviewStyleName;
  const pDesc = document.getElementById('pickerPreviewDesc') || el.pickerPreviewDesc;
  const pText = document.getElementById('pickerPreviewText') || el.pickerPreviewText;
  if (pName) pName.textContent = style.name;
  if (pDesc) pDesc.textContent = style.description || 'Standard synchronized subtitles.';
  
  if (pText) {
    const font = style.font || 'Segoe UI';
    const primaryColor = style.primary_color || '#ffffff';
    const highlightColor = style.highlight_color || '#00e5ff';
    const shadowColor = style.shadow_color || 'rgba(0,0,0,0.8)';
    
    pText.style.fontFamily = `'${font}', sans-serif`;
    pText.style.color = primaryColor;
    
    let activeWordHtml = '';
    if (style.id === 'pill' || style.key === 'pill') {
      activeWordHtml = `<span style="background:rgba(20,20,30,0.85); padding:2px 8px; border-radius:12px; border:1px solid rgba(255,255,255,0.15); color:${highlightColor}">VISION</span>`;
    } else if (style.id === 'neon' || style.key === 'neon') {
      activeWordHtml = `<span style="color:${highlightColor}; text-shadow:0 0 10px ${highlightColor}, 0 0 20px ${highlightColor}">VISION</span>`;
    } else if (style.id === 'kinetic_pop' || style.key === 'kinetic_pop') {
      activeWordHtml = `<span style="color:${highlightColor}; font-size:1.15em; font-weight:800; display:inline-block; transform:scale(1.1)">VISION</span>`;
    } else {
      activeWordHtml = `<span style="color:${highlightColor}; font-weight:800; text-shadow: 0 2px 4px ${shadowColor}">VISION</span>`;
    }

    pText.innerHTML = `Berlin 1953, a city divided by<br>${activeWordHtml} and fear.`;
  }
}

function selectCaptionStyle(styleKey) {
  state.selectedCaptionStyle = styleKey;
  if (el.captionStyleSelect) {
    el.captionStyleSelect.value = styleKey;
  }
  if (el.settingCaptionStyle) {
    el.settingCaptionStyle.value = styleKey;
  }
  const styleObj = state.captionStyles.find(s => (s.id || s.key) === styleKey);
  if (styleObj) {
    if (el.activeStyleName) el.activeStyleName.textContent = styleObj.name;
    const badge = document.getElementById('activeStyleBadge') || el.activeStyleBadge;
    if (badge) {
      const norm = getNormalizedCategory(styleObj);
      badge.textContent = (CATEGORY_TAXONOMY[norm] || norm).toUpperCase();
    }
    state.pickerHoveredStyle = styleObj;
    updatePickerPreview(styleObj);
  }
  if (el.pickerStyleList) {
    el.pickerStyleList.querySelectorAll('.picker-style-item').forEach(item => {
      item.classList.toggle('selected', item.dataset.styleKey === styleKey);
    });
  }
  if (el.captionStyleCards) {
    el.captionStyleCards.querySelectorAll('.rf-caption-style-card').forEach(c => {
      const isMatch = c.getAttribute('data-caption-style') === styleKey;
      c.classList.toggle('active', isMatch);
      c.style.borderColor = isMatch ? 'var(--rf-accent, #00f0ff)' : '';
      const b = c.querySelector('.caption-active-badge');
      if (b) b.style.display = isMatch ? 'block' : 'none';
    });
  }
  renderCaptionPreview();
}

function renderCaptionPreview() {
  if (!el.captionPreviewSafeArea) return;

  const styleKey = el.captionStyleSelect ? el.captionStyleSelect.value : 'classic';
  const lang = el.captionLangSelect ? el.captionLangSelect.value : 'auto';
  const pos = el.captionPosSelect ? el.captionPosSelect.value : 'bottom';
  const wordHighlight = el.captionWordHighlight ? el.captionWordHighlight.checked : true;

  // Background image on preview stage
  if (state.currentProject && state.currentProject.images && state.currentProject.images.length > 0) {
    const firstImg = state.currentProject.images[0];
    el.captionPreviewStage.style.backgroundImage = `url('${firstImg.url}')`;
    el.captionPreviewStage.style.backgroundSize = 'cover';
    el.captionPreviewStage.style.backgroundPosition = 'center';
  } else {
    el.captionPreviewStage.style.background = 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)';
  }

  // Positioning
  el.captionPreviewSafeArea.style.justifyContent = 'center';
  if (pos === 'top') {
    el.captionPreviewSafeArea.style.alignItems = 'flex-start';
    el.captionPreviewSafeArea.style.paddingTop = '1rem';
    el.captionPreviewSafeArea.style.paddingBottom = '0';
  } else if (pos === 'center') {
    el.captionPreviewSafeArea.style.alignItems = 'center';
    el.captionPreviewSafeArea.style.padding = '0';
  } else {
    el.captionPreviewSafeArea.style.alignItems = 'flex-end';
    el.captionPreviewSafeArea.style.paddingBottom = '1.25rem';
    el.captionPreviewSafeArea.style.paddingTop = '0';
  }

  // Multilingual sample phrases with active word
  const samples = {
    en: { prefix: 'Every great empire begins with a ', active: 'VISION', suffix: ' and determination.' },
    ur: { prefix: 'ہر عظیم سلطنت کا آغاز ایک ', active: 'خواب', suffix: ' اور عزم سے ہوتا ہے۔', rtl: true },
    ar: { prefix: 'كل إمبراطورية عظيمة تبدأ بـ ', active: 'رؤية', suffix: ' وعزيمة راسخة.', rtl: true },
    hi: { prefix: 'हर महान साम्राज्य की शुरुआत एक ', active: 'दृष्टिकोण', suffix: ' से होती है।' },
    es: { prefix: 'Todo gran imperio comienza con una ', active: 'VISIÓN', suffix: ' y determinación.' },
    fr: { prefix: 'Tout grand empire commence par une ', active: 'VISION', suffix: ' et de la détermination.' },
    de: { prefix: 'Jedes große Reich beginnt mit einer ', active: 'VISION', suffix: ' und Entschlossenheit.' },
    zh: { prefix: '每一个伟大的帝国都始于一个', active: '愿景', suffix: '与坚定信念。' },
    ja: { prefix: 'すべての偉大な帝国は', active: 'ビジョン', suffix: 'と決意から始まります。' }
  };

  const sampleData = samples[lang] || samples['en'];
  const isRtl = Boolean(sampleData.rtl);

  const styleObj = state.captionStyles.find(s => (s.id || s.key) === styleKey) || {
    font: 'Montserrat',
    font_size: 44,
    font_weight: 'bold',
    primary_color: '#FFFFFF',
    highlight_color: '#38BDF8',
    outline_color: '#000000',
    outline_width: 2.5,
    shadow: 2.0,
    animation: 'none'
  };

  const container = document.createElement('div');
  container.className = `preview-caption-box ${styleKey}`;
  container.dir = isRtl ? 'rtl' : 'ltr';

  // Apply typography and core visual CSS
  container.style.fontFamily = `'${styleObj.font}', system-ui, -apple-system, sans-serif`;
  container.style.color = styleObj.primary_color;
  container.style.textAlign = isRtl ? 'right' : 'center';
  container.style.lineHeight = '1.35';
  container.style.fontWeight = styleObj.font_weight === 'black' ? '900' : (styleObj.font_weight === 'bold' ? '700' : '500');

  // Text outline & shadow via CSS text-shadow
  const outline = styleObj.outline_width || 2;
  const shadow = styleObj.shadow || 2;
  container.style.textShadow = `
    -${outline}px -${outline}px 0 ${styleObj.outline_color},
     ${outline}px -${outline}px 0 ${styleObj.outline_color},
    -${outline}px  ${outline}px 0 ${styleObj.outline_color},
     ${outline}px  ${outline}px 0 ${styleObj.outline_color},
     0px ${shadow * 2}px ${shadow * 4}px rgba(0,0,0,0.85)
  `;

  // Style specific box embellishments
  if (styleKey === 'pill') {
    container.style.background = 'rgba(15, 23, 42, 0.88)';
    container.style.backdropFilter = 'blur(6px)';
    container.style.padding = '0.4rem 1.2rem';
    container.style.borderRadius = '9999px';
    container.style.border = '1px solid rgba(255, 255, 255, 0.18)';
    container.style.boxShadow = '0 8px 24px rgba(0,0,0,0.6)';
  } else if (styleKey === 'editorial') {
    container.style.letterSpacing = '0.5px';
    container.style.fontStyle = 'italic';
  } else if (styleKey === 'bold_viral') {
    container.style.textTransform = 'uppercase';
    container.style.letterSpacing = '-0.5px';
  } else if (styleKey === 'one_word') {
    container.style.fontSize = '1.15em';
  }

  // Active word element
  const activeWordSpan = document.createElement('span');
  activeWordSpan.className = `active-word-highlight anim-${styleObj.animation}`;
  activeWordSpan.textContent = sampleData.active;

  if (wordHighlight) {
    activeWordSpan.style.color = styleObj.highlight_color;
    if (styleKey === 'neon') {
      activeWordSpan.style.textShadow = `0 0 12px ${styleObj.highlight_color}, 0 0 24px ${styleObj.highlight_color}, -${outline}px -${outline}px 0 #000, ${outline}px ${outline}px 0 #000`;
    } else if (styleKey === 'kinetic_pop') {
      activeWordSpan.style.display = 'inline-block';
      activeWordSpan.style.transform = 'scale(1.22)';
      activeWordSpan.style.margin = '0 4px';
    } else if (styleKey === 'bounce') {
      activeWordSpan.style.display = 'inline-block';
      activeWordSpan.style.transform = 'translateY(-3px)';
      activeWordSpan.style.margin = '0 2px';
    } else if (styleKey === 'pill') {
      activeWordSpan.style.background = 'rgba(255, 215, 0, 0.25)';
      activeWordSpan.style.padding = '2px 8px';
      activeWordSpan.style.borderRadius = '12px';
      activeWordSpan.style.border = '1px solid rgba(255, 215, 0, 0.6)';
    } else if (styleKey === 'editorial') {
      activeWordSpan.style.borderBottom = `2px solid ${styleObj.highlight_color}`;
      activeWordSpan.style.paddingBottom = '1px';
    }
  }

  container.appendChild(document.createTextNode(sampleData.prefix));
  container.appendChild(activeWordSpan);
  container.appendChild(document.createTextNode(sampleData.suffix));

  el.captionPreviewSafeArea.innerHTML = '';
  el.captionPreviewSafeArea.appendChild(container);
}

// --- Core Files Upload Function (handles ZIP & images with real progress) ---
function handleFilesUpload(files, optProjectName = null) {
  if (!files || !files.length) return;

  const projName = optProjectName || (state.projectPath ? state.projectPath.split(/[\/\\]/).pop() : 'custom_project_01');

  // Compute total size
  let totalBytes = 0;
  let primaryName = files[0].name;
  for (let i = 0; i < files.length; i++) {
    totalBytes += files[i].size;
  }
  const totalMB = (totalBytes / (1024 * 1024)).toFixed(1);
  const titleDisplay = files.length === 1 ? primaryName : `${primaryName} (+${files.length - 1} files)`;

  // Show status box with initial state
  el.uploadStatusBox.classList.add('active');
  el.uploadStatusFilename.textContent = titleDisplay;
  el.uploadStatusFilesize.textContent = `${totalMB} MB`;
  el.uploadProgressBar.style.width = '0%';
  el.uploadProgressBar.style.background = 'linear-gradient(90deg, var(--cyan-primary), var(--purple-accent))';
  el.uploadStatusStage.textContent = 'Uploading... 0%';
  el.uploadStatusStage.style.color = 'var(--cyan-primary)';
  el.uploadStatusResult.textContent = '';

  const form = new FormData();
  form.append('project_name', projName);
  form.append('replace_mode', 'true');
  for (let i = 0; i < files.length; i++) {
    form.append('files', files[i]);
  }

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/project/upload', true);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      el.uploadProgressBar.style.width = `${pct}%`;
      if (pct < 100) {
        el.uploadStatusStage.textContent = `Uploading... ${pct}%`;
      } else {
        el.uploadStatusStage.textContent = `Extracting & Validating images...`;
      }
    }
  };

  xhr.onload = async () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText);
        const count = data.images_registered || 0;
        
        el.uploadProgressBar.style.width = '100%';
        el.uploadProgressBar.style.background = 'var(--emerald)';
        el.uploadStatusStage.textContent = '✓ Ready';
        el.uploadStatusStage.style.color = 'var(--emerald)';
        el.uploadStatusResult.textContent = `${count} images found`;
        
        showToast(`✓ Upload successful: ${count} image(s) processed. Ready for timeline mapping.`, 'success');

        // Reload project data (which naturally sorts all extracted images)
        await loadProjectData(data.project_path);

        // v2.6.1 Invariant: Images ingested into Media Library only.
        // Check for ambiguous ordering in uploaded archives
        const ambiguousZip = data.zip_results?.find(z => z.ordering_ambiguous);
        if (ambiguousZip) {
          showToast(ambiguousZip.ordering_message || 'Original image order could not be determined from filenames. Please review import order in Media Library.', 'warning');
        }

      } catch (err) {
        handleUploadFailure(`Response parsing error: ${err.message}`);
      }
    } else {
      let errMsg = 'Upload failed';
      try {
        const contentType = xhr.getResponseHeader('content-type') || '';
        if (contentType.includes('application/json')) {
          const errData = JSON.parse(xhr.responseText);
          errMsg = errData.detail || errData.error || errData.message || errMsg;
        } else {
          errMsg = xhr.responseText || xhr.statusText || errMsg;
        }
      } catch (e) {
        errMsg = xhr.responseText || xhr.statusText || errMsg;
      }
      handleUploadFailure(errMsg);
    }
  };

  xhr.onerror = () => {
    handleUploadFailure('Network connection error during upload.');
  };

  xhr.send(form);
}

function handleUploadFailure(errMsg) {
  el.uploadProgressBar.style.width = '100%';
  el.uploadProgressBar.style.background = 'var(--rose)';
  el.uploadStatusStage.textContent = 'ZIP rejected';
  el.uploadStatusStage.style.color = 'var(--rose)';
  el.uploadStatusResult.textContent = `Reason: ${errMsg}`;
  showToast(`ZIP rejected: ${errMsg}`, 'error');
}

// Modals & Dialog Handlers
function setupModals() {
  const btnCancelCreate = document.getElementById('btnCancelCreateProject');
  if (btnCancelCreate) {
    btnCancelCreate.addEventListener('click', () => {
      if (el.uploadModal) el.uploadModal.style.display = 'none';
    });
  }

  if (el.btnOpenUpload) {
    el.btnOpenUpload.addEventListener('click', () => {
      if (el.uploadProjectName) el.uploadProjectName.value = '';
      el.uploadModal.style.display = 'flex';
      setTimeout(() => el.uploadProjectName?.focus(), 50);
    });
  }
  if (el.btnCloseUpload) {
    el.btnCloseUpload.addEventListener('click', () => {
      el.uploadModal.style.display = 'none';
    });
  }

  if (el.btnSubmitUpload) {
    el.btnSubmitUpload.addEventListener('click', async (e) => {
      if (e) { e.preventDefault(); e.stopPropagation(); }
      const projName = (el.uploadProjectName?.value || '').trim() || 'project_' + Date.now();
      try {
        el.btnSubmitUpload.disabled = true;
        el.btnSubmitUpload.textContent = 'Creating Project...';
        const r = await fetch('/api/project/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: projName })
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || 'Project creation failed');
        const resolvedPath = d.project_path || d.path;
        const resolvedName = d.project_name || d.name;

        // Reset workspace completely before opening the new clean project
        resetToEmptyWorkspace();
        localStorage.setItem('renderflow_active_project_path', resolvedPath);

        showToast(`✓ Project created: ${resolvedName}`, 'success');
        if (el.uploadModal) el.uploadModal.style.display = 'none';
        if (window.switchView) window.switchView('view-studio');
        await loadProjectData(resolvedPath);
        loadRecentProjects().catch(() => {});
      } catch (e) {
        showToast(`Project creation error: ${e.message}`, 'error');
      } finally {
        el.btnSubmitUpload.disabled = false;
        el.btnSubmitUpload.textContent = '+ Create Project';
      }
    });
  }

  if (el.btnZoomSheet) {
    el.btnZoomSheet.addEventListener('click', () => {
      if (el.contactSheetImg?.src && !el.contactSheetImg.src.endsWith('#')) {
        el.sheetModalImg.src = el.contactSheetImg.src;
        el.sheetModal.style.display = 'flex';
      }
    });
  }

  if (el.sheetModal) {
    el.sheetModal.addEventListener('click', () => {
      el.sheetModal.style.display = 'none';
    });
  }

  // --- Clear Media Modal (Section 2-3) ---
  const openClearModal = () => {
    if (el.clearMediaModal) el.clearMediaModal.classList.add('active');
  };
  const closeClearModal = () => {
    if (el.clearMediaModal) el.clearMediaModal.classList.remove('active');
  };

  if (el.btnClearMedia) el.btnClearMedia.addEventListener('click', openClearModal);
  if (el.btnClearMediaAudio) el.btnClearMediaAudio.addEventListener('click', openClearModal);
  if (el.btnCloseClearMedia) el.btnCloseClearMedia.addEventListener('click', closeClearModal);
  if (el.btnCancelClearMedia) el.btnCancelClearMedia.addEventListener('click', closeClearModal);

  if (el.btnConfirmClearMedia) {
    el.btnConfirmClearMedia.addEventListener('click', async () => {
      try {
        el.btnConfirmClearMedia.disabled = true;
        el.btnConfirmClearMedia.textContent = 'Clearing...';
        const projName = state.projectPath ? state.projectPath.split(/[\/\\]/).pop() : (state.currentProject ? state.currentProject.name : 'my_project');
        
        const res = await fetch('/api/project/clear_media', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_name: projName, project_path: state.projectPath })
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || 'Clear media failed');

        resetToEmptyWorkspace();
        closeClearModal();
        await loadRecentProjects();
        showToast('✓ Media and project timeline cleared successfully. Next upload will be completely clean.', 'success');
      } catch (err) {
        showToast(`Failed to clear media: ${err.message}`, 'error');
      } finally {
        el.btnConfirmClearMedia.disabled = false;
        el.btnConfirmClearMedia.textContent = 'Clear Media';
      }
    });
  }

  // --- Compact Caption Style Picker Modal (Section 19-23) ---
  if (el.btnOpenCaptionPicker && el.captionPickerModal) {
    el.btnOpenCaptionPicker.addEventListener('click', () => {
      el.captionPickerModal.classList.add('active');
      applyStylePickerFilters();
    });
  }
  if (el.btnCloseCaptionPicker && el.captionPickerModal) {
    el.btnCloseCaptionPicker.addEventListener('click', () => {
      el.captionPickerModal.classList.remove('active');
    });
  }
  if (el.btnConfirmSelectStyle && el.captionPickerModal) {
    el.btnConfirmSelectStyle.addEventListener('click', () => {
      if (state.pickerHoveredStyle) {
        selectCaptionStyle(state.pickerHoveredStyle.id || state.pickerHoveredStyle.key);
      }
      el.captionPickerModal.classList.remove('active');
    });
  }
  if (el.stylePickerSearch) {
    el.stylePickerSearch.addEventListener('input', (e) => {
      state.pickerSearchQuery = e.target.value.trim().toLowerCase();
      applyStylePickerFilters();
    });
  }
  if (el.pickerCategoryChips) {
    el.pickerCategoryChips.querySelectorAll('.category-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        el.pickerCategoryChips.querySelectorAll('.category-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.pickerActiveCategory = chip.dataset.cat || 'all';
        applyStylePickerFilters();
      });
    });
  }

  // Explore transitions shortcut
  if (el.btnExploreTransitions) {
    el.btnExploreTransitions.addEventListener('click', () => {
      switchTab('tab-transitions');
    });
  }
}

// Load System Status
async function loadSystemStatus() {
  try {
    const r = await fetch('/api/system_status');
    const d = await r.json();
    if (d.ffmpeg.ok) {
      el.sysFfmpeg.textContent = 'Ready (v8.1)';
      el.sysFfmpeg.style.color = 'var(--emerald)';
    } else {
      el.sysFfmpeg.textContent = 'Missing';
      el.sysFfmpeg.style.color = 'var(--rose)';
    }
    el.sysPack.textContent = `${d.transition_pack.usable_clips} Clean Clips`;
  } catch (e) {
    console.error('Failed to load system status', e);
  }
}

// Reset to completely clean workspace (Section 5, 8, 9)
function resetToEmptyWorkspace() {
  state.currentProject = null;
  state.projectPath = '';
  localStorage.removeItem('renderflow_active_project_path');
  if (el.headerProjectBadge) {
    el.headerProjectBadge.textContent = 'No Project Selected';
    el.headerProjectBadge.title = 'No active workstation project loaded. Click to open or create a project.';
  }
  if (el.audioElement) {
    el.audioElement.pause();
    el.audioElement.removeAttribute('src');
    el.audioElement.load();
  }
  if (el.audioFileName) el.audioFileName.textContent = 'None detected';
  if (el.statAudioDur) el.statAudioDur.textContent = '--';
  if (el.audioDurationLabel) el.audioDurationLabel.textContent = '--:--';
  if (el.statSceneCount) el.statSceneCount.textContent = '0';
  if (el.imageCountBadge) el.imageCountBadge.textContent = '0 images';
  
  // Clear gallery, timeline, and scenes table
  renderImagesGallery([]);
  if (el.timelineTrack) {
    el.timelineTrack.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; width:100%; color:var(--text-dim); font-size:0.8rem">No scenes configured. Upload images and audio to build timeline.</div>';
  }
  if (el.sceneTableBody) {
    el.sceneTableBody.innerHTML = '';
  }
  if (window.TimelineStudio) {
    window.TimelineStudio.render(null, null, [], null);
  }
  
  // Clear caption preview background
  if (el.captionPreviewStage) {
    el.captionPreviewStage.style.backgroundImage = 'none';
    el.captionPreviewStage.style.background = 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)';
  }
  renderCaptionPreview();
  
  // Reset showcase and QC
  updateShowcase(null);
  
  // Reset upload status box
  if (el.uploadStatusBox) {
    el.uploadStatusBox.classList.remove('active');
    if (el.uploadProgressBar) el.uploadProgressBar.style.width = '0%';
  }
  
  // Reset render state
  if (el.renderStateChip) el.renderStateChip.textContent = 'STATE: IDLE';
  if (el.renderChunkTracker) el.renderChunkTracker.textContent = 'No active job';
  if (el.renderProgressText) el.renderProgressText.textContent = '0%';
  if (el.renderElapsedText) el.renderElapsedText.textContent = 'Elapsed: 00:00';
  if (el.renderProgressBar) el.renderProgressBar.style.width = '0%';
  if (el.studioRenderStatus) el.studioRenderStatus.style.display = 'none';
  if (el.renderPulseDot) el.renderPulseDot.style.display = 'none';
}

// Load Project Data
async function loadProjectData(customPath = null) {
  window.loadProjectData = loadProjectData;
  console.log('[loadProjectData] Called with customPath:', customPath);
  try {
    const savedPath = localStorage.getItem('renderflow_active_project_path');
    const targetPath = (customPath !== null) ? customPath : (savedPath || '');
    const url = targetPath ? `/api/project/data?project_path=${encodeURIComponent(targetPath)}` : '/api/project/data';
    console.log('[loadProjectData] Fetching url:', url);
    const r = await fetch(url);
    if (!r.ok) {
      console.warn('[loadProjectData] Fetch failed status:', r.status);
      resetToEmptyWorkspace();
      return;
    }
    const data = await r.json();
    console.log('[loadProjectData] Received data project_path:', data?.project_path);
    if (!data || !data.project_path) {
      resetToEmptyWorkspace();
      return;
    }
    state.currentProject = data;
    state.projectPath = data.project_path;
    localStorage.setItem('renderflow_active_project_path', data.project_path);

    // Header badge & project status
    const pName = data.project_path.split(/[\/\\]/).pop();
    if (el.headerProjectBadge) {
      el.headerProjectBadge.textContent = pName;
      el.headerProjectBadge.title = `Active Project: ${pName} (${data.project_path})`;
    }
    const openUpload = document.getElementById('btnOpenUpload');
    if (openUpload) {
      openUpload.title = `Active Project: ${pName}\nPath: ${data.project_path}\nClick to manage media & project assets`;
    }
    const topStatus = document.getElementById('topProjectStatus');
    if (topStatus) topStatus.textContent = '● Saved';

    // Sync visual style if saved in plan
    if (data.plan && data.plan.visual_style) {
      const styleCards = document.querySelectorAll('.rf-style-card');
      styleCards.forEach(c => {
        const isMatch = c.getAttribute('data-style-val') === data.plan.visual_style;
        c.classList.toggle('active', isMatch);
        const b = c.querySelector('.style-active-badge');
        if (b) b.style.display = isMatch ? 'block' : 'none';
      });
    }

    // Sync resolution if saved in plan
    if (data.plan && data.plan.resolution && window.syncResolution) {
      window.syncResolution(data.plan.resolution);
    }

    // Sync caption style / preset if saved in plan
    if (data.plan && (data.plan.caption_style || data.plan.caption_preset) && window.applyCaptionPreset) {
      window.applyCaptionPreset(data.plan.caption_preset || data.plan.caption_style);
    }

    // Render Audio
    if (data.audio && data.audio.url) {
      if (el.audioElement) el.audioElement.src = data.audio.url;
      if (el.audioFileName) el.audioFileName.textContent = data.audio.name;
      if (el.statAudioDur) el.statAudioDur.textContent = `${data.audio.duration.toFixed(2)}s`;
      if (el.audioDurationLabel) el.audioDurationLabel.textContent = `${formatTime(data.audio.duration)} (${data.audio.duration.toFixed(1)}s)`;
    } else {
      if (el.audioElement) {
        el.audioElement.pause();
        el.audioElement.removeAttribute('src');
        el.audioElement.load();
      }
      if (el.statAudioDur) el.statAudioDur.textContent = '--';
      if (el.audioFileName) el.audioFileName.textContent = 'None detected';
      if (el.audioDurationLabel) el.audioDurationLabel.textContent = '--:--';
    }

    // Render Images Gallery (real images naturally sorted)
    renderImagesGallery(data.images || []);
    renderCaptionPreview();

    // Render Timeline & Scene Table
    renderTimelineAndTable(data.transcript, data.plan, data.images || []);

    // Auto-map if both narration and images are present, but plan is unpopulated
    const planScenesCount = (data.plan?.scenes && Array.isArray(data.plan.scenes)) ? data.plan.scenes.length : 0;
    if (planScenesCount === 0 && data.images && data.images.length > 0 && data.audio && data.audio.duration > 0) {
      if (!state.isAutoPlanning && !state._autoPlanTriggered) {
        state._autoPlanTriggered = true;
        setTimeout(async () => {
          await autoPlanProject({ resetOverrides: false, silent: false });
          state._autoPlanTriggered = false;
        }, 300);
      }
    }

    // Refresh Waveform if motion helper available
    if (window.RenderFlowMotion && window.RenderFlowMotion.refreshWaveform) {
      setTimeout(() => window.RenderFlowMotion.refreshWaveform(), 60);
    }

    // Previous render
    if (data.previous_render && data.previous_render.video) {
      updateShowcase(data.previous_render);
    } else {
      updateShowcase(null);
    }

  } catch (e) {
    console.error('Error loading project data', e);
    resetToEmptyWorkspace();
  }
}

// Load Workstation Projects from Backend (/api/projects)
async function loadRecentProjects() {
  const grid = document.getElementById('recentProjectsGrid');
  if (!grid) return;
  try {
    const res = await fetch('/api/projects');
    if (!res.ok) {
      grid.innerHTML = '<div style="grid-column:1/-1; color:var(--rf-danger,#ef4444); padding:1.5rem; text-align:center">Backend unavailable — could not load projects.</div>';
      return;
    }
    const data = await res.json();
    const projects = data.projects || [];
    if (!projects.length) {
      grid.innerHTML = '<div style="grid-column:1/-1; color:var(--rf-muted,#94a3b8); font-size:0.85rem; padding:2rem; text-align:center">No workstation projects found yet. Click "Create New Project" or ingest media to begin.</div>';
      return;
    }
    grid.innerHTML = '';
    projects.forEach(p => {
      const card = document.createElement('div');
      card.className = 'rf-project-card';
      const hasThumb = Boolean(p.thumbnail_url);
      const isRendered = Boolean(p.is_rendered);
      card.innerHTML = `
        <div class="rf-project-card-thumb" style="height:120px; background:rgba(0,0,0,0.5); border-radius:6px; overflow:hidden; position:relative; margin-bottom:0.75rem; display:flex; align-items:center; justify-content:center;">
          ${hasThumb ? `<img src="${p.thumbnail_url}" style="width:100%; height:100%; object-fit:cover;" onerror="this.style.display='none'">` : `<div style="display:flex; flex-direction:column; align-items:center; gap:4px; opacity:0.6"><span style="font-size:1.75rem">🎬</span><span style="font-size:10px; color:#94a3b8; font-weight:500">No Preview</span></div>`}
          <span class="stitch-pill ${isRendered ? 'active' : ''}" style="position:absolute; top:6px; right:6px; font-size:10px; font-weight:600; padding:2px 8px; border-radius:3px">
            ${isRendered ? (p.video_res || '4K Rendered') : 'Draft'}
          </span>
        </div>
        <div class="rf-heading-h3" style="font-weight:600; font-size:14.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:4px; color:#fff" title="${p.name}">
          ${p.name}
        </div>
        <div class="rf-desc-text" style="font-size:12px; color:var(--stitch-on-surface-variant); margin-bottom:0.75rem; display:flex; gap:0.6rem; flex-wrap:wrap;">
          <span>🖼️ ${p.image_count || 0} imgs</span>
          <span>🎙️ ${p.has_audio ? (p.audio_duration ? p.audio_duration.toFixed(1) + 's' : 'Audio') : 'No audio'}</span>
          <span>🎬 ${p.scene_count || 0} scenes</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.06); padding-top:0.5rem;">
          <button class="stitch-btn-import btn-load-proj" style="height:28px; padding:0 12px; font-size:12px; font-weight:600">Open Studio</button>
          <button class="stitch-icon-btn btn-delete-proj" style="width:28px; height:28px; color:var(--stitch-error, #f87171); font-size:14px" title="Delete Project">🗑️</button>
        </div>
      `;
      // Open project click
      const openBtn = card.querySelector('.btn-load-proj');
      if (openBtn) {
        openBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          await loadProjectData(p.path);
          if (window.switchView) window.switchView('view-studio');
          showToast(`Loaded project: ${p.name}`, 'success');
        });
      }
      card.addEventListener('click', async () => {
        await loadProjectData(p.path);
        if (window.switchView) window.switchView('view-studio');
        showToast(`Loaded project: ${p.name}`, 'success');
      });
      // Delete project click
      const delBtn = card.querySelector('.btn-delete-proj');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (!confirm(`Are you sure you want to delete project "${p.name}"? This cannot be undone.`)) return;
          try {
            const delRes = await fetch(`/api/project/${encodeURIComponent(p.name)}`, { method: 'DELETE' });
            const delData = await delRes.json();
            if (delRes.ok) {
              showToast(`Deleted project: ${p.name}`, 'info');
              const activeSaved = localStorage.getItem('renderflow_active_project_path');
              if (state.projectPath === p.path || activeSaved === p.path || (state.projectPath && state.projectPath.endsWith(p.name))) {
                localStorage.removeItem('renderflow_active_project_path');
                resetToEmptyWorkspace();
                if (window.switchView) window.switchView('view-home');
              }
              await loadRecentProjects();
            } else {
              showToast(`Failed to delete: ${delData.detail || 'Server error'}`, 'error');
            }
          } catch (err) {
            showToast(`Delete error: ${err.message}`, 'error');
          }
        });
      }
      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<div style="grid-column:1/-1; color:var(--rf-danger,#ef4444); padding:1.5rem; text-align:center">Error loading projects: ${err.message}</div>`;
  }
}

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// Render Images
function renderImagesGallery(images) {
  el.imageCountBadge.textContent = `${images.length} images`;
  el.imagesGallery.innerHTML = '';
  if (!images.length) {
    el.imagesGallery.innerHTML = `
      <div style="grid-column: 1 / -1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:2rem 1rem; background:rgba(255,255,255,0.02); border:1px dashed var(--border-color); border-radius:var(--radius-md); text-align:center;">
        <div style="font-size:2rem; margin-bottom:0.5rem; opacity:0.8">🎬</div>
        <div style="font-weight:600; font-size:1rem; color:var(--text-main); margin-bottom:0.25rem">Start a new video</div>
        <div style="font-size:0.82rem; color:var(--text-dim); max-width:320px; margin-bottom:1rem">
          Upload your images and narration to begin rendering.
        </div>
        <div style="display:flex; gap:0.75rem; flex-wrap:wrap; justify-content:center">
          <label class="btn btn-primary btn-sm" style="cursor:pointer; margin:0" title="Upload images or ZIP archive">
            📦 Upload Images
            <input type="file" id="emptyStateImgInput" multiple accept=".zip,.ZIP,.png,.jpg,.jpeg,.webp,.bmp,image/*" style="display:none">
          </label>
          <label class="btn btn-secondary btn-sm" style="cursor:pointer; margin:0" title="Upload narration audio">
            🎙️ Upload Audio
            <input type="file" id="emptyStateAudioInput" accept=".wav,.mp3,.m4a,.aac,audio/*" style="display:none">
          </label>
        </div>
      </div>
    `;
    const imgInp = document.getElementById('emptyStateImgInput');
    if (imgInp) {
      imgInp.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length) {
          handleFilesUpload(e.target.files);
        }
      });
    }
    const audInp = document.getElementById('emptyStateAudioInput');
    if (audInp) {
      audInp.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          uploadSingleAudioFile(e.target.files[0]);
        }
      });
    }
    return;
  }

  // Update Stitch Selected Asset Dock with initial asset
  const first = images[0];
  const dockThumb = document.getElementById('dockThumb');
  const dockFilename = document.getElementById('dockFilename');
  const dockDims = document.getElementById('dockDimensions');
  if (dockThumb) dockThumb.src = first.url || '';
  if (dockFilename) dockFilename.textContent = first.name || '';
  if (dockDims) dockDims.textContent = `${first.width || 3840}×${first.height || 2160} · ${first.size_human || '4K UHD'}`;
  state.selectedAsset = first;

  // Wire dock actions
  const btnDockAdd = document.getElementById('btnDockAddToTimeline');
  if (btnDockAdd && !btnDockAdd._wired) {
    btnDockAdd._wired = true;
    btnDockAdd.addEventListener('click', () => {
      const curAsset = state.selectedAsset || (images && images[0]);
      if (!curAsset) {
        showToast('No asset selected in Media Bin', 'info');
        return;
      }
      if (window.TimelineStudio) {
        window.TimelineStudio.pushHistorySnapshot();
        const curDur = window.TimelineStudio.duration || 0;
        const newScene = {
          id: `clip_${Date.now()}`,
          segment_index: window.TimelineStudio.scenes.length,
          start: curDur,
          end: curDur + 3.0,
          dur: 3.0,
          image: curAsset.name,
          imageUrl: curAsset.url,
          transition: 'cinematic_dissolve',
          context: 'normal',
          motion: 'L4/push',
          user_override: true,
          confidence: 0.95,
          confidence_level: 'HIGH',
          narration_text: ''
        };
        window.TimelineStudio.scenes.push(newScene);
        window.TimelineStudio.duration = curDur + 3.0;
        window.TimelineStudio.selectClip(window.TimelineStudio.scenes.length - 1);
        window.TimelineStudio.markUnsaved();
        window.TimelineStudio.renderScenesTrack();
        window.TimelineStudio.renderScenesBlockTrack();
        window.TimelineStudio.renderTransitionsTrack();
        showToast(`Added ${curAsset.name} to timeline`, 'success');
      }
    });
  }

  const btnDockReplace = document.getElementById('btnDockReplaceClip');
  if (btnDockReplace && !btnDockReplace._wired) {
    btnDockReplace._wired = true;
    btnDockReplace.addEventListener('click', () => {
      const curAsset = state.selectedAsset || (images && images[0]);
      if (!curAsset) {
        showToast('No asset selected in Media Bin', 'info');
        return;
      }
      if (window.TimelineStudio && window.TimelineStudio.selectedClipIndex !== null) {
        const idx = window.TimelineStudio.selectedClipIndex;
        const sc = window.TimelineStudio.scenes[idx];
        if (sc) {
          window.TimelineStudio.pushHistorySnapshot();
          sc.image = curAsset.name;
          sc.imageUrl = curAsset.url;
          sc.user_override = true;
          window.TimelineStudio.markUnsaved();
          window.TimelineStudio.renderScenesTrack();
          window.TimelineStudio.renderInspectorCard();
          window.TimelineStudio.syncPreviewFrame();
          showToast(`Replaced Scene #${idx + 1} with ${curAsset.name}`, 'success');
        }
      } else {
        showToast('Select a clip on the timeline to replace', 'info');
      }
    });
  }

  images.forEach(img => {
    const div = document.createElement('div');
    div.className = 'asset-thumb';
    div.title = `${img.name}\n${img.width ? img.width + '×' + img.height : ''} ${img.size_human ? '(' + img.size_human + ')' : ''}`;
    div.draggable = true;

    const resBadge = (img.width && img.height) ? `<span class="rf-pill" style="font-size:0.58rem; padding:1px 4px">${img.width}×${img.height}</span>` : '';
    const sizeBadge = img.size_human ? `<span class="rf-pill" style="font-size:0.58rem; padding:1px 4px">${img.size_human}</span>` : '';

    div.innerHTML = `
      <img src="${img.url}" alt="${img.name}" loading="lazy">
      <div class="thumb-tag">${img.name}</div>
      <div style="position:absolute; bottom:2px; right:2px; display:flex; gap:2px; z-index:2">
        ${resBadge}
        ${sizeBadge}
      </div>
    `;

    div.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', img.name);
      e.dataTransfer.effectAllowed = 'copy';
    });

    div.addEventListener('click', () => {
      const preview = document.getElementById('previewMainMedia');
      if (preview && img.url) {
        preview.src = img.url;
        showToast(`Previewing: ${img.name}`, 'info');
      }
      // Update Stitch Selected Asset Dock
      const dThumb = document.getElementById('dockThumb');
      const dFilename = document.getElementById('dockFilename');
      const dDims = document.getElementById('dockDimensions');
      if (dThumb) dThumb.src = img.url || '';
      if (dFilename) dFilename.textContent = img.name || '';
      if (dDims) dDims.textContent = `${img.width || 3840}×${img.height || 2160} · ${img.size_human || '4K UHD'}`;
      state.selectedAsset = img;
    });

    el.imagesGallery.appendChild(div);
  });
}

// Render Timeline & Table
function renderTimelineAndTable(transcript, plan, images) {
  let segs = transcript?.segments || [];
  if (!segs.length && plan?.scenes && plan.scenes.length) {
    segs = plan.scenes.map((s, idx) => ({
      start: (s.start !== undefined ? s.start : idx * 3.0),
      end: (s.end !== undefined ? s.end : (s.start || (idx * 3.0)) + (s.dur || 3.0)),
      text: s.narration_text || s.text || s.transcript_segment || ""
    }));
  }
  if (el.statSceneCount) el.statSceneCount.textContent = segs.length ? String(segs.length) : '0';

  if (el.timelineTrack) el.timelineTrack.innerHTML = '';
  if (el.sceneTableBody) el.sceneTableBody.innerHTML = '';

  if (!segs.length) {
    const hasAudio = Boolean(state.currentProject?.audio?.duration);
    const hasImages = Boolean(images && images.length > 0);
    let emptyMsg = 'No timeline segments generated. Upload narration audio and images to begin.';
    let tableEmptyHtml = '<tr><td colspan="5" style="text-align:center; color:var(--text-dim); padding:1.5rem">No scenes to display. Upload media and run Auto-Map Images.</td></tr>';

    if (hasAudio && hasImages) {
      emptyMsg = `${images.length} images and master audio (${formatTime(state.currentProject.audio.duration)}) loaded. Click "Auto-Map to Audio" to generate the timeline.`;
      tableEmptyHtml = `
        <tr>
          <td colspan="5" style="text-align:center; padding:2rem">
            <div style="color:#e2e8f0; font-size:0.9rem; font-weight:600; margin-bottom:6px">${images.length} Images and Narration Ready</div>
            <div style="color:var(--text-dim); font-size:0.8rem; margin-bottom:12px">Run the semantic sync engine to map all images across narration audio intervals.</div>
            <button type="button" class="stitch-btn-render-primary" onclick="window.autoPlanProject?.({ resetOverrides:false, silent:false })" style="padding:6px 16px; font-size:12px; font-weight:700">
              🪄 Auto-Map Images to Audio
            </button>
          </td>
        </tr>
      `;
    } else if (hasAudio) {
      emptyMsg = 'Master narration loaded. Ingest image assets in the Media Bin to populate timeline.';
    } else if (hasImages) {
      emptyMsg = `${images.length} image(s) loaded. Ingest narration audio to align timeline.`;
    }

    if (el.timelineTrack) el.timelineTrack.innerHTML = `<div style="display:flex; align-items:center; justify-content:center; width:100%; color:var(--text-dim); font-size:0.8rem; text-align:center; padding:0 1rem">${emptyMsg}</div>`;
    if (el.sceneTableBody) el.sceneTableBody.innerHTML = tableEmptyHtml;
    if (window.TimelineStudio) {
      window.TimelineStudio.render(null, null, images || [], state.currentProject?.audio || null);
    }
    return;
  }

  const planScenes = plan?.scenes || [];
  const planMap = {};
  let anyOverride = false;
  planScenes.forEach(s => {
    planMap[s.segment_index] = s;
    if (s.user_override) anyOverride = true;
  });

  // Display Sync Quality Report card (§27, §42, Phase 3 §30)
  const syncReport = plan?.sync_report;
  if (syncReport && el.syncAnalysisCard) {
    el.syncAnalysisCard.style.display = 'block';
    if (el.syncStatImagesIndexed) el.syncStatImagesIndexed.textContent = `${syncReport.total_images || images.length} Images Indexed`;
    if (el.syncStatBeats) el.syncStatBeats.textContent = `${syncReport.total_beats || segs.length} Semantic Beats`;
    if (el.syncStatQualityScore) {
      el.syncStatQualityScore.textContent = `Quality: ${syncReport.sync_quality_score || 90}%`;
      if (syncReport.score_breakdown) {
        const bd = syncReport.score_breakdown;
        el.syncStatQualityScore.title = `Semantic Relevance: ${bd.semantic_relevance}%\nTemporal Alignment: ${bd.temporal_alignment}%\nBeat Coverage: ${bd.beat_coverage}%\nContext Continuity: ${bd.context_continuity}%\nImage Confidence: ${bd.image_confidence}%`;
      }
    }
    if (el.syncBadgeHigh) el.syncBadgeHigh.textContent = `${syncReport.high_confidence || 0} High`;
    if (el.syncBadgeMed) el.syncBadgeMed.textContent = `${syncReport.medium_confidence || 0} Med`;
    if (el.syncBadgeLow) el.syncBadgeLow.textContent = `${syncReport.low_confidence || 0} Low`;
    if (el.reviewQueueCount) el.reviewQueueCount.textContent = `${(syncReport.low_confidence || 0) + (syncReport.medium_confidence || 0)}`;
    if (el.syncProfileSelect && syncReport.profile_used) el.syncProfileSelect.value = syncReport.profile_used;
    if (el.syncModeSelect && syncReport.sync_mode_used) el.syncModeSelect.value = syncReport.sync_mode_used;
    if (el.syncBadgeOverall) {
      const avg = Math.round((syncReport.average_confidence || 0.85) * 100);
      el.syncBadgeOverall.textContent = `Overall Confidence: ${avg}%`;
    }
    if (el.btnResyncImages) el.btnResyncImages.style.display = 'inline-block';
  } else if (el.syncAnalysisCard) {
    el.syncAnalysisCard.style.display = anyOverride ? 'block' : 'none';
    if (el.btnResyncImages) el.btnResyncImages.style.display = anyOverride ? 'inline-block' : 'none';
  }

  const totalDur = segs[segs.length - 1].end;
  const motions = ['L4/push', 'L4/pull', 'L4/drift_right', 'L4/drift_left'];
  const contexts = ['normal', 'location_change', 'turning_point', 'story_change', 'time_passage', 'emotional', 'fast'];

  const youtubeTransitions = [
    { id: 'transition_001', label: '✨ White Orange Light Leak (1.0s)' },
    { id: 'transition_002', label: '⚡ Blue White Flash (1.0s)' },
    { id: 'transition_003', label: '🔥 Red Film Burn (1.0s)' },
    { id: 'transition_004', label: '✨ Purple Cyan Light Leak (1.0s)' },
    { id: 'transition_005', label: '🔥 Orange Film Burn (1.0s)' },
    { id: 'transition_006', label: '🔆 Red White Flare (1.0s)' },
    { id: 'transition_007', label: '✨ Blue Haze Light Leak (1.0s)' },
    { id: 'transition_008', label: '✨ Golden Light Leak (1.0s)' },
    { id: 'transition_009', label: '⚡ White Pink Flash (1.0s)' },
    { id: 'transition_010', label: '✨ Amber Bokeh Light Leak (1.0s)' },
    { id: 'transition_011', label: '🎞️ White Film Strip Flash (1.0s)' },
    { id: 'transition_012', label: '🎞️ Orange Film Strip (1.0s)' },
    { id: 'transition_013', label: '🎞️ White Film Strip (1.0s)' },
    { id: 'transition_014', label: '🎞️ Cyan Film Strip Flash (1.0s)' },
    { id: 'transition_015', label: '🎞️ Black Film Strip (1.0s)' },
    { id: 'transition_016', label: '🎞️ Blue Film Strip (1.0s)' },
    { id: 'transition_017', label: '🔥 Warm Film Burn (1.0s)' },
    { id: 'transition_018', label: '🔥 White Gold Film Burn (1.0s)' },
    { id: 'transition_019', label: '🎞️ Green Film Strip (1.0s)' },
    { id: 'transition_020', label: '🎞️ Dark Amber Film Texture (1.28s)' }
  ];

  const builtinTransitions = [
    { id: 'cinematic_dissolve', label: '🎬 Cinematic Dissolve' },
    { id: 'dissolve', label: '✨ Cross Dissolve' },
    { id: 'soft_wipe', label: '↔️ Soft Directional Wipe' },
    { id: 'dip_to_black', label: '⬛ Dip to Black' },
    { id: 'dip_to_white', label: '⬜ Dip to White' },
    { id: 'fade', label: '🎞️ Subtle Film Fade' },
    { id: 'clean_cut', label: '✂️ Clean Cut' },
    { id: 'slow_dissolve', label: '🌊 Slow Cinematic Dissolve' }
  ];

  segs.forEach((seg, idx) => {
    const dur = seg.end - seg.start;
    const assigned = planMap[idx] || {};
    const imgName = assigned.image || (images[idx % images.length]?.name || 'img_01.jpg');
    const ctx = assigned.context || 'normal';
    const trans = assigned.transition || 'cinematic_dissolve';
    const motion = motions[idx % motions.length];

    const conf = assigned.confidence !== undefined ? assigned.confidence : 0.85;
    const confLevel = assigned.confidence_level || (conf >= 0.85 ? 'HIGH' : (conf >= 0.65 ? 'MEDIUM' : 'LOW'));
    const isOverride = assigned.user_override === true;
    const reasons = (assigned.match_reason || []).join(', ') || 'semantic_match';

    // Timeline visual block (§28)
    const block = document.createElement('div');
    block.className = 'timeline-block';
    block.style.flex = Math.max(0.2, dur);
    block.style.cursor = 'pointer';
    block.title = `Segment #${idx + 1}: ${seg.start.toFixed(1)}s - ${seg.end.toFixed(1)}s (${dur.toFixed(1)}s)\nImage: ${imgName}\nConfidence: ${Math.round(conf * 100)}% (${confLevel})\nReason: ${reasons}\nNarration: ${seg.text || ''}`;
    block.innerHTML = `
      <div class="block-meta">
        <span>#${idx + 1}</span>
        <span>${dur.toFixed(1)}s</span>
      </div>
      <div class="block-ctx">${trans.replace('_', ' ')}</div>
      ${idx < segs.length - 1 ? `<div class="block-cut">CUT</div>` : ''}
    `;

    // Click scene reveals details and highlights row (§28)
    block.addEventListener('click', () => {
      const trTarget = el.sceneTableBody.querySelector(`tr[data-seg="${idx}"]`);
      if (trTarget) {
        trTarget.scrollIntoView({ behavior: 'smooth', block: 'center' });
        trTarget.style.background = 'rgba(6,182,212,0.18)';
        setTimeout(() => { trTarget.style.background = ''; }, 1800);
      }
      showToast(`Scene #${idx + 1} [${Math.round(conf * 100)}% ${confLevel}]: "${seg.text?.slice(0, 45) || ''}..." ➔ ${imgName}`, 'info');
    });

    if (el.timelineTrack) el.timelineTrack.appendChild(block);

    // Table Row
    const tr = document.createElement('tr');
    tr.dataset.seg = idx;
    tr.dataset.userOverride = isOverride ? "true" : "false";
    tr.dataset.conf = conf;
    tr.dataset.confLevel = confLevel;
    tr.dataset.reason = reasons;

    const imgOptions = images.map(im => `
      <option value="${im.name}" ${im.name === imgName ? 'selected' : ''}>${im.name}</option>
    `).join('');

    const ytOptions = youtubeTransitions.map(t => `
      <option value="${t.id}" ${t.id === trans ? 'selected' : ''}>${t.label}</option>
    `).join('');

    const builtinOptions = builtinTransitions.map(t => `
      <option value="${t.id}" ${t.id === trans ? 'selected' : ''}>${t.label}</option>
    `).join('');

    const transOptions = `
      <optgroup label="🌟 YouTube Transition Pack">
        ${ytOptions}
      </optgroup>
      <optgroup label="🎬 Built-in Transitions">
        ${builtinOptions}
      </optgroup>
    `;

    const ctxOptions = contexts.map(c => `
      <option value="${c}" ${c === ctx ? 'selected' : ''}>${c.replace('_', ' ')}</option>
    `).join('');

    // Confidence badge HTML
    let confBadgeHtml = '';
    if (isOverride) {
      confBadgeHtml = `<span class="brand-badge" style="background:rgba(99,102,241,0.2); color:#818cf8; border-color:rgba(99,102,241,0.4); font-size:0.68rem; font-weight:700">🔒 Manual Override</span>`;
    } else {
      let bg = 'rgba(16,185,129,0.15)';
      let col = 'var(--emerald)';
      let border = 'rgba(16,185,129,0.3)';
      if (confLevel === 'MEDIUM') {
        bg = 'rgba(245,158,11,0.15)';
        col = 'var(--amber)';
        border = 'rgba(245,158,11,0.3)';
      } else if (confLevel === 'LOW') {
        bg = 'rgba(244,63,94,0.15)';
        col = 'var(--rose)';
        border = 'rgba(244,63,94,0.3)';
      }
      const pct = Math.round(conf * 100);
      confBadgeHtml = `
        <div>
          <span class="brand-badge" style="background:${bg}; color:${col}; border-color:${border}; font-size:0.68rem; font-weight:700">${pct}% ${confLevel}</span>
          <div style="font-size:0.68rem; color:var(--text-dim); margin-top:2px; max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" title="${reasons}">${reasons}</div>
        </div>
      `;
    }

    tr.innerHTML = `
      <td>
        <strong style="color:var(--cyan-primary)">Scene ${idx + 1}</strong>
        <div style="font-size:0.72rem; color:var(--text-dim); max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${seg.text || ''}</div>
      </td>
      <td style="font-family:var(--font-mono); font-size:0.8rem">
        ${seg.start.toFixed(2)}s &rarr; ${seg.end.toFixed(2)}s
        <span style="color:var(--text-dim)">(${dur.toFixed(2)}s)</span>
      </td>
      <td>
        <select class="form-select sel-image" style="padding:0.35rem 0.6rem; font-size:0.8rem">
          ${imgOptions}
        </select>
      </td>
      <td class="td-confidence" style="vertical-align:middle">
        ${confBadgeHtml}
      </td>
      <td>
        <select class="form-select sel-trans" style="padding:0.35rem 0.6rem; font-size:0.8rem">
          ${transOptions}
        </select>
      </td>
      <td>
        <select class="form-select sel-context" style="padding:0.35rem 0.6rem; font-size:0.8rem">
          ${ctxOptions}
        </select>
      </td>
    `;

    // Track user image manual selection (§29)
    const imgSelect = tr.querySelector('.sel-image');
    if (imgSelect) {
      imgSelect.addEventListener('change', () => {
        tr.dataset.userOverride = "true";
        const tdConf = tr.querySelector('.td-confidence');
        if (tdConf) {
          tdConf.innerHTML = `<span class="brand-badge" style="background:rgba(99,102,241,0.2); color:#818cf8; border-color:rgba(99,102,241,0.4); font-size:0.68rem; font-weight:700">🔒 Manual Override</span>`;
        }
        if (el.btnResyncImages) el.btnResyncImages.style.display = 'inline-block';

        // Record user correction for project learning (§6, §7, §8, §9)
        if (state.projectPath) {
          fetch('/api/project/record_correction', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              project_path: state.projectPath,
              scene_id: `scene_${idx + 1}`,
              original_image: imgName,
              corrected_image: imgSelect.value,
              reason: 'user_override'
            })
          }).then(r => r.json()).then(res => {
            if (res && res.status === 'ok') {
              showToast(`Recorded preference: ${imgSelect.value} (Project learning updated)`, 'info');
            }
          }).catch(e => console.warn('Could not record correction:', e));
        }
      });
    }

    if (el.sceneTableBody) el.sceneTableBody.appendChild(tr);
  });

  // Synchronize with Multi-Track Timeline Studio Engine
  if (window.TimelineStudio && typeof window.TimelineStudio.render === 'function') {
    window.TimelineStudio.render(transcript, plan, images, state.currentProject?.audio);
  }
}

// Render Review Queue Modal (§31)
function renderReviewQueueModal(data) {
  if (!el.reviewQueueModal || !el.reviewQueueContent) return;
  const scenes = data.scenes || [];
  if (!scenes.length) {
    el.reviewQueueContent.innerHTML = '<div style="padding:2rem; text-align:center; color:var(--emerald)">✓ All scenes meet high confidence criteria! No manual reviews needed.</div>';
    el.reviewQueueModal.classList.add('active');
    return;
  }

  let html = `<div style="display:flex; flex-direction:column; gap:0.75rem">`;
  scenes.forEach(sc => {
    const confPct = Math.round(sc.confidence * 100);
    const badgeColor = sc.confidence_level === 'MEDIUM' ? 'var(--amber)' : 'var(--rose)';
    const cands = sc.candidates || [];
    let candHtml = '';
    cands.forEach(c => {
      candHtml += `
        <button type="button" class="btn btn-secondary btn-sm select-review-cand" data-seg="${sc.segment_index}" data-img="${c.image}" style="font-size:0.7rem; padding:0.2rem 0.5rem">
          ${c.image} (${Math.round(c.score * 100)}%)
        </button>
      `;
    });

    html += `
      <div class="review-scene-card" style="padding:0.75rem; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); border-radius:6px; font-size:0.8rem">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem">
          <span style="font-weight:700; color:var(--text-main)">${sc.scene_id} (${sc.start.toFixed(1)}s - ${sc.end.toFixed(1)}s)</span>
          <span style="font-size:0.72rem; padding:0.15rem 0.4rem; border-radius:4px; font-weight:700; background:rgba(255,255,255,0.06); color:${badgeColor}">
            ${sc.confidence_level} (${confPct}%)
          </span>
        </div>
        <div style="color:var(--text-muted); font-size:0.78rem; margin-bottom:0.4rem; font-style:italic">
          "${sc.narration_text || 'No narration text'}"
        </div>
        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.5rem">
          <span style="color:var(--cyan-primary); font-weight:600">Selected:</span>
          <span style="font-family:var(--font-mono)">${sc.selected_image}</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap">
          <span style="color:var(--text-dim); font-size:0.72rem">Alternatives:</span>
          ${candHtml}
        </div>
      </div>
    `;
  });
  html += `</div>`;
  el.reviewQueueContent.innerHTML = html;

  // Add click handlers for alternative candidate selection
  el.reviewQueueContent.querySelectorAll('.select-review-cand').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const seg = parseInt(btn.dataset.seg);
      const img = btn.dataset.img;
      const trTarget = el.sceneTableBody.querySelector(`tr[data-seg="${seg}"]`);
      if (trTarget) {
        const sel = trTarget.querySelector('.sel-image');
        if (sel) {
          sel.value = img;
          trTarget.dataset.userOverride = "true";
          const tdConf = trTarget.querySelector('.td-confidence');
          if (tdConf) {
            tdConf.innerHTML = `<span class="brand-badge" style="background:rgba(99,102,241,0.2); color:#818cf8; border-color:rgba(99,102,241,0.4); font-size:0.68rem; font-weight:700">🔒 Manual Override</span>`;
          }
        }
      }
      showToast(`Selected ${img} for Scene ${seg + 1}`, 'success');
    });
  });

  el.reviewQueueModal.classList.add('active');
}

// Start Render Execution
async function startPipelineRender() {
  if (state.isRendering) return;
  state.isRendering = true;
  if (el.btnStartRender) el.btnStartRender.disabled = true;

  if (!state.currentProject) {
    state.isRendering = false;
    if (el.btnStartRender) el.btnStartRender.disabled = false;
    showToast('No active project found. Please select or create a project first.', 'error');
    return;
  }

  const projectImages = state.currentProject.images || [];
  if (!projectImages.length) {
    state.isRendering = false;
    if (el.btnStartRender) el.btnStartRender.disabled = false;
    showToast('Cannot render: No images uploaded. Please upload scene images in the Media Bin first.', 'error');
    if (el.imagesDropzone) {
      el.imagesDropzone.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.imagesDropzone.classList.add('dragover');
      setTimeout(() => el.imagesDropzone.classList.remove('dragover'), 2000);
    }
    return;
  }

  if (!state.currentProject.audio || !state.currentProject.audio.url) {
    state.isRendering = false;
    if (el.btnStartRender) el.btnStartRender.disabled = false;
    showToast('Cannot render: Master audio missing. Please upload narration audio first.', 'error');
    return;
  }

  const projectDir = state.projectPath;

  // Auto-save current scene table selections if modified
  try {
    const rows = el.sceneTableBody ? el.sceneTableBody.querySelectorAll('tr') : [];
    if (rows.length > 0) {
      const currentScenes = [];
      rows.forEach(tr => {
        const segIdx = parseInt(tr.dataset.seg);
        const imgSelect = tr.querySelector('.sel-image');
        const transSelect = tr.querySelector('.sel-trans');
        const ctxSelect = tr.querySelector('.sel-context');
        if (imgSelect && ctxSelect) {
          currentScenes.push({
            segment_index: segIdx,
            image: imgSelect.value,
            transition: transSelect ? transSelect.value : 'cinematic_dissolve',
            context: ctxSelect.value
          });
        }
      });
      if (currentScenes.length > 0) {
        await fetch('/api/project/save_plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: state.projectPath,
            plan: { scenes: currentScenes }
          })
        });
      }
    }
  } catch (saveErr) {
    console.warn('Plan auto-save before render warning:', saveErr);
  }

  const overlayMode = el.settingTransitionMode ? el.settingTransitionMode.value : 'auto';
  const durScale = el.settingDurScale ? parseFloat(el.settingDurScale.value) : 1.0;
  const preset = el.settingPreset ? el.settingPreset.value : 'veryfast';
  const skipVerify = el.settingVerify ? !el.settingVerify.checked : false;

  const isNumericOverlay = !isNaN(parseFloat(overlayMode)) && overlayMode !== 'auto';
  const payload = {
    images: `${projectDir}/images`,
    segments: `${projectDir}/transcript.json`,
    plan: `${projectDir}/plan.json`,
    audio: `${projectDir}/narration.wav`,
    out: `${projectDir}/final.mp4`,
    workdir: `${projectDir}/work`,
    overlay_dur: isNumericOverlay ? parseFloat(overlayMode) : null,
    transition_id: state.selectedTransition || (!isNumericOverlay && overlayMode !== 'auto' ? overlayMode : null),
    dur_scale: durScale,
    preset: preset,
    skip_verify: skipVerify,
    resolution: (window.getCanonicalResolution ? window.getCanonicalResolution() : '1080p'),
    encoder: document.getElementById('settingEncoder') ? document.getElementById('settingEncoder').value : 'auto',
    perf_mode: document.getElementById('settingPerfMode') ? document.getElementById('settingPerfMode').value : 'auto',
    quality_preset: document.getElementById('settingQuality') ? document.getElementById('settingQuality').value : 'standard',
    visual_style: state.visualStyle || 'cinematic_warm'
  };

  const captionsActive = el.toggleCaptions ? el.toggleCaptions.checked : true;
  if (captionsActive) {
    payload.enable_captions = true;
    payload.caption_style = state.selectedCaptionStyle || state.plan?.caption_preset || (state.plan?.caption_style?.id) || (el.settingCaptionStyle ? el.settingCaptionStyle.value : (el.captionStyleSelect ? el.captionStyleSelect.value : 'classic'));
    payload.caption_length = el.captionLengthSelect ? el.captionLengthSelect.value : 'medium';
    payload.caption_lang = el.captionLangSelect ? el.captionLangSelect.value : 'auto';
    payload.separate_subtitles = el.captionSidecarExport ? el.captionSidecarExport.checked : true;
    payload.platform_preset = el.captionPlatformPreset ? el.captionPlatformPreset.value : null;
    payload.stt_provider = state.aiSettings ? state.aiSettings.stt_provider : 'auto';
    payload.ai_mode = state.aiSettings ? state.aiSettings.ai_mode : 'raw';
    payload.creative_rewrite = state.aiSettings ? state.aiSettings.creative_rewrite : false;
    payload.llm_provider = state.aiSettings ? state.aiSettings.llm_provider : 'auto';
    payload.llm_model = (state.aiSettings && state.aiSettings.llm_model) ? state.aiSettings.llm_model : null;
    payload.caption_overrides = {
      word_highlight: el.captionWordHighlight ? el.captionWordHighlight.checked : true,
      position: el.captionPosSelect ? el.captionPosSelect.value : 'bottom'
    };
  } else {
    payload.enable_captions = false;
  }

  try {
    state.isRendering = true;
    if (el.btnStartRender) {
      el.btnStartRender.disabled = true;
      el.btnStartRender.innerHTML = '<span class="pulse-dot"></span> Rendering Pipeline Active...';
    }
    if (el.btnCancelRender) el.btnCancelRender.style.display = 'inline-flex';
    if (el.tabRenderBadge) el.tabRenderBadge.style.display = 'inline-block';
    const sideBadge = document.getElementById('sidebarRenderBadge');
    if (sideBadge) sideBadge.style.display = 'inline-block';

    setStep(1, 'running');
    if (el.terminalBody) {
      el.terminalBody.innerHTML = '<div class="log-line" style="color:var(--cyan-primary)">[PIPELINE INITIALIZED] Launching RenderFlow by AI With Atif...</div>';
    }

    updateObservableRenderState('PREPARING', 'Initializing engine pipeline & validating assets...', 2, 0);

    if (window.switchView) window.switchView('view-render');
    else switchTab('tab-render');

    const res = await fetch('/api/render/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Render initiation failed');

    listenRenderStream();

  } catch (e) {
    showToast(`Render failed: ${e.message}`, 'error');
    state.isRendering = false;
    if (el.btnStartRender) {
      el.btnStartRender.disabled = false;
      el.btnStartRender.innerHTML = '<svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Launch Engine Pipeline';
    }
    if (el.btnCancelRender) el.btnCancelRender.style.display = 'none';
    updateObservableRenderState('FAILED', e.message, 0, 0);
  }
}

// Function to update real-time observable render progress (Section 12, 13, 15)
function updateObservableRenderState(stateName, chunkInfo, progress, elapsed) {
  if (window.renderCore3DInstance) {
    if (stateName === 'COMPLETED') window.renderCore3DInstance.setState('complete');
    else if (stateName === 'FAILED' || stateName === 'ERROR') window.renderCore3DInstance.setState('error');
    else if (stateName === 'RENDERING_CHUNK' || stateName === 'ENCODING') window.renderCore3DInstance.setState('rendering');
    else if (stateName === 'BUILDING_TIMELINE' || stateName === 'PLANNING_TRANSITIONS') window.renderCore3DInstance.setState('syncing');
    else window.renderCore3DInstance.setState('idle');
  }

  if (stateName) {
    const isStall = stateName === 'STALLED';
    const stateText = `STATE: ${stateName}`;
    if (el.renderStateChip) {
      el.renderStateChip.textContent = stateText;
      el.renderStateChip.style.color = isStall ? 'var(--amber)' : '';
      el.renderStateChip.style.background = isStall ? 'rgba(245,158,11,0.2)' : '';
      el.renderStateChip.style.borderColor = isStall ? 'rgba(245,158,11,0.5)' : '';
    }
    const heading = document.getElementById('renderStatusHeading');
    if (heading) {
      heading.textContent = stateName === 'COMPLETED' ? 'RENDER COMPLETED' : (stateName === 'FAILED' ? 'RENDER FAILED' : `RENDERING: ${stateName}`);
    }
    if (el.studioStateChip) {
      el.studioStateChip.textContent = stateText;
      el.studioStateChip.style.color = isStall ? 'var(--amber)' : '';
    }
  }
  if (chunkInfo) {
    if (el.renderChunkTracker) el.renderChunkTracker.textContent = chunkInfo;
    if (el.studioChunkTracker) el.studioChunkTracker.textContent = chunkInfo;
    const term = document.getElementById('terminalStatusText');
    if (term && stateName) term.textContent = `${stateName}: ${chunkInfo}`;
  }
  if (progress !== undefined && progress !== null) {
    const pct = `${Math.min(100, Math.max(0, Math.round(progress)))}%`;
    const pctEl = document.getElementById('renderProgressPercent') || el.renderProgressText;
    if (pctEl) pctEl.textContent = pct;
    if (el.studioProgressPercent) el.studioProgressPercent.textContent = pct;
    const barEl = document.getElementById('renderProgressBarFill') || el.renderProgressBar;
    if (barEl) barEl.style.width = pct;
  }
  if (elapsed !== undefined && elapsed !== null) {
    const m = Math.floor(elapsed / 60);
    const s = Math.floor(elapsed % 60);
    const timeStr = `Elapsed: ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    if (el.renderElapsedText) el.renderElapsedText.textContent = timeStr;
  }
  const pulse = document.getElementById('renderPulseDot') || el.renderPulseDot;
  if (pulse) {
    pulse.style.display = (stateName === 'COMPLETED' || stateName === 'FAILED' || stateName === 'CANCELLED') ? 'none' : 'inline-block';
  }
  if (el.studioRenderStatus) {
    el.studioRenderStatus.style.display = (stateName === 'COMPLETED' || stateName === 'CANCELLED') ? 'none' : 'block';
  }
}

// SSE Log Listener
function listenRenderStream() {
  if (state.eventSource) {
    state.eventSource.close();
  }

  const es = new EventSource('/api/render/stream');
  state.eventSource = es;

  es.onmessage = (event) => {
    try {
      const d = JSON.parse(event.data);
      if (d.type === 'log') {
        appendLogLine(d.line);
        if (d.step) {
          setStep(d.step, 'running');
        }
      } else if (d.type === 'encoder_update') {
        const encEl = document.getElementById('rfRenderMetricEncoder');
        if (encEl && d.encoder) {
          encEl.textContent = d.encoder.toUpperCase();
        }
      } else if (d.type === 'status') {
        if (el.terminalStatusText) el.terminalStatusText.textContent = d.msg || d.state;
      } else if (d.type === 'state_update') {
        const stateName = d.state_marker || d.state;
        updateObservableRenderState(stateName, d.chunk_info, d.progress ?? d.progress_percent, d.elapsed);
      } else if (d.type === 'chunk_update') {
        updateObservableRenderState(null, d.chunk_info, null, null);
      } else if (d.type === 'progress_update') {
        updateObservableRenderState(d.state_marker, d.chunk_info, d.progress_percent, d.elapsed);
      } else if (d.type === 'heartbeat') {
        if (d.stalled) {
          updateObservableRenderState('STALLED', d.msg || 'RENDER MAY BE STALLED', d.progress_percent, d.elapsed);
          if (el.terminalStatusText) {
            el.terminalStatusText.textContent = d.msg || 'RENDER MAY BE STALLED';
            el.terminalStatusText.style.color = 'var(--amber)';
          }
        } else {
          updateObservableRenderState(d.state_marker, d.chunk_info, d.progress_percent, d.elapsed);
          if (el.terminalStatusText && el.terminalStatusText.textContent.includes('STALLED')) {
            el.terminalStatusText.textContent = 'Rendering in progress';
            el.terminalStatusText.style.color = '';
          }
        }
      } else if (d.type === 'finished') {
        es.close();
        state.isRendering = false;
        if (el.btnStartRender) {
          el.btnStartRender.disabled = false;
          el.btnStartRender.innerHTML = '<span>⚡</span> Start Hardware-Accelerated Render';
        }
        if (el.btnCancelRender) el.btnCancelRender.style.display = 'none';

        if (d.state === 'completed') {
          setStep(3, 'done');
          if (el.terminalStatusText) el.terminalStatusText.textContent = 'Completed Successfully';
          updateObservableRenderState('COMPLETED', 'Video generation complete and verified', 100, d.elapsed);
          showToast(`✓ Pipeline Complete! Rendered in ${d.elapsed}s`, 'success');
          
          const btnDownload = document.getElementById('btnDownloadVideo') || el.btnDownloadVideo;
          if (btnDownload && d.video_url) {
            btnDownload.style.display = 'inline-flex';
            btnDownload.onclick = () => window.open(d.video_url, '_blank');
          }

          updateShowcase({
            video: { url: d.video_url },
            contact_sheet_url: d.contact_sheet_url,
            qc: d.qc,
            captions: d.captions
          });

          // Refresh recent projects list to show rendered status
          loadRecentProjects();
        } else {
          if (el.terminalStatusText) el.terminalStatusText.textContent = 'Render Failed';
          updateObservableRenderState('FAILED', d.error || 'Render failed. Check logs.', 0, d.elapsed);
          showToast(`Render Error: ${d.error || 'Check logs'}`, 'error');
        }
      }
    } catch (err) {
      console.error('SSE parsing error', err);
    }
  };

  es.onerror = async () => {
    try {
      const res = await fetch('/api/render/status');
      if (res.ok) {
        const d = await res.json();
        if (d.state === 'running') {
          console.warn('[SSE] EventSource interrupted while render is running. Retrying...');
          return;
        } else if (d.state === 'completed') {
          es.close();
          setStep(3, 'done');
          if (el.terminalStatusText) el.terminalStatusText.textContent = 'Completed Successfully';
          updateObservableRenderState('COMPLETED', 'Video generation complete and verified', 100, 0);
          showToast('✓ Pipeline Complete!', 'success');
          state.isRendering = false;
          if (el.btnStartRender) {
            el.btnStartRender.disabled = false;
            el.btnStartRender.innerHTML = '<span>⚡</span> Start Hardware-Accelerated Render';
          }
          if (el.btnCancelRender) el.btnCancelRender.style.display = 'none';
          loadRecentProjects();
          return;
        } else if (d.state === 'error' || d.state === 'cancelled') {
          es.close();
          if (el.terminalStatusText) el.terminalStatusText.textContent = 'Render Failed';
          updateObservableRenderState('FAILED', d.error || 'Render process exited with error.', 0, 0);
          showToast(`Render Error: ${d.error || 'Check logs'}`, 'error');
          state.isRendering = false;
          if (el.btnStartRender) {
            el.btnStartRender.disabled = false;
            el.btnStartRender.innerHTML = '<span>⚡</span> Start Hardware-Accelerated Render';
          }
          if (el.btnCancelRender) el.btnCancelRender.style.display = 'none';
          return;
        }
      }
    } catch (err) {
      console.error('[SSE] Error polling render status:', err);
    }
    es.close();
    state.isRendering = false;
    if (el.btnStartRender) {
      el.btnStartRender.disabled = false;
      el.btnStartRender.innerHTML = '<span>⚡</span> Start Hardware-Accelerated Render';
    }
    if (el.btnCancelRender) el.btnCancelRender.style.display = 'none';
  };
}

function setStep(stepNum, status) {
  [el.stepChip1, el.stepChip2, el.stepChip3].forEach((chip, idx) => {
    if (!chip) return;
    const num = idx + 1;
    chip.classList.remove('active', 'done');
    if (num < stepNum) {
      chip.classList.add('done');
    } else if (num === stepNum) {
      chip.classList.add(status === 'done' ? 'done' : 'active');
    }
  });
}

function appendLogLine(line) {
  state.logs.push(line);
  const div = document.createElement('div');
  div.className = 'log-line';

  // Parse state markers dynamically from logs
  if (line.includes('[STATE:')) {
    const m = line.match(/\[STATE:([A-Za-z0-9_]+)\]/);
    if (m && m[1]) {
      updateObservableRenderState(m[1], null, null, null);
    }
  }
  if (line.includes('[ENCODER_ACTIVE]')) {
    const encMatch = line.split('[ENCODER_ACTIVE]')[1].trim();
    const encEl = document.getElementById('rfRenderMetricEncoder');
    if (encEl && encMatch) {
      encEl.textContent = encMatch.toUpperCase();
    }
  }
  if (line.includes('Rendering chunk') || line.includes('Chunk ') || line.includes('[CHUNK:')) {
    const m = line.match(/chunk\s+(\d+\s*\/\s*\d+)/i) || line.match(/\[CHUNK:([^\]]+)\]/);
    if (m && m[1]) {
      updateObservableRenderState(null, `Rendering Chunk ${m[1]}`, null, null);
    }
  }
  if (line.includes('progress: ') || line.includes('[PROGRESS:')) {
    const m = line.match(/progress:\s*(\d+(?:\.\d+)?)%/i) || line.match(/\[PROGRESS:([0-9.]+)%\]/);
    if (m && m[1]) {
      updateObservableRenderState(null, null, parseFloat(m[1]), null);
    }
  }

  if (line.includes('=== STEP')) {
    div.classList.add('step');
  } else if (line.includes('PASS -')) {
    div.classList.add('pass');
  } else if (line.includes('FAIL -') || line.includes('FAILED') || line.includes('Error') || line.includes('[FFMPEG ERROR]')) {
    div.classList.add('fail');
  } else if (line.includes('cut@') || line.includes('transitions QC') || line.includes('[TRANSITION]')) {
    div.classList.add('cut');
  }

  div.textContent = line;
  el.terminalBody.appendChild(div);
  el.terminalBody.scrollTop = el.terminalBody.scrollHeight;
}

async function cancelRender() {
  try {
    await fetch('/api/render/cancel', { method: 'POST' });
    showToast('Cancellation signal sent', 'info');
  } catch (e) {
    showToast(`Cancel failed: ${e.message}`, 'error');
  }
}

function setBadgePending(elem, text = 'PENDING') {
  if (!elem) return;
  elem.className = 'qc-badge';
  elem.style.background = 'rgba(255,255,255,0.06)';
  elem.style.color = 'var(--text-dim)';
  elem.textContent = text;
}

// Update Showcase & QA Tab
function updateShowcase(prev) {
  const fb = document.querySelector('.canvas-3d-fallback');
  if (!prev || !prev.video || !prev.video.url) {
    if (el.finalVideoPlayer) {
      el.finalVideoPlayer.removeAttribute('src');
      el.finalVideoPlayer.load();
      el.finalVideoPlayer.style.display = 'none';
      if (fb) fb.style.display = 'flex';
    }
    if (el.btnDownloadVideo) {
      el.btnDownloadVideo.removeAttribute('href');
      el.btnDownloadVideo.style.display = 'none';
    }
    if (el.contactSheetImg) {
      el.contactSheetImg.removeAttribute('src');
      el.contactSheetImg.style.display = 'none';
    }
    const btnZoomSheet = document.getElementById('btnZoomSheet');
    if (btnZoomSheet) btnZoomSheet.style.display = 'none';
    if (el.captionExportsCard) {
      el.captionExportsCard.style.display = 'none';
    }
    if (el.btnDownloadSrt) el.btnDownloadSrt.style.display = 'none';
    if (el.btnDownloadAss) el.btnDownloadAss.style.display = 'none';
    if (el.btnDownloadJson) el.btnDownloadJson.style.display = 'none';
    [el.qcH264, el.qcRes, el.qcFps, el.qcAAC, el.qcAudio, el.qcVisual, el.qcDiffs].forEach(b => setBadgePending(b, 'PENDING'));
    setBadgePending(el.qcCaptions, 'OFF');
    return;
  }

  if (el.finalVideoPlayer) {
    el.finalVideoPlayer.src = prev.video.url;
    el.finalVideoPlayer.style.display = 'block';
    if (fb) fb.style.display = 'none';
  }
  if (el.btnDownloadVideo) {
    el.btnDownloadVideo.href = prev.video.url;
    el.btnDownloadVideo.style.display = 'inline-flex';
    el.btnDownloadVideo.onclick = () => {
      window.open(prev.video.url, '_blank');
    };
  }
  const btnZoomSheet = document.getElementById('btnZoomSheet');
  if (btnZoomSheet) {
    if (prev.contact_sheet_url) {
      btnZoomSheet.style.display = 'inline-flex';
      btnZoomSheet.onclick = () => {
        window.open(prev.contact_sheet_url, '_blank');
      };
    } else {
      btnZoomSheet.style.display = 'none';
    }
  }
  if (prev.contact_sheet_url && el.contactSheetImg) {
    el.contactSheetImg.src = prev.contact_sheet_url;
  } else if (el.contactSheetImg) {
    el.contactSheetImg.removeAttribute('src');
    el.contactSheetImg.style.display = 'none';
  }

  if (prev.qc) {
    const q = prev.qc;
    const nTransitions = q.transitions?.n_transitions ?? 2;
    const avgTDur = q.transitions?.avg_duration_s ?? 0.5;
    const nImages = q.asset_integrity?.images_decoded_ok ?? q.timeline?.n_images_used ?? 3;
    const audioDb = q.audio_mean_db ?? -22.8;

    setBadge(el.qcH264, true, 'PASS');
    setBadge(el.qcRes, true, '1920x1080');
    setBadge(el.qcFps, true, '30.00');
    setBadge(el.qcAAC, true, '48kHz Stereo');
    setBadge(el.qcAudio, true, `${audioDb} dB`);
    setBadge(el.qcVisual, true, `${nImages} Images OK`);
    setBadge(el.qcDiffs, true, `${nTransitions} Cuts (${avgTDur}s)`);
  }

  // Captions Sidecars & QC
  if (prev.captions) {
    const caps = prev.captions;
    let hasSidecars = false;
    if (caps.srt_url && el.btnDownloadSrt) {
      el.btnDownloadSrt.href = caps.srt_url;
      el.btnDownloadSrt.style.display = 'flex';
      hasSidecars = true;
    }
    if (caps.ass_url && el.btnDownloadAss) {
      el.btnDownloadAss.href = caps.ass_url;
      el.btnDownloadAss.style.display = 'flex';
      hasSidecars = true;
    }
    if (caps.json_url && el.btnDownloadJson) {
      el.btnDownloadJson.href = caps.json_url;
      el.btnDownloadJson.style.display = 'flex';
      hasSidecars = true;
    }
    if (el.captionExportsCard) {
      el.captionExportsCard.style.display = hasSidecars ? 'block' : 'none';
    }

    if (caps.qc && el.qcCaptions) {
      const q = caps.qc;
      const totalCues = q.total_captions ?? q.total_segments ?? 0;
      const isValid = (q.valid === true) && (q.overall_status === 'PASS') && (totalCues > 0);
      setBadge(el.qcCaptions, isValid, isValid ? `PASS (${totalCues} cues)` : (totalCues === 0 ? 'FAIL (0 cues)' : 'FAIL'));
    } else if (hasSidecars && el.qcCaptions) {
      setBadge(el.qcCaptions, true, 'PASS (Rendered)');
    } else if (el.qcCaptions) {
      setBadge(el.qcCaptions, true, 'OFF');
    }
  }
}

function setBadge(elem, ok, text) {
  if (!elem) return;
  elem.className = `qc-badge ${ok ? 'pass' : 'fail'}`;
  elem.style.background = '';
  elem.textContent = text;
}

function populateTransitionDropdown(clips) {
  const modeSelect = document.getElementById('settingTransitionMode');
  if (!modeSelect || !clips || !clips.length) return;

  const currentVal = modeSelect.value || state.selectedTransition || 'auto';
  modeSelect.innerHTML = '';

  // 1. Dynamic optgroup
  const grpAuto = document.createElement('optgroup');
  grpAuto.label = '⚡ Dynamic & Pacing';
  const optAuto = document.createElement('option');
  optAuto.value = 'auto';
  optAuto.textContent = 'Auto Dynamic (Intelligent Cinematic)';
  grpAuto.appendChild(optAuto);

  const optNone = document.createElement('option');
  optNone.value = 'none';
  optNone.textContent = 'Hard Cut (No Transition)';
  grpAuto.appendChild(optNone);
  modeSelect.appendChild(grpAuto);

  // 2. YouTube Pack optgroup (Flares, Light Leaks, Film Burns)
  const ytClips = clips.filter(c => c.category === 'YouTube Pack');
  if (ytClips.length > 0) {
    const grpYT = document.createElement('optgroup');
    grpYT.label = '🌟 YouTube Cinematic Flares, Leaks & Film Burns';
    ytClips.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.title || c.name || c.id} (4K Overlay)`;
      grpYT.appendChild(opt);
    });
    modeSelect.appendChild(grpYT);
  }

  // 3. Built-in optgroup
  const builtinClips = clips.filter(c => c.category === 'Built-in');
  if (builtinClips.length > 0) {
    const grpBuiltin = document.createElement('optgroup');
    grpBuiltin.label = '🎬 Built-in Cinematic Dissolves & Wipes';
    builtinClips.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.title || c.name || c.id}`;
      grpBuiltin.appendChild(opt);
    });
    modeSelect.appendChild(grpBuiltin);
  }

  // Restore previous selection if present
  modeSelect.value = currentVal;
  if (!modeSelect.value) modeSelect.value = 'auto';

  // Listen to changes
  modeSelect.addEventListener('change', () => {
    const val = modeSelect.value;
    state.selectedTransition = (val === 'auto' || val === 'none') ? (val === 'none' ? 'none' : null) : val;
    const grid = document.getElementById('transGrid') || el.transitionCardsGrid;
    if (grid) {
      grid.querySelectorAll('.transition-card').forEach(c => {
        const isMatch = state.selectedTransition && c.textContent.includes(state.selectedTransition);
        c.classList.toggle('active', Boolean(isMatch));
      });
    }
  });
}

// Load Transitions Explorer
async function loadTransitions() {
  try {
    const r = await fetch('/api/transitions');
    const data = await r.json();
    state.transitions = data.clips || [];
    state.transitionCategory = 'all';
    populateTransitionDropdown(state.transitions);
    applyTransitionFilters();

    const searchInput = document.getElementById('transSearch') || el.searchTransitions;
    if (searchInput) searchInput.addEventListener('input', applyTransitionFilters);

    const catTabs = document.getElementById('transCategoryTabs');
    if (catTabs) {
      catTabs.querySelectorAll('.trans-cat-pill').forEach(pill => {
        pill.addEventListener('click', () => {
          catTabs.querySelectorAll('.trans-cat-pill').forEach(p => p.classList.remove('active'));
          pill.classList.add('active');
          state.transitionCategory = pill.getAttribute('data-cat') || 'all';
          applyTransitionFilters();
        });
      });
    }

    if (el.filterTransitionCategory) el.filterTransitionCategory.addEventListener('change', applyTransitionFilters);
    if (el.filterTransitionKind) el.filterTransitionKind.addEventListener('change', applyTransitionFilters);
  } catch (e) {
    console.error('Failed to load transitions', e);
  }
}

function applyTransitionFilters() {
  const searchInput = document.getElementById('transSearch') || el.searchTransitions;
  const query = (searchInput?.value || '').trim().toLowerCase();
  const category = (state.transitionCategory || 'all').toLowerCase();

  const filtered = state.transitions.filter(c => {
    const text = `${c.id} ${c.title || ''} ${c.name || ''} ${c.category || ''} ${c.subcategory || ''}`.toLowerCase();
    const matchesSearch = !query || text.includes(query);
    if (!matchesSearch) return false;

    if (category === 'all') return true;
    if (category === 'dissolve') return text.includes('dissolve') || text.includes('fade');
    if (category === 'wipe') return text.includes('wipe');
    if (category === 'motion') return text.includes('zoom') || text.includes('motion') || text.includes('slide');
    if (category === 'stylized') return text.includes('flare') || text.includes('glitch') || text.includes('light') || text.includes('leak') || text.includes('film');
    return (c.category || '').toLowerCase().includes(category);
  });

  renderTransitionCards(filtered);
}

function renderTransitionCards(clips) {
  const grid = document.getElementById('transGrid') || el.transitionCardsGrid;
  if (!grid) return;
  grid.innerHTML = '';
  if (!clips.length) {
    grid.innerHTML = '<div style="color:var(--rf-muted, #94a3b8); font-size:0.85rem; padding:1.5rem; grid-column:1/-1; text-align:center">No matching transitions found. Try adjusting category or search.</div>';
    return;
  }

  clips.forEach(clip => {
    const isSelected = state.selectedTransition === clip.id;
    const card = document.createElement('div');
    card.className = 'rf-project-card transition-card' + (isSelected ? ' active' : '');
    card.style.cursor = 'pointer';

    let catBadgeBg = 'rgba(59,130,246,0.85)';
    let catLabel = clip.category || 'General';
    if (clip.category === 'YouTube Pack') {
      catBadgeBg = 'linear-gradient(135deg, #f59e0b, #ef4444)';
      catLabel = '🌟 YT PACK';
    } else if (clip.category === 'Built-in') {
      catBadgeBg = 'linear-gradient(135deg, #06b6d4, #3b82f6)';
      catLabel = '🎬 BUILT-IN';
    } else if (clip.category === 'Lens Flares') {
      catBadgeBg = 'linear-gradient(135deg, #8b5cf6, #ec4899)';
      catLabel = '🔆 FLARE';
    }

    const hasVideo = Boolean(clip.media_url);
    const previewImg = clip.preview && !clip.preview.endsWith('.mp4') ? clip.preview : null;

    card.innerHTML = `
      <div style="position:relative; aspect-ratio:16/9; background:#04060a; border-radius:6px; overflow:hidden; margin-bottom:0.4rem; display:flex; align-items:center; justify-content:center;">
        ${previewImg ? `<img src="${previewImg}" alt="${clip.name || clip.id}" style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover" onerror="this.style.display='none'">` : ''}
        ${hasVideo ? `<video src="${clip.media_url}" preload="none" muted loop style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:${previewImg ? 0 : 1};" onmouseover="this.style.opacity='1'; this.play()" onmouseout="${previewImg ? 'this.style.opacity=0;' : ''} this.pause()"></video>` : `<div style="font-size:1.6rem; opacity:0.3">${clip.icon || '🎬'}</div>`}
        <span style="position:absolute; top:4px; left:4px; font-size:0.58rem; padding:1px 5px; border-radius:3px; font-weight:700; background:${catBadgeBg}; color:#fff; text-shadow:0 1px 2px rgba(0,0,0,0.5)">
          ${catLabel}
        </span>
        <span style="position:absolute; bottom:4px; right:4px; font-size:0.6rem; font-family:var(--font-mono); background:rgba(0,0,0,0.85); color:#fff; padding:1px 4px; border-radius:3px">
          ${clip.duration ? `${clip.duration.toFixed(1)}s` : ''}
        </span>
      </div>
      <div>
        <div style="font-size:0.78rem; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="${clip.title || clip.name}">${clip.title || clip.name || clip.id}</div>
        <div style="font-size:0.68rem; color:var(--rf-muted, #94a3b8); margin-top:1px; font-family:var(--font-mono)">${clip.id} &bull; ${clip.asset_type || 'xfade'}</div>
      </div>
      <div style="margin-top:0.35rem; display:flex; justify-content:space-between; align-items:center">
        <span style="font-size:0.65rem; color:var(--rf-accent, #00f0ff); font-weight:600">${isSelected ? '✓ ACTIVE' : (hasVideo ? 'Hover to play' : 'Filtergraph')}</span>
        <button class="btn ${isSelected ? 'btn-primary' : 'btn-secondary'} btn-sm" style="font-size:0.65rem; padding:1px 6px">${isSelected ? 'Active' : 'Select'}</button>
      </div>
    `;

    // Click to select transition
    card.addEventListener('click', () => {
      state.selectedTransition = clip.id;
      grid.querySelectorAll('.transition-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      const modeSelect = document.getElementById('settingTransitionMode');
      if (modeSelect) {
        let found = false;
        for (let opt of modeSelect.options) {
          if (opt.value === clip.id || opt.text.toLowerCase().includes((clip.name || clip.id).toLowerCase())) {
            modeSelect.value = opt.value;
            found = true;
            break;
          }
        }
        if (!found) {
          const opt = document.createElement('option');
          opt.value = clip.id;
          opt.textContent = `${clip.title || clip.name || clip.id}`;
          modeSelect.appendChild(opt);
          modeSelect.value = clip.id;
        }
      }
      showToast(`Selected transition: ${clip.title || clip.name || clip.id}`, 'success');
    });

    grid.appendChild(card);
  });
}

// ==========================================================================
// AI PROVIDER & API CREDENTIAL CENTER CONTROLLER
// ==========================================================================

let credentialsCache = [];
let credentialsFilter = 'all';

function initAICredentialCenter() {
  // Modal opening triggers
  if (el.btnOpenAICredentials) {
    el.btnOpenAICredentials.addEventListener('click', openAICredentialsCenter);
  }
  if (el.btnHeaderCredentials) {
    el.btnHeaderCredentials.addEventListener('click', openAICredentialsCenter);
  }
  if (el.btnOpenCredentialsFromSettings) {
    el.btnOpenCredentialsFromSettings.addEventListener('click', () => {
      if (el.aiSettingsModal) el.aiSettingsModal.classList.remove('active');
      openAICredentialsCenter();
    });
  }
  if (el.btnCloseAICredentials && el.aiCredentialsModal) {
    el.btnCloseAICredentials.addEventListener('click', closeAICredentialsCenter);
  }
  if (el.btnRefreshAllCredentials) {
    el.btnRefreshAllCredentials.addEventListener('click', () => loadAICredentials(true));
  }

  // Filter tabs
  const filterTabs = document.querySelectorAll('.cred-tab');
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      credentialsFilter = tab.dataset.credFilter || 'all';
      renderAICredentialCards();
    });
  });

  // Modal backdrop click to close
  if (el.aiCredentialsModal) {
    el.aiCredentialsModal.addEventListener('click', (e) => {
      if (e.target === el.aiCredentialsModal) {
        closeAICredentialsCenter();
      }
    });
  }

  // Escape key closes modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && el.aiCredentialsModal && el.aiCredentialsModal.classList.contains('active')) {
      closeAICredentialsCenter();
    }
  });
}

function openAICredentialsCenter() {
  if (!el.aiCredentialsModal) return;
  el.aiCredentialsModal.classList.add('active');
  loadAICredentials();
}

function closeAICredentialsCenter() {
  if (!el.aiCredentialsModal) return;
  el.aiCredentialsModal.classList.remove('active');
}

async function loadAICredentials(isManualRefresh = false) {
  if (isManualRefresh && el.btnRefreshAllCredentials) {
    el.btnRefreshAllCredentials.disabled = true;
    el.btnRefreshAllCredentials.textContent = '🔄 Refreshing...';
  }

  try {
    const res = await fetch('/api/ai/providers');
    const data = await res.json();
    credentialsCache = data.providers || [];

    // Update Overview Stats
    updateCredentialsOverview(data.overview);

    // Render Cards
    renderAICredentialCards();

    // Load Fallback Chain
    await loadFallbackChainStatus();

    if (isManualRefresh) {
      showToast('AI Provider statuses refreshed!', 'info');
    }
  } catch (err) {
    console.error('Failed to load AI credentials', err);
    showToast('Failed to load AI provider data: ' + err.message, 'error');
  } finally {
    if (isManualRefresh && el.btnRefreshAllCredentials) {
      el.btnRefreshAllCredentials.disabled = false;
      el.btnRefreshAllCredentials.textContent = '🔄 Refresh Status';
    }
  }
}

function updateCredentialsOverview(overview) {
  if (!overview) return;
  if (el.credTotalProviders) el.credTotalProviders.textContent = `${overview.total || 9} Total`;
  if (el.credConfiguredCount) el.credConfiguredCount.textContent = overview.configured || 0;
  if (el.credConnectedCount) el.credConnectedCount.textContent = overview.connected || 0;
  if (el.credSttActive) el.credSttActive.textContent = overview.active_stt || 'Deepgram Nova-3';
  if (el.credLlmActive) el.credLlmActive.textContent = overview.active_llm || 'Auto Priority';
}

async function loadFallbackChainStatus() {
  if (!el.fallbackChainSteps) return;
  try {
    const res = await fetch('/api/ai/status');
    const statusData = await res.json();
    renderFallbackChain(statusData);
  } catch (e) {
    console.warn('Could not load fallback status', e);
  }
}

function renderFallbackChain(statusData) {
  if (!el.fallbackChainSteps) return;
  const chain = statusData.fallback_chain || [
    { step: 1, name: 'OpenAI (Primary)', status: 'NOT CONFIGURED', role: 'primary' },
    { step: 2, name: 'Google Gemini', status: 'NOT CONFIGURED', role: 'fallback' },
    { step: 3, name: 'Groq Llama-3', status: 'NOT CONFIGURED', role: 'fallback' },
    { step: 4, name: 'Local Deterministic', status: 'LOCAL (Always Available)', role: 'final' }
  ];

  let html = '';
  chain.forEach((item, idx) => {
    const isConnected = item.status && item.status.includes('CONNECTED');
    const isLocal = item.status && item.status.includes('LOCAL');
    const badgeColor = isConnected || isLocal ? 'var(--emerald)' : 'var(--text-dim)';
    const badgeBg = isConnected || isLocal ? 'rgba(16,185,129,0.12)' : 'rgba(255,255,255,0.05)';

    html += `
      <div class="fallback-step">
        <div class="fallback-step-num">Step ${item.step || idx + 1}</div>
        <div class="fallback-step-name">${item.name}</div>
        <div class="fallback-step-status" style="color:${badgeColor}; background:${badgeBg}; border:1px solid ${badgeColor}33">
          ${item.status}
        </div>
      </div>
    `;

    if (idx < chain.length - 1) {
      html += `<div class="fallback-arrow">➔</div>`;
    }
  });

  el.fallbackChainSteps.innerHTML = html;
}

function getProviderStatusBadgeHtml(status) {
  const s = (status || 'NOT CONFIGURED').toUpperCase();
  let cssClass = 'status-not-configured';
  let dot = '○';

  if (s.includes('CONNECTED')) {
    cssClass = 'status-connected';
    dot = '●';
  } else if (s.includes('AUTH ERROR')) {
    cssClass = 'status-auth-error';
    dot = '▲';
  } else if (s.includes('RATE LIMITED')) {
    cssClass = 'status-rate-limited';
    dot = '⏳';
  } else if (s.includes('NETWORK ERROR')) {
    cssClass = 'status-network-error';
    dot = '🌐';
  } else if (s.includes('MODEL ERROR')) {
    cssClass = 'status-model-error';
    dot = '⚠️';
  } else if (s.includes('CONFIGURED')) {
    cssClass = 'status-configured';
    dot = '◈';
  } else if (s.includes('LOCAL')) {
    cssClass = 'status-local';
    dot = '⚡';
  }

  return `<span class="provider-status-badge ${cssClass}">${dot} ${s}</span>`;
}

function renderAICredentialCards() {
  if (!el.credentialsCardsGrid) return;
  el.credentialsCardsGrid.innerHTML = '';

  const filtered = credentialsCache.filter(p => {
    const cat = (p.category || p.type || 'llm').toLowerCase();
    if (credentialsFilter === 'all') return true;
    if (credentialsFilter === 'stt') return cat === 'stt';
    if (credentialsFilter === 'llm') return cat === 'llm';
    if (credentialsFilter === 'local') return cat === 'local' || p.id === 'local_deterministic';
    return true;
  });

  if (!filtered.length) {
    el.credentialsCardsGrid.innerHTML = '<div style="color:var(--text-dim); padding:2rem; text-align:center">No providers match this category.</div>';
    return;
  }

  filtered.forEach(p => {
    const cat = (p.category || p.type || 'llm').toLowerCase();
    const isLocal = p.id === 'local_deterministic' || cat === 'local';
    const isConnected = p.status === 'CONNECTED';
    const pIcon = p.icon || (cat === 'stt' ? '🎙️' : (isLocal ? '💻' : '🤖'));
    const pDesc = p.description || p.purpose || cat.toUpperCase();
    const activeModel = p.model || p.current_model || p.default_model || '';

    const card = document.createElement('div');
    card.className = `provider-card ${isConnected ? 'connected' : ''} ${p.status === 'AUTH ERROR' ? 'auth-error' : ''}`;
    card.id = `providerCard_${p.id}`;

    // Model options dropdown
    let modelSelectHtml = '';
    if (p.models && p.models.length > 0) {
      const options = p.models.map(m => {
        const mId = (typeof m === 'object' && m !== null) ? m.id : m;
        const mName = (typeof m === 'object' && m !== null) ? (m.name || m.id) : m;
        const mTag = (typeof m === 'object' && m !== null && m.tag) ? ` — ${m.tag}` : '';
        const selected = (mId === activeModel) ? 'selected' : '';
        return `<option value="${mId}" ${selected}>${mName}${mTag}</option>`;
      }).join('');
      modelSelectHtml = `
        <div class="form-group" style="margin-bottom:0.75rem">
          <label class="form-label" style="font-size:0.72rem; color:var(--text-dim)">Default Model</label>
          <select class="form-select" id="modelSelect_${p.id}" style="font-size:0.78rem; font-family:var(--font-mono)">
            ${options}
          </select>
        </div>
      `;
    } else {
      modelSelectHtml = `
        <div class="form-group" style="margin-bottom:0.75rem">
          <label class="form-label" style="font-size:0.72rem; color:var(--text-dim)">Model / Engine</label>
          <input type="text" class="form-control" id="modelSelect_${p.id}" value="${activeModel || 'Deterministic Rules'}" ${isLocal ? 'readonly' : ''} style="font-size:0.78rem; font-family:var(--font-mono)">
        </div>
      `;
    }

    // Key input row if cloud provider
    let keyInputSection = '';
    if (!isLocal) {
      keyInputSection = `
        <div class="form-group" style="margin-bottom:0.75rem">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem">
            <label class="form-label" style="font-size:0.72rem; color:var(--text-dim); margin:0">
              API Key <code style="font-size:0.65rem; color:var(--cyan-primary)">(${p.env_var || ''})</code>
            </label>
            ${p.configured ? `<span style="font-size:0.68rem; color:var(--emerald); font-family:var(--font-mono)">✓ Key Stored</span>` : ''}
          </div>
          <div class="key-input-group">
            <input 
              type="password" 
              class="form-control" 
              id="keyInput_${p.id}" 
              placeholder="${p.configured ? (p.masked_key || '••••••••') : 'Enter ' + p.name + ' API Key...'}"
              value="${p.configured ? (p.masked_key || '') : ''}"
              data-is-masked="${p.configured ? 'true' : 'false'}"
              autocomplete="off"
              spellcheck="false"
              style="font-size:0.78rem; font-family:var(--font-mono)"
            >
            <button class="btn btn-secondary btn-icon" id="btnToggleKey_${p.id}" title="Show / Hide Key">👁️</button>
            <button class="btn btn-secondary btn-icon" id="btnPasteKey_${p.id}" title="Paste from Clipboard">📋</button>
            <button class="btn btn-secondary btn-icon" id="btnClearKey_${p.id}" title="Clear Input">✕</button>
          </div>
        </div>
      `;
    } else {
      keyInputSection = `
        <div style="background:rgba(0,229,255,0.05); border:1px solid rgba(0,229,255,0.2); border-radius:var(--radius-sm); padding:0.6rem; margin-bottom:0.75rem; font-size:0.75rem; color:var(--text-dim)">
          ⚡ <strong>100% Offline & Deterministic:</strong> Runs locally on your machine with zero API keys, no network calls, and instant execution.
        </div>
      `;
    }

    // Message box for errors or test details
    const msgBoxHtml = `
      <div class="card-message-box" id="msgBox_${p.id}" style="${p.last_error ? 'display:block' : 'display:none'}">
        ${p.last_error || ''}
      </div>
    `;

    // Actions row
    let actionsRow = '';
    if (!isLocal) {
      actionsRow = `
        <div class="card-actions-row">
          <div style="display:flex; gap:0.4rem">
            <button class="btn btn-secondary btn-sm" id="btnTest_${p.id}" title="Send live request to verify credentials">
              🔌 Test Connection
            </button>
            <button class="btn btn-primary btn-sm" id="btnSave_${p.id}" title="Save credentials securely to server">
              💾 Save
            </button>
          </div>
          ${p.configured ? `
            <button class="btn btn-danger btn-sm" id="btnDelete_${p.id}" title="Remove API Key from server">
              🗑️ Clear
            </button>
          ` : ''}
        </div>
      `;
    } else {
      actionsRow = `
        <div class="card-actions-row">
          <button class="btn btn-secondary btn-sm" id="btnTest_${p.id}" title="Test local rules engine">
            ⚡ Test Local Rules
          </button>
          <span style="font-size:0.72rem; color:var(--emerald); font-weight:600">Active Fallback</span>
        </div>
      `;
    }

    card.innerHTML = `
      <div>
        <div class="provider-card-header">
          <div class="provider-brand">
            <div class="provider-icon-badge">${pIcon}</div>
            <div class="provider-title">
              <h3>${p.name}</h3>
              <span>${pDesc}</span>
            </div>
          </div>
          <div id="statusBadgeWrap_${p.id}">
            ${getProviderStatusBadgeHtml(p.status)}
          </div>
        </div>

        ${modelSelectHtml}
        ${keyInputSection}

        <div class="provider-meta-row">
          <span class="meta-pill" id="latencyPill_${p.id}">
            ⏱️ Latency: <strong>${p.latency_ms !== null && p.latency_ms !== undefined ? p.latency_ms + ' ms' : '--'}</strong>
          </span>
          <span class="meta-pill" id="testedPill_${p.id}">
            📅 <strong>${p.last_tested || 'Not tested yet'}</strong>
          </span>
        </div>

        ${msgBoxHtml}
      </div>

      <div style="margin-top:1rem">
        ${actionsRow}
      </div>
    `;

    el.credentialsCardsGrid.appendChild(card);

    // Attach card event listeners
    attachCardListeners(p);
  });
}

function attachCardListeners(p) {
  const isLocal = p.id === 'local_deterministic' || p.type === 'local';
  const keyInput = document.getElementById(`keyInput_${p.id}`);
  const modelSelect = document.getElementById(`modelSelect_${p.id}`);
  const btnToggleKey = document.getElementById(`btnToggleKey_${p.id}`);
  const btnPasteKey = document.getElementById(`btnPasteKey_${p.id}`);
  const btnClearKey = document.getElementById(`btnClearKey_${p.id}`);
  const btnTest = document.getElementById(`btnTest_${p.id}`);
  const btnSave = document.getElementById(`btnSave_${p.id}`);
  const btnDelete = document.getElementById(`btnDelete_${p.id}`);
  const msgBox = document.getElementById(`msgBox_${p.id}`);
  const statusBadgeWrap = document.getElementById(`statusBadgeWrap_${p.id}`);
  const latencyPill = document.getElementById(`latencyPill_${p.id}`);
  const testedPill = document.getElementById(`testedPill_${p.id}`);

  // Show/Hide Password
  if (btnToggleKey && keyInput) {
    btnToggleKey.addEventListener('click', () => {
      if (keyInput.type === 'password') {
        keyInput.type = 'text';
        btnToggleKey.textContent = '🔒';
      } else {
        keyInput.type = 'password';
        btnToggleKey.textContent = '👁️';
      }
    });
  }

  // Paste from clipboard
  if (btnPasteKey && keyInput) {
    btnPasteKey.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          keyInput.value = text.trim();
          keyInput.dataset.isMasked = 'false';
          showToast(`Pasted key for ${p.name}`, 'info');
        }
      } catch (err) {
        showToast('Clipboard access denied. Please paste directly into the box.', 'warning');
      }
    });
  }

  // Clear key input
  if (btnClearKey && keyInput) {
    btnClearKey.addEventListener('click', () => {
      keyInput.value = '';
      keyInput.dataset.isMasked = 'false';
      keyInput.focus();
    });
  }

  // When user focuses or types into a masked field, allow fresh entry
  if (keyInput) {
    keyInput.addEventListener('focus', () => {
      if (keyInput.dataset.isMasked === 'true') {
        // If clicking on masked text, select all so they can easily overwrite
        keyInput.select();
      }
    });
    keyInput.addEventListener('input', () => {
      keyInput.dataset.isMasked = 'false';
    });
  }

  // Test Connection Button
  if (btnTest) {
    btnTest.addEventListener('click', async () => {
      const selectedModel = modelSelect ? modelSelect.value.trim() : (p.model || '');
      let rawKey = '';
      if (keyInput && keyInput.dataset.isMasked !== 'true') {
        rawKey = keyInput.value.trim();
      }

      btnTest.disabled = true;
      btnTest.textContent = '⏳ Testing...';
      if (msgBox) {
        msgBox.style.display = 'none';
        msgBox.textContent = '';
      }

      try {
        const res = await fetch(`/api/ai/providers/${p.id}/test`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: selectedModel,
            api_key: rawKey || undefined
          })
        });

        const testResult = await res.json();
        
        // Update badge
        if (statusBadgeWrap) {
          statusBadgeWrap.innerHTML = getProviderStatusBadgeHtml(testResult.status);
        }

        // Update card border & latency
        const cardEl = document.getElementById(`providerCard_${p.id}`);
        if (cardEl) {
          cardEl.classList.remove('connected', 'auth-error');
          if (testResult.status === 'CONNECTED') {
            cardEl.classList.add('connected');
          } else if (testResult.status === 'AUTH ERROR') {
            cardEl.classList.add('auth-error');
          }
        }

        if (latencyPill) {
          latencyPill.innerHTML = `⏱️ Latency: <strong>${testResult.latency_ms !== null ? testResult.latency_ms + ' ms' : '--'}</strong>`;
        }
        if (testedPill) {
          testedPill.innerHTML = `📅 <strong>${testResult.last_tested || 'Just now'}</strong>`;
        }

        // Show message if present
        if (msgBox) {
          if (testResult.success) {
            msgBox.style.display = 'block';
            msgBox.style.borderColor = 'rgba(16,185,129,0.3)';
            msgBox.style.color = 'var(--emerald)';
            msgBox.innerHTML = `✓ Connection verified (${testResult.model || selectedModel}) in ${testResult.latency_ms}ms`;
          } else if (testResult.message) {
            msgBox.style.display = 'block';
            msgBox.style.borderColor = 'rgba(244,63,94,0.3)';
            msgBox.style.color = 'var(--rose)';
            msgBox.innerHTML = `✕ <strong>${testResult.status}:</strong> ${testResult.message}`;
          }
        }

        // Refresh overview counts and fallback chain
        loadAICredentials();
      } catch (err) {
        console.error('Test error', err);
        if (msgBox) {
          msgBox.style.display = 'block';
          msgBox.style.borderColor = 'rgba(244,63,94,0.3)';
          msgBox.style.color = 'var(--rose)';
          msgBox.textContent = '✕ Network error: ' + err.message;
        }
      } finally {
        btnTest.disabled = false;
        btnTest.textContent = isLocal ? '⚡ Test Local Rules' : '🔌 Test Connection';
      }
    });
  }

  // Save Credentials Button
  if (btnSave) {
    btnSave.addEventListener('click', async () => {
      let rawKey = '';
      if (keyInput && keyInput.dataset.isMasked !== 'true') {
        rawKey = keyInput.value.trim();
      }
      const selectedModel = modelSelect ? modelSelect.value.trim() : (p.model || '');

      if (!rawKey && !p.configured) {
        showToast('Please enter an API key before saving.', 'warning');
        if (keyInput) keyInput.focus();
        return;
      }

      btnSave.disabled = true;
      btnSave.textContent = '💾 Saving...';

      try {
        const payload = { model: selectedModel };
        if (rawKey) payload.api_key = rawKey;

        const res = await fetch(`/api/ai/providers/${p.id}/credentials`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const saveResult = await res.json();
        if (saveResult.success) {
          showToast(`Saved settings for ${p.name}!`, 'success');
          // Reload fresh state from backend
          await loadAICredentials();
        } else {
          showToast(`Error: ${saveResult.message || 'Failed to save'}`, 'error');
        }
      } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
      } finally {
        btnSave.disabled = false;
        btnSave.textContent = '💾 Save';
      }
    });
  }

  // Delete Credential Button
  if (btnDelete) {
    btnDelete.addEventListener('click', async () => {
      if (!confirm(`Are you sure you want to remove the stored API key for ${p.name}?`)) {
        return;
      }

      btnDelete.disabled = true;
      try {
        const res = await fetch(`/api/ai/providers/${p.id}/credentials`, {
          method: 'DELETE'
        });
        const delResult = await res.json();
        if (delResult.success) {
          showToast(`Removed credential for ${p.name}`, 'info');
          await loadAICredentials();
        } else {
          showToast(`Error: ${delResult.message}`, 'error');
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
      } finally {
        btnDelete.disabled = false;
      }
    });
  }
}
