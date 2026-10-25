/* built 2504545 B art, version 53d684e0;
 * regenerate with floorplan/cartoon/build_card.py -- do not hand-edit the dist file */
window.__FPC_DATA__ = {"version":"53d684e0","image":"/local/floorplan/cartoon/floorplan_render.jpg","art_w":2400,"art_h":1792,"rooms":{"study":{"label":"Family Room","points_norm":[[0.01308,0.02131],[0.01308,0.38115],[0.30953,0.38115],[0.30953,0.33631],[0.29156,0.3292],[0.29156,0.02131]],"lights":["light.family_room_family_room"],"switches":["switch.family_room_right","switch.family_room_family_room_left"],"media":["media_player.family_room_tv"],"appliances":[],"covers":[],"locks":[],"temp":"sensor.family_room_family_room_motion_temperature","humidity":null,"motion":"binary_sensor.family_room_family_room_motion_motion","climate":null,"device_count":4},"kitchen":{"label":"Kitchen","points_norm":[[0.2932,0.01754],[0.2932,0.31614],[0.31199,0.3216],[0.31239,0.36809],[0.49737,0.36809],[0.5039,0.39762],[0.69459,0.39762],[0.69459,0.01754]],"lights":["light.z_wave_plus_s2_dimmer_light_switch","light.kitchen_kitchen_table","light.dimmer"],"switches":["switch.on_off_switch"],"media":["media_player.kitchen_display"],"appliances":[],"covers":[],"locks":[],"temp":"sensor.kitchen_motion_temperature","humidity":null,"motion":"binary_sensor.kitchen_motion_motion","climate":null,"device_count":5},"dining_room":{"label":"Dining Room","points_norm":[[0.71446,0.02035],[0.71446,0.36488],[0.94721,0.38238],[0.94721,0.02035]],"lights":[],"switches":[],"media":[],"appliances":[],"covers":[],"locks":[],"temp":null,"humidity":null,"motion":null,"climate":null,"device_count":0},"corridor":{"label":"Foyer","points_norm":[[0.41236,0.38118],[0.41236,0.48892],[0.55936,0.49439],[0.55976,0.90454],[0.75699,0.90454],[0.75781,0.56056],[0.92155,0.55618],[0.92155,0.39267],[0.50178,0.41072],[0.49525,0.38118]],"lights":["light.foyer_hall"],"switches":[],"media":[],"appliances":[],"covers":[],"locks":[],"temp":"sensor.hallway_hallway_temperature","humidity":"sensor.hallway_hallway_humidity","motion":"binary_sensor.hallway_motion_motion","climate":"climate.hallway_hallway","device_count":2},"laundry":{"label":"Laundry","points_norm":[[0.40784,0.50355],[0.40784,0.59633],[0.54341,0.59633],[0.54341,0.50355]],"lights":[],"switches":["switch.double_relay","switch.double_relay_2"],"media":[],"appliances":["switch.washer_power","switch.laundry_dryer_power"],"covers":[],"locks":[],"temp":null,"humidity":null,"motion":null,"climate":null,"device_count":4},"bathroom":{"label":"Bathroom","points_norm":[[0.4011,0.68085],[0.4011,0.78957],[0.54348,0.78957],[0.54348,0.68085]],"lights":[],"switches":[],"media":[],"appliances":[],"covers":[],"locks":[],"temp":null,"humidity":null,"motion":null,"climate":null,"device_count":0},"living_room":{"label":"Living Room","points_norm":[[0.77297,0.5748],[0.77297,0.91014],[0.9487,0.91014],[0.9487,0.5748]],"lights":["light.living_room_ceiling"],"switches":[],"media":["media_player.living_room_speaker"],"appliances":[],"covers":[],"locks":[],"temp":null,"humidity":null,"motion":null,"climate":null,"device_count":2},"garage":{"label":"Garage","points_norm":[[0.01215,0.39777],[0.01215,0.90134],[0.39535,0.90134],[0.39535,0.39777]],"lights":["light.gdo_left_garage_light","light.gdo_right_garage_light"],"switches":[],"media":[],"appliances":[],"covers":["cover.gdo_left_garage_door","cover.gdo_right_garage_door"],"locks":["lock.gdo_left_lock","lock.gdo_right_lock"],"temp":null,"humidity":null,"motion":null,"climate":null,"device_count":6}},"house":{"alarm_primary":"alarm_control_panel.house","alarm_secondary":["alarm_control_panel.garage","alarm_control_panel.master"],"weather":"weather.forecast_home","sun":"sun.sun","guest_mode":"input_boolean.guest_mode"},"cameras":[{"id":"driveway","label":"Driveway","entity":"camera.outside_driveway_camera","x":0.02,"y":0.972},{"id":"backyard_upper","label":"Backyard Upper","entity":"camera.backyard_backyard_upper_camera","x":0.7001,"y":0.0952},{"id":"kitchen","label":"Kitchen","entity":"camera.kitchen_kitchen_hub","x":0.4351,"y":0.0764},{"id":"garage","label":"Garage","entity":"camera.garage_garage_camera","x":0.2125,"y":0.4803},{"id":"front_door","label":"Front Door","entity":"camera.outside_front_door","x":0.6901,"y":0.972},{"id":"living_room","label":"Living Room","entity":"camera.living_room_living_room_camera","x":0.9434,"y":0.7409}]};
/* floorplan-cartoon-card — interactive cartoon floor plan for Home Assistant.
 *
 * Single file, no build step, no dependencies. Data (hotspots + entity map) is injected
 * by floorplan/cartoon/build_card.py as window.__FPC_DATA_<v>, because:
 *   - fetching JSON at runtime adds a second thing that can 404 or go stale against the
 *     image, and the polygons MUST match the image they were fitted to;
 *   - HA caches custom cards aggressively, so the data is versioned with the file.
 *
 * Design rules baked in (see docs/PHASE_CARTOON_REQUIREMENTS.md):
 *   - nothing looks interactive unless it is (FR-11);
 *   - state comes from hass.states, never from an optimistic local flip (FR-3);
 *   - a dead entity shows as unavailable, never as "off" (§5.3);
 *   - no SVG filters: glow is a radial gradient, animation is transform/opacity only (§7).
 */
