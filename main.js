const { app, BrowserWindow, ipcMain, Notification } = require('electron');
const { spawn, exec, execSync } = require('child_process');
const path = require('path');
const net = require('net');
const fs = require('fs');
const url = require('url');

let mainWindow;
let pythonProcess;
let setupProcess;
let isQuitting = false;
let isPiP = false;
let normalBounds = null;

// Track Chrome debug ports used by our scrapers (Bet365, BetBurger, Betano, Novibet)
const SCRAPER_DEBUG_PORTS = [9222, 9223, 9224, 9226];

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: "Odds Divergence Monitor",
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      backgroundThrottling: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  const userDataPath = app.getPath('userData');
  const setupMarker = path.join(userDataPath, '.setup_done_v7');
  const userVenvPython = path.join(userDataPath, 'venv', 'Scripts', 'python.exe');

  // Verifica se o setup ja foi feito e se o python do venv existe
  const isSetupDone = fs.existsSync(setupMarker) && fs.existsSync(userVenvPython);

  if (!isSetupDone) {
    // Carrega a tela de loading local
    mainWindow.loadFile(path.join(__dirname, 'loading.html'));
    
    console.log("Iniciando First-Run Setup...");
    const logPath = path.join(userDataPath, 'setup_log.txt');
    setupProcess = spawn('cmd.exe', ['/c', `setup.bat "${userDataPath}" > "${logPath}" 2>&1`], {
      cwd: __dirname,
      shell: true
    });

    setupProcess.stdout.on('data', (data) => {
      console.log(`[Setup]: ${data}`);
    });

    setupProcess.stderr.on('data', (data) => {
      console.error(`[Setup Error]: ${data}`);
    });

    setupProcess.on('close', (code) => {
      console.log(`Setup process exited with code ${code}`);
      if (code === 0) {
        // Cria o marcador para nunca mais rodar o setup apenas se teve sucesso
        fs.writeFileSync(setupMarker, 'true');
        
        // Agora inicia o servidor e carrega a pagina real
        startPythonServer();
        waitForServer(8005, () => {
          mainWindow.loadURL('http://127.0.0.1:8005');
        });
      } else {
        console.error(`Setup process failed with code ${code}`);
        if (mainWindow) {
          let logContent = '';
          try {
            logContent = fs.readFileSync(path.join(userDataPath, 'setup_log.txt'), 'utf8');
          } catch (e) {
            logContent = 'Não foi possível ler setup_log.txt: ' + e.message;
          }
          mainWindow.loadURL(url.format({
            pathname: path.join(__dirname, 'error.html'),
            protocol: 'file:',
            slashes: true,
            search: '?type=setup&log=' + encodeURIComponent(logContent)
          }));
        }
      }
    });
  } else {
    // Setup ja feito, inicia direto
    startPythonServer();
    waitForServer(8005, () => {
      mainWindow.loadURL('http://127.0.0.1:8005');
    });
  }

  // Intercepta todos os links target="_blank" e abre no navegador padrao do usuario (Chrome, Edge)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });

  ipcMain.on('toggle-pip', () => {
    if (!mainWindow) return;
    isPiP = !isPiP;
    if (isPiP) {
      normalBounds = mainWindow.getBounds();
      mainWindow.setMinimumSize(300, 400); // Permite encolher
      mainWindow.setAlwaysOnTop(true, 'screen-saver');
      mainWindow.setBounds({
        x: normalBounds.x + normalBounds.width - 380,
        y: normalBounds.y,
        width: 380,
        height: 600
      });
      mainWindow.webContents.send('pip-status', true);
    } else {
      mainWindow.setAlwaysOnTop(false);
      mainWindow.setMinimumSize(1024, 768); // Restaura tamanho mínimo
      if (normalBounds) {
        mainWindow.setBounds(normalBounds);
      } else {
        mainWindow.setSize(1280, 800);
      }
      mainWindow.webContents.send('pip-status', false);
    }
  });

  ipcMain.on('trigger-alert-notification', (event, alertData) => {
    if (mainWindow) {
      mainWindow.flashFrame(true);
    }
    if (Notification && Notification.isSupported() && alertData) {
      try {
        const notif = new Notification({
          title: `⚡ ${alertData.priority || 'DIVERGÊNCIA'} — ${alertData.sport || 'Tênis de Mesa'}`,
          body: `${alertData.match_name || 'Partida'}\n⏱️ Atraso Bet365: ${alertData.delay_seconds || '10'}s\nB365: ${alertData.bet365_score || '-'} vs Ref: ${alertData.betburger_score || alertData.xbet_score || '-'}`,
          silent: true,
          urgency: 'critical'
        });
        notif.on('click', () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        });
        notif.show();
      } catch (e) {}
    }
  });

  mainWindow.on('close', function (e) {
    if (!isQuitting) {
      e.preventDefault();
      isQuitting = true;
      gracefulShutdown();
    }
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function getPythonCommand() {
  const userDataPath = app.getPath('userData');
  // 1. Tenta o ambiente virtual local (venv) do AppData
  const userVenvPython = path.join(userDataPath, 'venv', 'Scripts', 'python.exe');
  if (fs.existsSync(userVenvPython)) {
    return userVenvPython;
  }

  // 2. Tenta o ambiente virtual local (venv) criado no __dirname
  const venvPython = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }

  // 3. Fallbacks antigos caso o venv nao exista
  const localAppData = process.env.LOCALAPPDATA;
  if (localAppData) {
    const py311 = path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe');
    const py312 = path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe');
    if (fs.existsSync(py311)) return py311;
    if (fs.existsSync(py312)) return py312;
  }
  return 'python'; // Fallback
}

function startPythonServer() {
  console.log('Starting Python Backend...');
  const pythonCmd = getPythonCommand();
  const userDataPath = app.getPath('userData');
  
  const logStream = fs.createWriteStream(path.join(userDataPath, 'python_log.txt'), { flags: 'a' });

  // Run python directly without shell wrapping to avoid quoting issues and ensure reliable process termination
  pythonProcess = spawn(pythonCmd, ['app/main.py'], {
    cwd: __dirname,
    shell: false
  });

  pythonProcess.on('error', (err) => {
    console.error(`Failed to start Python process: ${err.message}`);
    logStream.write(`[ERROR] Failed to start Python process: ${err.message}\n`);
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python]: ${data}`);
    logStream.write(`[STDOUT] ${data}\n`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Error]: ${data}`);
    logStream.write(`[STDERR] ${data}\n`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    logStream.write(`[EXIT] Process exited with code ${code}\n`);
  });
}

