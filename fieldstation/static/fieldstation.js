const state = {
  selectedChannel: 'all',
  channels: [],
  mapStatus: null,
  positions: [],
  waypoints: [],
  pendingWaypoints: [],
  selectedWaypointId: null,
  activeNetSession: null,
  netSessions: [],
  netLogEntries: [],
};

const NET_ENTRY_TYPES = [
  'check-in',
  'check-out',
  'voice contact',
  'relay',
  'situation report',
  'weather report',
  'resource/status update',
  'operator note',
  'message sent',
  'message received',
  'message failed',
  'node connected',
  'node disconnected',
  'telemetry update',
  'GPS/position update',
  'waypoint created',
  'waypoint shared',
  'waypoint received',
  'notable error',
];

const els = {
  operateTab: document.getElementById('operateTab'),
  mapTab: document.getElementById('mapTab'),
  netLogTab: document.getElementById('netLogTab'),
  settingsTab: document.getElementById('settingsTab'),
  operateScreen: document.getElementById('operateScreen'),
  mapScreen: document.getElementById('mapScreen'),
  netLogScreen: document.getElementById('netLogScreen'),
  settingsScreen: document.getElementById('settingsScreen'),
  connectionState: document.getElementById('connectionState'),
  connectionPort: document.getElementById('connectionPort'),
  localNode: document.getElementById('localNode'),
  lastPacket: document.getElementById('lastPacket'),
  offlineBanner: document.getElementById('offlineBanner'),
  offlineTitle: document.getElementById('offlineTitle'),
  offlineText: document.getElementById('offlineText'),
  localNodeIdentity: document.getElementById('localNodeIdentity'),
  localTactical: document.getElementById('localTactical'),
  connectionDetail: document.getElementById('connectionDetail'),
  lastConnection: document.getElementById('lastConnection'),
  reconnectAttempts: document.getElementById('reconnectAttempts'),
  clientDependency: document.getElementById('clientDependency'),
  localBattery: document.getElementById('localBattery'),
  localGps: document.getElementById('localGps'),
  localRadio: document.getElementById('localRadio'),
  nodeFreshness: document.getElementById('nodeFreshness'),
  channelTabs: document.getElementById('channelTabs'),
  chatHistory: document.getElementById('chatHistory'),
  composeForm: document.getElementById('composeForm'),
  messageBody: document.getElementById('messageBody'),
  knownNodes: document.getElementById('knownNodes'),
  recentEvents: document.getElementById('recentEvents'),
  refreshButton: document.getElementById('refreshButton'),
  fullscreenButton: document.getElementById('fullscreenButton'),
  mapModeText: document.getElementById('mapModeText'),
  nodeMarkers: document.getElementById('nodeMarkers'),
  waypointMarkers: document.getElementById('waypointMarkers'),
  addWaypointButton: document.getElementById('addWaypointButton'),
  clearWaypointButton: document.getElementById('clearWaypointButton'),
  waypointForm: document.getElementById('waypointForm'),
  waypointId: document.getElementById('waypointId'),
  waypointName: document.getElementById('waypointName'),
  waypointType: document.getElementById('waypointType'),
  waypointLatitude: document.getElementById('waypointLatitude'),
  waypointLongitude: document.getElementById('waypointLongitude'),
  waypointPriority: document.getElementById('waypointPriority'),
  waypointStatus: document.getElementById('waypointStatus'),
  waypointNotes: document.getElementById('waypointNotes'),
  copyWaypointButton: document.getElementById('copyWaypointButton'),
  shareChannel: document.getElementById('shareChannel'),
  shareWaypointButton: document.getElementById('shareWaypointButton'),
  sharePreview: document.getElementById('sharePreview'),
  waypointList: document.getElementById('waypointList'),
  pendingWaypoints: document.getElementById('pendingWaypoints'),
  activeNetSummary: document.getElementById('activeNetSummary'),
  closeNetButton: document.getElementById('closeNetButton'),
  netSessionForm: document.getElementById('netSessionForm'),
  netEventName: document.getElementById('netEventName'),
  netOperationalPeriod: document.getElementById('netOperationalPeriod'),
  netName: document.getElementById('netName'),
  netOperatorName: document.getElementById('netOperatorName'),
  netOperatorCallsign: document.getElementById('netOperatorCallsign'),
  netStationId: document.getElementById('netStationId'),
  netStationTactical: document.getElementById('netStationTactical'),
  netActiveChannel: document.getElementById('netActiveChannel'),
  netNotes: document.getElementById('netNotes'),
  netEntryForm: document.getElementById('netEntryForm'),
  entryTimestamp: document.getElementById('entryTimestamp'),
  entryType: document.getElementById('entryType'),
  entryFrom: document.getElementById('entryFrom'),
  entryFromTactical: document.getElementById('entryFromTactical'),
  entryTo: document.getElementById('entryTo'),
  entryToTactical: document.getElementById('entryToTactical'),
  entryChannel: document.getElementById('entryChannel'),
  entryMessage: document.getElementById('entryMessage'),
  netLogEntries: document.getElementById('netLogEntries'),
  export309Csv: document.getElementById('export309Csv'),
  export309Text: document.getElementById('export309Text'),
  export214Csv: document.getElementById('export214Csv'),
  export214Text: document.getElementById('export214Text'),
  exportPreview: document.getElementById('exportPreview'),
  channelProfileList: document.getElementById('channelProfileList'),
  exportProfileButton: document.getElementById('exportProfileButton'),
  importProfileButton: document.getElementById('importProfileButton'),
  profileJson: document.getElementById('profileJson'),
  bundleChannels: document.getElementById('bundleChannels'),
  bundleMap: document.getElementById('bundleMap'),
  bundleWaypoints: document.getElementById('bundleWaypoints'),
  bundleNodes: document.getElementById('bundleNodes'),
  bundleTactical: document.getElementById('bundleTactical'),
  bundleDocs: document.getElementById('bundleDocs'),
  previewBundleButton: document.getElementById('previewBundleButton'),
  exportBundleButton: document.getElementById('exportBundleButton'),
  bundleJson: document.getElementById('bundleJson'),
  usbTargetPath: document.getElementById('usbTargetPath'),
  usbIncludeBundle: document.getElementById('usbIncludeBundle'),
  previewUsbButton: document.getElementById('previewUsbButton'),
  createUsbButton: document.getElementById('createUsbButton'),
  usbPackageDir: document.getElementById('usbPackageDir'),
  verifyUsbButton: document.getElementById('verifyUsbButton'),
  usbWriterOutput: document.getElementById('usbWriterOutput'),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {'Content-Type': 'application/json'},
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function formatTime(value) {
  if (!value) return 'none';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleString();
}

function setConnection(status) {
  const connection = status.connection;
  els.connectionState.textContent = connection.state;
  els.connectionState.className = `status-pill ${connection.state}`;
  els.connectionPort.textContent = `USB: ${connection.selected_port || 'not selected'}`;
  const localDisplay = connection.local_node.display_name || connection.local_node.node_name || 'unavailable';
  els.localNode.textContent = `Local node: ${localDisplay}`;
  els.lastPacket.textContent = `Last packet: ${formatTime(connection.last_packet_at)}`;
  els.localNodeIdentity.textContent = localDisplay;
  els.localTactical.textContent = connection.local_node.tactical_callsign || 'Not assigned';
  els.connectionDetail.textContent = connection.error ? `${connection.detail} ${connection.error}` : connection.detail;
  els.lastConnection.textContent = formatTime(connection.last_successful_connection_at);
  els.reconnectAttempts.textContent = String(connection.reconnect_attempts || 0);
  els.clientDependency.textContent = connection.dependency?.available ? 'Meshtastic Python available' : 'Meshtastic Python missing';
  els.localBattery.textContent = formatBattery(connection.local_node);
  els.localGps.textContent = formatGps(connection.local_node);
  els.localRadio.textContent = formatRadio(connection.local_node);
  els.nodeFreshness.textContent = connection.stale ? 'stale' : 'recent';
  els.nodeFreshness.className = `mini-badge ${connection.stale ? 'stale' : 'recent'}`;
  els.offlineBanner.className = `offline-banner ${connection.state}`;
  els.offlineTitle.textContent = connection.state === 'connected'
    ? 'Node connected/read-only'
    : `${connection.state} mode`;
  els.offlineText.textContent = connection.state === 'connected'
    ? 'FieldStation is reading live USB node status. Sending, seen-by-mesh, recipient ACKs, and node configuration writes remain disabled.'
    : `${connection.detail} Queued messages are local only; live telemetry, seen-by-mesh, and recipient ACKs are unavailable.`;
}

function renderChannels() {
  const tabs = [{index: 'all', label: 'All'}, ...state.channels.map((channel) => ({
    index: String(channel.index),
    label: channel.label,
  }))];
  els.channelTabs.innerHTML = '';
  tabs.forEach((tab) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `channel-tab ${String(state.selectedChannel) === String(tab.index) ? 'active' : ''}`;
    button.textContent = tab.label;
    button.addEventListener('click', () => {
      state.selectedChannel = tab.index;
      renderChannels();
      loadMessages();
    });
    els.channelTabs.appendChild(button);
  });
}

