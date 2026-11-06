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

  var markers = [];
  var active = 'all';

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
    return '<div class="popup">' +
      '<h3>' + esc(p.name) + '</h3>' +
      (p.name_ja ? '<div class="ja">' + esc(p.name_ja) + '</div>' : '') +
      '<p>' + esc(p.desc) + '</p>' +
      '<div class="links">' + links + nav + '</div>' +
      (p.verified === false ? '<div class="warn">Location is approximate.</div>' : '') +
      '</div>';
  }

  function render() {
    markers.forEach(function (m) {
      var show = active === 'all' || m.cat === active;
      if (show && !map.hasLayer(m.marker)) m.marker.addTo(map);
      if (!show && map.hasLayer(m.marker)) map.removeLayer(m.marker);
    });
    document.querySelectorAll('.chip').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.cat === active));
    });
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
  }

  fetch('data/pins.json')
    .then(function (r) { return r.json(); })
    .then(function (pins) {
      pins.forEach(function (p) {
        var icon = L.divIcon({
          className: '',
          html: '<div class="pin ' + esc(p.category) + '"></div>',
          iconSize: [26, 26],
          iconAnchor: [13, 26],
          popupAnchor: [0, -24]
        });
        var marker = L.marker([p.lat, p.lng], { icon: icon, title: p.name })
          .bindPopup(popupHtml(p), { maxWidth: 260 });
        markers.push({ marker: marker, cat: p.category });
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
