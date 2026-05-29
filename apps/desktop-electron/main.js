const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const GATEWAY_URL = "http://127.0.0.1:18789";
const GATEWAY_READY_TIMEOUT = 25000;
// After onboard completes, the gateway may not be running yet; allow more time.
const POST_ONBOARD_GATEWAY_TIMEOUT = 60000;

let mainWindow = null;
let tray = null;
let gatewayProcess = null;
let isQuitting = false;
let onboardWindow = null;

// ---------------------------------------------------------------------------
// New-user detection
// ---------------------------------------------------------------------------

/**
 * Returns true when the user has NOT completed initial setup:
 *   - config file is missing, OR
 *   - gateway.mode is not set (openclaw onboard was never run), OR
 *   - no model provider has an API key configured.
 */
function needsOnboarding() {
  const configPath = path.join(os.homedir(), ".openclaw", "openclaw.json");
  if (!fs.existsSync(configPath)) {
    return true;
  }
  try {
    const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
    // No gateway mode → onboard was never run
    if (!config.gateway?.mode) {
      return true;
    }
    // Check if any model provider has a real API key
    const providers = config.models?.providers ?? {};
    const hasApiKey = Object.values(providers).some(
      (p) => (p && typeof p === "object") && (p.apiKey || p.key || p.token),
    );
    // Also accept auth-profiles-based setup (key stored separately)
    const hasAuthProfiles = config.agents?.authProfiles &&
      Object.keys(config.agents.authProfiles).length > 0;
    if (!hasApiKey && !hasAuthProfiles) {
      return true;
    }
    return false;
  } catch (err) {
    console.error("Could not parse openclaw.json; treating as new user:", err.message);
    return true;
  }
}

// ---------------------------------------------------------------------------
// Launch `openclaw onboard --install-daemon` in the system terminal
// ---------------------------------------------------------------------------

/**
 * Spawns the real `openclaw onboard --install-daemon` wizard in a new
 * terminal window so the user gets the identical interactive experience
 * as running it manually from the command line.
 *
 * Returns a Promise that resolves when the terminal process exits.
 */
function runOnboardInTerminal(openclawPath) {
  return new Promise((resolve) => {
    let proc;

    if (process.platform === "win32") {
      // Write a temp .bat file — avoids all cmd.exe quoting/escaping issues.
      const batPath = path.join(os.tmpdir(), "openclaw-onboard.bat");
      fs.writeFileSync(
        batPath,
        `@echo off\r\nnode "${openclawPath}" onboard --install-daemon\r\npause\r\n`,
      );
      proc = spawn("cmd.exe", ["/C", `start "OpenClaw Setup" cmd.exe /K "${batPath}"`], {
        shell: true,
        detached: true,
        stdio: "ignore",
      });
    } else if (process.platform === "darwin") {
      const cmd = `node '${openclawPath}' onboard --install-daemon`;
      const script = `tell application "Terminal"\n        activate\n        do script "${cmd.replace(/"/g, '\\"')}"\n      end tell`;
      proc = spawn("osascript", ["-e", script], { detached: true, stdio: "ignore" });
    } else {
      const cmd = `node "${openclawPath}" onboard --install-daemon`;
      const terminals = [
        ["gnome-terminal", ["--", "bash", "-c", `${cmd}; echo; read -p "Press Enter to close…"`]],
        ["xterm", ["-e", `${cmd}; echo; read -p "Press Enter to close…"`]],
        ["konsole", ["--hold", "-e", cmd]],
        ["xfce4-terminal", ["--hold", "-e", cmd]],
      ];
      for (const [bin, args] of terminals) {
        try { proc = spawn(bin, args, { detached: true, stdio: "ignore" }); break; } catch (_) {}
      }
    }

    if (!proc) {
      proc = spawn("node", [openclawPath, "onboard", "--install-daemon"], {
        stdio: "inherit",
        shell: false,
      });
    }

    proc.unref?.();

    // Poll config every 3 s; resolve as soon as setup looks complete.
    const poll = setInterval(() => {
      if (!needsOnboarding()) {
        clearInterval(poll);
        resolve();
      }
    }, 3000);

    proc.once?.("exit", () => {
      setTimeout(() => {
        clearInterval(poll);
        resolve();
      }, 1500);
    });
  });
}