function renderMessages(messages) {
  els.chatHistory.innerHTML = '';
  if (!messages.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No stored traffic for this view yet.';
    els.chatHistory.appendChild(empty);
    return;
  }
  messages.forEach((message) => {
    const article = document.createElement('article');
    article.className = `message ${message.direction}`;
    const receiptNote = message.status === 'queued_local'
      ? '<span class="local-note">local only, not sent to mesh</span>'
      : '';
    article.innerHTML = `
      <div class="message-meta">
        <span>${escapeHtml(message.sender_display)} | ${escapeHtml(message.channel_label)} | ${formatTime(message.timestamp)}</span>
        <span class="status-badge ${escapeHtml(message.status_tone || '')}">${escapeHtml(message.status_label)}</span>
      </div>
      ${receiptNote}
      <p class="message-body"></p>
    `;
    article.querySelector('.message-body').textContent = message.body;
    els.chatHistory.appendChild(article);
  });
  els.chatHistory.scrollTop = els.chatHistory.scrollHeight;
}

function renderNodes(nodes) {
  els.knownNodes.innerHTML = '';
  if (!nodes.length) {
    els.knownNodes.innerHTML = '<div class="empty-state">No known nodes stored yet.</div>';
    return;
  }
  nodes.forEach((node) => {
    const card = document.createElement('div');
    card.className = 'node-card';
    card.innerHTML = `
      <div class="node-title">${escapeHtml(node.display_name)}</div>
      <div class="node-meta">${escapeHtml(node.node_id)} | ${escapeHtml(node.freshness || 'stale')}${node.last_heard_at ? ` | last heard ${formatTime(node.last_heard_at)}` : ' | no packets heard'}</div>
      <div class="node-meta">${escapeHtml(formatNodeFacts(node))}</div>
      <form class="callsign-form">
        <input name="tactical_callsign" maxlength="32" autocomplete="off" placeholder="Tactical callsign" value="${escapeAttribute(node.tactical_callsign || '')}">
        <button type="submit">Save</button>
      </form>
    `;
    card.querySelector('form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const tactical = new FormData(event.currentTarget).get('tactical_callsign');
      await api('/api/tactical-callsigns', {
        method: 'POST',
        body: JSON.stringify({node_id: node.node_id, tactical_callsign: tactical}),
      });
      await refreshAll();
    });
    els.knownNodes.appendChild(card);
  });
}