function waitForServer(port, callback) {
  const client = new net.Socket();
  let retries = 0;
  const maxRetries = 30;

  const tryConnect = () => {
    client.connect({ port: port, host: '127.0.0.1' }, () => {
      client.destroy();
      console.log('Server is ready! Loading page...');
      callback();
    });
  };

  client.on('error', (err) => {
    retries++;
    if (retries >= maxRetries) {
      console.error('Timeout waiting for Python server to start.');
      if (mainWindow) {
        let logContent = '';
        try {
          const userDataPath = app.getPath('userData');
          logContent = fs.readFileSync(path.join(userDataPath, 'python_log.txt'), 'utf8');
        } catch (e) {
          logContent = 'Não foi possível ler python_log.txt: ' + e.message;
        }
        mainWindow.loadURL(url.format({
          pathname: path.join(__dirname, 'error.html'),
          protocol: 'file:',
          slashes: true,
          search: '?type=python&log=' + encodeURIComponent(logContent)
        }));
      }
      return;
    }
    setTimeout(tryConnect, 500);
  });

  tryConnect();
}

app.on('ready', createWindow);

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});

function killChromeOrphans() {
  // Kill Chrome/Edge processes listening on our scraper debug ports
  SCRAPER_DEBUG_PORTS.forEach(port => {
    try {
      // Find PID listening on the debug port and kill the whole tree
      const result = execSync(
        `for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port}') do taskkill /PID %a /T /F`,
        { shell: 'cmd.exe', timeout: 3000, stdio: 'pipe' }
      );
    } catch (e) {
      // Port not in use or already dead — that's fine
    }
  });
}

async function gracefulShutdown() {
  console.log('[Shutdown] Starting graceful shutdown...');

  // Step 1: Ask Python to shut down gracefully (FastAPI lifespan shutdown)
  if (pythonProcess && pythonProcess.pid) {
    console.log('[Shutdown] Sending SIGTERM to Python...');
    try {
      // Send graceful signal via HTTP so FastAPI lifespan runs
      exec('curl -s -X POST http://127.0.0.1:8005/shutdown 2>nul', () => {});
    } catch(e) {}
  }

  // Step 2: Wait 4 seconds for Python scrapers to close Chrome gracefully
  await new Promise(resolve => setTimeout(resolve, 4000));

  // Step 3: Force-kill Python process tree (in case it didn't exit)
  if (pythonProcess && pythonProcess.pid) {
    console.log('[Shutdown] Force-killing Python process tree...');
    try { execSync(`taskkill /pid ${pythonProcess.pid} /T /F`, { stdio: 'pipe' }); } catch(e) {}
  }
  if (setupProcess && setupProcess.pid) {
    try { execSync(`taskkill /pid ${setupProcess.pid} /T /F`, { stdio: 'pipe' }); } catch(e) {}
  }

  // Step 4: Kill any orphan Chrome processes on scraper debug ports
  console.log('[Shutdown] Killing orphan Chrome processes...');
  killChromeOrphans();

  // Step 5: Actually quit
  console.log('[Shutdown] Done. Quitting app.');
  app.exit(0);
}

// Handle unexpected exits cleanly
app.on('before-quit', (e) => {
  if (!isQuitting) {
    e.preventDefault();
    isQuitting = true;
    gracefulShutdown();
  }
});

process.on('SIGINT', () => {
  if (!isQuitting) {
    isQuitting = true;
    gracefulShutdown();
  }
});