/**
 * For EXISTING users who want to change their model provider, API key,
 * or any other setting: runs `openclaw onboard` (without --install-daemon)
 * in a terminal window, then reloads the main window when done.
 */
function runSetupChangeInTerminal(openclawPath) {
  return new Promise((resolve) => {
    let proc;

    if (process.platform === "win32") {
      // Write a temp .bat file to avoid cmd.exe quoting issues.
      const batPath = path.join(os.tmpdir(), "openclaw-setup-change.bat");
      fs.writeFileSync(
        batPath,
        `@echo off\r\nnode "${openclawPath}" onboard\r\npause\r\n`,
      );
      proc = spawn("cmd.exe", ["/C", `start "OpenClaw Setup" cmd.exe /K "${batPath}"`], {
        shell: true,
        detached: true,
        stdio: "ignore",
      });
    } else if (process.platform === "darwin") {
      const cmd = `node '${openclawPath}' onboard`;
      const script = `tell application "Terminal"\n        activate\n        do script "${cmd.replace(/"/g, '\\"')}"\n      end tell`;
      proc = spawn("osascript", ["-e", script], { detached: true, stdio: "ignore" });
    } else {
      const cmd = `node "${openclawPath}" onboard`;
      const terminals = [
        ["gnome-terminal", ["--", "bash", "-c", `${cmd}; echo; read -p "Press Enter to close…"`]],
        ["xterm", ["-e", `${cmd}; echo; read -p "Press Enter to close…"`]],
        ["konsole", ["--hold", "-e", cmd]],
        ["xfce4-terminal", ["--hold", "-e", cmd]],
      ];
      for (const [bin, args] of terminals) {
        try { proc = spawn(bin, args, { detached: true, stdio: "ignore" }); break; } catch (_) {}
      }
    }

    if (!proc) {
      proc = spawn("node", [openclawPath, "onboard"], { stdio: "inherit", shell: false });
    }

    proc.unref?.();
    proc.once?.("exit", () => setTimeout(resolve, 1500));

    const poll = setInterval(() => {
      if (!needsOnboarding()) {
        clearInterval(poll);
        setTimeout(resolve, 2000);
      }
    }, 3000);

    setTimeout(() => { clearInterval(poll); resolve(); }, 10 * 60 * 1000);
  });
}

// ---------------------------------------------------------------------------
// Onboarding splash window
// ---------------------------------------------------------------------------

/**
 * Shows a minimal splash window that tells the user setup is launching in
 * a terminal, and keeps the app alive while we wait for onboard to finish.
 */
