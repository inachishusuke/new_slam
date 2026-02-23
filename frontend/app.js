const API_BASE = '/api';

let isRecording = false;
let recordStartEpochSec = null;
let uiUpdateInterval = null;
let selectedFiles = new Set();
let filesData = [];
let fileLookup = new Map();

const elTime = document.getElementById('sys-time');
const elTemp = document.getElementById('sys-temp');
const elDisk = document.getElementById('sys-disk');
const elStatusCameraText = document.getElementById('status-camera-text');
const elStatusLidarText = document.getElementById('status-lidar-text');

const btnRecord = document.getElementById('btn-record');
const elRecordTimer = document.getElementById('record-timer');
const elRecordText = document.getElementById('record-text');
const elRecordCircle = document.getElementById('record-circle');

const btnConnectCamera = document.getElementById('btn-connect-camera');
const elCamText = document.getElementById('cam-text');
const elCamCircle = document.getElementById('cam-circle');

const btnOpenUsb = document.getElementById('btn-open-usb');
const modalUsb = document.getElementById('modal-usb');
const btnCloseUsb = document.getElementById('btn-close-usb');
const elFileList = document.getElementById('file-list');
const elSelectionCount = document.getElementById('selection-count');
const btnExportSelected = document.getElementById('btn-export-selected');

const btnSettings = document.getElementById('btn-settings');
const modalSettings = document.getElementById('modal-settings');
const btnCloseSettings = document.getElementById('btn-close-settings');
const btnSaveSettings = document.getElementById('btn-save-settings');
const radioOrientationModes = document.querySelectorAll('input[name="screen-orientation"]');
const radioCameraModes = document.querySelectorAll('input[name="camera-mode"]');
const groupCustomCamera = document.getElementById('custom-camera-inputs');
const inputCamX = document.getElementById('cam-x');
const inputCamY = document.getElementById('cam-y');
const inputCamZ = document.getElementById('cam-z');

const btnPower = document.getElementById('btn-power');

const modalConfirm = document.getElementById('modal-confirm');
const elConfirmTitle = document.getElementById('confirm-title');
const btnConfirmAction = document.getElementById('btn-confirm-action');
const btnCancelAction = document.getElementById('btn-cancel-action');
const elConfirmYesText = document.getElementById('confirm-yes-text');

let confirmCallback = null;

document.addEventListener('DOMContentLoaded', () => {
    setInterval(updateLocalClock, 1000);
    pollBackendStatus();
    uiUpdateInterval = setInterval(pollBackendStatus, 1000);
    setupEventListeners();
    initROS3DViewer();
    loadSettings();
});

function setupEventListeners() {
    btnRecord.addEventListener('click', () => {
        if (isRecording) {
            requestConfirmation('Ending<br>Scanning<br>Process', 'Stop Scan', () => executeRecordToggle('/record/stop'));
        } else {
            executeRecordToggle('/record/start');
        }
    });

    btnConnectCamera.addEventListener('click', () => {
        const active = elCamCircle.classList.contains('filled');
        if (active) {
            requestConfirmation('Stopping<br>Camera<br>Capture', 'Stop Cam', executeCameraStop);
        } else {
            executeCameraStart();
        }
    });

    btnPower.addEventListener('click', () => {
        requestConfirmation('Leaving<br>Stopping<br>Ending', 'Turn Off', shutdownSystem);
    });

    btnCancelAction.addEventListener('click', closeConfirmation);
    btnConfirmAction.addEventListener('click', () => {
        if (confirmCallback) confirmCallback();
        closeConfirmation();
    });

    btnOpenUsb.addEventListener('click', openUsbModal);
    btnCloseUsb.addEventListener('click', closeUsbModal);
    btnExportSelected.addEventListener('click', () => {
        requestConfirmation('Writing<br>Files<br>Exporting', 'Copy Data', executeUsbExport);
    });

    btnSettings.addEventListener('click', () => modalSettings.classList.remove('hidden'));
    btnCloseSettings.addEventListener('click', () => modalSettings.classList.add('hidden'));

    radioCameraModes.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'custom') groupCustomCamera.classList.remove('hidden');
            else groupCustomCamera.classList.add('hidden');
        });
    });

    btnSaveSettings.addEventListener('click', saveAndApplySettings);
}

