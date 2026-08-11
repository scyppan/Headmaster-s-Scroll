(() => {
  'use strict';

  const VERSION = 1;
  const POLL_DELAY_MS = 2000;
  const REQUEST_TIMEOUT_MS = 10000;
  const MAP_NATIVE_WIDTH = 3840;
  const MAP_NATIVE_HEIGHT = 2960;
  const MAP_ZOOM_STEP = 1.15;
  const MAP_MAX_ZOOM = 32;
  const MAP_PAN_STEP = 24;
  const DEFAULT_TOKEN_SCALE = 0.0055;
  const TOKEN_SCREEN_SIZES = [0, 0, 0, 0, 64, 60, 56, 52];
  const OVERVIEW_DOT_SCREEN_SIZES = [12, 11, 10, 9, 0, 0, 0, 0];
  const LABEL_SCREEN_SIZES = [15, 14, 13, 12, 11, 10.5, 10, 9.5];
  const LABEL_SCREEN_WIDTHS = [200, 185, 170, 155, 145, 135, 126, 118];
  const SECTIONS = [
    ['board', 'Game Board', '▦'],
    ['overview', 'Overview', '⌂'],
    ['attributes', 'Attributes', '◇'],
    ['spells', 'Spells', '✦'],
    ['proficiencies', 'Proficiencies', '✧'],
    ['potions', 'Potions', '⚗'],
    ['pets', 'Pets', '♞'],
    ['inventory', 'Inventory', '▣'],
    ['relationships', 'Relationships', '♡'],
    ['wounds', 'Wounds', '✚'],
    ['settings', 'Settings', '⚙']
  ];

  class GameBoardClient {
    constructor(options) {
      this.options = options;
      this.root = document.getElementById('gameboard');
      if (!this.root) throw new Error('Missing Game Board root: gameboard');
      this.apiBase = String(options.apiBase || '').replace(/\/$/, '');
      this.storageKey = options.storageKey || 'charms-check-game-board-invite';
      this.admissionStorageKey = `${this.storageKey}-admission`;
      this.layoutStorageKey = `${this.storageKey}-layout`;
      this.viewStorageKey = `${this.storageKey}-player-view`;
      this.invite = '';
      this.requestId = '';
      this.pollToken = '';
      this.socket = null;
      this.pollTimer = null;
      this.currentAnnouncement = '';
      this.state = 'unavailable';
      this.intentionalClose = false;
      this.requestingAdmission = false;
      this.playerId = '';
      this.characterId = '';
      this.assetCredential = '';
      this.board = { maps: [], actors: [], controlled_character_ids: [] };
      this.activeMapId = '';
      this.assetUrls = new Map();
      this.mapCameraStates = new Map();
      this.mapCameraSaveTimers = new Map();
      this.mapCameraDrag = null;
      this.mapResizeObserver = null;
      this.mapCameraFrame = 0;
      this.currentCampaignId = '';
      this.hydratedCampaignId = '';
      this.savedViewCampaignId = '';
      this.dragging = null;
      this.lastMovePreview = 0;
      this.activeSection = 'overview';
      this.chatMessages = [];
      this.cameraPreferenceKey = `${this.storageKey}-allow-headmaster-camera`;
      this.allowHeadmasterCamera = localStorage.getItem(this.cameraPreferenceKey) !== 'false';
      this.restoreViewState();
      this.render();
      this.bind();
      this.restoreLayout();
      this.openSection(this.activeSection);
    }

    render() {
      const navigation = SECTIONS.map(([id, label, icon]) => `
        <button type="button" class="ccgb-nav-item" data-section="${id}" title="${label}">
          <span class="ccgb-nav-icon" aria-hidden="true">${icon}</span>
          <span class="ccgb-nav-label">${label}</span>
        </button>`).join('');

      this.root.innerHTML = `
        <section class="ccgb-gate" data-ccgb="gate">
          <div class="ccgb-rule"></div>
          <h1>Game Board</h1>
          <p class="ccgb-status" data-ccgb="status">Preparing your invitation…</p>
          <div class="ccgb-spinner" data-ccgb="spinner" aria-hidden="true"></div>
          <button type="button" data-ccgb="retry" hidden>Request admission again</button>
          <div class="ccgb-rule"></div>
        </section>

        <section class="ccgb-board" data-ccgb="board" hidden>
          <header class="ccgb-toolbar">
            <button type="button" class="ccgb-icon-button" data-ccgb="toggle-nav" aria-label="Collapse profile menu" title="Collapse profile menu">☰</button>
            <div class="ccgb-brand">
              <strong>Game Board</strong>
              <span data-ccgb="session"></span>
            </div>
            <label class="ccgb-search">
              <span aria-hidden="true">⌕</span>
              <input type="search" data-ccgb="search" placeholder="Search this character" autocomplete="off">
            </label>
            <div class="ccgb-quality" title="Connection quality">
              <span class="ccgb-quality-dot" data-ccgb="quality-dot"></span>
              <span data-ccgb="quality-text">Measuring</span>
            </div>
            <button type="button" class="ccgb-icon-button" data-ccgb="toggle-details" aria-label="Toggle details" title="Toggle details">◫</button>
            <button type="button" class="ccgb-icon-button" data-ccgb="toggle-chat" aria-label="Toggle chat" title="Toggle chat">✉</button>
          </header>

          <div class="ccgb-workspace" data-ccgb="workspace">
            <nav class="ccgb-profile-nav" aria-label="Character profile sections">
              <div class="ccgb-sidebar-heading">Sections</div>
              <div class="ccgb-player-card">
                <span class="ccgb-avatar" data-ccgb="avatar">?</span>
                <span class="ccgb-player-name" data-ccgb="player">Player</span>
              </div>
              <div class="ccgb-nav-list">${navigation}</div>
            </nav>

            <main class="ccgb-main">
              <div class="ccgb-announcement" data-ccgb="announcement" hidden>
                <div>
                  <strong>Message from the Headmaster</strong>
                  <p data-ccgb="message"></p>
                </div>
                <button type="button" data-ccgb="acknowledge">Acknowledge</button>
              </div>
              <div class="ccgb-section-heading">
                <div>
                  <p class="ccgb-eyebrow">Character profile</p>
                  <h1 data-ccgb="section-title">Overview</h1>
                </div>
                <span class="ccgb-connected-mark">Connected</span>
              </div>
              <p class="ccgb-search-result" data-ccgb="search-result" hidden></p>
              <div class="ccgb-panel-grid" data-ccgb="section-content"></div>
            </main>

            <aside class="ccgb-details" aria-label="Character details">
              <div class="ccgb-panel-header">
                <div>
                  <p class="ccgb-eyebrow">At a glance</p>
                  <h2>Details</h2>
                </div>
                <button type="button" class="ccgb-close-panel" data-ccgb="close-details" aria-label="Collapse details">×</button>
              </div>
              <dl class="ccgb-detail-list">
                <div><dt>Character</dt><dd data-ccgb="detail-player">—</dd></div>
                <div><dt>Current area</dt><dd data-ccgb="detail-section">Overview</dd></div>
                <div><dt>Status</dt><dd>Available</dd></div>
                <div><dt>School</dt><dd>Not yet assigned</dd></div>
              </dl>
              <details class="ccgb-mini-panel" open>
                <summary>Quick notes</summary>
                <p>Character details and game tools will appear here as each section is connected to shared data.</p>
              </details>
            </aside>

            <aside class="ccgb-chat" aria-label="Session chat">
              <button type="button" class="ccgb-chat-rail" data-ccgb="chat-rail" aria-label="Expand chat" title="Expand chat">
                <span aria-hidden="true">✉</span><strong>Chat</strong>
              </button>
              <div class="ccgb-chat-content">
                <div class="ccgb-panel-header">
                  <div>
                    <p class="ccgb-eyebrow">Live room</p>
                    <h2>Chat</h2>
                  </div>
                  <button type="button" class="ccgb-collapse-panel" data-ccgb="close-chat" aria-label="Collapse chat" title="Collapse chat">›</button>
                </div>
                <div class="ccgb-chat-messages" data-ccgb="chat-messages" aria-live="polite"></div>
                <form class="ccgb-chat-form" data-ccgb="chat-form">
                  <label for="ccgb-chat-input">Message the room</label>
                  <div>
                    <input id="ccgb-chat-input" data-ccgb="chat-input" maxlength="500" placeholder="Write a message…" autocomplete="off">
                    <button type="submit">Send</button>
                  </div>
                </form>
              </div>
            </aside>
          </div>
        </section>`;
    }

    bind() {
      this.element('acknowledge').addEventListener('click', () => this.acknowledge());
      this.element('retry').addEventListener('click', () => this.requestAdmission());
      this.element('toggle-nav').addEventListener('click', () => this.toggleRegion('nav'));
      this.element('toggle-details').addEventListener('click', () => this.toggleRegion('details'));
      this.element('toggle-chat').addEventListener('click', () => this.toggleRegion('chat'));
      this.element('close-details').addEventListener('click', () => this.toggleRegion('details', true));
      this.element('close-chat').addEventListener('click', () => this.toggleRegion('chat', true));
      this.element('chat-rail').addEventListener('click', () => this.toggleRegion('chat'));
      this.element('search').addEventListener('input', event => this.search(event.target.value));
      this.element('chat-form').addEventListener('submit', event => {
        event.preventDefault();
        this.sendChat();
      });
      this.root.querySelectorAll('[data-section]').forEach(button => {
        button.addEventListener('click', () => this.openSection(button.dataset.section));
      });
      window.addEventListener('keydown', event => {
        if (this.activeSection === 'board' && (event.ctrlKey || event.metaKey) && event.key === '0') {
          event.preventDefault();
          this.resetMapCamera(this.activeMapId);
        }
      });
      window.addEventListener('blur', () => { this.mapCameraDrag = null; });
      window.addEventListener('pagehide', () => {
        this.saveViewState();
        this.mapCameraSaveTimers.forEach(timer => clearTimeout(timer));
        this.mapCameraSaveTimers.clear();
        this.mapCameraStates.forEach((_state, mapId) => this.saveCameraNow(mapId));
      });
    }

    element(name) {
      return this.root.querySelector(`[data-ccgb="${name}"]`);
    }

    start() {
      if (this.options.preview) {
        this.showPreview(this.options.preview);
        return;
      }
      if (!this.apiBase || this.apiBase === 'https://game.example.com') {
        this.show('unavailable', 'The Game Board address has not been configured yet.');
        return;
      }
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      this.invite = fragment.get('invite') || sessionStorage.getItem(this.storageKey) || '';
      if (!this.invite) {
        this.show('invalid', 'This page requires a private Game Board invitation link.');
        return;
      }
      sessionStorage.setItem(this.storageKey, this.invite);
      history.replaceState(null, '', window.location.pathname + window.location.search);
      const savedAdmission = this.loadAdmission();
      if (savedAdmission && savedAdmission.invite === this.invite) {
        this.requestId = savedAdmission.requestId;
        this.pollToken = savedAdmission.pollToken;
        this.show('waiting', 'Restoring your admission request…', { busy: true });
        this.pollAdmission();
        return;
      }
      this.requestAdmission();
    }

    show(state, message, { busy = false, retry = false, connected = false } = {}) {
      this.state = state;
      this.root.dataset.state = state;
      this.element('status').textContent = message;
      this.element('spinner').classList.toggle('is-off', !busy);
      this.element('retry').hidden = !retry;
      this.element('gate').hidden = connected;
      this.element('board').hidden = !connected;
    }

    async requestJson(url, options = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          const error = new Error(body.detail || `The Game Board returned ${response.status}.`);
          error.status = response.status;
          throw error;
        }
        return body;
      } catch (error) {
        if (error.name === 'AbortError') throw new Error('The Game Board did not respond in time.');
        if (error instanceof TypeError) {
          throw new Error('The Game Board host cannot be reached. Ask the Headmaster to check Game Board and the Tailscale Funnel.');
        }
        throw error;
      } finally {
        clearTimeout(timeout);
      }
    }

    async requestAdmission() {
      if (this.requestingAdmission) return;
      this.requestingAdmission = true;
      clearTimeout(this.pollTimer);
      if (this.socket) {
        this.intentionalClose = true;
        this.socket.close();
        this.socket = null;
      }
      this.show('waiting', 'Asking the Headmaster for permission to enter…', { busy: true });
      try {
        const result = await this.requestJson(`${this.apiBase}/v1/admissions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ invite_token: this.invite })
        });
        this.requestId = result.request_id;
        this.pollToken = result.poll_token;
        this.saveAdmission();
        this.pollAdmission();
      } catch (error) {
        const state = this.errorState(error);
        this.show(state, this.errorMessage(error), { retry: !['revoked', 'expired'].includes(state) });
      } finally {
        this.requestingAdmission = false;
      }
    }

    async pollAdmission() {
      try {
        const result = await this.requestJson(
          `${this.apiBase}/v1/admissions/${encodeURIComponent(this.requestId)}`,
          { headers: { Authorization: `Bearer ${this.pollToken}` } }
        );
        if (result.status === 'pending') {
          this.show('waiting', 'Waiting for the Headmaster to approve this connection…', { busy: true });
          this.pollTimer = setTimeout(() => this.pollAdmission(), POLL_DELAY_MS);
        } else if (result.status === 'approved') {
          this.connect(result.ticket);
        } else if (result.status === 'denied') {
          this.clearAdmission();
          this.show('denied', 'The Headmaster denied this connection.', { retry: true });
        } else if (result.status === 'revoked') {
          this.clearAdmission();
          this.show('revoked', 'This invitation has been revoked.');
        } else if (result.status === 'expired') {
          this.clearAdmission();
          this.show('expired', 'This game session has expired.');
        } else if (result.status === 'disconnected') {
          this.clearAdmission();
          this.show('waiting', 'Returning you to the Headmaster’s approval queue…', { busy: true });
          this.pollTimer = setTimeout(() => this.requestAdmission(), 750);
        } else if (result.status === 'connected') {
          this.show('waiting', 'Finishing the previous connection before requesting approval again…', { busy: true });
          this.pollTimer = setTimeout(() => this.pollAdmission(), 1000);
        } else {
          this.show('waiting', `Admission status: ${result.status}`, { busy: true });
          this.pollTimer = setTimeout(() => this.pollAdmission(), POLL_DELAY_MS);
        }
      } catch (error) {
        if (error.status === 403 || error.status === 404) {
          this.clearAdmission();
          this.show('waiting', 'Refreshing your admission request…', { busy: true });
          this.pollTimer = setTimeout(() => this.requestAdmission(), 750);
          return;
        }
        this.show(this.errorState(error), this.errorMessage(error), { retry: true });
      }
    }

    connect(ticket) {
      this.show('connecting', 'Permission granted. Opening the Game Board…', { busy: true });
      const wsBase = this.apiBase.replace(/^http/i, 'ws');
      this.intentionalClose = false;
      this.hydratedCampaignId = '';
      this.socket = new WebSocket(`${wsBase}/v1/session?ticket=${encodeURIComponent(ticket)}`);
      const connectionTimer = setTimeout(() => {
        if (this.socket && this.socket.readyState === WebSocket.CONNECTING) this.socket.close();
      }, 15000);
      this.socket.addEventListener('open', () => clearTimeout(connectionTimer));
      this.socket.addEventListener('message', event => this.receive(event));
      this.socket.addEventListener('error', () => {
        if (this.state === 'connecting') {
          this.show('unavailable', 'The live connection could not be opened.', { retry: true });
        }
      });
      this.socket.addEventListener('close', () => {
        clearTimeout(connectionTimer);
        this.releaseAssets();
        if (this.intentionalClose) {
          this.intentionalClose = false;
          return;
        }
        if (!['revoked', 'expired'].includes(this.state)) {
          this.setQuality('disconnected', 'Disconnected');
          this.show('disconnected', 'Connection lost. Request admission to return to the room.', { retry: true });
        }
      });
    }

    receive(event) {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (_) {
        return;
      }
      if (!message || message.v !== VERSION || typeof message.type !== 'string') return;
      if (message.type === 'connection_accepted') {
        this.playerId = message.player_id || '';
        this.characterId = message.character_id || '';
        this.assetCredential = message.asset_credential || '';
        this.element('player').textContent = message.player || 'Player';
        this.element('detail-player').textContent = message.player || 'Player';
        this.element('avatar').textContent = (message.player || '?').trim().charAt(0).toUpperCase();
        this.element('session').textContent = message.session || '';
        this.show('connected', 'You are connected.', { connected: true });
        this.setQuality('good', 'Connected');
      } else if (message.type === 'heartbeat') {
        this.send({ v: VERSION, type: 'heartbeat_ack', id: message.id });
      } else if (message.type === 'connection_quality') {
        const latency = Number.isFinite(Number(message.latency_ms))
          ? `${Math.round(Number(message.latency_ms))} ms`
          : 'Measuring';
        this.setQuality(message.quality || 'fair', latency);
      } else if (message.type === 'announcement') {
        this.currentAnnouncement = message.id;
        this.element('message').textContent = message.message || '';
        this.element('announcement').hidden = false;
      } else if (message.type === 'chat_history') {
        this.chatMessages = Array.isArray(message.messages) ? message.messages.slice(-100) : [];
        this.renderChat();
      } else if (message.type === 'chat_message' && message.message) {
        if (!this.chatMessages.some(item => item.id === message.message.id)) {
          this.chatMessages.push(message.message);
          this.chatMessages = this.chatMessages.slice(-100);
          this.renderChat();
        }
      } else if (message.type === 'identity_updated') {
        const player = message.player || 'Player';
        this.characterId = message.character_id || '';
        this.element('player').textContent = player;
        this.element('detail-player').textContent = player;
        this.element('avatar').textContent = player.trim().charAt(0).toUpperCase() || '?';
      } else if (message.type === 'board_snapshot' && message.board) {
        this.board = message.board;
        const campaignId = String(this.board.campaign_id || '');
        const firstCampaignSnapshot = campaignId !== this.hydratedCampaignId;
        if (firstCampaignSnapshot && this.savedViewCampaignId && campaignId !== this.savedViewCampaignId) {
          this.mapCameraStates.clear();
          this.activeMapId = '';
        }
        this.currentCampaignId = campaignId;
        (this.board.maps || []).forEach(map => {
          if (!this.mapCameraStates.has(map.record_id) && map.camera) {
            this.mapCameraStates.set(map.record_id, this.normalizedCamera(map.camera));
          }
        });
        const mapIds = new Set((this.board.maps || []).map(item => item.record_id));
        const controlled = (this.board.actors || []).find(actor =>
          (this.board.controlled_character_ids || []).includes(actor.actor_id)
        );
        if (!mapIds.has(this.activeMapId)) {
          if (mapIds.has(this.board.active_map_id)) this.activeMapId = this.board.active_map_id;
          else if (controlled && mapIds.has(controlled.map_id)) this.activeMapId = controlled.map_id;
          else this.activeMapId = this.board.maps?.[0]?.record_id || '';
        }
        this.hydratedCampaignId = campaignId;
        this.saveViewState();
        if (this.activeSection === 'board') this.renderBoardView();
      } else if (message.type === 'board_move_preview') {
        const actor = (this.board.actors || []).find(item => item.actor_id === message.person_id);
        if (actor) {
          actor.map_id = message.map_id;
          actor.x = Number(message.x);
          actor.y = Number(message.y);
          if (this.activeSection === 'board') this.positionBoardActors();
        }
      } else if (message.type === 'board_camera_focus' && message.camera) {
        if (!this.allowHeadmasterCamera) {
          this.showChatNotice('The Headmaster requested camera focus; your camera-control setting blocked it.');
          return;
        }
        const mapId = String(message.map_id || '');
        if (mapId) {
          this.activeMapId = mapId;
          this.mapCameraStates.set(mapId, this.normalizedCamera(message.camera));
          this.saveViewState();
          if (this.activeSection !== 'board') this.openSection('board');
          else this.renderBoardView();
          this.queueCameraSave(mapId, 0);
          this.showBoardNotice('The Headmaster focused your view here.');
        }
      } else if (message.type === 'access_revoked') {
        this.releaseAssets();
        this.show('revoked', message.message || 'Access was revoked.');
      } else if (message.type === 'session_expired') {
        this.releaseAssets();
        this.show('expired', message.message || 'The session has ended.');
      } else if (message.type === 'server_error') {
        const errorMessage = message.message || 'The message could not be sent.';
        if (this.activeSection === 'board') this.showBoardNotice(errorMessage);
        else this.showChatNotice(errorMessage);
      }
    }

    sendChat() {
      const input = this.element('chat-input');
      const message = input.value.trim();
      if (!message) return;
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        this.showChatNotice('Chat is unavailable while disconnected.');
        return;
      }
      this.send({ v: VERSION, type: 'chat_message', message });
      input.value = '';
      input.focus();
    }

    renderChat() {
      const container = this.element('chat-messages');
      container.replaceChildren();
      if (!this.chatMessages.length) {
        const empty = document.createElement('p');
        empty.className = 'ccgb-chat-empty';
        empty.textContent = 'No messages yet. Say hello to the room.';
        container.appendChild(empty);
        return;
      }
      this.chatMessages.forEach(message => {
        const article = document.createElement('article');
        const ownMessage = Boolean(this.playerId && message.sender_id === this.playerId);
        article.className = `ccgb-chat-message ${message.sender_role === 'headmaster' ? 'is-headmaster' : ''} ${ownMessage ? 'is-own' : ''}`;
        const heading = document.createElement('div');
        const name = document.createElement('strong');
        name.textContent = message.sender_name || 'Player';
        const time = document.createElement('time');
        const sentAt = new Date(message.sent_at || '');
        time.textContent = Number.isNaN(sentAt.valueOf()) ? '' : sentAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        heading.append(name, time);
        const text = document.createElement('p');
        text.textContent = message.text || '';
        article.append(heading, text);
        container.appendChild(article);
      });
      container.scrollTop = container.scrollHeight;
    }

    showChatNotice(text) {
      const container = this.element('chat-messages');
      const notice = document.createElement('p');
      notice.className = 'ccgb-chat-notice';
      notice.textContent = text;
      container.appendChild(notice);
      container.scrollTop = container.scrollHeight;
    }

    acknowledge() {
      if (!this.currentAnnouncement) return;
      this.send({ v: VERSION, type: 'acknowledgement', announcement_id: this.currentAnnouncement });
      this.element('announcement').hidden = true;
      this.currentAnnouncement = '';
    }

    send(message) {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify(message));
      }
    }

    setQuality(level, text) {
      this.element('quality-dot').className = `ccgb-quality-dot ${level}`;
      this.element('quality-text').textContent = text;
    }

    openSection(section) {
      const item = SECTIONS.find(([id]) => id === section) || SECTIONS[0];
      this.activeSection = item[0];
      this.saveViewState();
      this.root.classList.toggle('ccgb-board-active', item[0] === 'board');
      this.root.querySelectorAll('[data-section]').forEach(button => {
        const active = button.dataset.section === this.activeSection;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-current', active ? 'page' : 'false');
      });
      this.element('section-title').textContent = item[1];
      this.element('detail-section').textContent = item[1];
      if (item[0] === 'board') {
        this.renderBoardView();
        this.search(this.element('search').value);
        return;
      }
      if (this.mapResizeObserver) {
        this.mapResizeObserver.disconnect();
        this.mapResizeObserver = null;
      }
      const content = this.element('section-content');
      content.className = 'ccgb-panel-grid';
      if (item[0] === 'settings') {
        content.innerHTML = `
          <details class="ccgb-content-panel" open>
            <summary>Game Board settings</summary>
            <div>
              <label class="ccgb-setting-toggle">
                <input type="checkbox" data-ccgb-camera-lock>
                <span>Don't allow Headmaster to control my camera</span>
              </label>
              <p>You can still pan and zoom normally. When enabled, Headmaster focus requests will be ignored.</p>
            </div>
          </details>`;
        const cameraLock = content.querySelector('[data-ccgb-camera-lock]');
        cameraLock.checked = !this.allowHeadmasterCamera;
        cameraLock.addEventListener('change', () => {
          this.allowHeadmasterCamera = !cameraLock.checked;
          localStorage.setItem(this.cameraPreferenceKey, String(this.allowHeadmasterCamera));
        });
        this.search(this.element('search').value);
        return;
      }
      content.innerHTML = `
        <details class="ccgb-content-panel" open>
          <summary>${item[1]} summary</summary>
          <div><p>This area is ready for ${item[1].toLowerCase()} information from the shared character data.</p></div>
        </details>
        <details class="ccgb-content-panel" open>
          <summary>Session tools</summary>
          <div><p>Live tools and Headmaster-directed interactions for this section will appear here.</p></div>
        </details>
        <details class="ccgb-content-panel">
          <summary>Notes</summary>
          <div><p>Additional character notes can be organized here.</p></div>
        </details>`;
      this.search(this.element('search').value);
    }

    async assetUrl(assetId) {
      if (!assetId || !this.assetCredential) return '';
      if (this.assetUrls.has(assetId)) return this.assetUrls.get(assetId);
      const response = await fetch(
        `${this.apiBase}/v1/assets/${encodeURIComponent(assetId)}`,
        { headers: { Authorization: `Bearer ${this.assetCredential}` } }
      );
      if (!response.ok) throw new Error(`Private board image returned ${response.status}.`);
      const url = URL.createObjectURL(await response.blob());
      this.assetUrls.set(assetId, url);
      return url;
    }

    releaseAssets() {
      this.assetUrls.forEach(url => URL.revokeObjectURL(url));
      this.assetUrls.clear();
      this.assetCredential = '';
    }

    renderBoardView() {
      if (this.mapResizeObserver) {
        this.mapResizeObserver.disconnect();
        this.mapResizeObserver = null;
      }
      const content = this.element('section-content');
      content.replaceChildren();
      content.className = 'ccgb-panel-grid ccgb-board-content';
      const maps = Array.isArray(this.board.maps) ? this.board.maps : [];
      if (!maps.length) {
        const empty = document.createElement('div');
        empty.className = 'ccgb-board-empty';
        empty.textContent = 'The Headmaster has not opened a map for players yet.';
        content.appendChild(empty);
        return;
      }

      const shell = document.createElement('section');
      shell.className = 'ccgb-map-shell';
      const tabs = document.createElement('div');
      tabs.className = 'ccgb-map-tabs';
      maps.forEach(map => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = map.name || 'Map';
        button.className = map.record_id === this.activeMapId ? 'is-active' : '';
        button.addEventListener('click', () => {
          this.activeMapId = map.record_id;
          this.saveViewState();
          this.renderBoardView();
          this.queueCameraSave(map.record_id, 100);
        });
        tabs.appendChild(button);
      });
      const viewport = document.createElement('div');
      viewport.className = 'ccgb-map-viewport';
      viewport.dataset.ccgbMapId = this.activeMapId;
      const notice = document.createElement('div');
      notice.className = 'ccgb-map-notice';
      notice.hidden = true;
      viewport.appendChild(notice);
      const stage = document.createElement('div');
      stage.className = 'ccgb-map-stage';
      const map = maps.find(item => item.record_id === this.activeMapId) || maps[0];
      this.activeMapId = map.record_id;
      const metadata = map.asset || null;
      if (metadata?.asset_id) {
        const image = document.createElement('img');
        image.alt = map.name || 'Game map';
        image.draggable = false;
        this.assetUrl(metadata.asset_id)
          .then(url => { if (stage.isConnected) image.src = url; })
          .catch(error => this.showChatNotice(error.message));
        stage.appendChild(image);
      } else {
        const empty = document.createElement('p');
        empty.className = 'ccgb-map-image-missing';
        empty.textContent = 'This map has no available image.';
        stage.appendChild(empty);
      }
      viewport.appendChild(stage);
      shell.append(tabs, viewport);
      content.appendChild(shell);

      this.createBoardRegionLayer(stage, map);
      (this.board.actors || [])
        .filter(actor => actor.map_id === this.activeMapId)
        .forEach(actor => this.createBoardActor(stage, actor));
      this.createBoardObscurationLayer(stage, map);
      this.setupMapCamera(
        viewport,
        stage,
        map.record_id,
        Number(map.token_scale || DEFAULT_TOKEN_SCALE),
        map.camera
      );
    }

    createBoardRegionLayer(stage, map) {
      const regions = Array.isArray(map.regions) ? map.regions : [];
      if (!regions.length) return;
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.classList.add('ccgb-map-regions');
      svg.setAttribute('viewBox', '0 0 1000 1000');
      svg.setAttribute('preserveAspectRatio', 'none');
      regions.forEach(region => {
        if (!Array.isArray(region.points) || region.points.length < 3) return;
        const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        polygon.setAttribute('points', region.points.map(point => `${Number(point.x) * 1000},${Number(point.y) * 1000}`).join(' '));
        polygon.dataset.regionId = region.record_id || '';
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = region.hover_text || region.name || 'Map area';
        polygon.appendChild(title);
        if (region.behavior_type === 'travel') {
          polygon.classList.add('is-travel');
          polygon.addEventListener('click', event => this.activateTravelRegion(event, stage, map, region));
        }
        svg.appendChild(polygon);
      });
      stage.appendChild(svg);
    }

    createBoardObscurationLayer(stage, map) {
      const obscurations = Array.isArray(map.obscurations) ? map.obscurations : [];
      if (!obscurations.length) return;
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.classList.add('ccgb-map-obscurations');
      svg.setAttribute('viewBox', '0 0 1000 1000');
      svg.setAttribute('preserveAspectRatio', 'none');
      obscurations.forEach(obscuration => {
        if (!Array.isArray(obscuration.points) || obscuration.points.length < 3) return;
        const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        polygon.setAttribute('points', obscuration.points.map(point => `${Number(point.x) * 1000},${Number(point.y) * 1000}`).join(' '));
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = 'This area is obscured.';
        polygon.appendChild(title);
        svg.appendChild(polygon);
      });
      stage.appendChild(svg);
    }

    activateTravelRegion(event, stage, map, region) {
      event.preventDefault();
      event.stopPropagation();
      if (!region.target_available) {
        this.showBoardNotice('This area is off limits for now, speak with your headmaster.');
        return;
      }
      const actor = (this.board.actors || []).find(item =>
        item.map_id === map.record_id && (this.board.controlled_character_ids || []).includes(item.actor_id)
      );
      if (!actor) {
        this.showBoardNotice('You do not control a character on this map.');
        return;
      }
      const bounds = stage.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width)));
      const y = Math.max(0, Math.min(1, (event.clientY - bounds.top) / Math.max(1, bounds.height)));
      this.send({
        v: VERSION,
        type: 'board_travel',
        person_id: actor.actor_id,
        source_map_id: map.record_id,
        region_id: region.record_id,
        x,
        y
      });
    }

    showBoardNotice(message) {
      const notice = this.root.querySelector('.ccgb-map-notice');
      if (!notice) {
        this.showChatNotice(message);
        return;
      }
      notice.textContent = message;
      notice.hidden = false;
      clearTimeout(this.boardNoticeTimer);
      this.boardNoticeTimer = setTimeout(() => { if (notice.isConnected) notice.hidden = true; }, 5000);
    }

    normalizedCamera(camera) {
      const scale = Math.max(1, Math.min(MAP_MAX_ZOOM, Number(camera?.zoom || camera?.scale || 1)));
      return {
        scale,
        zoomClicks: Math.max(0, Math.round(Math.log(scale) / Math.log(MAP_ZOOM_STEP))),
        centerX: Math.max(0, Math.min(1, Number(camera?.center_x ?? camera?.centerX ?? 0.5))),
        centerY: Math.max(0, Math.min(1, Number(camera?.center_y ?? camera?.centerY ?? 0.5))),
        x: 0,
        y: 0
      };
    }

    cameraState(mapId, initialCamera = null) {
      if (!this.mapCameraStates.has(mapId)) {
        this.mapCameraStates.set(mapId, this.normalizedCamera(initialCamera));
      }
      return this.mapCameraStates.get(mapId);
    }

    syncCameraCenter(state, stage) {
      const scale = this.mapStageScale(stage, state);
      state.centerX = Math.max(0, Math.min(
        1, 0.5 - Number(state.x || 0) / Math.max(1, stage.offsetWidth * scale)
      ));
      state.centerY = Math.max(0, Math.min(
        1, 0.5 - Number(state.y || 0) / Math.max(1, stage.offsetHeight * scale)
      ));
    }

    mapStageScale(stage, state) {
      const fitScale = Math.max(0.0001, Number(stage.dataset.fitScale || 1));
      return fitScale * Math.max(1, Number(state.scale || 1));
    }

    zoomTier(state) {
      const clicks = Math.max(0, Number.isFinite(state.zoomClicks)
        ? state.zoomClicks
        : Math.round(Math.log(Math.max(1, state.scale)) / Math.log(MAP_ZOOM_STEP)));
      return Math.max(0, Math.min(TOKEN_SCREEN_SIZES.length - 1, Math.floor(clicks / 3)));
    }

    setupMapCamera(viewport, stage, mapId, tokenScale = DEFAULT_TOKEN_SCALE, initialCamera = null) {
      this.cameraState(mapId, initialCamera);
      const sizeStage = () => {
        cancelAnimationFrame(this.mapCameraFrame);
        this.mapCameraFrame = requestAnimationFrame(() => {
          if (!viewport.isConnected || !stage.isConnected) return;
          const availableWidth = Math.max(1, viewport.clientWidth);
          const availableHeight = Math.max(1, viewport.clientHeight);
          const fitScale = Math.min(
            availableWidth / MAP_NATIVE_WIDTH,
            availableHeight / MAP_NATIVE_HEIGHT
          );
          stage.style.width = `${MAP_NATIVE_WIDTH}px`;
          stage.style.height = `${MAP_NATIVE_HEIGHT}px`;
          stage.dataset.fitScale = String(fitScale);
          const tokenSize = MAP_NATIVE_WIDTH * Math.max(0.002, Math.min(0.03, tokenScale));
          stage.dataset.tokenSize = String(tokenSize);
          stage.style.setProperty('--map-token-size', `${tokenSize}px`);
          stage.style.setProperty('--map-dot-size', `${tokenSize * 0.9}px`);
          this.applyMapCamera(viewport, stage, mapId);
        });
      };
      this.mapResizeObserver = new ResizeObserver(sizeStage);
      this.mapResizeObserver.observe(viewport);
      sizeStage();
      viewport.addEventListener('wheel', event => {
        event.preventDefault();
        const state = this.cameraState(mapId);
        const direction = -Math.sign(event.deltaY || event.deltaX || 0);
        if (!direction) return;
        if (event.ctrlKey || event.metaKey) {
          const bounds = viewport.getBoundingClientRect();
          const cursorX = event.clientX - (bounds.left + bounds.width / 2);
          const cursorY = event.clientY - (bounds.top + bounds.height / 2);
          const currentStageScale = this.mapStageScale(stage, state);
          const worldX = (cursorX - state.x) / currentStageScale;
          const worldY = (cursorY - state.y) / currentStageScale;
          const maxClicks = Math.floor(Math.log(MAP_MAX_ZOOM) / Math.log(MAP_ZOOM_STEP));
          state.zoomClicks = Math.max(0, Math.min(maxClicks, Number(state.zoomClicks || 0) + direction));
          const next = Math.max(1, Math.min(MAP_MAX_ZOOM, MAP_ZOOM_STEP ** state.zoomClicks));
          const nextStageScale = Math.max(0.0001, Number(stage.dataset.fitScale || 1)) * next;
          state.x = cursorX - worldX * nextStageScale;
          state.y = cursorY - worldY * nextStageScale;
          state.scale = next;
        } else if (event.altKey) {
          state.x += direction * MAP_PAN_STEP;
        } else {
          state.y += direction * MAP_PAN_STEP;
        }
        this.syncCameraCenter(state, stage);
        this.applyMapCamera(viewport, stage, mapId);
        this.queueCameraSave(mapId);
      }, { passive: false });
      viewport.addEventListener('pointerdown', event => {
        if (event.button !== 1) return;
        event.preventDefault();
        viewport.setPointerCapture(event.pointerId);
        viewport.classList.add('is-camera-panning');
        const state = this.cameraState(mapId);
        this.mapCameraDrag = { mapId, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, x: state.x, y: state.y };
      });
      viewport.addEventListener('pointermove', event => {
        if (!this.mapCameraDrag || this.mapCameraDrag.pointerId !== event.pointerId) return;
        const state = this.cameraState(mapId);
        state.x = this.mapCameraDrag.x + event.clientX - this.mapCameraDrag.startX;
        state.y = this.mapCameraDrag.y + event.clientY - this.mapCameraDrag.startY;
        this.syncCameraCenter(state, stage);
        this.applyMapCamera(viewport, stage, mapId);
      });
      const endPan = event => {
        if (this.mapCameraDrag?.pointerId !== event.pointerId) return;
        this.mapCameraDrag = null;
        viewport.classList.remove('is-camera-panning');
        if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
        this.queueCameraSave(mapId, 100);
      };
      viewport.addEventListener('pointerup', endPan);
      viewport.addEventListener('pointercancel', endPan);
      viewport.addEventListener('lostpointercapture', () => {
        this.mapCameraDrag = null;
        viewport.classList.remove('is-camera-panning');
      });
      viewport.addEventListener('contextmenu', event => {
        if (this.mapCameraDrag) event.preventDefault();
      });
    }

    applyMapCamera(viewport, stage, mapId) {
      const state = this.cameraState(mapId);
      const stageScale = this.mapStageScale(stage, state);
      state.x = (0.5 - Number(state.centerX ?? 0.5)) * stage.offsetWidth * stageScale;
      state.y = (0.5 - Number(state.centerY ?? 0.5)) * stage.offsetHeight * stageScale;
      const boundX = Math.max(0, (stage.offsetWidth * stageScale - viewport.clientWidth) / 2);
      const boundY = Math.max(0, (stage.offsetHeight * stageScale - viewport.clientHeight) / 2);
      state.x = Math.max(-boundX, Math.min(boundX, state.x));
      state.y = Math.max(-boundY, Math.min(boundY, state.y));
      this.syncCameraCenter(state, stage);
      const tokenSize = Math.max(1, Number(stage.dataset.tokenSize || 6));
      const tier = this.zoomTier(state);
      const sizeRatio = Math.max(0.35, Math.min(5.5, tokenSize / (MAP_NATIVE_WIDTH * DEFAULT_TOKEN_SCALE)));
      const overviewMode = tier < 4;
      const tierScreenSize = overviewMode
        ? OVERVIEW_DOT_SCREEN_SIZES[tier]
        : TOKEN_SCREEN_SIZES[tier];
      const targetActorScreenSize = Math.max(8, tierScreenSize * sizeRatio);
      const actorCameraScale = targetActorScreenSize / Math.max(1, tokenSize * stageScale);
      const actorNetScale = Math.max(0.0001, stageScale * actorCameraScale);
      const screenToActor = value => value / actorNetScale;
      stage.style.setProperty('--map-actor-camera-scale', String(actorCameraScale));
      stage.style.setProperty('--map-nameplate-width', `${screenToActor(LABEL_SCREEN_WIDTHS[tier])}px`);
      stage.style.setProperty('--map-actor-border', `${screenToActor(1)}px`);
      stage.style.setProperty('--map-control-outline', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-control-offset', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-label-font-size', `${screenToActor(LABEL_SCREEN_SIZES[tier])}px`);
      stage.style.setProperty('--map-label-border', `${screenToActor(1)}px`);
      stage.style.setProperty('--map-label-radius', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-label-gap', `${screenToActor(3)}px`);
      stage.style.setProperty('--map-label-pad-y', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-label-pad-x', `${screenToActor(4)}px`);
      stage.style.setProperty('--map-label-max-width', `${screenToActor(LABEL_SCREEN_WIDTHS[tier])}px`);
      stage.style.setProperty('--map-position-dot-size', `${screenToActor(OVERVIEW_DOT_SCREEN_SIZES[tier] || 8)}px`);
      stage.style.setProperty('--map-position-line-width', `${screenToActor(1.5)}px`);
      stage.style.setProperty('--map-indicator-size', `${screenToActor(targetActorScreenSize * (tier === 4 ? 0.24 : 0.2))}px`);
      stage.style.setProperty('--map-indicator-gap', `${screenToActor(targetActorScreenSize * 0.055)}px`);
      stage.style.setProperty('--map-indicator-border', `${screenToActor(1)}px`);
      stage.style.setProperty('--map-indicator-offset', `${screenToActor(3)}px`);
      stage.dataset.zoomTier = String(tier);
      stage.style.transform = `translate(-50%, -50%) translate(${state.x}px, ${state.y}px) scale(${stageScale})`;
      stage.querySelectorAll('.ccgb-board-actor.is-player-character').forEach(piece => {
        piece.classList.toggle('is-overview-marker', overviewMode);
      });
      cancelAnimationFrame(this.actorLabelFrame);
      if (overviewMode) {
        this.actorLabelFrame = requestAnimationFrame(() => {
          if (viewport.isConnected && stage.isConnected) {
            this.positionOverviewLabels(viewport, stage, tier, actorNetScale);
          }
        });
      }
    }

    positionOverviewLabels(viewport, stage, tier, actorNetScale) {
      const pieces = Array.from(stage.querySelectorAll('.ccgb-board-actor.is-player-character.is-overview-marker'));
      if (!pieces.length) return;
      const viewportBounds = viewport.getBoundingClientRect();
      const stageBounds = stage.getBoundingClientRect();
      const bounds = {
        left: Math.max(viewportBounds.left + 6, stageBounds.left + 6),
        top: Math.max(viewportBounds.top + 6, stageBounds.top + 6),
        right: Math.min(viewportBounds.right - 6, stageBounds.right - 6),
        bottom: Math.min(viewportBounds.bottom - 6, stageBounds.bottom - 6)
      };
      const fontSize = LABEL_SCREEN_SIZES[tier];
      const maxWidth = LABEL_SCREEN_WIDTHS[tier];
      const dotSize = OVERVIEW_DOT_SCREEN_SIZES[tier];
      const anchors = pieces.map(piece => ({
        piece,
        x: stageBounds.left + Number(piece.dataset.actorX || 0.5) * stageBounds.width,
        y: stageBounds.top + Number(piece.dataset.actorY || 0.5) * stageBounds.height
      }));
      const occupied = [];
      const overlaps = (a, b, padding = 5) => !(
        a.right + padding <= b.left || a.left >= b.right + padding ||
        a.bottom + padding <= b.top || a.top >= b.bottom + padding
      );
      const overflow = rect =>
        Math.max(0, bounds.left - rect.left) + Math.max(0, rect.right - bounds.right) +
        Math.max(0, bounds.top - rect.top) + Math.max(0, rect.bottom - bounds.bottom);

      anchors.forEach(anchor => {
        const label = anchor.piece.querySelector('.ccgb-position-label');
        if (!label) return;
        const name = label.textContent || 'Character';
        const width = Math.min(maxWidth, Math.max(72, name.length * fontSize * 0.62 + 22));
        const height = fontSize + 14;
        const gap = dotSize / 2 + 12;
        const candidates = [
          [0, -(gap + height / 2)],
          [width / 2 + gap, 0],
          [-(width / 2 + gap), 0],
          [0, gap + height / 2],
          [width * 0.38 + gap, -(height / 2 + gap)],
          [-(width * 0.38 + gap), -(height / 2 + gap)],
          [width * 0.38 + gap, height / 2 + gap],
          [-(width * 0.38 + gap), height / 2 + gap]
        ];
        let best = null;
        candidates.forEach(([dx, dy]) => {
          const rect = {
            left: anchor.x + dx - width / 2,
            right: anchor.x + dx + width / 2,
            top: anchor.y + dy - height / 2,
            bottom: anchor.y + dy + height / 2
          };
          const plaqueHits = occupied.filter(item => overlaps(rect, item)).length;
          const tokenHits = anchors.filter(other => other !== anchor && (
            other.x >= rect.left - dotSize && other.x <= rect.right + dotSize &&
            other.y >= rect.top - dotSize && other.y <= rect.bottom + dotSize
          )).length;
          const score = plaqueHits * 10000 + tokenHits * 5000 + overflow(rect) * 100 + Math.hypot(dx, dy);
          if (!best || score < best.score) best = { dx, dy, rect, score };
        });
        if (!best) return;
        const nudgeX = best.rect.left < bounds.left
          ? bounds.left - best.rect.left
          : (best.rect.right > bounds.right ? bounds.right - best.rect.right : 0);
        const nudgeY = best.rect.top < bounds.top
          ? bounds.top - best.rect.top
          : (best.rect.bottom > bounds.bottom ? bounds.bottom - best.rect.bottom : 0);
        best.dx += nudgeX;
        best.dy += nudgeY;
        best.rect = {
          left: best.rect.left + nudgeX,
          right: best.rect.right + nudgeX,
          top: best.rect.top + nudgeY,
          bottom: best.rect.bottom + nudgeY
        };
        const shiftX = best.dx / actorNetScale;
        const shiftY = best.dy / actorNetScale;
        const distance = Math.hypot(best.dx, best.dy);
        const lineLength = Math.max(4, distance - Math.min(width, height) / 2 - 3);
        anchor.piece.style.setProperty('--map-position-label-x', `${shiftX}px`);
        anchor.piece.style.setProperty('--map-position-label-y', `${shiftY}px`);
        anchor.piece.style.setProperty('--map-position-line-length', `${lineLength / actorNetScale}px`);
        anchor.piece.style.setProperty('--map-position-line-angle', `${Math.atan2(best.dy, best.dx)}rad`);
        occupied.push(best.rect);
      });
    }

    resetMapCamera(mapId) {
      if (!mapId) return;
      this.mapCameraStates.set(mapId, this.normalizedCamera(null));
      const viewport = this.root.querySelector('.ccgb-map-viewport');
      const stage = this.root.querySelector('.ccgb-map-stage');
      if (viewport && stage) this.applyMapCamera(viewport, stage, mapId);
      this.queueCameraSave(mapId, 100);
    }

    queueCameraSave(mapId, delay = 450) {
      this.saveViewState();
      clearTimeout(this.mapCameraSaveTimers.get(mapId));
      this.mapCameraSaveTimers.set(mapId, setTimeout(() => {
        this.mapCameraSaveTimers.delete(mapId);
        this.saveCameraNow(mapId);
      }, delay));
    }

    saveCameraNow(mapId) {
      const state = this.mapCameraStates.get(mapId);
      if (!state) return;
      this.send({
        v: VERSION,
        type: 'board_camera',
        map_id: mapId,
        zoom: Number(state.scale || 1),
        center_x: Number(state.centerX ?? 0.5),
        center_y: Number(state.centerY ?? 0.5)
      });
    }

    createBoardActor(stage, actor) {
      const piece = document.createElement('div');
      piece.className = `ccgb-board-actor is-${actor.display_mode || 'dot'}`;
      piece.dataset.actorId = actor.actor_id;
      piece.dataset.actorX = String(Number(actor.x ?? 0.5));
      piece.dataset.actorY = String(Number(actor.y ?? 0.5));
      piece.classList.toggle('is-player-character', Boolean(actor.is_player_character));
      piece.style.setProperty('--actor-color', actor.faction_color || '#808080');
      piece.title = actor.faction_revealed && actor.faction_name
        ? `${actor.name || 'Unknown'} — ${actor.faction_name}`
        : (actor.name || 'Unknown');
      const controlled = (this.board.controlled_character_ids || []).includes(actor.actor_id);
      piece.classList.toggle('is-controlled', controlled);
      if (controlled) {
        piece.tabIndex = 0;
        piece.setAttribute('role', 'button');
        piece.setAttribute('aria-label', `Move ${actor.name || 'character'}`);
      }

      const indicators = document.createElement('span');
      indicators.className = 'ccgb-actor-indicators';
      [
        ['heavy', 'Heavy wounds — details coming soon'],
        ['medium', 'Medium wounds — details coming soon'],
        ['light', 'Light wounds — details coming soon'],
        ['status', 'Status — details coming soon']
      ].forEach(([kind, title]) => {
        const indicator = document.createElement('span');
        indicator.className = `is-${kind}`;
        indicator.title = title;
        indicators.appendChild(indicator);
      });
      piece.appendChild(indicators);

      if (actor.display_mode === 'token' && actor.portrait_asset_id) {
        const image = document.createElement('img');
        image.alt = '';
        image.draggable = false;
        this.assetUrl(actor.portrait_asset_id)
          .then(url => { if (piece.isConnected) image.src = url; })
          .catch(error => this.showChatNotice(error.message));
        piece.appendChild(image);
      } else if (actor.display_mode === 'nameplate') {
        const plate = document.createElement('span');
        plate.className = 'ccgb-nameplate-body';
        plate.textContent = actor.name || 'Character';
        piece.appendChild(plate);
      }
      if (actor.display_mode !== 'nameplate') {
        const label = document.createElement('span');
        label.className = 'ccgb-actor-label';
        label.textContent = actor.name || 'Unknown';
        piece.appendChild(label);
      }
      if (actor.is_player_character) {
        const leader = document.createElement('span');
        leader.className = 'ccgb-position-leader';
        const positionLabel = document.createElement('span');
        positionLabel.className = 'ccgb-position-label';
        positionLabel.textContent = actor.name || 'Character';
        piece.append(leader, positionLabel);
      }
      piece.style.left = `${Number(actor.x ?? 0.5) * 100}%`;
      piece.style.top = `${Number(actor.y ?? 0.5) * 100}%`;
      if (controlled) {
        piece.addEventListener('pointerdown', event => this.beginBoardDrag(event, actor, stage, piece));
      }
      stage.appendChild(piece);
    }

    beginBoardDrag(event, actor, stage, piece) {
      if (event.button !== 0) return;
      event.preventDefault();
      piece.setPointerCapture(event.pointerId);
      this.dragging = { actor, stage, piece, pointerId: event.pointerId };
      const move = moveEvent => this.moveBoardDrag(moveEvent);
      const end = endEvent => {
        piece.removeEventListener('pointermove', move);
        piece.removeEventListener('pointerup', end);
        piece.removeEventListener('pointercancel', end);
        this.endBoardDrag(endEvent);
      };
      piece.addEventListener('pointermove', move);
      piece.addEventListener('pointerup', end);
      piece.addEventListener('pointercancel', end);
    }

    boardPoint(event, stage) {
      const bounds = stage.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width))),
        y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / Math.max(1, bounds.height)))
      };
    }

    moveBoardDrag(event) {
      if (!this.dragging) return;
      const point = this.boardPoint(event, this.dragging.stage);
      this.dragging.actor.x = point.x;
      this.dragging.actor.y = point.y;
      this.dragging.piece.dataset.actorX = String(point.x);
      this.dragging.piece.dataset.actorY = String(point.y);
      this.dragging.piece.style.left = `${point.x * 100}%`;
      this.dragging.piece.style.top = `${point.y * 100}%`;
      const now = performance.now();
      if (now - this.lastMovePreview >= 80) {
        this.lastMovePreview = now;
        this.send({
          v: VERSION,
          type: 'board_move_preview',
          person_id: this.dragging.actor.actor_id,
          map_id: this.activeMapId,
          x: point.x,
          y: point.y
        });
      }
    }

    endBoardDrag(event) {
      if (!this.dragging) return;
      const point = this.boardPoint(event, this.dragging.stage);
      this.send({
        v: VERSION,
        type: 'board_move_commit',
        person_id: this.dragging.actor.actor_id,
        map_id: this.activeMapId,
        x: point.x,
        y: point.y
      });
      this.dragging = null;
    }

    positionBoardActors() {
      const stage = this.root.querySelector('.ccgb-map-stage');
      if (!stage) return;
      (this.board.actors || []).forEach(actor => {
        const piece = stage.querySelector(`[data-actor-id="${CSS.escape(actor.actor_id)}"]`);
        if (!piece || actor.map_id !== this.activeMapId) return;
        piece.style.left = `${Number(actor.x || 0.5) * 100}%`;
        piece.style.top = `${Number(actor.y || 0.5) * 100}%`;
      });
    }

    search(value) {
      const query = String(value || '').trim();
      const result = this.element('search-result');
      result.hidden = !query;
      result.textContent = query
        ? `Searching ${SECTIONS.find(([id]) => id === this.activeSection)?.[1] || 'this section'} for “${query}”. Data search will activate as character records are connected.`
        : '';
    }

    toggleRegion(region, forceClosed = false) {
      const className = `${region}-collapsed`;
      const workspace = this.element('workspace');
      workspace.classList.toggle(className, forceClosed || !workspace.classList.contains(className));
      this.saveLayout();
    }

    saveLayout() {
      const workspace = this.element('workspace');
      localStorage.setItem(this.layoutStorageKey, JSON.stringify({
        nav: workspace.classList.contains('nav-collapsed'),
        details: workspace.classList.contains('details-collapsed'),
        chat: workspace.classList.contains('chat-collapsed')
      }));
    }

    restoreLayout() {
      try {
        const value = JSON.parse(localStorage.getItem(this.layoutStorageKey) || '{}');
        const workspace = this.element('workspace');
        if (value.nav) workspace.classList.add('nav-collapsed');
        if (value.details) workspace.classList.add('details-collapsed');
        if (value.chat) workspace.classList.add('chat-collapsed');
      } catch (_) {
        // Keep the default open layout when a saved preference is malformed.
      }
    }

    saveViewState() {
      try {
        const cameras = {};
        this.mapCameraStates.forEach((state, mapId) => {
          cameras[mapId] = {
            zoom: Number(state.scale || 1),
            center_x: Number(state.centerX ?? 0.5),
            center_y: Number(state.centerY ?? 0.5)
          };
        });
        localStorage.setItem(this.viewStorageKey, JSON.stringify({
          section: this.activeSection,
          activeMapId: this.activeMapId,
          campaignId: this.currentCampaignId || this.savedViewCampaignId,
          cameras
        }));
        this.savedViewCampaignId = this.currentCampaignId || this.savedViewCampaignId;
      } catch (_) {
        // Server-side campaign persistence remains available when local storage is blocked.
      }
    }

    restoreViewState() {
      try {
        const value = JSON.parse(localStorage.getItem(this.viewStorageKey) || '{}');
        if (SECTIONS.some(([id]) => id === value.section)) this.activeSection = value.section;
        this.activeMapId = String(value.activeMapId || '');
        this.savedViewCampaignId = String(value.campaignId || '');
        Object.entries(value.cameras || {}).forEach(([mapId, camera]) => {
          if (mapId) this.mapCameraStates.set(mapId, this.normalizedCamera(camera));
        });
      } catch (_) {
        // Ignore malformed or unavailable local state and use the campaign snapshot.
      }
    }

    errorState(error) {
      const text = this.errorMessage(error).toLowerCase();
      if (text.includes('revoked')) return 'revoked';
      if (text.includes('expired') || text.includes('ended')) return 'expired';
      if (text.includes('invalid') || text.includes('invitation')) return 'invalid';
      return 'unavailable';
    }

    errorMessage(error) {
      return error instanceof Error ? error.message : String(error);
    }

    saveAdmission() {
      sessionStorage.setItem(this.admissionStorageKey, JSON.stringify({
        invite: this.invite,
        requestId: this.requestId,
        pollToken: this.pollToken
      }));
    }

    loadAdmission() {
      try {
        const value = JSON.parse(sessionStorage.getItem(this.admissionStorageKey) || 'null');
        return value && value.requestId && value.pollToken ? value : null;
      } catch (_) {
        return null;
      }
    }

    clearAdmission() {
      this.requestId = '';
      this.pollToken = '';
      sessionStorage.removeItem(this.admissionStorageKey);
    }

    showPreview(preview) {
      if (preview === 'waiting') {
        this.show('waiting', 'Waiting for the Headmaster to approve this connection…', { busy: true });
        return;
      }
      if (preview === 'denied') {
        this.show('denied', 'The Headmaster denied this connection.', { retry: true });
        return;
      }
      this.element('player').textContent = 'Edward Marksdale';
      this.playerId = 'preview-edward';
      this.element('detail-player').textContent = 'Edward Marksdale';
      this.element('avatar').textContent = 'E';
      this.element('session').textContent = 'Saturday Evening Session';
      this.show('connected', 'You are connected.', { connected: true });
      this.setQuality('good', '84 ms');
      this.chatMessages = [
        { id: '1', sender_id: 'headmaster', sender_name: 'Headmaster', sender_role: 'headmaster', text: 'Welcome. The first activity will begin shortly.', sent_at: new Date().toISOString() },
        { id: '2', sender_id: 'preview-edward', sender_name: 'Edward Marksdale', sender_role: 'player', text: 'Ready when you are!', sent_at: new Date().toISOString() },
        { id: '3', sender_id: 'preview-hermione', sender_name: 'Hermione', sender_role: 'player', text: 'I have my wand and notes.', sent_at: new Date().toISOString() }
      ];
      this.renderChat();
      this.board = {
        maps: [{
          record_id: 'preview-map',
          name: 'Great Hall',
          asset: null,
          obscurations: [{ record_id: 'preview-obscuration', points: [
            { x: 0.18, y: 0.2 }, { x: 0.82, y: 0.2 }, { x: 0.82, y: 0.78 }, { x: 0.18, y: 0.78 }
          ] }]
        }],
        actors: [
          { actor_id: 'preview-edward', map_id: 'preview-map', x: 0.32, y: 0.48, display_mode: 'nameplate', name: 'Edward Marksdale', faction_color: '#7b3f2b', is_player_character: true },
          { actor_id: 'preview-hermione', map_id: 'preview-map', x: 0.67, y: 0.39, display_mode: 'dot', name: 'Unknown', faction_color: '#808080' }
        ],
        controlled_character_ids: ['preview-edward']
      };
      this.activeMapId = 'preview-map';
      this.openSection('board');
    }
  }

  window.CharmsCheckGameBoard = Object.freeze({
    init(options = {}) {
      const client = new GameBoardClient(options);
      client.start();
      return client;
    }
  });
})();