function createOnboardSplash() {
  onboardWindow = new BrowserWindow({
    width: 680,
    height: 460,
    resizable: false,
    frame: false,
    backgroundColor: "#0f172a",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Build an inline HTML splash — no external file dependency
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>OpenClaw Setup</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
    color: #e2e8f0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    user-select: none;
    -webkit-app-region: drag;
  }
  .logo {
    font-size: 48px;
    margin-bottom: 20px;
    filter: drop-shadow(0 0 20px rgba(99,102,241,0.6));
  }
  h1 {
    font-size: 28px;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 10px;
    letter-spacing: -0.5px;
  }
  p {
    color: #94a3b8;
    font-size: 14px;
    text-align: center;
    max-width: 420px;
    line-height: 1.6;
    margin-bottom: 28px;
  }
  .badge {
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.35);
    border-radius: 12px;
    padding: 14px 22px;
    font-size: 13px;
    color: #a5b4fc;
    -webkit-app-region: no-drag;
  }
  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(99,102,241,0.3);
    border-top-color: #818cf8;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .step-list {
    margin-top: 28px;
    text-align: left;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
    -webkit-app-region: no-drag;
  }
  .step-list li {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    color: #64748b;
  }
  .step-list li.active { color: #a5b4fc; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #334155; flex-shrink: 0; }
  .dot.active { background: #818cf8; box-shadow: 0 0 8px rgba(129,140,248,0.7); }
</style>
</head>
<body>
  <div class="logo">🐾</div>
  <h1>Welcome to OpenClaw</h1>
  <p>A setup terminal has opened. Follow the interactive wizard to choose your AI model provider and configure your assistant.</p>
  <div class="badge">
    <div class="spinner"></div>
    <span>Waiting for setup to complete in terminal…</span>
  </div>
  <ul class="step-list">
    <li class="active"><div class="dot active"></div> Choose model provider (Gemini, OpenAI, Claude…)</li>
    <li><div class="dot"></div> Install gateway service</li>
    <li><div class="dot"></div> Set up workspace &amp; skills</li>
    <li><div class="dot"></div> Launch dashboard</li>
  </ul>
</body>
</html>`;

  onboardWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  onboardWindow.once("ready-to-show", () => {
    onboardWindow.show();
    onboardWindow.focus();
  });

  // Prevent closing the app when this window is closed
  onboardWindow.on("close", (e) => {
    if (!isQuitting) {
      e.preventDefault();
      onboardWindow.hide();
    }
  });
}

function destroyOnboardSplash() {
  if (onboardWindow) {
    isQuitting = false; // allow orderly destroy without triggering app quit
    onboardWindow.destroy();
    onboardWindow = null;
  }
}

// ---------------------------------------------------------------------------
// Gateway
// ---------------------------------------------------------------------------

function startGateway() {
  const openclawPath = path.resolve(__dirname, "../../openclaw.mjs");
  console.log(`Starting OpenClaw gateway from: ${openclawPath}`);

  gatewayProcess = spawn("node", [openclawPath, "gateway", "run", "--force"], {
    detached: false,
    stdio: "inherit",
    shell: false,
  });

  gatewayProcess.on("exit", (code) => {
    console.log(`Gateway process exited with code: ${code}`);
    if (!isQuitting) {
      console.error("Gateway exited unexpectedly! Restarting…");
      startGateway();
    }
  });

  gatewayProcess.on("error", (err) => {
    console.error("Failed to spawn gateway process:", err);
  });
}

async function waitForGateway(timeoutMs) {
  const start = Date.now();
  console.log("Waiting for OpenClaw gateway to become responsive…");
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(GATEWAY_URL);
      if (res.ok || res.status === 401 || res.status === 403 || res.status === 200) {
        console.log("Gateway is active and responsive!");
        return true;
      }
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Main window (dashboard)
// ---------------------------------------------------------------------------

function getGatewayUrl() {
  let url = GATEWAY_URL;
  try {
    const configPath = path.join(os.homedir(), ".openclaw", "openclaw.json");
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
      const token = config.gateway?.auth?.token;
      if (token) {
        url += `#token=${encodeURIComponent(token)}`;
      }
    }
  } catch (err) {
    console.error("Failed to read gateway token from config:", err);
  }
  return url;
}

/**
 * Creates the main BrowserWindow and optionally loads a "connecting…" page
 * while the gateway is still warming up. Call `mainWindow.loadURL(getGatewayUrl())`
 * once the gateway is ready to switch to the real dashboard.
 */
