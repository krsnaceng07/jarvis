// JARVIS WhatsApp bridge.
//
// Node sidecar for the Python channel plugin. stdout is a JSON-lines protocol;
// all human-readable output (pino logs, terminal QR) goes to stderr so the
// Python reader never has to parse mixed content.
//
// Modes:
//   node bridge.js listen --auth-dir <dir>
//   node bridge.js login  --auth-dir <dir> [--no-terminal] [--phone <digits>] [--force]
//
// Events written to stdout:
//   {"event":"qr","qr":"..."}                        login: fresh QR payload
//   {"event":"pairing_code","code":"ABCD-EFGH"}      login --phone
//   {"event":"connected","who":"<jid>"}              socket opened
//   {"event":"listener_ready","who":"<jid>"}         listen mode ready
//   {"event":"message","remoteJid":...}              inbound message
//   {"event":"send_result","requestId":...,"ok":true,"messageId":"..."}
//   {"event":"listener_closed","error":"..."}        socket gave up
//
// Commands read from stdin:
//   {"action":"send","target":"<jid>","text":"...","requestId":"..."}
//   {"action":"stop"}

'use strict';

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const baileys = require('@whiskeysockets/baileys');
const makeWASocket = baileys.default || baileys.makeWASocket;
const useMultiFileAuthState = baileys.useMultiFileAuthState;
const DisconnectReason = baileys.DisconnectReason;
const Browsers = baileys.Browsers;
const jidNormalizedUser = baileys.jidNormalizedUser;

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function log(...args) {
  process.stderr.write(`[bridge] ${args.join(' ')}\n`);
}

// Baileys expects a pino-shaped logger. Keep it silent so user/group names and
// message metadata never reach logs, and stdout stays pure JSON protocol.
const SILENT_LOGGER = (() => {
  const noop = () => {};
  const logger = {
    level: 'silent',
    trace: noop,
    debug: noop,
    info: noop,
    warn: noop,
    error: noop,
    fatal: noop,
    child: () => logger,
  };
  return logger;
})();

function parseArgs(argv) {
  const opts = { mode: null, authDir: null, terminal: true, phone: null, force: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === 'listen' || arg === 'login') {
      opts.mode = arg;
    } else if (arg === '--auth-dir') {
      opts.authDir = argv[i + 1];
      i += 1;
    } else if (arg === '--no-terminal') {
      opts.terminal = false;
    } else if (arg === '--phone') {
      opts.phone = argv[i + 1];
      i += 1;
    } else if (arg === '--force') {
      opts.force = true;
    }
  }
  return opts;
}

function clearAuthDir(authDir) {
  for (const entry of fs.readdirSync(authDir)) {
    if (entry === '.' || entry === '..') continue;
    fs.rmSync(path.join(authDir, entry), { recursive: true, force: true });
  }
}

function extractText(message) {
  if (!message) return '';
  const inner =
    message.ephemeralMessage?.message ||
    message.viewOnceMessage?.message ||
    message.viewOnceMessageV2?.message ||
    message.documentWithCaptionMessage?.message ||
    message;
  return (
    inner.conversation ||
    inner.extendedTextMessage?.text ||
    inner.imageMessage?.caption ||
    inner.videoMessage?.caption ||
    inner.buttonsResponseMessage?.selectedDisplayText ||
    inner.templateButtonReplyMessage?.selectedDisplayText ||
    inner.listResponseMessage?.title ||
    ''
  );
}