function renderEvents(events) {
  els.recentEvents.innerHTML = '';
  if (!events.length) {
    els.recentEvents.innerHTML = '<div class="empty-state">No recent events.</div>';
    return;
  }
  events.forEach((event) => {
    const item = document.createElement('div');
    item.className = 'event-item';
    item.innerHTML = `
      <strong>${escapeHtml(event.summary)}</strong>
      <span class="event-time">${escapeHtml(event.event_type)} | ${formatTime(event.created_at)}</span>
    `;
    els.recentEvents.appendChild(item);
  });
}

function setView(name) {
  const targets = {
    operate: [els.operateTab, els.operateScreen],
    map: [els.mapTab, els.mapScreen],
    netlog: [els.netLogTab, els.netLogScreen],
    settings: [els.settingsTab, els.settingsScreen],
  };
  Object.entries(targets).forEach(([key, pair]) => {
    const active = key === name;
    pair[0].classList.toggle('active', active);
    pair[1].classList.toggle('active', active);
  });
}

function populateWaypointOptions() {
  const types = state.mapStatus?.waypoint_types || [];
  const statuses = state.mapStatus?.waypoint_statuses || [];
  els.waypointType.innerHTML = types.map((type) => `<option value="${escapeAttribute(type)}">${escapeHtml(type)}</option>`).join('');
  els.waypointStatus.innerHTML = statuses
    .filter((status) => status !== 'deleted')
    .map((status) => `<option value="${escapeAttribute(status)}">${escapeHtml(status)}</option>`)
    .join('');
  els.shareChannel.innerHTML = state.channels.map((channel) => (
    `<option value="${channel.index}">${escapeHtml(channel.label)}</option>`
  )).join('');
  els.netActiveChannel.innerHTML = state.channels.map((channel) => (
    `<option value="${channel.index}">${escapeHtml(channel.label)}</option>`
  )).join('');
  els.entryChannel.innerHTML = state.channels.map((channel) => (
    `<option value="${channel.index}">${escapeHtml(channel.label)}</option>`
  )).join('');
}

