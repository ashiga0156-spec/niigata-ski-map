(function () {
  'use strict';

  var CATEGORIES = [
    { id: 'all', label: 'All' },
    { id: 'ski', label: 'Ski' },
    { id: 'sake', label: 'Sake' },
    { id: 'access', label: 'Access' }
  ];

  var map = L.map('map', { zoomControl: true }).setView([37.05, 138.5], 9);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  var VISIT_LABEL = { A: 'Tour & tasting', B: 'Shop only', C: 'Inquire first' };
  var cluster = L.markerClusterGroup({
    maxClusterRadius: 40,
    showCoverageOnHover: false,
    disableClusteringAtZoom: 13
  });
  map.addLayer(cluster);

  var markers = [];
  var active = 'all';
  var toursOnly = false;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function safeUrl(u) {
    return /^https?:\/\//i.test(u) ? u : '';
  }

  function popupHtml(p) {
    var links = (p.links || []).map(function (l) {
      var url = safeUrl(l.url);
      if (!url) return '';
      // rel="sponsored" is appropriate for affiliate links
      var rel = l.affiliate ? 'sponsored noopener' : 'noopener';
      return '<a href="' + esc(url) + '" target="_blank" rel="' + rel + '">' + esc(l.label) + '</a>';
    }).join('');
    var nav = '<a href="https://www.google.com/maps/search/?api=1&query=' + p.lat + ',' + p.lng +
      '" target="_blank" rel="noopener">Open in Google Maps</a>';
    var badge = '';
    if (p.category === 'sake' && VISIT_LABEL[p.visit]) {
      var seasonal = p.visit === 'A' && /^Seasonal/i.test(p.visit_note || '');
      badge = '<div class="visit visit-' + p.visit + '"><span class="badge">' +
        esc(VISIT_LABEL[p.visit]) + (seasonal ? ' · Seasonal' : '') + '</span>' +
        (p.visit_note ? '<span class="note">' + esc(p.visit_note) + '</span>' : '') + '</div>';
    }
    return '<div class="popup">' +
      '<h3>' + esc(p.name) + '</h3>' +
      (p.name_ja ? '<div class="ja">' + esc(p.name_ja) + '</div>' : '') +
      badge +
      '<p>' + esc(p.desc) + '</p>' +
      '<div class="links">' + links + nav + '</div>' +
      (p.verified === false ? '<div class="warn">Location is approximate.</div>' : '') +
      '</div>';
  }

  function render() {
    var shown = markers.filter(function (m) {
      if (active !== 'all' && m.cat !== active) return false;
      // "Tours only" hides sake pins that are not A; ski/access pins are unaffected.
      if (toursOnly && m.cat === 'sake' && m.visit !== 'A') return false;
      return true;
    }).map(function (m) { return m.marker; });
    cluster.clearLayers();
    cluster.addLayers(shown);
    document.querySelectorAll('.chip[data-cat]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.cat === active));
    });
    var t = document.getElementById('tours-only');
    if (t) t.setAttribute('aria-pressed', String(toursOnly));
  }

  function buildFilters() {
    var box = document.getElementById('filters');
    CATEGORIES.forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.dataset.cat = c.id;
      b.textContent = c.label;
      b.addEventListener('click', function () { active = c.id; render(); });
      box.appendChild(b);
    });
    var t = document.createElement('button');
    t.type = 'button';
    t.id = 'tours-only';
    t.className = 'chip chip-tours';
    t.textContent = 'Tours only';
    t.title = 'Show only breweries that offer a tour and tasting';
    t.addEventListener('click', function () { toursOnly = !toursOnly; render(); });
    box.appendChild(t);
  }

  fetch('data/pins.json')
    .then(function (r) { return r.json(); })
    .then(function (pins) {
      pins.forEach(function (p) {
        var isSake = p.category === 'sake' && VISIT_LABEL[p.visit];
        var visitClass = isSake ? ' visit-' + p.visit : '';
        // A pins are larger; B/C sake pins are smaller.
        var sz = !isSake ? 26 : (p.visit === 'A' ? 32 : 20);
        var icon = L.divIcon({
          className: '',
          html: '<div class="pin ' + esc(p.category) + visitClass + '"></div>',
          iconSize: [sz, sz],
          iconAnchor: [sz / 2, sz],
          popupAnchor: [0, -(sz - 2)]
        });
        var marker = L.marker([p.lat, p.lng], { icon: icon, title: p.name })
          .bindPopup(popupHtml(p), { maxWidth: 260 });
        markers.push({ marker: marker, cat: p.category, visit: p.visit });
      });
      render();
      if (markers.length) {
        var group = L.featureGroup(markers.map(function (m) { return m.marker; }));
        map.fitBounds(group.getBounds().pad(0.15));
      }
    })
    .catch(function (e) { console.error('Failed to load pins', e); });

  buildFilters();

  var me;
  document.getElementById('locate').addEventListener('click', function () {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
      var ll = [pos.coords.latitude, pos.coords.longitude];
      if (me) map.removeLayer(me);
      me = L.circleMarker(ll, { radius: 8, color: '#fff', weight: 3, fillColor: '#1f7ae0', fillOpacity: 1 }).addTo(map);
      map.setView(ll, 12);
    });
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('sw.js').catch(function (e) { console.warn('SW failed', e); });
    });
  }
})();