function createWindow(loadingPage = false) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "OpenClaw Assistant",
    backgroundColor: "#0f172a",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    mainWindow.focus();
  });

  if (loadingPage) {
    // Show a premium loading screen while gateway warms up
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>OpenClaw</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
    color: #e2e8f0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    user-select: none;
    -webkit-app-region: drag;
  }
  .logo { font-size: 52px; margin-bottom: 18px; filter: drop-shadow(0 0 20px rgba(99,102,241,.6)); }
  h1 {
    font-size: 26px; font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
  }
  p { color: #64748b; font-size: 14px; margin-bottom: 28px; }
  .spinner {
    width: 36px; height: 36px;
    border: 3px solid rgba(99,102,241,.25);
    border-top-color: #818cf8;
    border-radius: 50%;
    animation: spin .9s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <div class="logo">🐾</div>
  <h1>OpenClaw</h1>
  <p>Starting gateway…</p>
  <div class="spinner"></div>
</body>
</html>`;
    mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  } else {
    mainWindow.loadURL(getGatewayUrl());
  }

  mainWindow.on("close", (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ---------------------------------------------------------------------------
// System tray
// ---------------------------------------------------------------------------

function createTray() {
  const iconPath = path.join(__dirname, "assets", "icon.png");
  const icon = nativeImage.createFromPath(iconPath);

  tray = new Tray(icon.resize({ width: 16, height: 16 }));

  function rebuildMenu() {
    const openclawPath = path.resolve(__dirname, "../../openclaw.mjs");

    const contextMenu = Menu.buildFromTemplate([
      {
        label: "Open Assistant",
        click: () => {
          mainWindow?.show();
          mainWindow?.focus();
        },
      },
      { type: "separator" },
      {
        // Existing users: re-run the full onboard wizard to change
        // model provider, API key, channels, skills, etc.
        label: "⚙️  Change Model / Re-run Setup",
        click: async () => {
          // Disable the menu item while setup is running
          tray.setToolTip("OpenClaw — Setup running in terminal…");

          await runSetupChangeInTerminal(openclawPath);

          // Reload the dashboard so the new model/config takes effect
          tray.setToolTip("OpenClaw Voice Assistant");
          if (mainWindow) {
            mainWindow.loadURL(getGatewayUrl());
            mainWindow.show();
            mainWindow.focus();
          }
          rebuildMenu();
        },
      },
      {
        label: "🔍  Check Gateway Status",
        click: () => {
          // Open a terminal and run `openclaw gateway status`
          const cmd = `node "${openclawPath}" gateway status`;
          if (process.platform === "win32") {
            spawn("cmd.exe",
              ["/C", `start "OpenClaw Gateway Status" cmd.exe /K "${cmd} & pause"`],
              { shell: false, detached: true, stdio: "ignore" },
            ).unref();
          } else if (process.platform === "darwin") {
            const script = `tell application "Terminal" to do script "${cmd.replace(/"/g, '\\"')}"`;
            spawn("osascript", ["-e", script], { detached: true, stdio: "ignore" }).unref();
          } else {
            spawn("xterm", ["-e", `${cmd}; read -p 'Press Enter…'`],
              { detached: true, stdio: "ignore" }
            ).unref();
          }
        },
      },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]);

    tray.setContextMenu(contextMenu);
  }

  tray.setToolTip("OpenClaw Voice Assistant");
  rebuildMenu();

  tray.on("click", () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}

// Track whether we are in the middle of the onboard→main handoff
let isTransitioning = false;

app.whenReady().then(async () => {
  const openclawPath = path.resolve(__dirname, "../../openclaw.mjs");

  if (needsOnboarding()) {
    console.log("New user detected — launching OpenClaw onboarding wizard.");
    createOnboardSplash();
    await runOnboardInTerminal(openclawPath);
    console.log("Onboarding complete (or terminal closed). Proceeding to gateway…");
  }

  // IMPORTANT: create the main window BEFORE destroying the splash so that
  // window-all-closed never fires between the two (which would quit the app).
  isTransitioning = true;
  createWindow(/* loadingPage= */ true); // shows "Starting gateway…" instantly
  destroyOnboardSplash();                // now safe — mainWindow keeps app alive
  isTransitioning = false;

  // Start gateway (daemon installed by onboard may already be running;
  // --force handles port conflicts gracefully).
  startGateway();

  const ready = await waitForGateway(GATEWAY_READY_TIMEOUT);
  if (!ready) {
    console.error("OpenClaw gateway failed to start within the timeout period.");
  }

  // Switch the loading screen to the real dashboard URL
  if (mainWindow) {
    mainWindow.loadURL(getGatewayUrl());
  }

  createTray();

  try {
    app.setLoginItemSettings({ openAtLogin: true });
  } catch (e) {
    console.warn("Could not set login item settings:", e.message);
  }
});

app.on("window-all-closed", () => {
  // During the splash→main transition there is a brief gap with no windows;
  // do not quit during that period.
  if (isTransitioning) return;
  if (process.platform !== "darwin") {
    isQuitting = true;
    app.quit();
  }
});


app.on("before-quit", () => {
  isQuitting = true;
  if (gatewayProcess) {
    console.log("Terminating OpenClaw gateway process…");
    gatewayProcess.kill();
  }
});