function renderMapStatus(status) {
  state.mapStatus = status;
  els.mapModeText.textContent = `${status.region} | ${status.mode.replace(/_/g, ' ')} | no internet required`;
  populateWaypointOptions();
}

function renderPositions(positions) {
  state.positions = positions;
  els.nodeMarkers.innerHTML = '';
  positions.forEach((position) => {
    const point = projectPoint(position.latitude, position.longitude);
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `map-marker node ${position.freshness || 'stale'}`;
    marker.style.left = `${point.x}%`;
    marker.style.top = `${point.y}%`;
    marker.title = `${position.display_name} | stored position`;
    marker.textContent = position.display_name;
    els.nodeMarkers.appendChild(marker);
  });
}

function renderWaypoints(waypoints) {
  state.waypoints = waypoints;
  els.waypointMarkers.innerHTML = '';
  els.waypointList.innerHTML = '';
  if (!waypoints.length) {
    els.waypointList.innerHTML = '<div class="empty-state">No local waypoints yet.</div>';
  }
  waypoints.forEach((waypoint) => {
    const point = projectPoint(waypoint.latitude, waypoint.longitude);
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `map-marker waypoint ${waypoint.status}`;
    marker.style.left = `${point.x}%`;
    marker.style.top = `${point.y}%`;
    marker.title = `${waypoint.name} | ${waypoint.type}`;
    marker.textContent = waypoint.name;
    marker.addEventListener('click', () => selectWaypoint(waypoint.id));
    els.waypointMarkers.appendChild(marker);

    const card = document.createElement('div');
    card.className = 'waypoint-card';
    card.innerHTML = `
      <div class="node-title">${escapeHtml(waypoint.name)}</div>
      <div class="node-meta">${escapeHtml(waypoint.type)} | ${escapeHtml(waypoint.status)} | ${formatCoord(waypoint)}</div>
      <div class="node-meta">By ${escapeHtml(waypoint.created_by_display)}${waypoint.shared_channel_label ? ` | shared ${escapeHtml(waypoint.shared_channel_label)}` : ''}</div>
      <div class="card-actions">
        <button type="button" data-action="edit">View/Edit</button>
        <button type="button" data-action="resolved">Resolved</button>
        <button type="button" data-action="stale">Stale</button>
        <button type="button" data-action="delete">Delete</button>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener('click', () => selectWaypoint(waypoint.id));
    card.querySelector('[data-action="resolved"]').addEventListener('click', () => quickWaypointStatus(waypoint.id, 'resolved'));
    card.querySelector('[data-action="stale"]').addEventListener('click', () => quickWaypointStatus(waypoint.id, 'stale'));
    card.querySelector('[data-action="delete"]').addEventListener('click', () => quickWaypointStatus(waypoint.id, 'deleted'));
    els.waypointList.appendChild(card);
  });
  updateSharePreview();
}

function renderPendingWaypoints(items) {
  state.pendingWaypoints = items;
  els.pendingWaypoints.innerHTML = '';
  if (!items.length) {
    els.pendingWaypoints.innerHTML = '<div class="empty-state">No pending received waypoints.</div>';
    return;
  }
  items.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'pending-card';
    card.innerHTML = `
      <div class="node-title">${escapeHtml(item.name)}</div>
      <div class="node-meta">${escapeHtml(item.type)} | ${formatCoord(item)} | from ${escapeHtml(item.sender_display || 'unknown sender')}</div>
      <div class="node-meta">${escapeHtml(item.raw_message_body)}</div>
      <div class="card-actions">
        <button type="button" data-action="view">View on Map</button>
        <button type="button" data-action="save">Save</button>
        <button type="button" data-action="ignore">Ignore</button>
      </div>
    `;
    card.querySelector('[data-action="view"]').addEventListener('click', () => fillWaypointForm(item));
    card.querySelector('[data-action="save"]').addEventListener('click', () => savePendingWaypoint(item.id));
    card.querySelector('[data-action="ignore"]').addEventListener('click', () => ignorePendingWaypoint(item.id));
    els.pendingWaypoints.appendChild(card);
  });
}

function projectPoint(latitude, longitude) {
  const bounds = state.mapStatus?.bounds || {north: 39.38, south: 38.86, west: -91.28, east: -90.58};
  const x = ((Number(longitude) - bounds.west) / (bounds.east - bounds.west)) * 100;
  const y = ((bounds.north - Number(latitude)) / (bounds.north - bounds.south)) * 100;
  return {
    x: Math.min(96, Math.max(4, x)),
    y: Math.min(94, Math.max(6, y)),
  };
}

function selectWaypoint(id) {
  const waypoint = state.waypoints.find((item) => Number(item.id) === Number(id));
  if (!waypoint) return;
  state.selectedWaypointId = waypoint.id;
  fillWaypointForm(waypoint);
  updateSharePreview();
}

function fillWaypointForm(waypoint) {
  els.waypointId.value = waypoint.id || '';
  els.waypointName.value = waypoint.name || '';
  els.waypointType.value = waypoint.type || 'General';
  els.waypointLatitude.value = waypoint.latitude ?? '';
  els.waypointLongitude.value = waypoint.longitude ?? '';
  els.waypointPriority.value = waypoint.priority || 'Normal';
  els.waypointStatus.value = waypoint.status || 'active';
  els.waypointNotes.value = waypoint.notes || '';
}

function clearWaypointForm() {
  state.selectedWaypointId = null;
  els.waypointForm.reset();
  els.waypointId.value = '';
  els.waypointPriority.value = 'Normal';
  els.waypointStatus.value = 'active';
  if (els.waypointType.options.length) els.waypointType.value = 'General';
  updateSharePreview();
}

function waypointPayload() {
  return {
    id: els.waypointId.value ? Number(els.waypointId.value) : undefined,
    name: els.waypointName.value,
    type: els.waypointType.value,
    latitude: els.waypointLatitude.value,
    longitude: els.waypointLongitude.value,
    priority: els.waypointPriority.value,
    status: els.waypointStatus.value,
    notes: els.waypointNotes.value,
  };
}

function currentWaypointText() {
  const payload = waypointPayload();
  if (!payload.name || !payload.latitude || !payload.longitude) return '';
  const lines = [
    `WAYPOINT: ${payload.name}`,
    `TYPE: ${payload.type || 'General'}`,
    `GPS: ${Number(payload.latitude).toFixed(5)},${Number(payload.longitude).toFixed(5)}`,
  ];
  if (payload.notes) lines.push(`NOTE: ${payload.notes.slice(0, 120)}`);
  return lines.join('\n');
}

function updateSharePreview() {
  els.sharePreview.textContent = currentWaypointText() || 'Select or enter a waypoint to preview the share message.';
}

function formatCoord(item) {
  return `${Number(item.latitude).toFixed(5)}, ${Number(item.longitude).toFixed(5)}`;
}

function populateNetOptions() {
  els.entryType.innerHTML = NET_ENTRY_TYPES.map((type) => `<option value="${escapeAttribute(type)}">${escapeHtml(type)}</option>`).join('');
}

function renderNetSessions(payload) {
  state.netSessions = payload.net_sessions || [];
  state.activeNetSession = payload.active_net_session || null;
  if (!state.activeNetSession) {
    els.activeNetSummary.innerHTML = '<div class="empty-state">No active net session.</div>';
    els.closeNetButton.disabled = true;
    return;
  }
  const session = state.activeNetSession;
  els.closeNetButton.disabled = false;
  els.activeNetSummary.innerHTML = `
    <div class="node-title">${escapeHtml(session.net_name)} | ${escapeHtml(session.status)}</div>
    <div class="node-meta">${escapeHtml(session.event_name)} | ${escapeHtml(session.operational_period || 'no operational period')}</div>
    <div class="node-meta">Operator ${escapeHtml(session.operator_name)} ${escapeHtml(session.operator_callsign || '')} | Station ${escapeHtml(session.station_display)}</div>
    <div class="node-meta">Channel ${escapeHtml(session.active_channel_label)} | Started ${formatTime(session.start_time)}</div>
  `;
}

function renderNetEntries(entries) {
  state.netLogEntries = entries;
  els.netLogEntries.innerHTML = '';
  if (!entries.length) {
    els.netLogEntries.innerHTML = '<div class="empty-state">No net log entries yet.</div>';
    return;
  }
  entries.forEach((entry) => {
    const row = document.createElement('div');
    row.className = `netlog-row ${entry.source}`;
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(formatTime(entry.timestamp))}</strong>
        <span>${escapeHtml(entry.entry_type)} | ${escapeHtml(entry.source)}</span>
      </div>
      <div>${escapeHtml(entry.from_display || 'FieldStation')} ${entry.to_display ? `-> ${escapeHtml(entry.to_display)}` : ''}</div>
      <div>${escapeHtml(entry.channel_label || '')}</div>
      <div>${escapeHtml(entry.message)}</div>
    `;
    els.netLogEntries.appendChild(row);
  });
}