function renderConfirmTitle(titleText) {
    const parts = String(titleText).split('<br>');
    elConfirmTitle.replaceChildren();
    parts.forEach((part, index) => {
        if (index > 0) elConfirmTitle.appendChild(document.createElement('br'));
        elConfirmTitle.appendChild(document.createTextNode(part));
    });
}

function requestConfirmation(titleText, confirmButtonText, callback) {
    renderConfirmTitle(titleText);
    elConfirmYesText.textContent = confirmButtonText;
    confirmCallback = callback;
    modalConfirm.classList.remove('hidden');
}

function closeConfirmation() {
    modalConfirm.classList.add('hidden');
    confirmCallback = null;
}

function formatTime(seconds) {
    const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function updateLocalClock() {
    const now = new Date();
    elTime.textContent = now.toLocaleTimeString('en-US', { hour12: false });
}

async function pollBackendStatus() {
    try {
        const res = await fetch(`${API_BASE}/status`);
        if (!res.ok) return;
        const data = await res.json();

        elTemp.textContent = `${(data.cpu_temp_c ?? 0).toFixed(1)}C`;
        elDisk.textContent = `${(data.free_disk_gb ?? 0).toFixed(1)}GB`;
        if ((data.free_disk_gb ?? 0) < 10.0) elDisk.classList.add('alert-text');
        else elDisk.classList.remove('alert-text');

        const thermalOverlay = document.getElementById('thermal-overlay');
        const voltageOverlay = document.getElementById('voltage-overlay');
        const interactionArea = document.querySelector('.interaction-area');

        let shouldLockUI = false;

        if ((data.cpu_temp_c ?? 0) >= 80.0) {
            elTemp.classList.add('alert-text');
            thermalOverlay?.classList.remove('hidden');
            shouldLockUI = true;
            if (typeof toggleThermalThrottling === 'function') toggleThermalThrottling(true);
        } else {
            elTemp.classList.remove('alert-text');
            thermalOverlay?.classList.add('hidden');
            if (typeof toggleThermalThrottling === 'function') toggleThermalThrottling(false);
        }

        if (data.undervoltage) {
            voltageOverlay?.classList.remove('hidden');
            shouldLockUI = true;
        } else {
            voltageOverlay?.classList.add('hidden');
        }

        interactionArea.style.pointerEvents = shouldLockUI ? 'none' : 'auto';
        interactionArea.style.opacity = shouldLockUI ? '0.3' : '1.0';

        elStatusLidarText.textContent = data.ros_running ? 'Active' : 'Down';
        isRecording = Boolean(data.is_recording ?? data.recording);
        updateRecordingUI();

        if (isRecording) {
            const reported = Number(data.recording_duration_sec ?? 0);
            if (reported > 0) {
                elRecordTimer.textContent = formatTime(reported);
                recordStartEpochSec = Date.now() / 1000 - reported;
            } else {
                if (!recordStartEpochSec) recordStartEpochSec = Date.now() / 1000;
                const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - recordStartEpochSec));
                elRecordTimer.textContent = formatTime(elapsed);
            }
        } else {
            recordStartEpochSec = null;
            elRecordTimer.textContent = '00:00:00';
        }

        const camConnected = !!(data.camera && data.camera.connected);
        elStatusCameraText.textContent = camConnected ? 'Online' : 'Offline';
        if (camConnected) {
            elCamText.textContent = 'Cam Ready';
            elCamCircle.classList.add('filled');
        } else {
            elCamText.textContent = 'Camera';
            elCamCircle.classList.remove('filled');
        }
    } catch (_) {
        // keep UI running offline
    }
}

async function executeRecordToggle(endpoint) {
    btnRecord.style.pointerEvents = 'none';
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, { method: 'POST' });
        if (!res.ok) throw new Error('record request failed');
        const payload = await res.json().catch(() => ({}));
        if (typeof payload.is_recording === 'boolean') {
            isRecording = payload.is_recording;
        } else if (endpoint.endsWith('/start')) {
            isRecording = true;
        } else {
            isRecording = false;
        }

        if (isRecording) {
            recordStartEpochSec = Date.now() / 1000;
            showToast('Capturing Data');
        } else {
            recordStartEpochSec = null;
            showToast('Processing Map');
        }
        updateRecordingUI();
    } catch (_) {
        showToast('System Error');
    } finally {
        setTimeout(() => { btnRecord.style.pointerEvents = 'auto'; }, 500);
    }
}