(() => {
  const DATA = window.__FPC_DATA__;
  if (!DATA) {
    console.error('[floorplan-cartoon] data payload missing');
    return;
  }
  const { rooms, house, image, version, art_w: ART_W, art_h: ART_H, cameras = [] } = DATA;

  // Camera pins sit at plan coordinates (normalised to the art), not inside room polygons:
  // driveway and front door are exterior mounts, so they sit on the plan's edge.
  const CAM_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
    + 'd="M15 8.5V6a1.5 1.5 0 0 0-1.5-1.5h-9A1.5 1.5 0 0 0 3 6v10.5A1.5 1.5 0 0 0 4.5 18h9a1.5 1.5 0 0 0 '
    + '1.5-1.5v-2.4l4.2 2.7c.7.5 1.8 0 1.8-1V6.7c0-1-1.1-1.5-1.8-1z"/></svg>';
  const camPins = cameras.map((c) =>
    `<button class="cam" data-cam="${c.id}" style="left:${(c.x * 100).toFixed(2)}%;top:${(c.y * 100).toFixed(2)}%"`
    + ` aria-label="${c.label} camera" title="${c.label}">${CAM_ICON}</button>`).join('');
  const ART = `${image}?v=${version}`;

  const SVC = {
    light: 'light/toggle',
    switch: 'switch/toggle',
    media_player: 'media_player/media_play_pause',
    cover: 'cover/toggle',
  };
  const ON_STATES = new Set(['on', 'open', 'playing', 'unlocked']);

  const css = `
    :host {
      display: block;
      height: 100%;          /* panel-mode views hand the card the whole viewport */
      max-height: 100vh;     /* ...but HA computes that view as taller than the window */
      min-height: 0;
      --fpc-ink: #f2f5f8;
      --fpc-ink-dim: #a9b4c0;
      --fpc-panel: #10161d;
      --fpc-accent: #4ea1ff;
      --fpc-warn: #ff6b5e;
      --fpc-radius: 14px;
      --fpc-floor-glow: 0.55;
      position: relative;
    }
    :host([night]) { --fpc-ink: #e8eef6; --fpc-panel: #0a0f14; --fpc-floor-glow: 0.8; }
    /* height:100% + flex centring: the plan is fitted by JS to the SHORTER axis, so a
       3:2 render on a wider-than-3:2 tablet letterboxes instead of running off the
       bottom. Before this, .stage was width:100% and the art's height simply overflowed
       the viewport (measured: 813px of content in a 601px viewport). */
    .wrap { position: relative; background: #1a1f26; border-radius: var(--fpc-radius);
            overflow: hidden; height: 100%;
            display: flex; align-items: center; justify-content: center; }
    :host([night]) .wrap { background: #0c1116; }
    /* one composited layer, no animation: cheap enough for the tablet */
    :host([night]) .stage img { filter: brightness(.62) saturate(.82) hue-rotate(-8deg); }
    :host([night]) .stage svg { mix-blend-mode: normal; }
    /* aspect-ratio holds the correct shape before _fit() runs (and in a plain masonry
       column), so the image can safely fill BOTH axes: a width:auto height mismatch
       between img and .stage would slide the hotspot overlay off the art. flex:0 0 auto
       stops the card's flex centring from shrinking the stage -- measured 805px inline
       being rendered at 687px, which also pushed it off-centre. */
    .stage { position: relative; width: 100%; aspect-ratio: ${ART_W} / ${ART_H};
             flex: 0 0 auto; min-width: 0; display: block; }
    .stage img { display: block; width: 100%; height: 100%; user-select: none; -webkit-user-drag: none; }
    .stage svg { position: absolute; inset: 0; width: 100%; height: 100%; }
    .room { fill: rgba(78,161,255,0); stroke: rgba(78,161,255,0);
            stroke-width: calc(2.5 * var(--k, 3) * 1px);
            cursor: pointer; transition: fill .18s ease, stroke .18s ease; }
    .room:hover, .room:focus-visible { fill: rgba(78,161,255,.16); stroke: rgba(190,225,255,.85); outline: none; }
    .room.lit { fill: rgba(255,196,110,.08); stroke: rgba(255,206,130,.0); }
    .room.motion { animation: pulse 1.2s ease-in-out 2; }
    @keyframes pulse { 0%,100% { stroke-opacity: .35 } 50% { stroke-opacity: 1 } }
    .room.empty { cursor: default; }
    .room.empty:hover { fill: rgba(78,161,255,.05); stroke: rgba(150,170,190,.35); }
    .temp-bg { fill: rgba(12,17,22,.55); stroke: rgba(255,255,255,.18);
               stroke-width: calc(1 * var(--k, 3) * 1px); }
    .temp { fill: #fff; font-weight: 600; font-family: system-ui, sans-serif;
            font-size: calc(13 * var(--k, 3) * 1px); text-anchor: middle;
            paint-order: stroke; stroke: rgba(0,0,0,.55);
            stroke-width: calc(3 * var(--k, 3) * 1px); pointer-events: none; }
    .badge { fill: #12181f; fill-opacity: .72; stroke: rgba(255,255,255,.35); stroke-width: 1.5; }
    .badge-txt { fill: #fff; font-weight: 600; font-family: system-ui, sans-serif;
                 font-size: calc(12 * var(--k, 3) * 1px);
                 text-anchor: middle; dominant-baseline: middle; pointer-events: none; }

    /* Pinned, not in flow. As a flex item the HUD (309px wide) stole width from the
       centred .stage and shoved the plan 54px past the right edge. */
    .hud { display: flex; gap: 8px; align-items: center; padding: 8px 10px;
           position: absolute; top: 0; left: 0; right: 0; z-index: 2; }
    .chip { pointer-events: auto; display: inline-flex; align-items: center; gap: 6px;
            background: rgba(12,17,22,.78); border: 1px solid rgba(255,255,255,.14);
            color: var(--fpc-ink); border-radius: 999px; padding: 6px 11px;
            font: 600 12px/1 system-ui, sans-serif; backdrop-filter: blur(6px); }
    .chip button { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
                   min-height: 32px; }
    .chip.alarm-armed { border-color: rgba(255,107,94,.6); color: #ffd9d4; }
    .chip.alarm-triggered { background: rgba(120,20,16,.9); border-color: #ff6b5e; animation: pulse 1s infinite; }
    .chip.guest-on { background: rgba(255,193,87,.20); border-color: rgba(255,193,87,.6); color: #ffe9c2; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #57d98a; }
    .dot.off { background: #6d7a88; }
    .dot.warn { background: #ffb020; }
    .spacer { flex: 1; }

    .sheet { position: absolute; left: 0; right: 0; bottom: 0; max-height: 62%;
             background: color-mix(in srgb, var(--fpc-panel) 96%, transparent);
             color: var(--fpc-ink); border-top: 1px solid rgba(255,255,255,.12);
             border-radius: 16px 16px 0 0; transform: translateY(102%);
             transition: transform .22s cubic-bezier(.2,.8,.2,1); display: flex; flex-direction: column; }
    .sheet.open { transform: translateY(0); }
    .sheet header { display: flex; align-items: center; gap: 8px; padding: 12px 14px 8px; }
    .sheet h2 { font: 700 16px/1.2 system-ui, sans-serif; margin: 0; flex: 1; }
    .sheet .x { all: unset; cursor: pointer; font-size: 20px; line-height: 1; padding: 6px 10px;
                color: var(--fpc-ink-dim); }
    .rows { overflow: auto; padding: 0 10px 14px; display: grid; gap: 6px; }
    .row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; min-height: 44px;
           background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.07);
           border-radius: 10px; }
    .row .name { flex: 1; font: 500 14px/1.2 system-ui, sans-serif; }
    .row .meta { color: var(--fpc-ink-dim); font: 500 12px/1 system-ui, sans-serif; }
    .row button { all: unset; cursor: pointer; min-width: 68px; min-height: 34px; text-align: center;
                  border-radius: 8px; padding: 6px 10px; font: 600 12px/1 system-ui, sans-serif;
                  background: rgba(78,161,255,.16); border: 1px solid rgba(78,161,255,.4); color: #cfe6ff; }
    .row button.on { background: rgba(87,217,138,.18); border-color: rgba(87,217,138,.5); color: #c9ffe0; }
    .row button:disabled { opacity: .45; cursor: not-allowed; }
    .empty-note { padding: 6px 14px 18px; color: var(--fpc-ink-dim); font: 500 13px/1.4 system-ui, sans-serif; }
    /* Camera pins. Sits inside .stage so it scales with the art; pointer-events:none on
       the layer keeps room taps working between pins. */
    .cams { position: absolute; inset: 0; pointer-events: none; }
    .cam { position: absolute; transform: translate(-50%,-50%); pointer-events: auto;
           cursor: pointer; width: 32px; height: 32px; padding: 0; border-radius: 50%;
           display: grid; place-items: center; background: rgba(10,15,20,.82);
           border: 1px solid rgba(120,190,255,.62); color: #d6ebff;
           box-shadow: 0 2px 10px rgba(0,0,0,.45); -webkit-tap-highlight-color: transparent; }
    .cam svg { width: 17px; height: 17px; }
    .cam:active { background: rgba(78,161,255,.34); }
    .cam.off { border-color: rgba(255,255,255,.16); color: #7f8c99; }

    .camview { position: absolute; inset: 0; z-index: 6; display: none; flex-direction: column;
               background: rgba(4,7,10,.94); color: var(--fpc-ink);
               border-radius: var(--fpc-radius); }
    .camview.open { display: flex; }
    .camview header { display: flex; align-items: center; gap: 8px; padding: 10px 12px 4px; }
    .camview h2 { font: 700 15px/1.2 system-ui, sans-serif; margin: 0; flex: 1; }
    .camview .x { all: unset; cursor: pointer; font-size: 20px; line-height: 1; padding: 6px 10px;
                  color: var(--fpc-ink-dim); }
    .camview .frame { flex: 1; min-height: 0; display: grid; place-items: center; padding: 0 8px; }
    .camview img { max-width: 100%; max-height: 100%; border-radius: 10px; background: #000; }
    .camview footer { display: flex; align-items: center; gap: 10px; padding: 8px 12px 12px; }
    .camview .meta { flex: 1; color: var(--fpc-ink-dim); font: 500 12px/1 system-ui, sans-serif; }
    .camview footer button { all: unset; cursor: pointer; padding: 8px 14px; min-height: 38px;
        border-radius: 9px; background: rgba(78,161,255,.18);
        border: 1px solid rgba(78,161,255,.45); color: #cfe6ff;
        font: 600 13px/1 system-ui, sans-serif; }
    .camview footer button:disabled { opacity: .45; }

    .toast { position: absolute; left: 50%; bottom: 18px; transform: translate(-50%, 20px);
             background: rgba(150,30,24,.95); color: #fff; padding: 9px 14px; border-radius: 10px;
             font: 600 13px/1.2 system-ui, sans-serif; opacity: 0; pointer-events: none;
             transition: opacity .2s, transform .2s; }
    .toast.show { opacity: 1; transform: translate(-50%, 0); }
    @media (prefers-reduced-motion: reduce) {
      .room.motion, .chip.alarm-triggered { animation: none; }
      .sheet { transition: none; }
    }
  `;

  const fmt = (n) => (Math.round(n * 10) / 10).toFixed(1);

  class FloorplanCartoonCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._built = false;
      this._pressTimer = null;
      this._longPressed = false;
      this._ro = null;
    }

    setConfig(config) {
      this._config = config || {};
    }

    static getStubConfig() {
      return { type: 'custom:floorplan-cartoon-card' };
    }

    getCardSize() { return 12; }

    set hass(hass) {
      this._hass = hass;
      if (!this._built) this._build();
      this._update();
    }

    // Fit the art inside the card box on BOTH axes. Width-only sizing (the old
    // behaviour) is correct in a masonry column but overflows a panel-mode view, where
    // the card is as wide as the screen and the 3:2 art is taller than the viewport.
    // When the container has no height yet (masonry), fall back to width-only.
    _fit() {
      const sh = this.shadowRoot;
      if (!sh) return;
      const wrap = sh.querySelector('.wrap');
      const stage = sh.querySelector('.stage');
      if (!wrap || !stage) return;
      const aw = wrap.clientWidth || 0;
      const ah = wrap.clientHeight || 0;
      if (!aw) return;
      // Cap by window.innerHeight: the panel view measures 691px in a 601px window
      // (HA leaves header space even when kiosk-mode hides the header), so trusting the
      // container alone scaled the plan 90px past the bottom of the screen.
      const ahCap = Math.min(ah, window.innerHeight || ah);
      const scale = ahCap > 40 ? Math.min(aw / ART_W, ahCap / ART_H) : aw / ART_W;
      stage.style.width = Math.round(ART_W * scale) + 'px';
      stage.style.height = Math.round(ART_H * scale) + 'px';
    }

    disconnectedCallback() {
      if (this._ro) { this._ro.disconnect(); this._ro = null; }
      clearInterval(this._camTimer);
      this._camTimer = null;
    }

    // HA sizes the lovelace view taller than the viewport when the header is hidden
    // (measured 691px vs 601px), which leaves a scrollable band under the card. The card
    // cannot style its ancestors through the shadow boundary, but it can pin the host
    // element it lives in. Guarded: only touches elements that really are HA views.
    _pinViewHeight() {
      try {
        const root = this.getRootNode && this.getRootNode();
        const host = root && root.host;
        const tag = host && host.tagName ? host.tagName.toLowerCase() : '';
        if (tag === 'hui-view' || tag === 'hui-panel-view') {
          host.style.height = '100vh';
          host.style.minHeight = '0';
          host.style.overflow = 'hidden';
        }
      } catch (e) { /* never let cosmetics break the card */ }
    }

    _build() {
      const sh = this.shadowRoot;
      sh.innerHTML = `<style>${css}</style>
        <div class="wrap">
          <div class="hud">
            <span class="chip" id="clock"></span>
            <span class="chip" id="wx"><span class="dot off"></span><span class="t">—</span></span>
            <span class="chip" id="alarm"><button><span class="dot off"></span><span class="t">Alarm</span></button></span>
            <span class="chip" id="guest"><button title="Guest mode — keeps the house occupied so the alarm will not arm"><span class="dot off"></span><span class="t">Guest</span></button></span>
            <span class="spacer"></span>
            <span class="chip" id="mode"><button title="Toggle day/night">◐</button></span>
          </div>
          <div class="stage">
            <img alt="Floor plan" src="${ART}" draggable="false">
            <svg viewBox="0 0 ${ART_W} ${ART_H}" preserveAspectRatio="none" aria-hidden="false">
              <defs>
                <radialGradient id="lamp"><stop offset="0%" stop-color="#ffd79a" stop-opacity=".85"/>
                  <stop offset="60%" stop-color="#ffbc63" stop-opacity=".35"/>
                  <stop offset="100%" stop-color="#ffbc63" stop-opacity="0"/></radialGradient>
              </defs>
              <g class="glow"></g>
              <g class="rooms"></g>
              <g class="labels"></g>
            </svg>
            <div class="cams">${camPins}</div>
          </div>
          <div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-label="Room devices">
            <header><h2 id="sheetTitle">Room</h2><button class="x" aria-label="Close">×</button></header>
            <div class="rows" id="rows"></div>
          </div>
          <div class="camview" id="camview" role="dialog" aria-modal="true" aria-label="Camera">
            <header><h2 id="camTitle">Camera</h2><button class="x" aria-label="Close">×</button></header>
            <div class="frame"><img id="camImg" alt="" draggable="false"></div>
            <footer><span class="meta" id="camMeta"></span><button id="camLive">Live view</button></footer>
          </div>
          <div class="toast" id="toast"></div>
        </div>`;

      this._pinViewHeight();
      this._fit();
      if (window.ResizeObserver) {
        this._ro = new ResizeObserver(() => this._fit());
        this._ro.observe(sh.querySelector('.wrap'));
      }

      const svg = sh.querySelector('svg');
      const gRooms = svg.querySelector('.rooms');
      const gLabels = svg.querySelector('.labels');
      const gGlow = svg.querySelector('.glow');

      let i = 0;
      for (const [rid, room] of Object.entries(rooms)) {
        const pts = room.points_norm.map(([x, y]) => `${(x * ART_W).toFixed(1)},${(y * ART_H).toFixed(1)}`).join(' ');
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        poly.setAttribute('points', pts);
        poly.setAttribute('class', 'room' + (room.device_count ? '' : ' empty'));
        poly.dataset.room = rid;
        poly.setAttribute('tabindex', room.device_count ? '0' : '-1');
        poly.setAttribute('role', 'button');
        poly.setAttribute('aria-label', `${room.label}`);
        poly.style.fillOpacity = ''; // set per state
        gRooms.appendChild(poly);

        // glow pool at the centroid, sized to the polygon's extent
        const xs = room.points_norm.map((p) => p[0] * ART_W);
        const ys = room.points_norm.map((p) => p[1] * ART_H);
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        const rx = (Math.max(...xs) - Math.min(...xs)) * 0.55;
        const ry = (Math.max(...ys) - Math.min(...ys)) * 0.55;
        const glow = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
        glow.setAttribute('cx', cx); glow.setAttribute('cy', cy);
        glow.setAttribute('rx', rx); glow.setAttribute('ry', ry);
        glow.setAttribute('fill', 'url(#lamp)');
        glow.setAttribute('opacity', '0');
        glow.dataset.glow = rid;
        gGlow.appendChild(glow);

        if (room.temp) {
          const ty = (Math.min(...ys) + (Math.max(...ys) - Math.min(...ys)) * 0.22);
          const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          bg.setAttribute('x', cx - 62); bg.setAttribute('y', ty - 30);
          bg.setAttribute('width', 124); bg.setAttribute('height', 46);
          bg.setAttribute('rx', 23);
          bg.setAttribute('class', 'temp-bg');
          bg.dataset.tempbg = rid;
          gLabels.appendChild(bg);
          const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          t.setAttribute('x', cx);
          t.setAttribute('y', ty + 3);
          t.setAttribute('class', 'temp');
          t.setAttribute('dominant-baseline', 'middle');
          t.dataset.temp = rid;
          gLabels.appendChild(t);
        }
        i++;
      }

      // interactions
      gRooms.addEventListener('pointerdown', (e) => this._down(e));
      gRooms.addEventListener('pointerup', (e) => this._up(e));
      gRooms.addEventListener('pointercancel', () => clearTimeout(this._pressTimer));
      gRooms.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this._openSheet(e.target.dataset.room);
        }
      });
      sh.getElementById('alarm').addEventListener('click', () => this._openSheet('__alarm'));
      sh.getElementById('guest').addEventListener('click', () => this._toggleGuest());
      sh.getElementById('mode').addEventListener('click', () => this._toggleNight());
      sh.querySelectorAll('.cam').forEach((b) => {
        b.addEventListener('click', (e) => { e.stopPropagation(); this._openCam(b.dataset.cam); });
      });
      sh.querySelector('#camview .x').addEventListener('click', () => this._closeCam());
      sh.querySelector('#camLive').addEventListener('click', () => this._liveCam());
      sh.querySelector('.sheet .x').addEventListener('click', () => this._closeSheet());
      sh.getElementById('sheet').addEventListener('click', (e) => {
        if (e.target.id === 'sheet') this._closeSheet();
      });
      this._esc = (e) => {
        if (e.key !== 'Escape') return;
        if (sh.getElementById('camview').classList.contains('open')) this._closeCam();
        else this._closeSheet();
      };
      document.addEventListener('keydown', this._esc);

      // --k = art pixels per rendered pixel: keeps every stroke and label the same
      // apparent size at any card width. Inside a 1x1 viewBox a "13px" label became
      // 13 *user units* = 10,400 screen px, which painted the whole card dark -- the
      // bug this viewBox change fixes.
      const setK = () => {
        const w = svg.getBoundingClientRect().width || 800;
        svg.style.setProperty('--k', String(ART_W / w));
      };
      setK();
      if (window.ResizeObserver) new ResizeObserver(setK).observe(svg);

      this._built = true;
    }

    disconnectedCallback() {
      if (this._esc) document.removeEventListener('keydown', this._esc);
      clearTimeout(this._pressTimer);
    }

    // ---- interaction -------------------------------------------------------
    _down(e) {
      const el = e.target.closest('.room');
      if (!el) return;
      this._longPressed = false;
      const rid = el.dataset.room;
      this._pressTimer = setTimeout(() => {
        this._longPressed = true;
        this._toggleAll(rid);
      }, 600);
    }

    _up(e) {
      clearTimeout(this._pressTimer);
      const el = e.target.closest('.room');
      if (!el || this._longPressed) return;
      this._openSheet(el.dataset.room);
    }

    _toggleAll(rid) {
      const room = rooms[rid];
      const ids = [...(room.lights || []), ...(room.switches || [])];
      if (!ids.length) return;
      const anyOff = ids.some((id) => this._state(id) !== 'on');
      const svc = anyOff ? 'turn_on' : 'turn_off';
      ids.forEach((id) => {
        const dom = id.split('.')[0];
        this._call(dom === 'light' ? `light/${svc}` : `homeassistant/${svc}`, { entity_id: id });
      });
      this._toast(`${anyOff ? 'On' : 'Off'}: ${room.label}`);
    }

    // ---- cameras -----------------------------------------------------------
    _camEntry(id) { return cameras.find((c) => c.id === id); }

    _openCam(id) {
      const cam = this._camEntry(id);
      if (!cam) return;
      this._cam = cam;
      this._closeSheet();
      const sh = this.shadowRoot;
      sh.getElementById('camTitle').textContent = cam.label;
      sh.getElementById('camImg').alt = cam.label + ' camera snapshot';
      this._snap();
      clearInterval(this._camTimer);
      this._camTimer = setInterval(() => this._snap(), 5000);
      sh.getElementById('camview').classList.add('open');
    }

    // HA camera entities expose a signed still in entity_picture. The URL is cached by the
    // browser, so a cache-buster is what turns "the same frame forever" into a refreshed one.
    _snap() {
      const cam = this._cam, sh = this.shadowRoot;
      if (!cam || !sh) return;
      const st = this._hass && this._hass.states ? this._hass.states[cam.entity] : null;
      const img = sh.getElementById('camImg');
      const meta = sh.getElementById('camMeta');
      const live = sh.getElementById('camLive');
      if (!st) { img.removeAttribute('src'); meta.textContent = 'no entity'; live.disabled = true; return; }
      const pic = st.attributes && st.attributes.entity_picture;
      const t = new Date().toLocaleTimeString();
      if (!pic) {
        img.removeAttribute('src');
        meta.textContent = st.state + ' · no snapshot';
        live.disabled = st.state === 'unavailable';
        return;
      }
      img.src = pic + (pic.indexOf('?') >= 0 ? '&' : '?') + '_=' + Date.now();
      meta.textContent = st.state + ' · ' + t;
      live.disabled = st.state === 'unavailable';
    }

    _liveCam() {
      if (!this._cam) return;
      // Hand off to HA's own dialog: it owns the WebRTC/HLS player, the audio track and the
      // Nest stream lifecycle. A second player inside the card would only fight it.
      this.dispatchEvent(new CustomEvent('hass-more-info',
        { detail: { entityId: this._cam.entity }, bubbles: true, composed: true }));
      this._closeCam();
    }

    _closeCam() {
      clearInterval(this._camTimer);
      this._camTimer = null;
      this._cam = null;
      const sh = this.shadowRoot;
      if (sh) sh.getElementById('camview').classList.remove('open');
    }

    _openSheet(rid) {
      const sh = this.shadowRoot;
      const sheet = sh.getElementById('sheet');
      const rows = sh.getElementById('rows');
      const title = sh.getElementById('sheetTitle');
      rows.innerHTML = '';

      if (rid === '__alarm') {
        title.textContent = 'Alarm';
        this._alarmRows(rows);
      } else {
        const room = rooms[rid];
        if (!room) return;
        title.textContent = room.label;
        this._deviceRows(rows, room);
      }
      sheet.classList.add('open');
      this._sheetRoom = rid;
    }

    _closeSheet() {
      this.shadowRoot.getElementById('sheet').classList.remove('open');
      this._sheetRoom = null;
    }

    _deviceRows(host, room) {
      const groups = [
        ['Doors', room.covers],
        ['Locks', room.locks],
        ['Lights', room.lights],
        ['Switches', room.switches],
        ['Appliances', room.appliances],
        ['Media', room.media],
      ];
      let any = false;
      for (const [label, ids] of groups) {
        for (const id of ids || []) {
          any = true;
          host.appendChild(this._row(id));
        }
      }
      if (room.climate) { any = true; host.appendChild(this._climateRow(room.climate)); }
      if (room.temp) {
        any = true;
        const r = document.createElement('div');
        r.className = 'row';
        r.innerHTML = `<span class="name">Temperature</span><span class="meta" data-sensor="${room.temp}"></span>`;
        host.appendChild(r);
      }
      if (room.humidity) {
        const r = document.createElement('div');
        r.className = 'row';
        r.innerHTML = `<span class="name">Humidity</span><span class="meta" data-sensor="${room.humidity}"></span>`;
        host.appendChild(r);
      }
      if (!any) {
        const p = document.createElement('div');
        p.className = 'empty-note';
        p.textContent = 'No devices in this room.';
        host.appendChild(p);
      }
      this._refreshSheetValues();
    }

    _alarmRows(host) {
      const ids = [house.alarm_primary, ...(house.alarm_secondary || [])];
      for (const id of ids) {
        const st = this._state(id);
        const row = document.createElement('div');
        row.className = 'row';
        const name = this._friendly(id);
        const modes = this._alarmModes(id);
        row.innerHTML = `<span class="name">${name}</span><span class="meta">${st}</span>`;
        const box = document.createElement('span');
        for (const m of modes) {
          const b = document.createElement('button');
          b.textContent = m.label;
          b.onclick = () => this._alarmSet(id, m.service);
          box.appendChild(b);
          box.appendChild(document.createTextNode(' '));
        }
        row.appendChild(box);
        host.appendChild(row);
      }
    }

    _alarmModes(id) {
      const st = this._hass.states[id];
      const f = (st && st.attributes && st.attributes.supported_features) || 0;
      const out = [];
      if (f & 1) out.push({ label: 'Home', service: 'alarm_arm_home' });
      if (f & 2) out.push({ label: 'Away', service: 'alarm_arm_away' });
      if (f & 4) out.push({ label: 'Night', service: 'alarm_arm_night' });
      out.push({ label: 'Disarm', service: 'alarm_disarm' });
      return out;
    }

    _alarmSet(id, service) {
      this._call(`alarm_control_panel/${service}`, { entity_id: id });
    }

    _climateRow(id) {
      const row = document.createElement('div');
      row.className = 'row';
      row.innerHTML = `<span class="name">${this._friendly(id)}</span><span class="meta" data-sensor="${id}"></span>`;
      return row;
    }

    _row(id) {
      const row = document.createElement('div');
      row.className = 'row';
      const st = this._state(id);
      const dom = id.split('.')[0];
      const label = this._friendly(id);
      row.innerHTML = `<span class="name">${label}</span>
        <span class="meta" data-state="${id}">${st}</span>
        <button data-toggle="${id}" aria-label="Toggle ${label}"></button>`;
      const btn = row.querySelector('button');
      btn.onclick = () => {
        const st = this._state(id);
        if (dom === 'lock') {
          this._call(`lock/${st === 'locked' ? 'unlock' : 'lock'}`, { entity_id: id });
          return;
        }
        if (!SVC[dom]) { this._toast(`No control for ${dom}`); return; }
        const [d, s] = SVC[dom].split('/');
        this._call(`${d}/${s}`, { entity_id: id });
      };
      return row;
    }

    // ---- state → visuals ---------------------------------------------------
    _update() {
      // a pin whose camera is unreachable should read as dead, not as "tap me"
      const sh0 = this.shadowRoot;
      if (sh0) sh0.querySelectorAll('.cam').forEach((b) => {
        const c = this._camEntry(b.dataset.cam);
        const st = c && this._hass && this._hass.states ? this._hass.states[c.entity] : null;
        b.classList.toggle('off', !st || st.state === 'unavailable');
      });
      const hass = this._hass;
      if (!hass) return;
      const sh = this.shadowRoot;

      // clock
      const now = new Date();
      sh.getElementById('clock').textContent =
        now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

      // night mode from the sun
      const sun = house.sun && hass.states[house.sun];
      const night = sun ? sun.state === 'below_horizon' : false;
      if (night !== this._autoNight) {
        this._autoNight = night;
        if (!this._manualNight) this.toggleAttribute('night', night);
      }

      // weather
      const wx = house.weather && hass.states[house.weather];
      const wxChip = sh.getElementById('wx');
      if (wx) {
        const t = wx.attributes.temperature;
        const WORDS = { 'clear-night': 'Clear', 'partlycloudy': 'Partly cloudy',
          'cloudy': 'Cloudy', 'rainy': 'Rain', 'snowy': 'Snow', 'fog': 'Fog',
          'windy': 'Windy', 'lightning': 'Storms', 'hail': 'Hail',
          'exceptional': 'Alert', 'sunny': 'Sunny', 'clear': 'Clear' };
        const cond = WORDS[wx.state] || wx.state.replace(/[-_]/g, ' ');
        // condition only, no "night" wording: the entity reports clear-night at midday and
        // the label then contradicts the clock next to it.
        wxChip.querySelector('.t').textContent =
          `${cond}${t !== undefined ? ` · ${fmt(t)}°` : ''}`;
        wxChip.querySelector('.dot').className = 'dot';
      } else {
        wxChip.querySelector('.t').textContent = '—';
        wxChip.querySelector('.dot').className = 'dot off';
      }

      // alarm
      const al = house.alarm_primary && hass.states[house.alarm_primary];
      const alChip = sh.getElementById('alarm');
      if (al) {
        alChip.querySelector('.t').textContent = al.state.replace(/_/g, ' ');
        alChip.classList.toggle('alarm-triggered', al.state === 'triggered');
        alChip.classList.toggle('alarm-armed',
          ['armed_home', 'armed_away', 'armed_night'].includes(al.state));
        alChip.querySelector('.dot').className =
          al.state === 'triggered' ? 'dot warn'
            : al.state.startsWith('armed') ? 'dot warn' : 'dot off';
      }

      // guest mode — manual override that keeps the house "occupied" so mode_away and
      // alarm_arm_away cannot fire while somebody is staying over.
      const gChip = sh.getElementById('guest');
      if (gChip) {
        const g = house.guest_mode && hass.states[house.guest_mode];
        const gOn = !!g && g.state === 'on';
        gChip.classList.toggle('guest-on', gOn);
        gChip.querySelector('.t').textContent = gOn ? 'Guest on' : 'Guest';
        gChip.querySelector('.dot').className = gOn ? 'dot warn' : 'dot off';
        gChip.style.display = house.guest_mode ? '' : 'none';
      }

      // rooms
      for (const [rid, room] of Object.entries(rooms)) {
        const poly = sh.querySelector(`.room[data-room="${rid}"]`);
        if (!poly) continue;
        const ids = [...(room.lights || []), ...(room.switches || [])];
        const anyOn = ids.some((id) => this._state(id) === 'on');
        poly.classList.toggle('lit', anyOn);
        const glow = sh.querySelector(`ellipse[data-glow="${rid}"]`);
        if (glow) glow.setAttribute('opacity', anyOn ? '1' : '0');

        const motionId = room.motion;
        if (motionId) {
          const m = this._state(motionId) === 'on';
          if (m && !poly.classList.contains('motion')) {
            poly.classList.add('motion');
            setTimeout(() => poly.classList.remove('motion'), 2600);
          }
        }

        if (room.temp) {
          const t = sh.querySelector(`text[data-temp="${rid}"]`);
          const st = hass.states[room.temp];
          const pill = sh.querySelector(`rect[data-tempbg="${rid}"]`);
          const has = st && !['unknown', 'unavailable'].includes(st.state);
          if (t) t.textContent = has ? `${fmt(parseFloat(st.state))}°` : '';
          if (pill) pill.setAttribute('opacity', has ? '1' : '0');
        }
      }

      if (this._sheetRoom) this._refreshSheetValues();
    }

    _refreshSheetValues() {
      const sh = this.shadowRoot;
      sh.querySelectorAll('[data-toggle]').forEach((btn) => {
        const id = btn.dataset.toggle;
        const st = this._state(id);
        const dom = id.split('.')[0];
        const active = ON_STATES.has(st);
        const words = dom === 'lock' ? ['Locked', 'Unlocked']
          : dom === 'cover' ? ['Open', 'Closed']
          : ['On', 'Off'];
        // the button shows the ACTION, not the state: on a lock "Unlocked" as a button
        // label reads as "press to unlock", which is the opposite of what happens.
        btn.textContent = dom === 'lock' ? (st === 'locked' ? 'Unlock' : 'Lock')
          : dom === 'cover' ? (active ? 'Close' : 'Open')
          : (active ? 'Off' : 'On');
        btn.classList.toggle('on', active);
        btn.disabled = ['unavailable', 'unknown'].includes(st);
        void words;
      });
      sh.querySelectorAll('[data-state]').forEach((el) => {
        el.textContent = this._state(el.dataset.state);
      });
      sh.querySelectorAll('[data-sensor]').forEach((el) => {
        const st = this._hass.states[el.dataset.sensor];
        if (!st) { el.textContent = '—'; return; }
        if (st.attributes.current_temperature !== undefined) {
          el.textContent = `${fmt(st.attributes.current_temperature)}° · ${st.state}`;
        } else {
          el.textContent = ['unknown', 'unavailable'].includes(st.state) ? '—'
            : `${fmt(parseFloat(st.state))}${st.attributes.unit_of_measurement || ''}`;
        }
      });
    }

    // ---- helpers -----------------------------------------------------------
    _state(id) {
      const s = this._hass && this._hass.states[id];
      return s ? s.state : 'unavailable';
    }

    _friendly(id) {
      const s = this._hass && this._hass.states[id];
      return (s && s.attributes && s.attributes.friendly_name) || id.split('.')[1].replace(/_/g, ' ');
    }

    _call(service, data) {
      const [domain, svc] = service.split('/');
      this._hass.callService(domain, svc, data).catch((err) => {
        this._toast(`${svc.replace(/_/g, ' ')} failed`);
        console.error('[floorplan-cartoon] service call failed', service, data, err);
      });
    }

    _toast(msg) {
      const t = this.shadowRoot.getElementById('toast');
      if (!t) return;
      t.textContent = msg;
      t.classList.add('show');
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
    }

    _toggleGuest() {
      const g = house.guest_mode;
      if (!g) return;
      const on = this._state(g) === 'on';
      this._call(`input_boolean/${on ? 'turn_off' : 'turn_on'}`, { entity_id: g });
      this._toast(on ? 'Guest mode off' : 'Guest mode on — house stays occupied');
    }

    _toggleNight() {
      this._manualNight = !this._manualNight;
      this.toggleAttribute('night', this._manualNight ? !this.hasAttribute('night') : this._autoNight);
    }
  }

  customElements.define('floorplan-cartoon-card', FloorplanCartoonCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'floorplan-cartoon-card',
    name: 'Cartoon Floorplan',
    description: 'Interactive cartoon floor plan',
  });
})();