function renderChannelProfiles(profiles) {
  els.channelProfileList.innerHTML = '';
  if (!profiles.length) {
    els.channelProfileList.innerHTML = '<div class="empty-state">No channel profiles.</div>';
    return;
  }
  profiles.forEach((profile) => {
    const item = document.createElement('div');
    item.className = 'profile-card';
    item.innerHTML = `
      <div class="node-title">${escapeHtml(profile.name)}</div>
      <div class="node-meta">${escapeHtml(profile.description || 'No description')}</div>
      <div class="node-meta">${escapeHtml(profile.channels.map((channel) => channel.label).join(' | '))}</div>
      <div class="local-note">Local template only; not applied to node hardware</div>
    `;
    els.channelProfileList.appendChild(item);
  });
}

function starterCategories() {
  const categories = [];
  if (els.bundleChannels.checked) categories.push('channel_profiles');
  if (els.bundleMap.checked) categories.push('map_placeholder');
  if (els.bundleWaypoints.checked) categories.push('waypoints');
  if (els.bundleNodes.checked) categories.push('known_remote_nodes');
  if (els.bundleTactical.checked) categories.push('remote_tactical_callsigns');
  if (els.bundleDocs.checked) {
    categories.push('ics_templates');
    categories.push('documentation');
  }
  return categories;
}

