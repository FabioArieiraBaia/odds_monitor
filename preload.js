const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  togglePiP: () => ipcRenderer.send('toggle-pip'),
  onPiPStatus: (callback) => ipcRenderer.on('pip-status', (event, value) => callback(value)),
  sendNativeAlert: (data) => ipcRenderer.send('trigger-alert-notification', data),
  focusBet365Window: (matchData) => ipcRenderer.send('focus-bet365', matchData)
});