function requestPairingCode(sock, phone, attempt) {
  sock
    .requestPairingCode(phone)
    .then((code) => {
      emit({ event: 'pairing_code', code });
      log(`pairing code requested (${phone})`);
    })
    .catch((err) => {
      log(`pairing code request failed: ${err.message}`);
      if (attempt < 4) {
        setTimeout(() => requestPairingCode(sock, phone, attempt + 1), 3000);
      } else {
        emit({ event: 'listener_closed', error: `pairing code failed: ${err.message}` });
      }
    });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.mode || !opts.authDir) {
    log('usage: bridge.js <listen|login> --auth-dir <dir>');
    process.exit(2);
  }

  fs.mkdirSync(opts.authDir, { recursive: true });
  if (opts.mode === 'login' && opts.force) {
    clearAuthDir(opts.authDir);
    log('cleared auth dir for --force relink');
  }

  const { state, saveCreds } = await useMultiFileAuthState(opts.authDir);

  let sock = null;
  let stopping = false;
  let ready = false;
  let pairingRequested = false;
  let restartTimer = null;
  let loginExited = false;

  function connect() {
    if (stopping) return;
    sock = makeWASocket({
      auth: state,
      browser: Browsers.ubuntu('JARVIS'),
      syncFullHistory: false,
      markOnlineOnConnect: false,
      printQRInTerminal: false,
      logger: SILENT_LOGGER,
      generateHighQualityLinkPreview: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        emit({ event: 'qr', qr });
        if (opts.terminal) {
          try {
            require('qrcode-terminal').generate(qr, { small: true }, (rendered) => {
              process.stderr.write(`${rendered}\n`);
            });
          } catch (err) {
            log(`terminal QR failed: ${err.message}`);
          }
        }
        if (opts.mode === 'login' && opts.phone && !pairingRequested) {
          pairingRequested = true;
          requestPairingCode(sock, opts.phone, 0);
        }
      }

      if (connection === 'open') {
        ready = true;
        const who = sock.user ? jidNormalizedUser(sock.user.id) : 'linked';
        emit({ event: 'connected', who });
        if (opts.mode === 'listen') {
          emit({ event: 'listener_ready', who });
        } else if (!loginExited) {
          loginExited = true;
          // Give Baileys a beat to flush creds.json before the parent re-reads it.
          setTimeout(() => process.exit(0), 700);
        }
      }

      if (connection === 'close') {
        ready = false;
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const loggedOut = statusCode === DisconnectReason.loggedOut;
        const restartRequired = statusCode === DisconnectReason.restartRequired;
        if (stopping) return;
        if (loggedOut) {
          emit({ event: 'listener_closed', error: 'logged out' });
          log('logged out; not reconnecting');
          if (opts.mode === 'login') process.exit(1);
          return;
        }
        const delay = restartRequired ? 250 : 2000;
        log(`connection closed (code ${statusCode ?? 'unknown'}); reconnecting in ${delay}ms`);
        if (opts.mode === 'login') {
          emit({
            event: 'listener_closed',
            error: `connection closed during login (code ${statusCode ?? 'unknown'})`,
          });
        }
        if (restartTimer) clearTimeout(restartTimer);
        restartTimer = setTimeout(() => {
          restartTimer = null;
          connect();
        }, delay);
      }
    });

    sock.ev.on('messages.upsert', ({ messages, type }) => {
      if (type !== 'notify') return;
      for (const msg of messages || []) {
        const remoteJid = msg.key?.remoteJid || '';
        if (!remoteJid || remoteJid === 'status@broadcast') continue;
        const text = extractText(msg.message);
        if (!text) continue;
        emit({
          event: 'message',
          remoteJid,
          fromMe: Boolean(msg.key.fromMe),
          pushName: msg.pushName || '',
          messageId: msg.key.id || '',
          text,
        });
      }
    });
  }

  connect();

  function shutdown(reason) {
    if (stopping) return;
    stopping = true;
    if (restartTimer) clearTimeout(restartTimer);
    // Never call sock.logout() here: logout unlinks the device server-side and
    // forces a fresh QR on the next start. Just drop the socket.
    try {
      sock?.end(new Error(reason));
    } catch (err) {
      log(`socket close failed: ${err.message}`);
    }
    setTimeout(() => process.exit(0), 100);
  }

  if (opts.mode === 'listen') {
    const rl = readline.createInterface({ input: process.stdin });
    rl.on('line', async (line) => {
      const raw = line.trim();
      if (!raw) return;
      let cmd;
      try {
        cmd = JSON.parse(raw);
      } catch (err) {
        log(`invalid stdin command: ${err.message}`);
        return;
      }

      const action = cmd.action;
      if (action === 'stop') {
        shutdown('bridge stop requested');
        return;
      }

      if (action === 'send') {
        const target = String(cmd.target || '').trim();
        const text = String(cmd.text || '');
        const requestId = cmd.requestId || null;
        if (!target || !text) {
          emit({ event: 'send_result', requestId, ok: false, error: 'missing target or text' });
          return;
        }
        try {
          const sent = await sock.sendMessage(target, { text });
          emit({
            event: 'send_result',
            requestId,
            ok: true,
            messageId: sent?.key?.id || '',
          });
        } catch (err) {
          emit({ event: 'send_result', requestId, ok: false, error: err.message });
        }
      }
    });
    // Parent Python died or closed the pipe: do not leave a linked-device
    // socket behind, and never let it hijack the next bridge start.
    rl.on('close', () => shutdown('bridge stdin closed'));
  }

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('uncaughtException', (err) => {
    log(`uncaught exception: ${err.stack || err.message}`);
    emit({ event: 'listener_closed', error: err.message });
  });
  process.on('unhandledRejection', (err) => {
    log(`unhandled rejection: ${err?.stack || err}`);
  });
}

main().catch((err) => {
  log(`fatal: ${err.stack || err.message}`);
  process.exit(1);
});