function usbPayload() {
  return {
    target_path: els.usbTargetPath.value,
    include_starter_bundle: els.usbIncludeBundle.checked,
    starter_categories: starterCategories(),
  };
}

async function loadStatus() {
  setConnection(await api('/api/status'));
}

async function loadChannels() {
  const payload = await api('/api/channels');
  state.channels = payload.channels;
  renderChannels();
}

async function loadMessages() {
  const payload = await api(`/api/messages?channel=${encodeURIComponent(state.selectedChannel)}`);
  renderMessages(payload.messages);
}

async function loadNodes() {
  const payload = await api('/api/nodes');
  renderNodes(payload.nodes);
}

async function loadEvents() {
  const payload = await api('/api/events');
  renderEvents(payload.events);
}

async function loadMapStatus() {
  renderMapStatus(await api('/api/map/status'));
}

async function loadPositions() {
  const payload = await api('/api/positions');
  renderPositions(payload.positions);
}

async function loadWaypoints() {
  const payload = await api('/api/waypoints');
  renderWaypoints(payload.waypoints);
}

async function loadPendingWaypoints() {
  const payload = await api('/api/pending-waypoints');
  renderPendingWaypoints(payload.pending_waypoints);
}

async function loadNetSessions() {
  renderNetSessions(await api('/api/net-sessions'));
}

async function loadNetLogEntries() {
  const sessionId = state.activeNetSession?.id || '';
  const payload = await api(`/api/net-log-entries${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`);
  renderNetEntries(payload.entries);
}

async function loadChannelProfiles() {
  const payload = await api('/api/channel-profiles');
  renderChannelProfiles(payload.channel_profiles);
}

async function refreshAll() {
  await Promise.all([
    loadStatus(),
    loadChannels(),
    loadMessages(),
    loadNodes(),
    loadEvents(),
    loadMapStatus(),
    loadPositions(),
    loadWaypoints(),
    loadPendingWaypoints(),
  ]);
  populateNetOptions();
  await loadNetSessions();
  await loadNetLogEntries();
  await loadChannelProfiles();
}

