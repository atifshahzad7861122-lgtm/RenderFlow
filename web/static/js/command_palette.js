/**
 * RenderFlow by AI With Atif — Command Palette & Keyboard Shortcuts System
 * =========================================================================
 * Provides fast keyboard-driven navigation (Ctrl+K), global shortcuts,
 * and searchable workstation commands.
 */

class RenderFlowCommandPalette {
  constructor() {
    this.isOpen = false;
    this.selectedIndex = 0;
    this.commands = [
      // Projects
      { group: 'Project', title: 'New Project', shortcut: 'Ctrl+N', action: () => this.triggerAction('new-project') },
      { group: 'Project', title: 'Open Project', shortcut: 'Ctrl+O', action: () => this.triggerAction('open-project') },
      { group: 'Project', title: 'Save Current Plan', shortcut: 'Ctrl+S', action: () => this.triggerAction('save-plan') },
      
      // Workflows & Media
      { group: 'Workflow', title: 'Upload Media & ZIPs', shortcut: '', action: () => this.triggerAction('open-upload') },
      { group: 'Workflow', title: 'Sync Audio & Timeline Beats', shortcut: '', action: () => this.triggerAction('auto-plan') },
      { group: 'Workflow', title: 'Switch to Timeline Editor', shortcut: '', action: () => this.switchTab('tab-studio') },
      { group: 'Workflow', title: 'Switch to Caption Styles', shortcut: '', action: () => this.triggerAction('open-caption-picker') },
      { group: 'Workflow', title: 'Switch to Video Showcase & QC', shortcut: '', action: () => this.switchTab('tab-showcase') },
      { group: 'Workflow', title: 'Switch to Transition Explorer', shortcut: '', action: () => this.switchTab('tab-transitions') },

      // Rendering & Output
      { group: 'Render', title: 'Start Video Render', shortcut: 'Ctrl+R', action: () => this.triggerAction('start-render') },
      { group: 'Render', title: 'Cancel Active Render', shortcut: '', action: () => this.triggerAction('cancel-render') },
      { group: 'Render', title: 'Output Resolution: 1080p Full HD', shortcut: '', action: () => this.setResolution('1080p') },
      { group: 'Render', title: 'Output Resolution: 1440p QHD', shortcut: '', action: () => this.setResolution('1440p') },
      { group: 'Render', title: 'Output Resolution: 4K UHD', shortcut: '', action: () => this.setResolution('4k') },
      
      // Themes
      { group: 'Themes', title: 'Open Theme Picker Popover', shortcut: '', action: () => this.triggerAction('open-theme-picker') },
      { group: 'Themes', title: 'Apply Theme: Cinematic Glass', shortcut: '', action: () => this.setTheme('glass') },
      { group: 'Themes', title: 'Apply Theme: Muddy Editorial', shortcut: '', action: () => this.setTheme('muddy') },
      { group: 'Themes', title: 'Apply Theme: Apple Spatial', shortcut: '', action: () => this.setTheme('apple') },
      { group: 'Themes', title: 'Apply Theme: F1 Telemetry', shortcut: '', action: () => this.setTheme('f1') },

      // System & Diagnostics
      { group: 'System', title: 'Workstation Preferences & Appearance Settings', shortcut: '', action: () => this.triggerAction('open-settings') },
      { group: 'System', title: 'Hardware Diagnostics & Benchmark', shortcut: '', action: () => this.triggerAction('open-hardware-diag') },
      { group: 'System', title: 'System Health Check', shortcut: '', action: () => this.triggerAction('open-system-health') },
      { group: 'System', title: 'API & AI Credentials Center', shortcut: '', action: () => this.triggerAction('open-credentials') },
      { group: 'System', title: 'Clear Engine Log Terminal', shortcut: '', action: () => this.triggerAction('clear-logs') },
      { group: 'System', title: 'About RenderFlow · AI With Atif', shortcut: '', action: () => this.triggerAction('open-about') },
    ];

    this.filteredCommands = [...this.commands];
    this.createDOM();
    this.bindShortcuts();
  }

  createDOM() {
    this.backdrop = document.createElement('div');
    this.backdrop.className = 'cmd-palette-backdrop';
    this.backdrop.id = 'cmdPaletteBackdrop';

    this.backdrop.innerHTML = `
      <div class="cmd-palette" onclick="event.stopPropagation()">
        <div class="cmd-input-wrap">
          <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="cmd-input" id="cmdPaletteInput" placeholder="Type a command or search actions..." autocomplete="off">
          <span style="font-size:0.75rem; color:var(--text-dim); font-family:var(--font-mono)">ESC</span>
        </div>
        <div class="cmd-results" id="cmdPaletteResults"></div>
      </div>
    `;

    this.backdrop.addEventListener('click', () => this.close());
    document.body.appendChild(this.backdrop);

    this.input = document.getElementById('cmdPaletteInput');
    this.resultsContainer = document.getElementById('cmdPaletteResults');

    this.input.addEventListener('input', (e) => this.onFilter(e.target.value));
    this.input.addEventListener('keydown', (e) => this.onKeyDown(e));
  }

  bindShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Toggle Command Palette (Ctrl+K or Cmd+K)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        this.toggle();
        return;
      }

      // Close on Escape
      if (e.key === 'Escape' && this.isOpen) {
        e.preventDefault();
        this.close();
        return;
      }

      // Other global shortcuts
      if ((e.ctrlKey || e.metaKey) && !this.isOpen) {
        if (e.key.toLowerCase() === 'n') {
          e.preventDefault();
          this.triggerAction('new-project');
        } else if (e.key.toLowerCase() === 's') {
          e.preventDefault();
          this.triggerAction('save-plan');
        } else if (e.key.toLowerCase() === 'r') {
          e.preventDefault();
          this.triggerAction('start-render');
        } else if (e.key.toLowerCase() === 'o') {
          e.preventDefault();
          this.triggerAction('open-project');
        }
      }
    });
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  open() {
    this.isOpen = true;
    this.backdrop.classList.add('open');
    this.input.value = '';
    this.onFilter('');
    this.input.focus();
  }

  close() {
    this.isOpen = false;
    this.backdrop.classList.remove('open');
  }

  onFilter(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
      this.filteredCommands = [...this.commands];
    } else {
      this.filteredCommands = this.commands.filter(cmd => 
        cmd.title.toLowerCase().includes(q) || cmd.group.toLowerCase().includes(q)
      );
    }
    this.selectedIndex = 0;
    this.renderResults();
  }

  renderResults() {
    this.resultsContainer.innerHTML = '';
    if (this.filteredCommands.length === 0) {
      this.resultsContainer.innerHTML = `
        <div style="padding:1.5rem; text-align:center; color:var(--text-dim); font-size:0.85rem">
          No matching commands found.
        </div>
      `;
      return;
    }

    let currentGroup = '';
    this.filteredCommands.forEach((cmd, idx) => {
      if (cmd.group !== currentGroup) {
        currentGroup = cmd.group;
        const groupEl = document.createElement('div');
        groupEl.className = 'cmd-group-label';
        groupEl.textContent = currentGroup;
        this.resultsContainer.appendChild(groupEl);
      }

      const item = document.createElement('div');
      item.className = `cmd-item ${idx === this.selectedIndex ? 'selected' : ''}`;
      item.innerHTML = `
        <span>${cmd.title}</span>
        ${cmd.shortcut ? `<span class="cmd-item-shortcut">${cmd.shortcut}</span>` : ''}
      `;
      item.addEventListener('click', () => {
        this.close();
        cmd.action();
      });
      this.resultsContainer.appendChild(item);
    });
  }

  onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.selectedIndex = (this.selectedIndex + 1) % this.filteredCommands.length;
      this.renderResults();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.selectedIndex = (this.selectedIndex - 1 + this.filteredCommands.length) % this.filteredCommands.length;
      this.renderResults();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (this.filteredCommands[this.selectedIndex]) {
        const cmd = this.filteredCommands[this.selectedIndex];
        this.close();
        cmd.action();
      }
    }
  }

  triggerAction(id) {
    const map = {
      'new-project': 'btnOpenUpload',
      'open-project': 'btnOpenUpload',
      'save-plan': 'btnSavePlan',
      'open-upload': 'btnOpenUpload',
      'auto-plan': 'btnAutoPlan',
      'open-caption-picker': 'btnSelectCaptionStyle',
      'start-render': 'btnStartRender',
      'cancel-render': 'btnCancelRender',
      'open-theme-picker': 'btnThemeSelector',
      'open-settings': 'btnSettingsModal',
      'open-credentials': 'btnHeaderCredentials',
      'clear-logs': 'btnClearLogs',
      'open-hardware-diag': 'btnHardwareDiag',
      'open-system-health': 'btnSystemHealth',
      'open-about': 'btnAboutModal'
    };
    const btnId = map[id];
    if (btnId) {
      const el = document.getElementById(btnId);
      if (el) el.click();
    }
  }

  switchTab(tabId) {
    const map = {
      'tab-studio': 'view-studio',
      'tab-render': 'view-render',
      'tab-showcase': 'view-studio',
      'tab-transitions': 'view-transitions'
    };
    if (window.switchView) {
      window.switchView(map[tabId] || tabId);
      return;
    }
    const tabBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
    if (tabBtn) tabBtn.click();
  }

  setResolution(res) {
    const sel = document.getElementById('renderResolutionSelect');
    if (sel) {
      sel.value = res;
      sel.dispatchEvent(new Event('change'));
      if (window.showToast) window.showToast(`Resolution set to ${res.toUpperCase()}`);
    }
  }

  setTheme(themeName) {
    if (window.setRenderFlowTheme) {
      window.setRenderFlowTheme(themeName);
    } else {
      document.documentElement.setAttribute('data-theme', themeName);
      localStorage.setItem('renderflow_theme', themeName);
      const badge = document.getElementById('themeCurrentBadge');
      if (badge) badge.textContent = themeName.toUpperCase();
      if (window.showToast) window.showToast(`Applied ${themeName.toUpperCase()} theme`);
    }
  }
}

// Instantiate Global Command Palette
window.renderflowCommandPalette = new RenderFlowCommandPalette();
