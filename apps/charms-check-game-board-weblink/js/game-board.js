(() => {
  'use strict';

  const VERSION = 1;
  const POLL_DELAY_MS = 2000;
  const REQUEST_TIMEOUT_MS = 10000;

  class GameBoardClient {
    constructor(options) {
      this.options = options;
      this.root = document.getElementById('gameboard');
      if (!this.root) throw new Error('Missing Game Board root: gameboard');
      this.apiBase = String(options.apiBase || '').replace(/\/$/, '');
      this.storageKey = options.storageKey || 'charms-check-game-board-invite';
      this.admissionStorageKey = `${this.storageKey}-admission`;
      this.invite = '';
      this.requestId = '';
      this.pollToken = '';
      this.socket = null;
      this.pollTimer = null;
      this.currentAnnouncement = '';
      this.state = 'unavailable';
      this.intentionalClose = false;
      this.requestingAdmission = false;
      this.render();
      this.bind();
    }

    render() {
      this.root.innerHTML = `
        <div class="ccgb-scroll">
          <div class="ccgb-rule"></div>
          <h1>Game Board</h1>
          <p class="ccgb-status" data-ccgb="status">Preparing your invitation…</p>
          <div class="ccgb-spinner" data-ccgb="spinner" aria-hidden="true"></div>
          <section data-ccgb="connected" hidden>
            <p class="ccgb-welcome">Welcome, <strong data-ccgb="player"></strong>.</p>
            <p data-ccgb="session"></p>
            <div class="ccgb-quality">
              <span class="ccgb-quality-dot" data-ccgb="quality-dot"></span>
              <span data-ccgb="quality-text">Measuring connection</span>
            </div>
            <div class="ccgb-announcement" data-ccgb="announcement" hidden>
              <h2>Message from the Headmaster</h2>
              <p data-ccgb="message"></p>
              <button type="button" data-ccgb="acknowledge">Acknowledge</button>
            </div>
          </section>
          <button type="button" data-ccgb="retry" hidden>Request admission again</button>
          <div class="ccgb-rule"></div>
        </div>`;
    }

    bind() {
      this.element('acknowledge').addEventListener('click', () => this.acknowledge());
      this.element('retry').addEventListener('click', () => this.requestAdmission());
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
      this.element('connected').hidden = !connected;
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
          this.show('unavailable', 'The connection could not be opened.', { retry: true });
        }
      });
      this.socket.addEventListener('close', () => {
        clearTimeout(connectionTimer);
        if (this.intentionalClose) {
          this.intentionalClose = false;
          return;
        }
        if (!['revoked', 'expired'].includes(this.state)) {
          this.setQuality('disconnected', 'Disconnected');
          this.show('disconnected', 'Connection lost. The Headmaster must approve you again.', { retry: true });
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
        this.element('player').textContent = message.player || 'Player';
        this.element('session').textContent = message.session || '';
        this.show('connected', 'You are connected.', { connected: true });
        this.setQuality('good', 'Connected — measuring latency');
      } else if (message.type === 'heartbeat') {
        this.send({ v: VERSION, type: 'heartbeat_ack', id: message.id });
      } else if (message.type === 'connection_quality') {
        const latency = Number.isFinite(Number(message.latency_ms))
          ? `${Math.round(Number(message.latency_ms))} ms`
          : 'Measuring connection';
        this.setQuality(message.quality || 'fair', latency);
      } else if (message.type === 'announcement') {
        this.currentAnnouncement = message.id;
        this.element('message').textContent = message.message || '';
        this.element('announcement').hidden = false;
      } else if (message.type === 'access_revoked') {
        this.show('revoked', message.message || 'Access was revoked.');
      } else if (message.type === 'session_expired') {
        this.show('expired', message.message || 'The session has ended.');
      } else if (message.type === 'server_error') {
        console.warn('[Charms Check] Game Board message:', message.message);
      }
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
      this.element('player').textContent = 'Hermione';
      this.element('session').textContent = 'Saturday Evening Session';
      this.show('connected', 'You are connected.', { connected: true });
      this.setQuality('good', 'Good — 84 ms');
      this.currentAnnouncement = 'preview-announcement';
      this.element('message').textContent = 'Welcome. The first activity will begin shortly.';
      this.element('announcement').hidden = false;
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