async function saveWaypointForm() {
  const payload = waypointPayload();
  const path = payload.id ? '/api/waypoint-update' : '/api/waypoints';
  await api(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  await Promise.all([loadWaypoints(), loadEvents()]);
}

async function quickWaypointStatus(id, status) {
  await api('/api/waypoint-update', {
    method: 'POST',
    body: JSON.stringify({id, status}),
  });
  if (Number(state.selectedWaypointId) === Number(id) && status === 'deleted') clearWaypointForm();
  await Promise.all([loadWaypoints(), loadEvents()]);
}

async function shareSelectedWaypoint() {
  const id = els.waypointId.value;
  if (!id) return;
  await api('/api/waypoint-share', {
    method: 'POST',
    body: JSON.stringify({id: Number(id), channel_index: Number(els.shareChannel.value || 0)}),
  });
  await Promise.all([loadWaypoints(), loadMessages(), loadEvents()]);
}

async function savePendingWaypoint(id) {
  await api('/api/pending-waypoint-save', {
    method: 'POST',
    body: JSON.stringify({id}),
  });
  await Promise.all([loadWaypoints(), loadPendingWaypoints(), loadEvents()]);
}

async function ignorePendingWaypoint(id) {
  await api('/api/pending-waypoint-ignore', {
    method: 'POST',
    body: JSON.stringify({id}),
  });
  await Promise.all([loadPendingWaypoints(), loadEvents()]);
}

async function startNetSession() {
  await api('/api/net-sessions', {
    method: 'POST',
    body: JSON.stringify({
      event_name: els.netEventName.value,
      operational_period: els.netOperationalPeriod.value,
      net_name: els.netName.value,
      operator_name: els.netOperatorName.value,
      operator_callsign: els.netOperatorCallsign.value,
      station_id: els.netStationId.value,
      station_tactical_callsign: els.netStationTactical.value,
      active_channel_index: Number(els.netActiveChannel.value || 0),
      notes: els.netNotes.value,
    }),
  });
  els.netSessionForm.reset();
  await refreshAll();
}

async function closeNetSession() {
  if (!state.activeNetSession) return;
  await api('/api/net-session-close', {
    method: 'POST',
    body: JSON.stringify({id: state.activeNetSession.id}),
  });
  await refreshAll();
}

async function addManualNetEntry() {
  await api('/api/net-log-entries', {
    method: 'POST',
    body: JSON.stringify({
      net_session_id: state.activeNetSession?.id,
      timestamp: els.entryTimestamp.value,
      entry_type: els.entryType.value,
      from_node_name: els.entryFrom.value,
      from_tactical_callsign: els.entryFromTactical.value,
      to_node_name: els.entryTo.value,
      to_tactical_callsign: els.entryToTactical.value,
      channel_index: Number(els.entryChannel.value || 0),
      message: els.entryMessage.value,
    }),
  });
  els.entryMessage.value = '';
  els.entryTimestamp.value = '';
  await Promise.all([loadNetLogEntries(), loadEvents()]);
}

async function runExport(type, format) {
  const path = type === 'ics309' ? '/api/ics309-export' : '/api/ics214-export';
  const payload = await api(path, {
    method: 'POST',
    body: JSON.stringify({session_id: state.activeNetSession?.id, format}),
  });
  els.exportPreview.textContent = `${payload.filename}\n\n${payload.content}`;
  await loadEvents();
}

async function exportDefaultProfile() {
  const payload = await api('/api/channel-profile-export', {
    method: 'POST',
    body: JSON.stringify({id: 1, include_sensitive: false}),
  });
  els.profileJson.value = JSON.stringify(payload, null, 2);
}

async function importProfileJson() {
  const document = JSON.parse(els.profileJson.value);
  await api('/api/channel-profile-import', {
    method: 'POST',
    body: JSON.stringify({document}),
  });
  await loadChannelProfiles();
}

async function previewStarterBundle() {
  const payload = await api('/api/starter-bundle/preview', {
    method: 'POST',
    body: JSON.stringify({categories: starterCategories()}),
  });
  els.bundleJson.value = JSON.stringify(payload, null, 2);
}

async function exportStarterBundle() {
  const payload = await api('/api/starter-bundle/export', {
    method: 'POST',
    body: JSON.stringify({categories: starterCategories(), source_label: 'FieldStation starter data'}),
  });
  els.bundleJson.value = JSON.stringify(payload, null, 2);
}

async function previewUsbPackage() {
  const payload = await api('/api/usb-writer/preview', {
    method: 'POST',
    body: JSON.stringify(usbPayload()),
  });
  els.usbWriterOutput.textContent = JSON.stringify(payload, null, 2);
}

async function createUsbPackage() {
  const payload = await api('/api/usb-writer/create', {
    method: 'POST',
    body: JSON.stringify(usbPayload()),
  });
  els.usbPackageDir.value = payload.package_dir;
  els.usbWriterOutput.textContent = JSON.stringify(payload, null, 2);
}

async function verifyUsbPackage() {
  const payload = await api('/api/usb-writer/verify', {
    method: 'POST',
    body: JSON.stringify({package_dir: els.usbPackageDir.value}),
  });
  els.usbWriterOutput.textContent = JSON.stringify(payload, null, 2);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }[char]));
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

