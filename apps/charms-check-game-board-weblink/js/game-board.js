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
  const TOKEN_SCREEN_SIZES = [0, 0, 0, 0, 0, 0, 68, 64];
  const OVERVIEW_DOT_SCREEN_SIZES = [12, 11, 10, 9, 8, 7, 0, 0];
  const LABEL_SCREEN_SIZES = [15.2, 14.7, 13.7, 12.7, 11.5, 11, 10.5, 10];
  const LABEL_SCREEN_WIDTHS = [208, 192, 177, 162, 152, 142, 132, 124];
  const SKILL_ABILITIES = {
    Charms: 'Power', Transfiguration: 'Power', Defense: 'Power', 'Dark Arts': 'Power',
    Runes: 'Erudition', Arithmancy: 'Erudition', Muggles: 'Erudition', History: 'Erudition',
    Flying: 'Panache', Alchemy: 'Panache', Potions: 'Panache', Artificing: 'Panache', Herbology: 'Panache',
    Astronomy: 'Naturalism', Divination: 'Naturalism', Creatures: 'Naturalism', Perception: 'Naturalism', Social: 'Naturalism'
  };
  const SECTIONS = [
    ['board', 'Game Board', '▦'],
    ['overview', 'Overview', '⌂'],
    ['attributes', 'Attributes', '◇'],
    ['spells', 'Spells', '✦'],
    ['proficiencies', 'Proficiencies', '✧'],
    ['recipes', 'Recipes', '⚗'],
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
      this.mapRepaintTimer = 0;
      this.mapRepaintFrame = 0;
      this.currentCampaignId = '';
      this.hydratedCampaignId = '';
      this.savedViewCampaignId = '';
      this.dragging = null;
      this.lastMovePreview = 0;
      this.activeSection = 'overview';
      this.chatMessages = [];
      this.characterSheet = null;
      this.favoriteStorageKey = `${this.storageKey}-favorites`;
      this.chatFontStorageKey = `${this.storageKey}-chat-font-size`;
      this.chatFontSize = Math.max(
        11,
        Math.min(22, Number(localStorage.getItem(this.chatFontStorageKey)) || 14)
      );
      try {
        this.favorites = new Set(JSON.parse(localStorage.getItem(this.favoriteStorageKey) || '[]'));
      } catch (_error) {
        this.favorites = new Set();
      }
      this.cameraPreferenceKey = `${this.storageKey}-allow-headmaster-camera`;
      this.allowHeadmasterCamera = localStorage.getItem(this.cameraPreferenceKey) !== 'false';
      this.restoreViewState();
      this.render();
      this.syncViewportHeight();
      this.applyChatFontSize();
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
                <span class="ccgb-player-name" data-ccgb="player">Player</span>
                <span class="ccgb-player-birth" data-ccgb="player-birth"></span>
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
                <div class="ccgb-connection-markers">
                  <span class="ccgb-zoom-level" data-ccgb="zoom-level">Zoom 100% (0 clicks)</span>
                  <span class="ccgb-connected-mark">Connected</span>
                </div>
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
                  <div class="ccgb-chat-header-controls">
                    <button type="button" data-ccgb="chat-smaller" aria-label="Decrease chat text size" title="Decrease chat text size">−</button>
                    <button type="button" data-ccgb="chat-larger" aria-label="Increase chat text size" title="Increase chat text size">+</button>
                    <button type="button" class="ccgb-collapse-panel" data-ccgb="close-chat" aria-label="Collapse chat" title="Collapse chat">›</button>
                  </div>
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
      this.element('chat-smaller').addEventListener('click', () => this.adjustChatFontSize(-1));
      this.element('chat-larger').addEventListener('click', () => this.adjustChatFontSize(1));
      window.addEventListener('resize', () => this.syncViewportHeight());
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
        if (Object.prototype.hasOwnProperty.call(message, 'character_attributes')) {
          this.board.character_attributes = message.character_attributes;
        }
        if (Object.prototype.hasOwnProperty.call(message, 'character_sheet')) {
          this.characterSheet = message.character_sheet;
        }
        this.assetCredential = message.asset_credential || '';
        this.element('player').textContent = message.player || 'Player';
        this.element('detail-player').textContent = message.player || 'Player';
        this.element('session').textContent = message.session || '';
        this.show('connected', 'You are connected.', { connected: true });
        this.setQuality('good', 'Connected');
        this.updatePlayerIdentity(message.player || 'Player');
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
        if (Object.prototype.hasOwnProperty.call(message, 'character_attributes')) {
          this.board.character_attributes = message.character_attributes;
        }
        if (Object.prototype.hasOwnProperty.call(message, 'character_sheet')) {
          this.characterSheet = message.character_sheet;
        }
        this.element('player').textContent = player;
        this.element('detail-player').textContent = player;
        this.updatePlayerIdentity(player);
        this.releaseAssets();
        if (this.activeSection !== 'board') this.openSection(this.activeSection);
      } else if (message.type === 'board_snapshot' && message.board) {
        const previousAttributes = this.board && this.board.character_attributes;
        const previousSheet = this.characterSheet;
        this.board = message.board;
        if (!Object.prototype.hasOwnProperty.call(this.board, 'character_attributes') && previousAttributes) {
          this.board.character_attributes = previousAttributes;
        }
        this.characterSheet = this.board.character_sheet || previousSheet || null;
        this.updatePlayerIdentity();
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
        else this.openSection(this.activeSection);
      } else if ((message.type === 'character_sheet_snapshot' || message.type === 'character_sheet_updated') && message.character_sheet) {
        this.characterSheet = message.character_sheet;
        this.board.character_attributes = message.character_sheet.attributes;
        this.updatePlayerIdentity();
        if (this.activeSection !== 'board') this.openSection(this.activeSection);
      } else if (message.type === 'request_submitted') {
        this.showChatNotice(message.message || 'Request sent to the Headmaster.');
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
      } else if (message.type === 'board_transport' && message.camera) {
        // Transport is part of moving this player's character, not the
        // optional Headmaster camera-control feature. Always take the player
        // to the destination so they can see where their token arrived.
        const mapId = String(message.map_id || '');
        if (mapId) {
          this.activeMapId = mapId;
          this.mapCameraStates.set(mapId, this.normalizedCamera(message.camera));
          this.saveViewState();
          if (this.activeSection !== 'board') this.openSection('board');
          else this.renderBoardView();
          this.queueCameraSave(mapId, 0);
          this.showBoardNotice('You have been transported.');
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

    updatePlayerIdentity(fallback = '') {
      const overview = this.characterSheet?.overview;
      const name = overview?.name || fallback || this.element('player').textContent || 'Player';
      const age = Number(overview?.age);
      const eminence = Number(overview?.eminence);
      const hasAge = overview?.age !== null && overview?.age !== undefined && Number.isFinite(age);
      this.element('player').textContent = hasAge ? `${name} (${age})` : name;
      const detail = this.element('player-birth');
      detail.textContent = Number.isFinite(eminence) && eminence > 0 ? `Eminence: ${eminence}` : '';
      detail.hidden = !detail.textContent;
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

    postChatText(message) {
      const text = String(message || '').trim();
      if (!text) return;
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        this.showChatNotice('Chat is unavailable while disconnected.');
        return;
      }
      this.send({ v: VERSION, type: 'chat_message', message: text.slice(0, 500) });
    }

    applyChatFontSize() {
      this.root.style.setProperty('--ccgb-chat-font-size', `${this.chatFontSize}px`);
    }

    syncViewportHeight() {
      const top = Math.max(0, this.root.getBoundingClientRect().top);
      const available = Math.max(420, window.innerHeight - top - 7);
      this.root.style.setProperty('--ccgb-board-height', `${available}px`);
    }

    adjustChatFontSize(direction) {
      const next = Math.max(11, Math.min(22, this.chatFontSize + Number(direction || 0)));
      if (next === this.chatFontSize) return;
      this.chatFontSize = next;
      localStorage.setItem(this.chatFontStorageKey, String(next));
      this.applyChatFontSize();
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
        const activityOutcome = String(message.activity?.outcome || '');
        const outcomeClass = ['critical_failure', 'failure', 'success', 'critical_success'].includes(activityOutcome)
          ? `is-roll-${activityOutcome.replace('_', '-')}`
          : '';
        article.className = `ccgb-chat-message ${message.sender_role === 'headmaster' ? 'is-headmaster' : ''} ${ownMessage ? 'is-own' : ''} ${outcomeClass}`;
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
        if (message.activity) {
          const details = document.createElement('details');
          details.className = 'ccgb-roll-details';
          const summary = document.createElement('summary');
          summary.className = 'ccgb-roll-result';
          summary.title = `Click to inspect the dice and every modifier`;
          summary.textContent = `${message.activity.target_name || 'Roll'} · ${Number(message.activity.total || 0)}`;
          const body = document.createElement('div');
          body.className = 'ccgb-roll-object';
          const components = document.createElement('dl');
          components.className = 'ccgb-roll-components';
          (message.activity.components || []).forEach((component, index) => {
            const term = document.createElement('div');
            const label = document.createElement('dt');
            const value = document.createElement('dd');
            const isDie = component.kind === 'die';
            label.textContent = isDie && (message.activity.dice || []).length === 1
              ? 'd10'
              : (component.label || component.kind || 'Value');
            if (isDie) {
              const die = document.createElement('span');
              const dieValue = Number(component.value || 0);
              die.className = `ccgb-roll-die ${dieValue === 10 ? 'is-critical-success' : dieValue === 1 ? 'is-critical-failure' : ''}`;
              die.title = `${label.textContent}: ${dieValue}`;
              die.textContent = String(dieValue);
              value.appendChild(die);
            } else {
              value.textContent = String(Number(component.value || 0));
            }
            term.append(label, value);
            components.appendChild(term);
            (component.sources || []).forEach(source => {
              const sourceTerm = document.createElement('div');
              sourceTerm.className = 'ccgb-roll-source';
              const sourceLabel = document.createElement('dt');
              const sourceValue = document.createElement('dd');
              sourceLabel.textContent = source.label || 'Source';
              sourceValue.textContent = String(Number(source.value ?? 0));
              sourceTerm.append(sourceLabel, sourceValue);
              components.appendChild(sourceTerm);
            });
          });
          if (message.activity.threshold != null) {
            const term = document.createElement('div');
            term.innerHTML = `<dt>Threshold</dt><dd>${Number(message.activity.threshold)}</dd>`;
            components.appendChild(term);
          }
          const totalTerm = document.createElement('div');
          totalTerm.className = 'ccgb-roll-total';
          totalTerm.innerHTML = `<dt>Total</dt><dd>${Number(message.activity.total || 0)}</dd>`;
          components.appendChild(totalTerm);
          body.append(components);
          details.append(summary, body);
          article.appendChild(details);
        }
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
          </details>
          <details class="ccgb-content-panel" open>
            <summary>Presentation</summary>
            <div><p>Favorites stay in this browser. Roll history lasts only for this Game Board session.</p></div>
          </details>
          <details class="ccgb-content-panel" open>
            <summary>Session roll history</summary>
            <div class="ccgb-history-list">${this.escapeHtml(this.rollHistoryText())}</div>
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
      if (item[0] === 'attributes') {
        this.renderAttributesPanel(content);
        this.search(this.element('search').value);
        return;
      }
      if (item[0] === 'overview') this.renderOverviewPanel(content);
      else if (['spells', 'proficiencies', 'recipes'].includes(item[0])) this.renderKnowledgePanel(content, item[0]);
      else if (item[0] === 'pets') this.renderPetsPanel(content);
      else if (item[0] === 'inventory') this.renderInventoryPanel(content);
      else if (item[0] === 'relationships') this.renderRelationshipsPanel(content);
      else if (item[0] === 'wounds') this.renderWoundsPanel(content);
      this.search(this.element('search').value);
    }

    escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
    }

    sheetUnavailable(content, label) {
      content.innerHTML = `<section class="ccgb-sheet-empty"><h2>${this.characterId ? `Loading ${this.escapeHtml(label)}...` : `${this.escapeHtml(label)} unavailable`}</h2><p>${this.characterId ? 'Refreshing your private character sheet.' : 'No World Builder character is linked to this player.'}</p></section>`;
    }

    requestRoll(rollType, targetId) {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        this.showChatNotice('Rolls are unavailable while disconnected.');
        return;
      }
      this.send({ v: VERSION, type: 'character_roll_request', roll_type: rollType, target_id: targetId });
    }

    bindRollButtons(content) {
      content.querySelectorAll('[data-roll-type]').forEach(button => button.addEventListener('click', () => {
        this.requestRoll(button.dataset.rollType, button.dataset.targetId);
      }));
    }

    rollHistoryText() {
      const rolls = this.chatMessages.filter(message => message.activity);
      return rolls.length ? rolls.map(message => message.text).join('\n') : 'No rolls in this session yet.';
    }

    renderOverviewPanel(content) {
      const overview = this.characterSheet && this.characterSheet.overview;
      if (!overview) return this.sheetUnavailable(content, 'Overview');
      content.className = 'ccgb-sheet-grid ccgb-overview-grid';
      content.innerHTML = `
        <section class="ccgb-sheet-card ccgb-profile-card">
          <div class="ccgb-profile-portrait" data-sheet-portrait>${this.escapeHtml(overview.name).charAt(0)}</div>
          <div><h2>${this.escapeHtml(overview.name)}</h2><dl>
            <div><dt>Born</dt><dd>${this.escapeHtml(overview.birth || 'Not recorded')}</dd></div>
            <div><dt>School</dt><dd>${this.escapeHtml(overview.school || 'Not recorded')}</dd></div>
            <div><dt>Canon</dt><dd>${overview.canon ? 'Yes' : 'No'}</dd></div>
            <div><dt>Eminence</dt><dd>${Number(overview.eminence || 0)}</dd></div>
          </dl></div>
        </section>
        <section class="ccgb-sheet-card"><h2>Biography</h2><p>${this.escapeHtml(overview.narrative || 'No narrative recorded.')}</p></section>`;
      if (overview.portrait_asset_id) this.assetUrl(overview.portrait_asset_id).then(url => {
        const holder = content.querySelector('[data-sheet-portrait]');
        if (holder && url) holder.innerHTML = `<img src="${url}" alt="Portrait of ${this.escapeHtml(overview.name)}">`;
      }).catch(() => {});
    }

    renderKnowledgePanel(content, collection) {
      return this.renderKnowledgeCatalog(content, collection);
    }

    renderKnowledgeCatalog(content, collection) {
      const records = this.characterSheet && this.characterSheet[collection];
      if (!records) return this.sheetUnavailable(content, collection);
      const singular = { spells: 'spell', proficiencies: 'proficiency', recipes: 'recipe' }[collection];
      const fieldValues = field => [...new Set(records.map(item => String(item[field] || '')).filter(Boolean))].sort((a, b) => a.localeCompare(b));
      const tagValues = [...new Set(records.flatMap(item => Array.isArray(item.tags) ? item.tags : String(item.tags || '').split(',')).map(value => String(value).trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
      const optionList = (field, label) => `<select data-catalog-filter="${field}" aria-label="Filter by ${label}"><option value="">All ${label}</option>${fieldValues(field).map(value => `<option value="${this.escapeHtml(value)}">${this.escapeHtml(value)}</option>`).join('')}</select>`;
      const valueByName = (this.characterSheet?.attributes?.attributes || []).reduce((values, item) => { values[item.name] = Number(item.value || 0); return values; }, {});
      const skillByName = (this.characterSheet?.attributes?.skills || []).reduce((values, item) => { values[item.name] = Number(item.value || 0); return values; }, {});
      const requiredRoll = record => {
        if (record.threshold == null || record.threshold === '') return null;
        const skill = String(record.skill || (collection === 'recipes' ? 'Potions' : ''));
        return Number(record.threshold) - Number(skillByName[skill] || 0) - Number(valueByName[SKILL_ABILITIES[skill]] || 0);
      };
      const spellBand = record => {
        const needed = requiredRoll(record);
        if (needed === null) return 'No threshold';
        if (needed > 10) return "Can't cast";
        if (needed <= 3) return 'Easy to cast';
        if (needed <= 6) return 'Medium confidence';
        if (needed <= 8) return 'Difficult to cast';
        return 'Very difficult to cast';
      };
      content.className = `ccgb-knowledge-browser ${collection === 'spells' ? 'is-spellbook' : ''}`;
      content.innerHTML = `
        <div class="ccgb-catalog-tools">
          <input type="search" data-catalog-search placeholder="Search ${collection}">
          ${optionList('skill', 'skills')}
          ${optionList('source', 'sources')}
          ${collection === 'spells' ? optionList('subtype', 'subtypes') : ''}
          <select data-catalog-tag aria-label="Filter by tag"><option value="">All tags</option>${tagValues.map(value => `<option value="${this.escapeHtml(value)}">#${this.escapeHtml(value)}</option>`).join('')}</select>
          ${collection === 'spells' ? '<select data-catalog-band aria-label="Casting confidence"><option value="">All casting confidence</option><option>Easy to cast</option><option>Medium confidence</option><option>Difficult to cast</option><option>Very difficult to cast</option><option>Can\'t cast</option><option>No threshold</option></select>' : ''}
          <label class="ccgb-threshold-filter"><span>Difficulty</span><input type="number" min="0" data-catalog-min placeholder="Min"><span>to</span><input type="number" min="0" data-catalog-max placeholder="Max"></label>
          <select data-catalog-sort aria-label="Sort results"><option value="name">Name A–Z</option><option value="difficulty">Difficulty</option><option value="skill">Skill</option><option value="source">Source</option></select>
          <label><input type="checkbox" data-favorites-only> Favorites</label>
          <button type="button" class="ccgb-teach-open" data-teach-open>Teach...</button>
        </div>
        <section class="ccgb-teach-panel" data-teach-panel hidden>
          <header><strong>Submit a teaching request</strong><span>Only characters on your map are available.</span></header>
          <div class="ccgb-teach-columns">
            <div><label>Pupil</label><input type="search" data-teach-pupil-search placeholder="Search nearby characters" autocomplete="off"><div class="ccgb-teach-choices" data-teach-pupils></div></div>
            <div><label>Known ${singular}</label><div class="ccgb-teach-filter-row"><input type="search" data-teach-subject-search placeholder="Search known ${collection}" autocomplete="off"><select data-teach-skill><option value="">All skills</option>${fieldValues('skill').map(value => `<option value="${this.escapeHtml(value)}">${this.escapeHtml(value)}</option>`).join('')}</select><select data-teach-sort><option value="name">Name</option><option value="difficulty">Difficulty</option><option value="skill">Skill</option></select></div><div class="ccgb-teach-choices" data-teach-subjects></div></div>
          </div>
          <p data-teach-selection>Select a pupil and subject.</p>
          <div><button type="button" data-teach-cancel>Cancel</button><button type="button" data-teach-submit disabled>Send request</button></div>
        </section>
        <div class="ccgb-knowledge-results"><span data-result-count></span><div class="ccgb-knowledge-pills" data-knowledge-pills></div></div>`;

      let selectedId = records[0]?.record_id || '';
      const normalizedText = value => String(value || '').toLocaleLowerCase();
      const fuzzyScore = (record, query) => {
        if (!query) return 1;
        const terms = query.split(/\s+/).filter(Boolean);
        const name = normalizedText(record.name);
        const haystack = normalizedText([record.name, record.skill, record.subtype, record.source, record.description, record.raw_effect, record.raw_effects, ...(Array.isArray(record.tags) ? record.tags : String(record.tags || '').split(','))].join(' '));
        if (!terms.every(term => haystack.includes(term))) return -1;
        return terms.reduce((score, term) => score + (name.startsWith(term) ? 12 : name.includes(term) ? 6 : 1), 0);
      };

      const renderResults = () => {
        const query = normalizedText(content.querySelector('[data-catalog-search]').value.trim());
        const filters = [...content.querySelectorAll('[data-catalog-filter]')].map(element => [element.dataset.catalogFilter, element.value]);
        const minText = content.querySelector('[data-catalog-min]').value;
        const maxText = content.querySelector('[data-catalog-max]').value;
        const minimum = minText === '' ? null : Number(minText);
        const maximum = maxText === '' ? null : Number(maxText);
        const favoritesOnly = content.querySelector('[data-favorites-only]').checked;
        const sort = content.querySelector('[data-catalog-sort]').value;
        const band = content.querySelector('[data-catalog-band]')?.value || '';
        const tag = content.querySelector('[data-catalog-tag]').value;
        const values = records.map(record => ({ record, score: fuzzyScore(record, query) })).filter(({ record, score }) => {
          const wrongFilter = filters.some(([field, value]) => value && String(record[field] || '') !== value);
          const difficulty = record.threshold == null ? null : Number(record.threshold);
          const recordTags = (Array.isArray(record.tags) ? record.tags : String(record.tags || '').split(',')).map(value => String(value).trim());
          return score >= 0 && !wrongFilter && (!tag || recordTags.includes(tag)) && (!band || spellBand(record) === band) && (minimum === null || difficulty === null || difficulty >= minimum) && (maximum === null || difficulty === null || difficulty <= maximum) && (!favoritesOnly || this.favorites.has(`${collection}:${record.record_id}`));
        });
        values.sort((left, right) => {
          if (query && right.score !== left.score) return right.score - left.score;
          if (sort === 'difficulty') return Number(left.record.threshold ?? 1e9) - Number(right.record.threshold ?? 1e9) || left.record.name.localeCompare(right.record.name);
          if (sort === 'skill' || sort === 'source') return String(left.record[sort] || '').localeCompare(String(right.record[sort] || '')) || left.record.name.localeCompare(right.record.name);
          return left.record.name.localeCompare(right.record.name);
        });
        const holder = content.querySelector('[data-knowledge-pills]');
        const grouped = collection === 'spells'
          ? ['Easy to cast', 'Medium confidence', 'Difficult to cast', 'Very difficult to cast', "Can't cast", 'No threshold'].map(label => [label, values.filter(item => spellBand(item.record) === label)]).filter(([, items]) => items.length)
          : [['', values]];
        holder.innerHTML = grouped.map(([label, items]) => `${label ? `<h3>${this.escapeHtml(label)}</h3>` : ''}<div class="ccgb-knowledge-pill-group">${items.map(({ record }) => {
          const favorite = this.favorites.has(`${collection}:${record.record_id}`);
          const bandClass = collection === 'spells' ? ` is-band-${spellBand(record).toLowerCase().replaceAll(/[^a-z]+/g, '-').replace(/^-|-$/g, '')}` : '';
          return `<button type="button" class="ccgb-knowledge-pill${bandClass} ${record.record_id === selectedId ? 'is-selected' : ''} ${favorite ? 'is-favorite' : ''}" data-record-id="${this.escapeHtml(record.record_id)}" title="${this.escapeHtml(record.description || record.raw_effect || record.raw_effects || 'No description recorded.')}\n\nClick to roll · Ctrl-click to favorite · Alt-click to share"><span class="ccgb-pill-star" aria-hidden="true">${favorite ? '★' : ''}</span><span>${this.escapeHtml(record.name)}</span></button>`;
        }).join('')}</div>`).join('') || `<p class="ccgb-empty-result">No matching ${collection}.</p>`;
        content.querySelector('[data-result-count]').textContent = `${values.length} known ${values.length === 1 ? singular : collection}`;
        holder.querySelectorAll('[data-record-id]').forEach(button => {
          button.addEventListener('contextmenu', event => event.preventDefault());
          button.addEventListener('mousedown', event => {
            if ((event.ctrlKey || event.metaKey) && event.button === 0) event.preventDefault();
          });
          button.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          const record = records.find(item => item.record_id === button.dataset.recordId);
          if (!record) return;
          if (event.ctrlKey || event.metaKey) {
            const key = `${collection}:${record.record_id}`;
            if (this.favorites.has(key)) this.favorites.delete(key); else this.favorites.add(key);
            localStorage.setItem(this.favoriteStorageKey, JSON.stringify([...this.favorites]));
            renderResults();
            return;
          }
          if (event.altKey) {
            const threshold = record.threshold == null ? '' : ` (${record.threshold})`;
            this.postChatText(`${record.name}${threshold}\n${record.description || record.raw_effect || record.raw_effects || 'No description recorded.'}`);
            return;
          }
          selectedId = record.record_id;
          renderResults();
          this.requestRoll(singular, record.record_id);
          });
        });
      };
      content.querySelectorAll('[data-catalog-search],[data-catalog-filter],[data-catalog-tag],[data-catalog-band],[data-catalog-min],[data-catalog-max],[data-catalog-sort],[data-favorites-only]').forEach(element => element.addEventListener('input', renderResults));
      this.bindTeachingPanel(content, collection, singular, records);
      renderResults();
    }

    bindTeachingPanel(content, collection, kind, records) {
      const panel = content.querySelector('[data-teach-panel]');
      const pupils = (this.characterSheet?.teaching_targets || []);
      let pupilId = '';
      let subjectId = '';
      const selection = panel.querySelector('[data-teach-selection]');
      const submit = panel.querySelector('[data-teach-submit]');
      const updateSelection = () => {
        const pupil = pupils.find(item => item.record_id === pupilId);
        const subject = records.find(item => item.record_id === subjectId);
        selection.textContent = pupil && subject ? `Teach ${subject.name} to ${pupil.name}` : 'Select a pupil and subject.';
        submit.disabled = !(pupil && subject);
      };
      const renderChoices = (holder, values, query, selected, select) => {
        holder.innerHTML = values.filter(item => item.name.toLowerCase().includes(query)).slice(0, 100).map(item =>
          `<button type="button" class="${item.record_id === selected ? 'is-selected' : ''}" data-choice-id="${this.escapeHtml(item.record_id)}">${this.escapeHtml(item.name)}</button>`
        ).join('') || '<span>No matches.</span>';
        holder.querySelectorAll('[data-choice-id]').forEach(button => button.addEventListener('click', () => select(button.dataset.choiceId)));
      };
      const pupilSearch = panel.querySelector('[data-teach-pupil-search]');
      const subjectSearch = panel.querySelector('[data-teach-subject-search]');
      const subjectSkill = panel.querySelector('[data-teach-skill]');
      const subjectSort = panel.querySelector('[data-teach-sort]');
      const renderPupils = () => renderChoices(panel.querySelector('[data-teach-pupils]'), pupils, pupilSearch.value.trim().toLowerCase(), pupilId, value => { pupilId = value; renderPupils(); updateSelection(); });
      const renderSubjects = () => {
        const query = subjectSearch.value.trim().toLowerCase();
        const skill = subjectSkill.value;
        const values = records.filter(item => !skill || String(item.skill || '') === skill).sort((left, right) => {
          if (subjectSort.value === 'difficulty') return Number(left.threshold ?? 1e9) - Number(right.threshold ?? 1e9) || left.name.localeCompare(right.name);
          if (subjectSort.value === 'skill') return String(left.skill || '').localeCompare(String(right.skill || '')) || left.name.localeCompare(right.name);
          return left.name.localeCompare(right.name);
        });
        renderChoices(panel.querySelector('[data-teach-subjects]'), values, query, subjectId, value => { subjectId = value; renderSubjects(); updateSelection(); });
      };
      content.querySelector('[data-teach-open]').addEventListener('click', () => {
        panel.hidden = false;
        renderPupils(); renderSubjects(); updateSelection(); pupilSearch.focus();
      });
      panel.querySelector('[data-teach-cancel]').addEventListener('click', () => { panel.hidden = true; });
      pupilSearch.addEventListener('input', renderPupils);
      subjectSearch.addEventListener('input', renderSubjects);
      subjectSkill.addEventListener('input', renderSubjects);
      subjectSort.addEventListener('input', renderSubjects);
      submit.addEventListener('click', () => {
        const subject = records.find(item => item.record_id === subjectId);
        if (!subject || !pupilId) return;
        this.send({
          v: VERSION, type: 'teaching_request', pupil_person_id: pupilId,
          knowledge_kind: kind, knowledge_record_id: subjectId,
          knowledge_collection: subject.collection || collection,
        });
        panel.hidden = true;
        this.showChatNotice('Sending teaching request...');
      });
    }

    renderRecordRequirements(record) {
      const rows = [];
      if (record.required_materials?.length) rows.push(`<strong>Materials:</strong> ${this.escapeHtml(record.required_materials.map(item => item.name || item).join(', '))}`);
      if (record.required_proficiencies?.length) rows.push(`<strong>Proficiencies:</strong> ${this.escapeHtml(record.required_proficiencies.map(item => item.name || item).join(', '))}`);
      if (record.ingredients?.length) rows.push(`<strong>Ingredients:</strong> ${this.escapeHtml(record.ingredients.map(item => `${item.quantity || ''} ${item.name || item}`.trim()).join(', '))}`);
      if (record.brew_time) rows.push(`<strong>Time:</strong> ${this.escapeHtml(record.brew_time)}`);
      if (record.additional_instructions) rows.push(`<strong>Method:</strong> ${this.escapeHtml(record.additional_instructions)}`);
      return rows.length ? `<p class="ccgb-requirements">${rows.join('<br>')}</p>` : '';
    }

    renderPetsPanel(content) {
      const records = this.characterSheet && this.characterSheet.pets;
      if (!records) return this.sheetUnavailable(content, 'Pets');
      content.className = 'ccgb-sheet-grid';
      content.innerHTML = records.map(item => {
        const species = item.species || {};
        const statistics = [
          ['Classification', species.classification], ['Size', species.size],
          ['Movement', species.movement], ['Wound cap', species.wound_cap],
          ['Attacks', species.attacks], ['Abilities', species.abilities]
        ].filter(([, value]) => value !== undefined && value !== null && String(value).trim());
        return `<article class="ccgb-sheet-card"><h2>${this.escapeHtml(item.name)}</h2>
          <p class="ccgb-badges">${(item.relationships || []).map(value => `<span class="is-${value}">${this.escapeHtml(value)}</span>`).join('')}</p>
          <p><strong>${this.escapeHtml(species.name || 'Species not recorded')}</strong></p>
          ${statistics.length ? `<dl class="ccgb-creature-stats">${statistics.map(([label, value]) => `<div><dt>${this.escapeHtml(label)}</dt><dd>${this.escapeHtml(Array.isArray(value) ? value.map(part => part.name || part).join(', ') : value)}</dd></div>`).join('')}</dl>` : ''}
          <details><summary>Relationship history</summary>${(item.history || []).map(event => `<p><strong>${this.escapeHtml(event.date)}</strong> ${this.escapeHtml(event.relationship)} ${this.escapeHtml(event.note)}</p>`).join('')}</details>
        </article>`;
      }).join('') || '<p class="ccgb-empty-result">No dated creature relationships yet.</p>';
    }

    renderInventoryPanel(content) {
      const records = this.characterSheet && this.characterSheet.inventory;
      if (!records) return this.sheetUnavailable(content, 'Inventory');
      content.className = 'ccgb-sheet-grid';
      content.innerHTML = records.map(item => `<article class="ccgb-sheet-card"><h2>${this.escapeHtml(item.name)}</h2><p><strong>${this.escapeHtml(item.category)}</strong> - ${this.escapeHtml(item.method)} ${this.escapeHtml(item.acquired)}</p><p>${this.escapeHtml(item.description)}</p></article>`).join('') || '<p class="ccgb-empty-result">No historically owned items at this date.</p>';
    }

    renderRelationshipsPanel(content) {
      const records = this.characterSheet && this.characterSheet.relationships;
      if (!records) return this.sheetUnavailable(content, 'Relationships');
      content.className = 'ccgb-sheet-grid';
      const grouped = records.reduce((result, item) => {
        (result[item.type || 'Other'] ||= []).push(item);
        return result;
      }, {});
      content.innerHTML = Object.entries(grouped).map(([type, items]) => `<section class="ccgb-sheet-card"><h2>${this.escapeHtml(type)}</h2><div class="ccgb-relationship-history">${items.map(item => `<article><strong>${this.escapeHtml((item.people || []).join(', ') || 'Relationship event')}</strong><span>${this.escapeHtml(item.date)}</span><p>${this.escapeHtml(item.detail || item.event_type)}</p></article>`).join('')}</div></section>`).join('') || '<p class="ccgb-empty-result">No effective relationship events at this date.</p>';
    }

    renderWoundsPanel(content) {
      if (!this.characterSheet) return this.sheetUnavailable(content, 'Wounds');
      const wounds = this.characterSheet.wounds || [];
      content.className = 'ccgb-sheet-grid';
      content.innerHTML = `<section class="ccgb-sheet-card"><h2>Battle state</h2><p>${this.characterSheet.battle?.active ? `In battle: ${this.escapeHtml(this.characterSheet.battle.name)}` : 'Not currently in battle.'}</p></section>${wounds.map(item => `<article class="ccgb-sheet-card ccgb-wound is-${this.escapeHtml(item.severity)}"><h2>${this.escapeHtml(item.severity)} wound</h2><p>${this.escapeHtml(item.note || 'No details recorded.')}</p><small>${this.escapeHtml(item.created_at || '')}</small></article>`).join('') || '<p class="ccgb-empty-result">No campaign wounds.</p>'}`;
    }

    renderAttributesPanel(content) {
      content.className = 'ccgb-panel-grid ccgb-attributes-panel';
      const summary = (this.characterSheet && this.characterSheet.attributes) || (this.board && this.board.character_attributes);
      if (!summary) {
        const linked = Boolean(this.characterId);
        content.innerHTML = `
          <section class="ccgb-attribute-card ccgb-attribute-empty">
            <h2>${linked ? 'Loading attributes…' : 'Attributes unavailable'}</h2>
            <p>${linked
              ? 'Your linked World Builder character data is being loaded.'
              : 'No World Builder character is linked to this player.'}</p>
          </section>`;
        return;
      }

      const escapeHtml = value => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
      const abilityRecords = new Map((summary.attributes || []).map(item => [item.name, item]));
      const skillRecords = new Map((summary.skills || []).map(item => [item.name, item]));
      const statText = record => {
        const base = Number(record?.value || 0);
        const bonus = Number(record?.bonus || 0);
        return `${base}${bonus ? ` (${bonus > 0 ? '+' : ''}${bonus})` : ''}`;
      };
      const abilityTitle = ability => {
        const breakdown = abilityRecords.get(ability)?.breakdown || {};
        return [
          `Base: ${Number(breakdown.base || 0)}`,
          `Wand: ${Number(breakdown.wand || 0)}`,
          `Accessories: ${Number(breakdown.accessories || 0)}`,
          `Passive: ${Number(breakdown.passive || 0)}`
        ].join('\n');
      };
      const characteristicTitle = item => {
        const breakdown = item?.breakdown || {};
        return [
          `Base: ${Number(breakdown.base || 0)}`,
          `Passive: ${Number(breakdown.passive || 0)}`
        ].join('\n');
      };
      const skillTitle = skill => {
        const record = skillRecords.get(skill) || {};
        const breakdown = record.breakdown || {};
        // This is deliberately a fixed ledger. Never trust an older cached
        // `sources` array: every row must appear even when its value is zero.
        return [
          ['Buys', 'buys'],
          ['Corecourses', 'core_courses'],
          ['Electives', 'elective_courses'],
          ['Traits', 'trait_bonus'],
          ['Wand parts', 'wand_parts'],
          ['Wand', 'wand'],
          ['Quality', 'wand_quality'],
          ['Accessories', 'accessories'],
          ['Passive', 'passive'],
          ['Eminence', 'eminence'],
          ['Temp', 'temporary']
        ].map(([label, key]) => `${label}: ${Number(breakdown[key] ?? 0)}`).join('\n');
      };
      const abilityOrder = ['Power', 'Erudition', 'Panache', 'Naturalism'];
      const skillsByAbility = {
        Power: ['Charms', 'Dark Arts', 'Defense', 'Transfiguration'],
        Erudition: ['Runes', 'Arithmancy', 'Muggles', 'History'],
        Panache: ['Flying', 'Alchemy', 'Potions', 'Artificing', 'Herbology'],
        Naturalism: ['Astronomy', 'Divination', 'Creatures', 'Perception', 'Social']
      };
      const abilityGroups = abilityOrder.map(ability => `
        <div class="ccgb-roll-group">
          <button class="ccgb-roll-pill is-ability" data-roll-type="ability" data-target-id="${escapeHtml(ability)}" title="${escapeHtml(abilityTitle(ability))}">
            <span>${escapeHtml(ability)}</span><strong>${escapeHtml(statText(abilityRecords.get(ability)))}</strong>
          </button>
          <div class="ccgb-skill-pills">
            ${(skillsByAbility[ability] || []).map(skill => `
              <button class="ccgb-roll-pill is-skill" data-roll-type="skill" data-target-id="${escapeHtml(skill)}" title="${escapeHtml(skillTitle(skill))}">
                <span>${escapeHtml(skill)}</span><strong>${escapeHtml(statText(skillRecords.get(skill)))}</strong>
              </button>`).join('')}
          </div>
        </div>`).join('');
      const characteristicPills = (summary.characteristics || []).map(item => `
        <button class="ccgb-roll-pill is-characteristic" data-roll-type="characteristic" data-target-id="${escapeHtml(item.name)}" title="${escapeHtml(characteristicTitle(item))}">
          <span>${escapeHtml(item.name)}</span><strong>${Math.max(1, Math.min(5, Number(item.dice) || 1))}d10</strong>
        </button>`).join('');
      const parentalPills = (summary.parental_values || []).map(item => `
        <button class="ccgb-roll-pill is-parental" data-roll-type="parental" data-target-id="${escapeHtml(item.name)}" title="Roll ${escapeHtml(item.name)}">
          <span>${escapeHtml(item.name)}</span><strong>${Number(item.value) || 0}</strong>
        </button>`).join('');
      const traitPills = (summary.traits || []).length
        ? summary.traits.map(trait => `<span class="ccgb-roll-pill is-trait">${escapeHtml(trait)}</span>`).join('')
        : '<p class="ccgb-no-rolls">No traits recorded.</p>';

      content.innerHTML = `
        <section class="ccgb-attribute-card ccgb-ability-card">
          <h2>Ability and Skill Rolls</h2>
          <div class="ccgb-ability-grid">${abilityGroups}</div>
        </section>
        <div class="ccgb-attribute-lower-grid">
          <section class="ccgb-attribute-card">
            <h2>Characteristics Rolls</h2>
            <div class="ccgb-roll-list">${characteristicPills}</div>
          </section>
          <div class="ccgb-attribute-stack">
            <section class="ccgb-attribute-card">
              <h2>Parental Rolls</h2>
              <div class="ccgb-roll-list">${parentalPills}</div>
            </section>
            <section class="ccgb-attribute-card">
              <h2>Traits</h2>
              <div class="ccgb-roll-list is-traits">${traitPills}</div>
            </section>
          </div>
        </div>`;
      this.bindRollButtons(content);
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
      const locatorLayer = document.createElement('div');
      locatorLayer.className = 'ccgb-player-locators';
      locatorLayer.setAttribute('aria-hidden', 'true');
      viewport.appendChild(locatorLayer);
      const stage = document.createElement('div');
      stage.className = 'ccgb-map-stage';
      const map = maps.find(item => item.record_id === this.activeMapId) || maps[0];
      stage._ccgbZoomProfile = map.zoom_profile || {};
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

    zoomClicks(state) {
      return Math.max(0, Number.isFinite(state.zoomClicks)
        ? state.zoomClicks
        : Math.round(Math.log(Math.max(1, state.scale)) / Math.log(MAP_ZOOM_STEP)));
    }

    zoomTier(state) {
      const clicks = this.zoomClicks(state);
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
      const overviewMode = tier < 6;
      const tierScreenSize = overviewMode
        ? OVERVIEW_DOT_SCREEN_SIZES[tier]
        : TOKEN_SCREEN_SIZES[tier];
      const profileTiers = stage._ccgbZoomProfile?.tiers || {};
      const applicableClicks = Object.keys(profileTiers)
        .map(value => Number(value))
        .filter(value => Number.isFinite(value) && value <= this.zoomClicks(state))
        .sort((left, right) => right - left)[0];
      const tierOverride = Number.isFinite(applicableClicks) ? profileTiers[String(applicableClicks)] : {};
      const configuredTokenSize = Number(tierOverride.token_size);
      const targetActorScreenSize = Math.max(
        8,
        (Number.isFinite(configuredTokenSize) ? configuredTokenSize : tierScreenSize) * sizeRatio
      );
      const actorCameraScale = targetActorScreenSize / Math.max(1, tokenSize * stageScale);
      const actorNetScale = Math.max(0.0001, stageScale * actorCameraScale);
      const screenToActor = value => value / actorNetScale;
      stage.style.setProperty('--map-actor-camera-scale', String(actorCameraScale));
      stage.style.setProperty('--map-nameplate-width', `${screenToActor(LABEL_SCREEN_WIDTHS[tier])}px`);
      stage.style.setProperty('--map-actor-border', `${screenToActor(1)}px`);
      stage.style.setProperty('--map-control-outline', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-control-offset', `${screenToActor(2)}px`);
      const configuredLabelSize = Number(tierOverride.nameplate_size);
      const defaultLabelSize = Number(stage._ccgbZoomProfile?.default_nameplate_size);
      const labelScreenSize = Number.isFinite(configuredLabelSize)
        ? configuredLabelSize
        : (Number.isFinite(defaultLabelSize) ? defaultLabelSize : LABEL_SCREEN_SIZES[tier]);
      stage.style.setProperty('--map-label-font-size', `${screenToActor(labelScreenSize)}px`);
      stage.style.setProperty('--map-label-border', `${screenToActor(1)}px`);
      stage.style.setProperty('--map-label-radius', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-label-gap', `${screenToActor(3)}px`);
      stage.style.setProperty('--map-label-pad-y', `${screenToActor(2)}px`);
      stage.style.setProperty('--map-label-pad-x', `${screenToActor(4)}px`);
      stage.style.setProperty('--map-label-max-width', `${screenToActor(LABEL_SCREEN_WIDTHS[tier])}px`);
      stage.style.setProperty('--map-position-dot-size', `${screenToActor(OVERVIEW_DOT_SCREEN_SIZES[tier] || 8)}px`);
      stage.style.setProperty('--map-position-line-width', `${screenToActor(1.5)}px`);
      stage.dataset.zoomTier = String(tier);
      stage.style.transform = `translate(-50%, -50%) translate(${state.x}px, ${state.y}px) scale(${stageScale})`;
      const zoomLevel = this.root.querySelector('[data-ccgb="zoom-level"]');
      if (zoomLevel) {
        const clicks = Math.max(0, Number(state.zoomClicks || 0));
        zoomLevel.textContent = `Zoom ${Math.round(Number(state.scale || 1) * 100)}% (${clicks} click${clicks === 1 ? '' : 's'})`;
      }
      stage.querySelectorAll('.ccgb-board-actor').forEach(piece => {
        const tracked = piece.classList.contains('is-player-character') || piece.classList.contains('is-name-revealed');
        piece.classList.toggle('is-overview-marker', overviewMode && tracked);
      });
      cancelAnimationFrame(this.actorLabelFrame);
      this.actorLabelFrame = requestAnimationFrame(() => {
        if (viewport.isConnected && stage.isConnected) {
          this.positionPlayerViewportLocators(viewport, stage, tier, labelScreenSize, overviewMode);
        }
      });
      this.queueSharpMapRepaint(stage);
    }

    positionPlayerViewportLocators(viewport, stage, tier, fontSize, overviewMode) {
      const layer = viewport.querySelector('.ccgb-player-locators');
      if (!layer) return;
      const pieces = Array.from(stage.querySelectorAll('.ccgb-board-actor'));
      layer.replaceChildren();
      if (!pieces.length) return;

      const viewportBounds = viewport.getBoundingClientRect();
      const stageBounds = stage.getBoundingClientRect();
      const margin = 9;
      const widthLimit = Math.max(72, Math.min(LABEL_SCREEN_WIDTHS[tier], viewport.clientWidth - margin * 2));
      const occupied = [];
      const overlaps = (left, top, width, height, other) => !(
        left + width + 4 <= other.left || left >= other.right + 4 ||
        top + height + 4 <= other.top || top >= other.bottom + 4
      );
      const edgePointToward = (targetX, targetY, halfWidth, halfHeight) => {
        const centerX = viewport.clientWidth / 2;
        const centerY = viewport.clientHeight / 2;
        const dx = targetX - centerX;
        const dy = targetY - centerY;
        if (!dx && !dy) return { x: centerX, y: centerY };
        const limitX = Math.max(1, centerX - margin - halfWidth);
        const limitY = Math.max(1, centerY - margin - halfHeight);
        const factor = Math.min(
          dx ? limitX / Math.abs(dx) : Infinity,
          dy ? limitY / Math.abs(dy) : Infinity
        );
        return { x: centerX + dx * factor, y: centerY + dy * factor };
      };

      pieces.forEach((piece, index) => {
        piece.classList.add('has-viewport-locator');
        const actorX = stageBounds.left - viewportBounds.left + Number(piece.dataset.actorX ?? 0.5) * stageBounds.width;
        const actorY = stageBounds.top - viewportBounds.top + Number(piece.dataset.actorY ?? 0.5) * stageBounds.height;
        const onScreen = actorX >= margin && actorX <= viewport.clientWidth - margin &&
          actorY >= margin && actorY <= viewport.clientHeight - margin;
        const name = piece.querySelector('.ccgb-position-label')?.textContent || piece.title || 'Character';

        const locator = document.createElement('div');
        locator.className = 'ccgb-player-locator';
        const dot = document.createElement('span');
        dot.className = 'ccgb-player-locator-dot';
        const line = document.createElement('span');
        line.className = 'ccgb-player-locator-line';
        const plaque = document.createElement('span');
        plaque.className = 'ccgb-player-locator-plaque';
        plaque.textContent = name;
        plaque.style.backgroundColor = piece.style.getPropertyValue('--actor-plaque-background') || '#b0b0b0';
        plaque.style.borderColor = piece.style.getPropertyValue('--actor-plaque-border') || '#707070';
        const controlled = piece.classList.contains('is-controlled');
        plaque.classList.toggle('is-controlled', controlled);
        const individualScale = Math.max(0.5, Math.min(3, Number(piece.dataset.nameplateScale || 1)));
        plaque.style.fontSize = `${fontSize * individualScale}px`;
        plaque.style.maxWidth = `${widthLimit}px`;
        locator.append(dot, line, plaque);
        layer.appendChild(locator);

        const plaqueWidth = Math.min(widthLimit, Math.max(72, plaque.offsetWidth || name.length * fontSize * 0.62 + 18));
        const plaqueHeight = Math.max(fontSize + 10, plaque.offsetHeight || fontSize + 10);
        const edgeAnchor = onScreen
          ? { x: actorX, y: actorY }
          : edgePointToward(actorX, actorY, 0, 0);
        const anchorX = edgeAnchor.x;
        const anchorY = edgeAnchor.y;
        const savedOffsetX = Number(piece.dataset.labelOffsetX || 0) * stageBounds.width;
        const savedOffsetY = Number(piece.dataset.labelOffsetY || 0) * stageBounds.height;
        const offscreenPlaque = edgePointToward(actorX, actorY, plaqueWidth / 2, plaqueHeight / 2);
        let plaqueX = onScreen
          ? Math.max(margin + plaqueWidth / 2, Math.min(viewport.clientWidth - margin - plaqueWidth / 2, actorX + savedOffsetX))
          : offscreenPlaque.x;
        let plaqueY = onScreen
          ? Math.max(
              margin + plaqueHeight / 2,
              Math.min(viewport.clientHeight - margin - plaqueHeight / 2, actorY + (savedOffsetX || savedOffsetY ? savedOffsetY : -22))
            )
          : offscreenPlaque.y;

        // Keep multiple player plaques legible without ever allowing one to
        // leave the viewport.  The small stagger is deterministic per player.
        for (let attempt = 0; attempt < 8; attempt += 1) {
          const left = plaqueX - plaqueWidth / 2;
          const top = plaqueY - plaqueHeight / 2;
          if (!occupied.some(other => overlaps(left, top, plaqueWidth, plaqueHeight, other))) break;
          const direction = (index + attempt) % 2 ? 1 : -1;
          plaqueY = Math.max(
            margin + plaqueHeight / 2,
            Math.min(viewport.clientHeight - margin - plaqueHeight / 2, plaqueY + direction * (plaqueHeight + 5))
          );
        }
        occupied.push({
          left: plaqueX - plaqueWidth / 2,
          right: plaqueX + plaqueWidth / 2,
          top: plaqueY - plaqueHeight / 2,
          bottom: plaqueY + plaqueHeight / 2
        });

        plaque.style.left = `${plaqueX}px`;
        plaque.style.top = `${plaqueY}px`;
        dot.style.left = `${anchorX}px`;
        dot.style.top = `${anchorY}px`;
        // The label and leader remain visible, but an off-screen character's
        // clamped edge marker must not masquerade as their real position.
        dot.hidden = !onScreen;
        // An off-screen actor has no fake edge dot. Its leader begins at the
        // plaque and points through the viewport toward the actor's true
        // camera-relative position.
        const lineTargetX = onScreen ? anchorX : actorX;
        const lineTargetY = onScreen ? anchorY : actorY;
        const dx = lineTargetX - plaqueX;
        const dy = lineTargetY - plaqueY;
        const distance = Math.hypot(dx, dy);
        const pieceBounds = piece.getBoundingClientRect();
        const tokenEdge = onScreen && piece.classList.contains('is-token')
          ? Math.max(0, Math.min(pieceBounds.width, pieceBounds.height) / 2)
          : 0;
        line.style.left = `${plaqueX}px`;
        line.style.top = `${plaqueY}px`;
        const visibleDistance = onScreen
          ? Math.max(4, distance - tokenEdge)
          : Math.max(18, Math.min(72, distance));
        line.style.width = `${visibleDistance}px`;
        line.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
        if (controlled) this.bindLocatorPlaqueDrag(plaque, piece, actorX, actorY, viewport, stage);
      });
    }

    bindLocatorPlaqueDrag(plaque, piece, actorX, actorY, viewport, stage) {
      plaque.addEventListener('pointerdown', event => {
        if (event.button !== 0 || !event.ctrlKey) return;
        event.preventDefault();
        event.stopPropagation();
        plaque.setPointerCapture(event.pointerId);
        const actor = (this.board.actors || []).find(item => item.actor_id === piece.dataset.actorId);
        if (!actor) return;
        const viewportBounds = viewport.getBoundingClientRect();
        const stageBounds = stage.getBoundingClientRect();
        const move = moveEvent => {
          const targetX = Math.max(8, Math.min(viewport.clientWidth - 8, moveEvent.clientX - viewportBounds.left));
          const targetY = Math.max(8, Math.min(viewport.clientHeight - 8, moveEvent.clientY - viewportBounds.top));
          const normalizedX = (targetX - actorX) / Math.max(1, stageBounds.width);
          const normalizedY = (targetY - actorY) / Math.max(1, stageBounds.height);
          actor.label_offset = {
            x: Math.max(-1, Math.min(1, normalizedX)),
            y: Math.max(-1, Math.min(1, normalizedY))
          };
          piece.dataset.labelOffsetX = String(actor.label_offset.x);
          piece.dataset.labelOffsetY = String(actor.label_offset.y);
          plaque.style.left = `${targetX}px`;
          plaque.style.top = `${targetY}px`;
          const locator = plaque.parentElement;
          const dot = locator?.querySelector('.ccgb-player-locator-dot');
          const line = locator?.querySelector('.ccgb-player-locator-line');
          if (dot) {
            dot.style.left = `${actorX}px`;
            dot.style.top = `${actorY}px`;
            dot.hidden = false;
          }
          if (line) {
            const dx = actorX - targetX;
            const dy = actorY - targetY;
            line.style.left = `${targetX}px`;
            line.style.top = `${targetY}px`;
            line.style.width = `${Math.max(4, Math.hypot(dx, dy))}px`;
            line.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
          }
        };
        const end = () => {
          plaque.removeEventListener('pointermove', move);
          plaque.removeEventListener('pointerup', end);
          plaque.removeEventListener('pointercancel', end);
          this.send({
            v: VERSION,
            type: 'board_label_move',
            person_id: actor.actor_id,
            label_offset: actor.label_offset
          });
        };
        plaque.addEventListener('pointermove', move);
        plaque.addEventListener('pointerup', end);
        plaque.addEventListener('pointercancel', end);
      });
    }

    queueSharpMapRepaint(stage) {
      if (!stage?.isConnected) return;
      stage.classList.add('is-camera-moving');
      clearTimeout(this.mapRepaintTimer);
      cancelAnimationFrame(this.mapRepaintFrame);
      this.mapRepaintTimer = setTimeout(() => {
        if (!stage.isConnected) return;
        stage.classList.remove('is-camera-moving');
        const image = stage.querySelector(':scope > img');
        if (!image) return;
        image.classList.add('is-repainting');
        void image.offsetWidth;
        this.mapRepaintFrame = requestAnimationFrame(() => {
          if (!image.isConnected) return;
          image.classList.remove('is-repainting');
        });
      }, 90);
    }

    positionOffscreenPlayerLocator(viewport, stage, tier, actorNetScale) {
      const pieces = Array.from(stage.querySelectorAll('.ccgb-board-actor.is-player-character, .ccgb-board-actor.is-name-revealed'));
      if (!pieces.length) return;
      const viewportBounds = viewport.getBoundingClientRect();
      const stageBounds = stage.getBoundingClientRect();
      const bounds = {
        left: Math.max(viewportBounds.left + 10, stageBounds.left + 10),
        top: Math.max(viewportBounds.top + 10, stageBounds.top + 10),
        right: Math.min(viewportBounds.right - 10, stageBounds.right - 10),
        bottom: Math.min(viewportBounds.bottom - 10, stageBounds.bottom - 10)
      };
      if (bounds.right <= bounds.left || bounds.bottom <= bounds.top) return;
      const fontSize = LABEL_SCREEN_SIZES[tier];
      const maxWidth = LABEL_SCREEN_WIDTHS[tier];
      pieces.forEach(piece => {
        const actorX = stageBounds.left + Number(piece.dataset.actorX ?? 0.5) * stageBounds.width;
        const actorY = stageBounds.top + Number(piece.dataset.actorY ?? 0.5) * stageBounds.height;
        const onScreen = actorX >= bounds.left && actorX <= bounds.right && actorY >= bounds.top && actorY <= bounds.bottom;
        piece.classList.add('has-viewport-locator');
        piece.classList.toggle('is-offscreen-locator', !onScreen);
        const label = piece.querySelector('.ccgb-position-label');
        const name = label?.textContent || 'Character';
        const width = Math.min(maxWidth, Math.max(72, name.length * fontSize * 0.62 + 22));
        const height = fontSize + 14;
        const preferredY = onScreen ? actorY - height / 2 - 18 : actorY;
        const labelX = Math.max(bounds.left + width / 2, Math.min(bounds.right - width / 2, actorX));
        const labelY = Math.max(bounds.top + height / 2, Math.min(bounds.bottom - height / 2, preferredY));
        const shiftX = (labelX - actorX) / actorNetScale;
        const shiftY = (labelY - actorY) / actorNetScale;
        const direction = Math.atan2(actorY - labelY, actorX - labelX);
        const distance = Math.hypot(actorX - labelX, actorY - labelY);
        piece.style.setProperty('--map-position-label-x', `${shiftX}px`);
        piece.style.setProperty('--map-position-label-y', `${shiftY}px`);
        piece.style.setProperty('--map-position-line-x', `${shiftX}px`);
        piece.style.setProperty('--map-position-line-y', `${shiftY}px`);
        piece.style.setProperty(
          '--map-position-line-length',
          `${Math.max(5, distance - Math.min(width, height) / 2) / actorNetScale}px`
        );
        piece.style.setProperty('--map-position-line-angle', `${direction}rad`);
      });
    }

    positionOverviewLabels(viewport, stage, tier, actorNetScale) {
      const pieces = Array.from(stage.querySelectorAll('.ccgb-board-actor.is-overview-marker'));
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
        anchor.piece.style.setProperty('--map-position-line-x', '0px');
        anchor.piece.style.setProperty('--map-position-line-y', '0px');
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
      piece.dataset.nameplateScale = String(Number(actor.nameplate_scale ?? 1));
      piece.dataset.labelOffsetX = String(Number(actor.label_offset?.x || 0));
      piece.dataset.labelOffsetY = String(Number(actor.label_offset?.y || 0));
      piece.style.setProperty('--actor-nameplate-scale', String(Number(actor.nameplate_scale ?? 1)));
      piece.style.setProperty('--actor-label-offset-x', `${Number(actor.label_offset?.x || 0) * MAP_NATIVE_WIDTH}px`);
      piece.style.setProperty('--actor-label-offset-y', `${Number(actor.label_offset?.y || 0) * MAP_NATIVE_HEIGHT}px`);
      piece.classList.toggle('is-player-character', Boolean(actor.is_player_character));
      piece.classList.toggle('is-name-revealed', Boolean(actor.name_revealed));
      piece.style.setProperty('--actor-color', actor.faction_color || '#808080');
      piece.style.setProperty('--actor-group-color', actor.group_color || '#b0b0b0');
      piece.style.setProperty('--actor-plaque-background', actor.plaque_background || '#b0b0b0');
      piece.style.setProperty('--actor-plaque-border', actor.plaque_border || '#707070');
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
      const label = document.createElement('span');
      label.className = 'ccgb-actor-label';
      label.textContent = actor.name || 'Unknown';
      const leader = document.createElement('span');
      leader.className = 'ccgb-position-leader';
      const positionLabel = document.createElement('span');
      positionLabel.className = 'ccgb-position-label';
      positionLabel.textContent = actor.name || 'Unknown';
      piece.append(label, leader, positionLabel);
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
      const viewport = this.root.querySelector('.ccgb-map-viewport');
      const state = this.cameraState(this.activeMapId);
      if (viewport) {
        const tier = this.zoomTier(state);
        const tokenSize = Math.max(1, Number(this.dragging.stage.dataset.tokenSize || 6));
        const stageScale = this.mapStageScale(this.dragging.stage, state);
        const sizeRatio = Math.max(0.35, Math.min(5.5, tokenSize / (MAP_NATIVE_WIDTH * DEFAULT_TOKEN_SCALE)));
        const targetActorScreenSize = Math.max(8, (TOKEN_SCREEN_SIZES[tier] || 8) * sizeRatio);
        const actorNetScale = Math.max(0.0001, stageScale * targetActorScreenSize / Math.max(1, tokenSize * stageScale));
        this.positionPlayerViewportLocators(
          viewport,
          this.dragging.stage,
          tier,
          Number(this.dragging.stage._ccgbZoomProfile?.default_nameplate_size) || LABEL_SCREEN_SIZES[tier],
          tier < 6
        );
      }
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
        piece.dataset.actorX = String(Number(actor.x ?? 0.5));
        piece.dataset.actorY = String(Number(actor.y ?? 0.5));
        piece.style.left = `${Number(actor.x ?? 0.5) * 100}%`;
        piece.style.top = `${Number(actor.y ?? 0.5) * 100}%`;
      });
      const viewport = this.root.querySelector('.ccgb-map-viewport');
      if (viewport) this.applyMapCamera(viewport, stage, this.activeMapId);
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
        controlled_character_ids: ['preview-edward'],
        character_attributes: {
          character_id: 'preview-edward',
          character_name: 'Edward Marksdale',
          as_of: '1943-09-01T08:00',
          attributes: [
            { name: 'Power', value: 4 }, { name: 'Erudition', value: 2 },
            { name: 'Panache', value: 2 }, { name: 'Naturalism', value: 3 }
          ],
          skills: [
            { name: 'Charms', value: 5 }, { name: 'Transfiguration', value: 6 },
            { name: 'Defense', value: 5 }, { name: 'Dark Arts', value: 0 },
            { name: 'Arithmancy', value: 3 }, { name: 'Runes', value: 0 },
            { name: 'History', value: 5 }, { name: 'Muggles', value: 0 },
            { name: 'Potions', value: 5 }, { name: 'Alchemy', value: 0 },
            { name: 'Artificing', value: 0 }, { name: 'Flying', value: 1 },
            { name: 'Herbology', value: 5 }, { name: 'Creatures', value: 3 },
            { name: 'Astronomy', value: 6 }, { name: 'Divination', value: 3 },
            { name: 'Perception', value: 0 }, { name: 'Social', value: 11 }
          ],
          characteristics: [
            { name: 'Fortitude', dice: 1 }, { name: 'Willpower', dice: 1 },
            { name: 'Intellect', dice: 1 }, { name: 'Creativity', dice: 3 },
            { name: 'Equanimity', dice: 2 }, { name: 'Charisma', dice: 3 },
            { name: 'Attractiveness', dice: 2 }, { name: 'Strength', dice: 4 },
            { name: 'Agility', dice: 5 }
          ],
          parental_values: [
            { name: 'Generosity', value: 9 },
            { name: 'Permissiveness', value: 4 },
            { name: 'Wealth', value: 1 }
          ],
          traits: ['Observant', 'Protective']
        }
      };
      this.activeMapId = 'preview-map';
      this.openSection(this.activeSection);
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
