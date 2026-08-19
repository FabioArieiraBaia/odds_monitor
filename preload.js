const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  togglePiP: () => ipcRenderer.send('toggle-pip'),
  onPiPStatus: (callback) => ipcRenderer.on('pip-status', (event, value) => callback(value))
});
