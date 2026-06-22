const { app, BrowserWindow } = require('electron');
const { spawn, exec, execSync } = require('child_process');
const path = require('path');
const net = require('net');
const fs = require('fs');

let mainWindow;
let pythonProcess;
let setupProcess;
let isQuitting = false;

// Track Chrome debug ports used by our scrapers
const SCRAPER_DEBUG_PORTS = [9222, 9223];

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
      contextIsolation: true
    }
  });

  const setupMarker = path.join(__dirname, '.setup_done_v2');

  // Verifica se o setup ja foi feito
  if (!fs.existsSync(setupMarker)) {
    // Carrega a tela de loading local
    mainWindow.loadFile(path.join(__dirname, 'loading.html'));
    
    console.log("Iniciando First-Run Setup...");
    setupProcess = spawn('cmd.exe', ['/c', 'setup.bat > setup_log.txt 2>&1'], {
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
      // Cria o marcador para nunca mais rodar o setup
      fs.writeFileSync(setupMarker, 'true');
      
      // Agora inicia o servidor e carrega a pagina real
      startPythonServer();
      waitForServer(8000, () => {
        mainWindow.loadURL('http://127.0.0.1:8000');
      });
    });
  } else {
    // Setup ja feito, inicia direto
    startPythonServer();
    waitForServer(8000, () => {
      mainWindow.loadURL('http://127.0.0.1:8000');
    });
  }

  // Intercepta todos os links target="_blank" e abre no navegador padrao do usuario (Chrome, Edge)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
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
  
  // Use absolute path if found, avoiding PATH refresh issues on first install
  pythonProcess = spawn(`"${pythonCmd}"`, ['app/main.py'], {
    cwd: __dirname,
    shell: true
  });

  const logStream = fs.createWriteStream(path.join(__dirname, 'python_log.txt'), { flags: 'a' });

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
      // Ao invez de chamar o callback para abrir a pagina, carrega a tela de erro
      if (mainWindow) mainWindow.loadFile(path.join(__dirname, 'error.html'));
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
      exec('curl -s -X POST http://127.0.0.1:8000/shutdown 2>nul', () => {});
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