function formatBattery(node) {
  const pieces = [];
  if (node.battery_level !== null && node.battery_level !== undefined) pieces.push(`${node.battery_level}%`);
  if (node.voltage !== null && node.voltage !== undefined) pieces.push(`${node.voltage}V`);
  if (node.charging_state) pieces.push(node.charging_state);
  return pieces.length ? pieces.join(' | ') : 'unknown';
}

function formatGps(node) {
  if (node.latitude !== null && node.latitude !== undefined && node.longitude !== null && node.longitude !== undefined) {
    return `${Number(node.latitude).toFixed(5)}, ${Number(node.longitude).toFixed(5)}`;
  }
  return node.gps_status || 'unknown';
}

function formatRadio(node) {
  const pieces = [];
  if (node.region) pieces.push(node.region);
  if (node.modem_preset) pieces.push(node.modem_preset);
  if (node.current_channel !== null && node.current_channel !== undefined) pieces.push(`ch ${node.current_channel}`);
  return pieces.length ? pieces.join(' | ') : 'unknown';
}

function formatNodeFacts(node) {
  const pieces = [];
  if (node.battery_level !== null && node.battery_level !== undefined) pieces.push(`battery ${node.battery_level}%`);
  if (node.rssi !== null && node.rssi !== undefined) pieces.push(`RSSI ${node.rssi}`);
  if (node.snr !== null && node.snr !== undefined) pieces.push(`SNR ${node.snr}`);
  if (node.latitude !== null && node.latitude !== undefined && node.longitude !== null && node.longitude !== undefined) {
    pieces.push(`${Number(node.latitude).toFixed(5)}, ${Number(node.longitude).toFixed(5)}`);
  }
  return pieces.length ? pieces.join(' | ') : 'no live telemetry';
}

els.composeForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = els.messageBody.value.trim();
  if (!body) return;
  const channelIndex = state.selectedChannel === 'all' ? 0 : Number(state.selectedChannel);
  await api('/api/send-message', {
    method: 'POST',
    body: JSON.stringify({channel_index: channelIndex, body}),
  });
  els.messageBody.value = '';
  state.selectedChannel = String(channelIndex);
  await refreshAll();
});

els.operateTab.addEventListener('click', () => setView('operate'));
els.mapTab.addEventListener('click', () => setView('map'));
els.netLogTab.addEventListener('click', () => setView('netlog'));
els.settingsTab.addEventListener('click', () => setView('settings'));
els.addWaypointButton.addEventListener('click', () => {
  clearWaypointForm();
  els.waypointName.focus();
});
els.clearWaypointButton.addEventListener('click', clearWaypointForm);
els.waypointForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await saveWaypointForm();
});
els.shareWaypointButton.addEventListener('click', shareSelectedWaypoint);
els.netSessionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await startNetSession();
});
els.netEntryForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await addManualNetEntry();
});
els.closeNetButton.addEventListener('click', closeNetSession);
els.export309Csv.addEventListener('click', () => runExport('ics309', 'csv'));
els.export309Text.addEventListener('click', () => runExport('ics309', 'text'));
els.export214Csv.addEventListener('click', () => runExport('ics214', 'csv'));
els.export214Text.addEventListener('click', () => runExport('ics214', 'text'));
els.exportProfileButton.addEventListener('click', exportDefaultProfile);
els.importProfileButton.addEventListener('click', importProfileJson);
els.previewBundleButton.addEventListener('click', previewStarterBundle);
els.exportBundleButton.addEventListener('click', exportStarterBundle);
els.previewUsbButton.addEventListener('click', previewUsbPackage);
els.createUsbButton.addEventListener('click', createUsbPackage);
els.verifyUsbButton.addEventListener('click', verifyUsbPackage);
els.copyWaypointButton.addEventListener('click', async () => {
  const text = currentWaypointText();
  if (!text) return;
  await navigator.clipboard?.writeText(text);
});
['input', 'change'].forEach((eventName) => {
  els.waypointForm.addEventListener(eventName, updateSharePreview);
});
els.refreshButton.addEventListener('click', refreshAll);
els.fullscreenButton.addEventListener('click', () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.();
  } else {
    document.exitFullscreen?.();
  }
});

refreshAll();
setInterval(refreshAll, 15000);