function updateRecordingUI() {
    const interactionArea = document.querySelector('.interaction-area');
    const viewerOverlay = document.getElementById('viewer-overlay');

    if (isRecording) {
        btnRecord.classList.add('recording');
        elRecordCircle.classList.add('red', 'pulse');
        elRecordTimer.classList.add('active');
        elRecordText.textContent = 'Scanning';
        viewerOverlay.style.opacity = '0';

        if (typeof pointCloudMaterial !== 'undefined' && pointCloudMaterial) {
            pointCloudMaterial.color.setHex(0xD91A1A);
            pointCloudMaterial.size = 0.15;
        } else if (typeof window.mock3DMaterial !== 'undefined') {
            window.mock3DMaterial.color.setHex(0xD91A1A);
        }

        interactionArea.classList.add('scanning-mode');
    } else {
        btnRecord.classList.remove('recording');
        elRecordCircle.classList.remove('red', 'pulse');
        elRecordTimer.classList.remove('active');
        elRecordText.textContent = 'Start';
        viewerOverlay.style.opacity = '1';

        if (typeof pointCloudMaterial !== 'undefined' && pointCloudMaterial) {
            pointCloudMaterial.color.setHex(0x000000);
            pointCloudMaterial.size = 0.1;
        } else if (typeof window.mock3DMaterial !== 'undefined') {
            window.mock3DMaterial.color.setHex(0x000000);
        }

        interactionArea.classList.remove('scanning-mode');
    }
}

async function executeCameraStart() {
    if (btnConnectCamera.style.pointerEvents === 'none') return;
    btnConnectCamera.style.pointerEvents = 'none';
    elCamCircle.classList.add('pulse');
    showToast('Connecting...');

    try {
        const res = await fetch(`${API_BASE}/camera/record/start`, { method: 'POST' });
        if (!res.ok) throw new Error('camera start failed');
        elStatusCameraText.textContent = 'Online';
        elCamText.textContent = 'Cam Ready';
        elCamCircle.classList.add('filled');
        showToast('Camera Active');
    } catch (_) {
        showToast('Connection Failed');
    } finally {
        btnConnectCamera.style.pointerEvents = 'auto';
        elCamCircle.classList.remove('pulse');
    }
}

async function executeCameraStop() {
    try {
        await fetch(`${API_BASE}/camera/record/stop`, { method: 'POST' });
    } catch (_) {
        // ignore
    }
    elStatusCameraText.textContent = 'Offline';
    elCamText.textContent = 'Camera';
    elCamCircle.classList.remove('filled');
    showToast('Camera Stopped');
}

async function fetchFiles() {
    try {
        const res = await fetch(`${API_BASE}/files`);
        const payload = await res.json();
        const maps = (payload.maps || []).map((name) => ({ id: `map:${name}`, name, type: 'map' }));
        const bags = (payload.rosbag || []).map((name) => ({ id: `rosbag:${name}`, name, type: 'rosbag' }));
        const logs = (payload.logs || []).map((name) => ({ id: `log:${name}`, name, type: 'log' }));
        filesData = [...maps, ...bags, ...logs];
        renderFileList();
    } catch (_) {
        elFileList.innerHTML = '<div>Error loading files</div>';
    }
}

function renderFileList() {
    elFileList.replaceChildren();
    selectedFiles.clear();
    fileLookup = new Map();
    updateSelectionUI();

    if (filesData.length === 0) {
        const empty = document.createElement('div');
        empty.textContent = 'No data available';
        elFileList.appendChild(empty);
        return;
    }

    filesData.forEach(file => {
        fileLookup.set(file.id, file);
        const div = document.createElement('div');
        div.className = 'file-item';

        const info = document.createElement('div');
        info.className = 'file-info';

        const name = document.createElement('span');
        name.className = 'f-name';
        name.textContent = file.name;

        const meta = document.createElement('span');
        meta.className = 'f-meta';
        meta.textContent = file.type;

        const status = document.createElement('div');
        status.className = 'f-status';

        info.appendChild(name);
        info.appendChild(meta);
        div.appendChild(info);
        div.appendChild(status);

        div.onclick = () => {
            if (selectedFiles.has(file.id)) {
                selectedFiles.delete(file.id);
                div.classList.remove('selected');
            } else {
                selectedFiles.add(file.id);
                div.classList.add('selected');
            }
            updateSelectionUI();
        };
        elFileList.appendChild(div);
    });
}

