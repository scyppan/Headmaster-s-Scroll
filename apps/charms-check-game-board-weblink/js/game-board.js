(() => {
  'use strict';

  const VERSION = 1;
  const POLL_DELAY_MS = 2000;
  const REQUEST_TIMEOUT_MS = 10000;
  const MAP_NATIVE_WIDTH = 3840;
  const MAP_NATIVE_HEIGHT = 2960;
  const MAP_ASPECT_RATIO = MAP_NATIVE_WIDTH / MAP_NATIVE_HEIGHT;
  const MAP_ZOOM_STEP = 1.15;
  const MAP_MAX_ZOOM = 32;
  const MAP_PAN_STEP = 24;
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
      this.mapCameraDrag = null;
      this.mapResizeObserver = null;
      this.mapCameraFrame = 0;
      this.dragging = null;
      this.lastMovePreview = 0;
      this.activeSection = 'overview';
      this.chatMessages = [];
      this.render();
      this.bind();
      this.restoreLayout();
      this.openSection('overview');
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
        const mapIds = new Set((this.board.maps || []).map(item => item.record_id));
        const controlled = (this.board.actors || []).find(actor =>
          (this.board.controlled_character_ids || []).includes(actor.actor_id)
        );
        if (controlled && mapIds.has(controlled.map_id)) this.activeMapId = controlled.map_id;
        else if (!mapIds.has(this.activeMapId)) this.activeMapId = this.board.maps?.[0]?.record_id || '';
        if (this.activeSection === 'board') this.renderBoardView();
      } else if (message.type === 'board_move_preview') {
        const actor = (this.board.actors || []).find(item => item.actor_id === message.person_id);
        if (actor) {
          actor.map_id = message.map_id;
          actor.x = Number(message.x);
          actor.y = Number(message.y);
          if (this.activeSection === 'board') this.positionBoardActors();
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
          this.renderBoardView();
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
      this.setupMapCamera(viewport, stage, map.record_id, Number(map.token_scale || 0.0055));
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

    cameraState(mapId) {
      if (!this.mapCameraStates.has(mapId)) {
        this.mapCameraStates.set(mapId, { scale: 1, x: 0, y: 0 });
      }
      return this.mapCameraStates.get(mapId);
    }

    setupMapCamera(viewport, stage, mapId, tokenScale = 0.0055) {
      const sizeStage = () => {
        cancelAnimationFrame(this.mapCameraFrame);
        this.mapCameraFrame = requestAnimationFrame(() => {
          if (!viewport.isConnected || !stage.isConnected) return;
          const availableWidth = Math.max(1, viewport.clientWidth);
          const availableHeight = Math.max(1, viewport.clientHeight);
          const width = Math.min(
            MAP_NATIVE_WIDTH,
            availableWidth,
            availableHeight * MAP_ASPECT_RATIO
          );
          const height = width / MAP_ASPECT_RATIO;
          stage.style.width = `${Math.floor(width * 100) / 100}px`;
          stage.style.height = `${Math.floor(height * 100) / 100}px`;
          const tokenSize = Math.max(6, width * Math.max(0.002, Math.min(0.03, tokenScale)));
          stage.style.setProperty('--map-token-size', `${tokenSize}px`);
          stage.style.setProperty('--map-dot-size', `${Math.max(4, tokenSize * 0.55)}px`);
          stage.style.setProperty('--map-nameplate-width', `${Math.max(46, tokenSize * 3)}px`);
          stage.dataset.renderWidth = String(Math.round(width));
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
          const worldX = (cursorX - state.x) / state.scale;
          const worldY = (cursorY - state.y) / state.scale;
          const next = Math.max(1, Math.min(MAP_MAX_ZOOM, state.scale * (MAP_ZOOM_STEP ** direction)));
          state.x = cursorX - worldX * next;
          state.y = cursorY - worldY * next;
          state.scale = next;
        } else if (event.altKey) {
          state.x += direction * MAP_PAN_STEP;
        } else {
          state.y += direction * MAP_PAN_STEP;
        }
        this.applyMapCamera(viewport, stage, mapId);
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
        this.applyMapCamera(viewport, stage, mapId);
      });
      const endPan = event => {
        if (this.mapCameraDrag?.pointerId !== event.pointerId) return;
        this.mapCameraDrag = null;
        viewport.classList.remove('is-camera-panning');
        if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
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
      const boundX = Math.max(0, (stage.offsetWidth * state.scale - viewport.clientWidth) / 2);
      const boundY = Math.max(0, (stage.offsetHeight * state.scale - viewport.clientHeight) / 2);
      state.x = Math.max(-boundX, Math.min(boundX, state.x));
      state.y = Math.max(-boundY, Math.min(boundY, state.y));
      stage.style.transform = `translate(-50%, -50%) translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
    }

    resetMapCamera(mapId) {
      if (!mapId) return;
      this.mapCameraStates.set(mapId, { scale: 1, x: 0, y: 0 });
      const viewport = this.root.querySelector('.ccgb-map-viewport');
      const stage = this.root.querySelector('.ccgb-map-stage');
      if (viewport && stage) this.applyMapCamera(viewport, stage, mapId);
    }

    createBoardActor(stage, actor) {
      const piece = document.createElement('button');
      piece.type = 'button';
      piece.className = `ccgb-board-actor is-${actor.display_mode || 'dot'}`;
      piece.dataset.actorId = actor.actor_id;
      piece.style.setProperty('--actor-color', actor.faction_color || '#808080');
      piece.title = actor.faction_revealed && actor.faction_name
        ? `${actor.name || 'Unknown'} — ${actor.faction_name}`
        : (actor.name || 'Unknown');
      const controlled = (this.board.controlled_character_ids || []).includes(actor.actor_id);
      piece.classList.toggle('is-controlled', controlled);

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
        plate.textContent = actor.name || 'Character';
        piece.appendChild(plate);
      }
      if (actor.display_mode !== 'nameplate') {
        const label = document.createElement('span');
        label.className = 'ccgb-actor-label';
        label.textContent = actor.name || 'Unknown';
        piece.appendChild(label);
      }
      piece.style.left = `${Number(actor.x || 0.5) * 100}%`;
      piece.style.top = `${Number(actor.y || 0.5) * 100}%`;
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
        maps: [{ record_id: 'preview-map', name: 'Great Hall', asset: null }],
        actors: [
          { actor_id: 'preview-edward', map_id: 'preview-map', x: 0.32, y: 0.48, display_mode: 'nameplate', name: 'Edward Marksdale', faction_color: '#7b3f2b' },
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
