def page():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FieldStation</title>
  <link rel="stylesheet" href="/static/fieldstation.css">
</head>
<body>
  <main class="station-shell">
    <header class="topbar">
      <div class="brand-block">
        <p class="eyebrow">Offline Operator Terminal</p>
        <h1>FieldStation</h1>
      </div>
      <div class="status-strip">
        <span id="connectionState" class="status-pill disconnected">Disconnected</span>
        <span id="connectionPort" class="status-text">USB: not selected</span>
        <span id="localNode" class="status-text">Local node: unavailable</span>
        <span id="lastPacket" class="status-text">Last packet: none</span>
        <button id="fullscreenButton" class="icon-button" type="button" title="Fullscreen">[]</button>
      </div>
    </header>

    <section id="offlineBanner" class="offline-banner">
      <strong id="offlineTitle">Offline/stub mode</strong>
      <span id="offlineText">FieldStation is not connected to a live node. Messages are local queue entries only.</span>
    </section>

    <nav class="mode-tabs" aria-label="FieldStation views">
      <button id="operateTab" class="mode-tab active" type="button">Operate</button>
      <button id="mapTab" class="mode-tab" type="button">Map</button>
      <button id="netLogTab" class="mode-tab" type="button">Net Log</button>
      <button id="settingsTab" class="mode-tab" type="button">Settings</button>
    </nav>

    <section id="operateScreen" class="workspace view-screen active">
      <section class="chat-panel">
        <nav id="channelTabs" class="channel-tabs" aria-label="Channels"></nav>
        <div id="chatHistory" class="chat-history" aria-live="polite"></div>
        <form id="composeForm" class="compose">
          <label class="compose-label" for="messageBody">Message</label>
          <textarea id="messageBody" name="body" rows="3" maxlength="220" placeholder="Type a message for the selected channel"></textarea>
          <button type="submit">Queue Local</button>
        </form>
      </section>

      <aside class="side-panel">
        <section class="panel-block">
          <div class="section-title">
            <h2>Local Node</h2>
            <span id="nodeFreshness" class="mini-badge stale">stale</span>
          </div>
          <dl class="status-list">
            <dt>Identity</dt>
            <dd id="localNodeIdentity">Local operator</dd>
            <dt>Tactical</dt>
            <dd id="localTactical">Not assigned</dd>
            <dt>Connection</dt>
            <dd id="connectionDetail">Disconnected</dd>
            <dt>Last conn</dt>
            <dd id="lastConnection">none</dd>
            <dt>Retries</dt>
            <dd id="reconnectAttempts">0</dd>
            <dt>Client</dt>
            <dd id="clientDependency">unknown</dd>
            <dt>Battery</dt>
            <dd id="localBattery">unknown</dd>
            <dt>GPS</dt>
            <dd id="localGps">unknown</dd>
            <dt>Radio</dt>
            <dd id="localRadio">unknown</dd>
          </dl>
        </section>

        <section class="panel-block">
          <div class="section-title">
            <h2>Known Nodes</h2>
            <button id="refreshButton" class="small-button" type="button">Refresh</button>
          </div>
          <div id="knownNodes" class="node-list"></div>
        </section>

        <section class="panel-block">
          <h2>Recent Events</h2>
          <div id="recentEvents" class="event-list"></div>
        </section>
      </aside>
    </section>

    <section id="mapScreen" class="map-workspace view-screen">
      <section class="map-stage">
        <div class="map-toolbar">
          <div>
            <h2>Lincoln County, Missouri</h2>
            <p id="mapModeText">Coordinate plot placeholder. No basemap, internet tiles, or live telemetry.</p>
          </div>
          <div class="map-controls">
            <button id="mapZoomOut" class="small-button" type="button" title="Zoom out">-</button>
            <button id="mapZoomIn" class="small-button" type="button" title="Zoom in">+</button>
            <button id="mapReset" class="small-button" type="button">Reset</button>
            <button id="addWaypointButton" class="small-button" type="button">Add Waypoint</button>
          </div>
        </div>
        <div id="offlineMap" class="offline-map" role="img" aria-label="Offline map">
          <div id="mapPanLayer" class="map-pan-layer">
            <div id="mapTiles" class="map-tiles"></div>
            <canvas id="mapCanvas" class="map-canvas" aria-hidden="true"></canvas>
            <div class="map-grid"></div>
            <div id="nodeMarkers" class="marker-layer"></div>
            <div id="waypointMarkers" class="marker-layer"></div>
          </div>
          <div id="mapLabel" class="map-label">Coordinate plot - not a map</div>
          <div class="map-axis north">N</div>
          <div class="map-axis south">S</div>
          <div class="map-axis west">W</div>
          <div class="map-axis east">E</div>
        </div>
        <p id="mapNote" class="map-note">This is only a coordinate plot against rough regional bounds. It is not a street, topo, or parcel map.</p>
      </section>

      <aside class="map-side">
        <section class="panel-block">
          <div class="section-title">
            <h2>Waypoint</h2>
            <button id="clearWaypointButton" class="small-button" type="button">Clear</button>
          </div>
          <form id="waypointForm" class="waypoint-form">
            <input id="waypointId" name="id" type="hidden">
            <label>Name<input id="waypointName" name="name" maxlength="120" required></label>
            <label>Type<select id="waypointType" name="type"></select></label>
            <div class="form-grid">
              <label>Latitude<input id="waypointLatitude" name="latitude" inputmode="decimal" required></label>
              <label>Longitude<input id="waypointLongitude" name="longitude" inputmode="decimal" required></label>
            </div>
            <div class="form-grid">
              <label>Priority<input id="waypointPriority" name="priority" maxlength="32" value="Normal"></label>
              <label>Status<select id="waypointStatus" name="status"></select></label>
            </div>
            <label>Notes<textarea id="waypointNotes" name="notes" rows="3" maxlength="500"></textarea></label>
            <div class="form-actions">
              <button type="submit">Save</button>
              <button id="copyWaypointButton" type="button">Copy Text</button>
            </div>
          </form>
        </section>

        <section class="panel-block">
          <div class="section-title">
            <h2>Share</h2>
            <select id="shareChannel"></select>
          </div>
          <button id="shareWaypointButton" class="wide-button" type="button">Queue Share Message</button>
          <pre id="sharePreview" class="share-preview"></pre>
        </section>

        <section class="panel-block">
          <h2>Waypoints</h2>
          <div id="waypointList" class="waypoint-list"></div>
        </section>

        <section class="panel-block">
          <h2>Pending Received Waypoints</h2>
          <div id="pendingWaypoints" class="pending-list"></div>
        </section>
      </aside>
    </section>

    <section id="netLogScreen" class="netlog-workspace view-screen">
      <section class="netlog-main">
        <section class="panel-block">
          <div class="section-title">
            <h2>Active Net Session</h2>
            <button id="closeNetButton" class="small-button" type="button">Close Net</button>
          </div>
          <div id="activeNetSummary" class="net-summary">No active net session.</div>
        </section>

        <section class="panel-block">
          <h2>Log Entries</h2>
          <div id="netLogEntries" class="netlog-table"></div>
        </section>
      </section>

      <aside class="netlog-side">
        <section class="panel-block">
          <h2>Start Net</h2>
          <form id="netSessionForm" class="waypoint-form">
            <label>Event Name<input id="netEventName" name="event_name" required></label>
            <label>Operational Period<input id="netOperationalPeriod" name="operational_period"></label>
            <label>Net Name<input id="netName" name="net_name" required></label>
            <div class="form-grid">
              <label>Operator<input id="netOperatorName" name="operator_name" required></label>
              <label>Callsign<input id="netOperatorCallsign" name="operator_callsign"></label>
            </div>
            <div class="form-grid">
              <label>Station ID<input id="netStationId" name="station_id"></label>
              <label>Tactical<input id="netStationTactical" name="station_tactical_callsign"></label>
            </div>
            <label>Channel<select id="netActiveChannel" name="active_channel_index"></select></label>
            <label>Notes<textarea id="netNotes" name="notes" rows="2"></textarea></label>
            <button class="wide-button" type="submit">Start Net Session</button>
          </form>
        </section>

        <section class="panel-block net-entry-panel">
          <h2>Manual Entry</h2>
          <form id="netEntryForm" class="waypoint-form">
            <label>Time<input id="entryTimestamp" name="timestamp"></label>
            <label>Type<select id="entryType" name="entry_type"></select></label>
            <div class="form-grid">
              <label>From<input id="entryFrom" name="from_node_name"></label>
              <label>From Tactical<input id="entryFromTactical" name="from_tactical_callsign"></label>
            </div>
            <div class="form-grid">
              <label>To<input id="entryTo" name="to_node_name"></label>
              <label>To Tactical<input id="entryToTactical" name="to_tactical_callsign"></label>
            </div>
            <label>Channel<select id="entryChannel" name="channel_index"></select></label>
            <label>Message/Notes<textarea id="entryMessage" name="message" rows="3" required></textarea></label>
            <button class="wide-button" type="submit">Add Log Entry</button>
          </form>
        </section>

        <section class="panel-block">
          <h2>Exports</h2>
          <div class="form-grid">
            <button id="export309Csv" class="wide-button" type="button">ICS 309 CSV</button>
            <button id="export309Text" class="wide-button" type="button">ICS 309 Text</button>
            <button id="export214Csv" class="wide-button" type="button">ICS 214 CSV</button>
            <button id="export214Text" class="wide-button" type="button">ICS 214 Text</button>
          </div>
          <pre id="exportPreview" class="share-preview">Exports are generated locally and returned by the FieldStation API.</pre>
        </section>
      </aside>
    </section>

    <section id="settingsScreen" class="settings-screen view-screen">
      <section class="panel-block">
        <h2>Settings</h2>
        <p>FieldStation is running offline-first. Live node send/receive, online map tiles, and hardware configuration are not part of this phase.</p>
      </section>
      <section class="settings-grid">
        <section class="panel-block">
          <h2>Channel Profiles</h2>
          <p class="node-meta">Local templates only. Profiles are not written to radio hardware in this phase.</p>
          <div id="channelProfileList" class="profile-list"></div>
          <div class="form-actions">
            <button id="exportProfileButton" type="button">Export Default</button>
            <button id="importProfileButton" type="button">Import JSON</button>
          </div>
          <textarea id="profileJson" class="tool-textarea" rows="8" placeholder="Channel profile JSON import/export"></textarea>
        </section>

        <section class="panel-block">
          <h2>Starter Data Bundle</h2>
          <p class="node-meta">Not a clone. Local station identity, messages, net logs, raw events, machine settings, serial paths, and secrets are excluded by default.</p>
          <label class="check-row"><input id="bundleChannels" type="checkbox" checked> Channel profile templates</label>
          <label class="check-row"><input id="bundleMap" type="checkbox" checked> Map placeholder metadata</label>
          <label class="check-row"><input id="bundleWaypoints" type="checkbox" checked> Waypoint library</label>
          <label class="check-row"><input id="bundleNodes" type="checkbox" checked> Remote node directory</label>
          <label class="check-row"><input id="bundleTactical" type="checkbox" checked> Remote tactical callsigns</label>
          <label class="check-row"><input id="bundleDocs" type="checkbox" checked> Documentation and ICS notes</label>
          <div class="form-actions">
            <button id="previewBundleButton" type="button">Preview Bundle</button>
            <button id="exportBundleButton" type="button">Export Bundle</button>
          </div>
          <textarea id="bundleJson" class="tool-textarea" rows="8" placeholder="Starter Data Bundle JSON"></textarea>
        </section>

        <section class="panel-block">
          <h2>Make FieldStation USB</h2>
          <p class="node-meta">Creates a folder package only. No formatting, no raw disk writes, no bootable image.</p>
          <label class="tool-label">Target folder<input id="usbTargetPath" placeholder="/tmp or mounted USB folder"></label>
          <label class="check-row"><input id="usbIncludeBundle" type="checkbox" checked> Include Starter Data Bundle</label>
          <div class="form-actions">
            <button id="previewUsbButton" type="button">Preview USB</button>
            <button id="createUsbButton" type="button">Create Package</button>
          </div>
          <label class="tool-label">Package folder<input id="usbPackageDir" placeholder="Created package path"></label>
          <button id="verifyUsbButton" class="wide-button" type="button">Verify Checksums</button>
          <pre id="usbWriterOutput" class="share-preview">USB Writer is folder-only and additive.</pre>
        </section>
      </section>
    </section>
  </main>
  <script src="/static/fieldstation.js"></script>
</body>
</html>"""