function updateSelectionUI() {
    if (selectedFiles.size > 0) {
        btnExportSelected.style.display = 'flex';
        elSelectionCount.textContent = `Copy ${selectedFiles.size}`;
    } else {
        btnExportSelected.style.display = 'none';
    }
}

function openUsbModal() {
    modalUsb.classList.remove('hidden');
    elFileList.innerHTML = '<div>Looking for data...</div>';
    fetchFiles();
}

function closeUsbModal() {
    modalUsb.classList.add('hidden');
}

async function executeUsbExport() {
    if (selectedFiles.size === 0) return;

    btnExportSelected.style.pointerEvents = 'none';
    elSelectionCount.textContent = 'Copying...';
    btnExportSelected.querySelector('.circle')?.classList.add('pulse');

    const selectedEntries = Array.from(selectedFiles)
        .map((id) => fileLookup.get(id))
        .filter((file) => file && file.name && file.type)
        .map((file) => ({ type: file.type, name: file.name }));

    try {
        const res = await fetch(`${API_BASE}/usb/transfer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: selectedEntries })
        });

        if (res.ok) {
            showToast('Transfer Complete');
            closeUsbModal();
        } else {
            showToast('Transfer Failed');
        }
    } catch (_) {
        showToast('Transfer Failed');
    } finally {
        btnExportSelected.style.pointerEvents = 'auto';
        btnExportSelected.querySelector('.circle')?.classList.remove('pulse');
    }
}

function shutdownSystem() {
    showToast('Powering Off');
    fetch(`${API_BASE}/system/shutdown`, { method: 'POST' });
}

function showToast(message) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
}

function loadSettings() {
    const savedOrientation = localStorage.getItem('screenOrientation') || 'portrait';
    const savedMode = localStorage.getItem('cameraMode') || '3rd';
    const savedX = parseFloat(localStorage.getItem('cameraX')) || 0;
    const savedY = parseFloat(localStorage.getItem('cameraY')) || -5;
    const savedZ = parseFloat(localStorage.getItem('cameraZ')) || 2;

    radioOrientationModes.forEach(radio => { radio.checked = (radio.value === savedOrientation); });
    applyScreenOrientation(savedOrientation);

    radioCameraModes.forEach(radio => { radio.checked = (radio.value === savedMode); });
    inputCamX.value = savedX;
    inputCamY.value = savedY;
    inputCamZ.value = savedZ;

    if (savedMode === 'custom') groupCustomCamera.classList.remove('hidden');
    else groupCustomCamera.classList.add('hidden');

    setTimeout(() => applyCameraSettings(savedMode, savedX, savedY, savedZ), 700);
}

function saveAndApplySettings() {
    let selectedOrientation = 'portrait';
    radioOrientationModes.forEach(r => { if (r.checked) selectedOrientation = r.value; });

    let selectedMode = '3rd';
    radioCameraModes.forEach(r => { if (r.checked) selectedMode = r.value; });

    const cx = parseFloat(inputCamX.value) || 0;
    const cy = parseFloat(inputCamY.value) || -5;
    const cz = parseFloat(inputCamZ.value) || 2;

    localStorage.setItem('screenOrientation', selectedOrientation);
    localStorage.setItem('cameraMode', selectedMode);
    localStorage.setItem('cameraX', cx.toString());
    localStorage.setItem('cameraY', cy.toString());
    localStorage.setItem('cameraZ', cz.toString());

    applyScreenOrientation(selectedOrientation);
    applyCameraSettings(selectedMode, cx, cy, cz);

    modalSettings.classList.add('hidden');
    showToast('Settings Applied');
}

function applyScreenOrientation(mode) {
    const container = document.querySelector('.app-container');
    if (mode === 'landscape') container.classList.add('landscape-mode');
    else container.classList.remove('landscape-mode');

    setTimeout(() => { window.dispatchEvent(new Event('resize')); }, 120);
}

function applyCameraSettings(mode, cx, cy, cz) {
    if (typeof setCameraPose !== 'function') return;

    if (mode === '1st') setCameraPose(0, 0.5, 0.5);
    else if (mode === '3rd') setCameraPose(0, -5, 2);
    else if (mode === 'custom') setCameraPose(cx, cy, cz);
}
