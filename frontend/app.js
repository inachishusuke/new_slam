async function refreshStatus() {
  const res = await fetch('/api/status');
  const data = await res.json();
  document.getElementById('status').textContent = JSON.stringify(data, null, 2);
}

async function invoke(path, method) {
  const res = await fetch(path, { method });
  const body = await res.json();
  alert(body.message || body.detail || 'Done');
  refreshStatus();
}

setInterval(refreshStatus, 5000);
refreshStatus();
