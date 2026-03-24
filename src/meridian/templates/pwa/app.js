/* Meridian PWA — Connection Setup */
(function() {
'use strict';

/* -----------------------------------------------------------------------
 * i18n translations
 * ----------------------------------------------------------------------- */
var T = {
  ru: {
    title: 'Настройка подключения',
    subtitle: 'Отсканируйте QR-код или нажмите, чтобы открыть в приложении',
    trust: 'Это безопасное подключение, настроенное для вас',
    'trust.named': '{name} настроил(а) это подключение для вас',
    primary: 'Основной', backup: 'Резервный',
    'primary.rec': 'Рекомендовано',
    'primary.desc': 'Рекомендуется — самое быстрое и надёжное подключение. Используйте в первую очередь.',
    'backup.desc': 'Запасной — через CDN. Используйте, только если оба варианта выше не работают.',
    'xhttp.desc': 'Альтернатива — используйте, если Основной не работает. Труднее обнаружить.',
    open: 'Открыть в приложении',
    share: 'Поделиться',
    'copy.link': 'Скопировать ссылку',
    'show.raw': 'Показать ссылку',
    'copy.hint': 'нажмите для копирования',
    apps: 'Приложения',
    'apps.desc': 'Установите одно из них, затем нажмите «Открыть в приложении» или отсканируйте QR-код.',
    setup: 'Быстрая настройка',
    step1: 'Установите клиентское приложение из списка выше',
    step2: 'Нажмите «Открыть в приложении» — подключение импортируется автоматически',
    step3: 'Или отсканируйте QR-код с другого устройства',
    step4: 'Активируйте подключение в приложении',
    clock: 'Синхронизация часов',
    'clock.desc': 'Часы устройства должны быть точными с отклонением не более 30 секунд. Откройте Настройки > Дата и время > включите «Автоматически».',
    ping: 'Не подключается?',
    'ping.desc': 'Проверьте, доступен ли сервер с вашего устройства:',
    'ping.link': 'Запустить тест',
    stats: 'Использование', 'stats.upload': 'Загрузка', 'stats.download': 'Скачивание',
    'install.title': 'Установите приложение',
    'install.btn': 'Установить',
    'sub.label': 'Подписка (автообновление)',
    'sub.desc': 'Добавьте этот URL как подписку в приложении для автоматических обновлений.',
    'install.offline': 'Доступ к подключению офлайн',
    'backup.direct': 'ЗАПАСНОЙ (ПРЯМОЙ)',
    'relay.desc': 'Подключайтесь через реле для лучшей надёжности в вашем регионе.',
    'direct.desc': 'Прямое подключение — используйте, если реле недоступно.',
    'more.options': 'Другие варианты подключения',
    'show.qr': 'Показать QR-код',
    'share.page': 'Поделиться этой страницей',
  },
  fa: {
    title: 'تنظیم اتصال',
    subtitle: 'کد QR را اسکن کنید یا برای باز کردن در برنامه ضربه بزنید',
    trust: 'این یک اتصال امن است که برای شما تنظیم شده',
    'trust.named': '{name} این اتصال را برای شما تنظیم کرده',
    primary: 'اصلی', backup: 'پشتیبان',
    'primary.rec': 'پیشنهادی',
    'primary.desc': 'پیشنهادی — سریع‌ترین و پایدارترین اتصال. ابتدا این را امتحان کنید.',
    'backup.desc': 'جایگزین نهایی — از طریق CDN. فقط اگر هر دو گزینه بالا کار نکرد استفاده کنید.',
    'xhttp.desc': 'جایگزین — اگر اصلی کار نمی‌کند استفاده کنید. شناسایی آن دشوارتر است.',
    open: 'باز کردن در برنامه',
    share: 'اشتراک‌گذاری',
    'copy.link': 'کپی لینک',
    'show.raw': 'نمایش لینک',
    'copy.hint': 'برای کپی ضربه بزنید',
    apps: 'برنامه‌ها',
    'apps.desc': 'یکی را نصب کنید، سپس «باز کردن در برنامه» را بزنید یا کد QR را اسکن کنید.',
    setup: 'راه‌اندازی سریع',
    step1: 'یک برنامه کلاینت از لیست بالا نصب کنید',
    step2: '«باز کردن در برنامه» را بزنید — اتصال به‌طور خودکار وارد می‌شود',
    step3: 'یا کد QR را از دستگاه دیگری اسکن کنید',
    step4: 'اتصال را در برنامه فعال کنید',
    clock: 'همگام‌سازی ساعت',
    'clock.desc': 'ساعت دستگاه باید با دقت ۳۰ ثانیه تنظیم باشد. به تنظیمات > تاریخ و ساعت > «تنظیم خودکار» بروید.',
    ping: 'متصل نمی‌شوید?',
    'ping.desc': 'بررسی کنید آیا سرور از دستگاه شما قابل دسترسی است:',
    'ping.link': 'اجرای تست پینگ',
    stats: 'مصرف', 'stats.upload': 'آپلود', 'stats.download': 'دانلود',
    'install.title': 'برنامه را نصب کنید',
    'install.btn': 'نصب',
    'sub.label': 'اشتراک (بروزرسانی خودکار)',
    'sub.desc': 'این URL را به عنوان اشتراک در برنامه اضافه کنید.',
    'install.offline': 'دسترسی آفلاین به اتصال',
    'backup.direct': 'پشتیبان (مستقیم)',
    'relay.desc': 'برای بهترین پایداری در منطقه خود از طریق رله متصل شوید.',
    'direct.desc': 'اتصال مستقیم — اگر رله در دسترس نیست استفاده کنید.',
    'more.options': 'گزینه‌های دیگر',
    'show.qr': 'نمایش کد QR',
    'share.page': 'اشتراک‌گذاری این صفحه',
  },
  zh: {
    title: '连接设置',
    subtitle: '扫描二维码或点击在应用中打开',
    trust: '这是为您设置的安全连接',
    'trust.named': '{name} 为您设置了此连接',
    primary: '主要', backup: '备用',
    'primary.rec': '推荐',
    'primary.desc': '推荐 — 最快最稳定的连接。请优先使用。',
    'backup.desc': '备用通道 — 通过 CDN 路由。仅在以上两种都失败时使用。',
    'xhttp.desc': '备选 — 主连接不可用时使用。更难被检测。',
    open: '在应用中打开',
    share: '分享',
    'copy.link': '复制链接',
    'show.raw': '显示链接',
    'copy.hint': '点击复制',
    apps: '客户端应用',
    'apps.desc': '安装一个应用，然后点击"在应用中打开"或扫描二维码。',
    setup: '快速设置',
    step1: '从上方列表安装一个客户端应用',
    step2: '点击"在应用中打开"——连接自动导入',
    step3: '或从另一台设备扫描二维码',
    step4: '在应用中激活连接',
    clock: '时钟同步',
    'clock.desc': '设备时钟必须精确到 30 秒以内。前往设置 > 日期与时间 > 启用"自动设置"。',
    ping: '无法连接？',
    'ping.desc': '测试服务器是否可从您的设备访问：',
    'ping.link': '运行Ping测试',
    stats: '用量', 'stats.upload': '上传', 'stats.download': '下载',
    'install.title': '安装应用',
    'install.btn': '安装',
    'sub.label': '订阅（自动更新）',
    'sub.desc': '将此 URL 作为订阅添加到应用中以自动更新。',
    'install.offline': '离线访问连接',
    'backup.direct': '备用（直连）',
    'relay.desc': '通过中继连接以获得最佳可靠性。',
    'direct.desc': '直接连接 — 中继不可用时使用。',
    'more.options': '更多连接选项',
    'show.qr': '显示二维码',
    'share.page': '分享此页面',
  },
};

/* -----------------------------------------------------------------------
 * Platform detection
 * ----------------------------------------------------------------------- */
function detectPlatform() {
  var ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  if (/Mac/i.test(ua) && navigator.maxTouchPoints > 1) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  if (/Win/i.test(ua)) return 'windows';
  if (/Mac/i.test(ua)) return 'macos';
  return 'linux';
}

/* -----------------------------------------------------------------------
 * Deep link construction
 * ----------------------------------------------------------------------- */
function buildOpenUrl(url, platform) {
  if (platform === 'android') {
    return 'intent://import/' + encodeURIComponent(url) +
      '#Intent;scheme=hiddify;package=app.hiddify.com;' +
      'S.browser_fallback_url=' + encodeURIComponent(
        'https://play.google.com/store/apps/details?id=app.hiddify.com'
      ) + ';end';
  }
  return url;
}

function tryOpenIOS(index) {
  var el = document.querySelector('[data-ios-idx="' + index + '"]');
  if (!el) return;
  var url = el.getAttribute('data-url');
  if (!url) return;
  copyToClipboard(url);
  var start = Date.now();
  window.location.href = url;
  setTimeout(function() {
    if (Date.now() - start < 2000) {
      window.location.href = 'https://apps.apple.com/app/v2raytun/id6476628951';
    }
  }, 1500);
}

/* -----------------------------------------------------------------------
 * Clipboard + toast
 * ----------------------------------------------------------------------- */
function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(showToast).catch(function() {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
  if ('vibrate' in navigator) navigator.vibrate(30);
}

function fallbackCopy(text) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  showToast();
}

function showToast() {
  var t = document.getElementById('toast');
  if (!t) return;
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 1200);
}

/* -----------------------------------------------------------------------
 * Screen Wake Lock
 * ----------------------------------------------------------------------- */
var wakeLock = null;

function requestWakeLock() {
  if (!('wakeLock' in navigator)) return;
  navigator.wakeLock.request('screen').then(function(wl) {
    wakeLock = wl;
    wl.addEventListener('release', function() { wakeLock = null; });
  }).catch(function() {});
}

document.addEventListener('visibilitychange', function() {
  if (wakeLock === null && document.visibilityState === 'visible') {
    requestWakeLock();
  }
});

/* -----------------------------------------------------------------------
 * PWA install prompt
 * ----------------------------------------------------------------------- */
var deferredInstallPrompt = null;

window.addEventListener('beforeinstallprompt', function(e) {
  e.preventDefault();
  if (window.matchMedia('(display-mode: standalone)').matches || navigator.standalone) return;
  deferredInstallPrompt = e;
  var banner = document.getElementById('install-banner');
  if (banner) banner.classList.add('show');
});

function handleInstallClick() {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  deferredInstallPrompt.userChoice.then(function() {
    deferredInstallPrompt = null;
    var banner = document.getElementById('install-banner');
    if (banner) banner.classList.remove('show');
  });
}

function dismissInstallBanner() {
  deferredInstallPrompt = null;
  var banner = document.getElementById('install-banner');
  if (banner) banner.classList.remove('show');
}

/* -----------------------------------------------------------------------
 * Stats loading
 * ----------------------------------------------------------------------- */
function loadStats(uuid) {
  if (!uuid) return;
  var base = location.pathname.replace(/\/[^/]*\/?$/, '');
  fetch(base + '/stats/' + uuid + '.json')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(d) {
      if (!d) return;
      var el = document.getElementById('stats');
      if (!el) return;
      function fmt(b) {
        if (b >= 1073741824) return (b / 1073741824).toFixed(1) + ' GB';
        if (b >= 1048576) return (b / 1048576).toFixed(0) + ' MB';
        if (b >= 1024) return (b / 1024).toFixed(0) + ' KB';
        return b + ' B';
      }
      function ago(ts) {
        if (!ts) return '';
        var s = Math.floor((Date.now() - ts) / 1000);
        if (s < 60) return 'Active now';
        if (s < 3600) return 'Active ' + Math.floor(s / 60) + 'm ago';
        if (s < 86400) return 'Active ' + Math.floor(s / 3600) + 'h ago';
        return 'Active ' + Math.floor(s / 86400) + 'd ago';
      }
      document.getElementById('s-up').textContent = fmt(d.up);
      document.getElementById('s-down').textContent = fmt(d.down);
      var act = document.getElementById('s-active');
      if (d.lastOnline && act) act.textContent = ago(d.lastOnline);
      el.style.display = 'block';
    })
    .catch(function() {});
}

/* -----------------------------------------------------------------------
 * Subscription URL
 * ----------------------------------------------------------------------- */
function getSubscriptionUrl() {
  var path = location.pathname.replace(/\/?$/, '');
  return location.origin + path + '/sub.txt';
}

/* -----------------------------------------------------------------------
 * Web Share API
 * ----------------------------------------------------------------------- */
function shareUrl(url) {
  if (navigator.share) {
    navigator.share({ title: 'VPN Config', text: url }).catch(function() {});
  } else {
    copyToClipboard(url);
  }
}

function sharePageUrl() {
  if (navigator.share) {
    navigator.share({ title: 'VPN Connection', url: location.href }).catch(function() {});
  } else {
    copyToClipboard(location.href);
  }
}

/* -----------------------------------------------------------------------
 * Clock skew detection
 * ----------------------------------------------------------------------- */
function checkClockSkew(generatedAt) {
  if (!generatedAt) return 'ok';
  try {
    var serverTime = new Date(generatedAt).getTime();
    var age = Date.now() - serverTime;
    /* If page was generated more than 1h ago, can't reliably detect skew */
    if (Math.abs(age) > 3600000) return 'ok';
    /* Only warn if clock is off by more than 2 minutes (Reality needs ~30s) */
    return age < -120000 ? 'bad' : 'ok'; /* device clock is BEHIND server */
  } catch (e) { return 'ok'; }
}

/* -----------------------------------------------------------------------
 * Base64 validation (defense-in-depth for QR data)
 * ----------------------------------------------------------------------- */
var SKIP_NAMES = ['default', 'demo', 'test', 'client'];

function isPersonalName(name) {
  return name && SKIP_NAMES.indexOf(name.toLowerCase()) === -1;
}

var B64_RE = /^[A-Za-z0-9+/=]+$/;
function isValidBase64(s) { return s && B64_RE.test(s); }

/* -----------------------------------------------------------------------
 * iOS button index counter
 * ----------------------------------------------------------------------- */
var iosButtonIndex = 0;

/* -----------------------------------------------------------------------
 * SVG icons (inline, no external requests)
 * ----------------------------------------------------------------------- */
var ICON_COPY = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
var ICON_QR = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="4" height="4" rx="1"/><line x1="22" y1="14" x2="22" y2="14.01"/><line x1="22" y1="22" x2="22" y2="22.01"/><line x1="18" y1="22" x2="18" y2="22.01"/></svg>';

/* -----------------------------------------------------------------------
 * Page rendering from config.json
 * ----------------------------------------------------------------------- */
function renderPage(config) {
  var app = document.getElementById('app');
  if (!app) return;
  var platform = detectPlatform();
  iosButtonIndex = 0;
  var html = '';
  var hasRelays = config.relays && config.relays.length > 0;
  var clockStatus = checkClockSkew(config.generated_at);

  /* Clock warning at TOP if skew detected */
  if (clockStatus === 'bad') {
    html += '<div class="warn clock-warn-urgent">';
    html += '<h3 data-t="clock">Clock Sync Required</h3>';
    html += '<p data-t="clock.desc">Your device clock must be accurate within 30 seconds. Go to Settings &gt; Date &amp; Time &gt; enable "Set Automatically".</p>';
    html += '</div>';
  }

  /* Trust bar */
  var trustName = isPersonalName(config.client_name) ? capitalize(config.client_name) : '';
  html += '<div class="trust-bar">';
  html += '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
  if (trustName) {
    html += '<span data-t="trust.named">' + escapeHtml(trustName) + ' set up this secure connection for you</span>';
  } else {
    html += '<span data-t="trust">This is a secure connection set up for you</span>';
  }
  html += '</div>';

  /* Header */
  var titleExtra = trustName ? ' — ' + escapeHtml(trustName) : '';
  html += '<div class="hdr">';
  html += '<h1 data-t="title">Connection Setup' + titleExtra + '</h1>';
  html += '<p data-t="subtitle">Scan QR code or tap to open in your app</p>';

  /* Language selector */
  html += '<div class="lang-bar">';
  var langs = [['en', '\uD83C\uDDEC\uD83C\uDDE7 EN'], ['ru', '\uD83C\uDDF7\uD83C\uDDFA RU'], ['fa', '\uD83C\uDDEE\uD83C\uDDF7 FA'], ['zh', '\uD83C\uDDE8\uD83C\uDDF3 ZH']];
  for (var li = 0; li < langs.length; li++) {
    html += '<button class="lang-btn" data-lang="' + langs[li][0] + '" onclick="switchLang(\'' + langs[li][0] + '\')">' + langs[li][1] + '</button>';
  }
  html += '</div>';
  html += '</div>';

  /* PWA install banner */
  html += '<div class="install-banner" id="install-banner">';
  html += '<div class="install-banner-text"><strong data-t="install.title">Install this app</strong><span data-t="install.offline">Access your connection offline</span></div>';
  html += '<button class="install-btn" onclick="handleInstallClick()" data-t="install.btn">Install</button>';
  html += '<button class="install-dismiss" onclick="dismissInstallBanner()">&times;</button>';
  html += '</div>';

  /* Stats */
  html += '<div class="stats" id="stats">';
  html += '<div class="stats-title" data-t="stats">Usage</div>';
  html += '<div class="stats-grid">';
  html += '<div class="stats-item"><div class="stats-val" id="s-up">&mdash;</div><div class="stats-label" data-t="stats.upload">Upload</div></div>';
  html += '<div class="stats-item"><div class="stats-val" id="s-down">&mdash;</div><div class="stats-label" data-t="stats.download">Download</div></div>';
  html += '</div>';
  html += '<div class="stats-active" id="s-active"></div>';
  html += '</div>';

  /* Primary protocol card (hero) — first relay or first direct */
  var primaryCards = '';
  var secondaryCards = '';

  if (hasRelays) {
    /* First relay card is primary (hero) */
    var firstRelay = config.relays[0];
    if (firstRelay.urls.length > 0) {
      primaryCards += renderProtocolCard(firstRelay.urls[0], platform, {
        extraLabel: 'via ' + escapeHtml(firstRelay.name || firstRelay.ip),
        isRelay: true,
        isPrimary: true,
        isHero: true,
      });
    }
    /* Remaining relay URLs */
    for (var ri = 0; ri < config.relays.length; ri++) {
      var relay = config.relays[ri];
      var startIdx = (ri === 0) ? 1 : 0;
      for (var rui = startIdx; rui < relay.urls.length; rui++) {
        secondaryCards += renderProtocolCard(relay.urls[rui], platform, {
          extraLabel: 'via ' + escapeHtml(relay.name || relay.ip),
          isRelay: true,
        });
      }
    }
    /* Direct cards go to secondary */
    if (config.protocols.length > 0) {
      secondaryCards += '<div class="section-divider" data-t="backup.direct">BACKUP (DIRECT)</div>';
    }
    for (var pi = 0; pi < config.protocols.length; pi++) {
      secondaryCards += renderProtocolCard(config.protocols[pi], platform, {
        hasRelays: true,
        isFirst: pi === 0,
      });
    }
  } else {
    /* No relays: first protocol is primary (hero), rest are secondary */
    if (config.protocols.length > 0) {
      primaryCards += renderProtocolCard(config.protocols[0], platform, {
        isFirst: true,
        isPrimary: true,
        isHero: true,
      });
    }
    for (var pi2 = 1; pi2 < config.protocols.length; pi2++) {
      secondaryCards += renderProtocolCard(config.protocols[pi2], platform, {});
    }
  }

  /* Render primary card (hero) */
  html += '<div class="cards-grid">' + primaryCards + '</div>';

  /* Secondary cards collapsed */
  if (secondaryCards) {
    html += '<details class="more-options">';
    html += '<summary data-t="more.options">More connection options</summary>';
    html += '<div class="cards-grid">' + secondaryCards + '</div>';
    html += '</details>';
  }

  /* Client Apps */
  html += renderAppsCard(config.apps, platform);

  /* Quick Setup */
  html += '<div class="card">';
  html += '<div style="font-size:.78rem;font-weight:600;margin-bottom:4px" data-t="setup">Quick Setup</div>';
  html += '<div class="steps">';
  html += '<div class="step" data-t="step1">Install a client app from the list above</div>';
  html += '<div class="step" data-t="step2">Tap "Open in App" — the connection imports automatically</div>';
  html += '<div class="step" data-t="step3">Or scan the QR code from another device</div>';
  html += '<div class="step" data-t="step4">Activate the connection in the app</div>';
  html += '</div>';
  html += '</div>';

  /* Subscription URL */
  var subUrl = getSubscriptionUrl();
  html += '<div class="card">';
  html += '<div style="font-size:.78rem;font-weight:600;margin-bottom:4px" data-t="sub.label">Subscription (auto-update)</div>';
  html += '<p class="card-desc" data-t="sub.desc">Add this URL as a subscription in your app for automatic updates.</p>';
  html += '<div class="sub-url">';
  html += '<div class="sub-url-value" onclick="copyToClipboard(this.textContent)">' + escapeHtml(subUrl) + '</div>';
  html += '</div>';
  html += '</div>';

  /* Clock warning (informational, only if NOT already shown at top) */
  if (clockStatus === 'ok') {
    html += '<div class="warn">';
    html += '<h3 data-t="clock">Clock Sync Required</h3>';
    html += '<p data-t="clock.desc">Your device clock must be accurate within 30 seconds. Go to Settings &gt; Date &amp; Time &gt; enable "Set Automatically".</p>';
    html += '</div>';
  }

  /* Ping test */
  var pingUrl = 'https://getmeridian.org/ping?ip=' + encodeURIComponent(config.server_ip);
  if (config.domain) pingUrl += '&domain=' + encodeURIComponent(config.domain);
  html += '<div class="warn" style="border-color:var(--amber-br);background:var(--amber-bg)">';
  html += '<h3 data-t="ping">Not connecting?</h3>';
  html += '<p><span data-t="ping.desc">Test if the server is reachable from your device:</span> ';
  html += '<a href="' + escapeHtml(pingUrl) + '" target="_blank" style="color:var(--amber)" data-t="ping.link">Run ping test</a></p>';
  html += '</div>';

  /* Footer */
  html += '<div class="foot">';
  if (navigator.share) {
    html += '<button class="share-page-btn" onclick="sharePageUrl()" data-t="share.page">';
    html += '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>';
    html += 'Share this page</button>';
  }
  html += '<div class="links">';
  html += '<a href="https://getmeridian.org" target="_blank">Powered by Meridian</a>';
  html += '<span class="sep">&middot;</span>';
  html += '<a href="https://github.com/uburuntu/meridian" target="_blank">GitHub</a>';
  html += '</div>';
  html += '</div>';

  app.innerHTML = html;

  /* Post-render */
  var primaryUuid = extractUuid(config.protocols);
  if (primaryUuid) loadStats(primaryUuid);
  requestWakeLock();
  applyI18n(config.client_name);
  highlightActiveLang();
}

/* -----------------------------------------------------------------------
 * Card rendering
 * ----------------------------------------------------------------------- */
function renderProtocolCard(proto, platform, opts) {
  opts = opts || {};
  var isBlue = proto.key !== 'wss';
  var colorClass = isBlue ? 'card-blue' : 'card-amber';
  var heroClass = opts.isHero ? ' card-hero' : '';
  var html = '<div class="card ' + colorClass + heroClass + '">';

  /* Label */
  html += '<div class="card-label"><i></i> ';
  if (opts.isRelay) {
    html += '<span>&#9733; ' + escapeHtml(proto.label) + '</span>';
    if (opts.extraLabel) {
      html += '<span class="card-rec">' + escapeHtml(opts.extraLabel) + '</span>';
    }
  } else if (opts.isFirst && !opts.hasRelays) {
    html += '<span data-t="primary">' + escapeHtml(proto.label) + '</span>';
    if (proto.recommended) {
      html += '<span class="card-rec" data-t="primary.rec">Recommended</span>';
    }
  } else if (proto.key === 'wss') {
    html += '<span data-t="backup">Backup</span>';
  } else if (proto.key === 'xhttp') {
    html += '<span>XHTTP</span>';
  } else {
    html += '<span data-t="primary">' + escapeHtml(proto.label) + '</span>';
  }
  html += '</div>';

  /* Description */
  if (opts.isRelay) {
    html += '<p class="card-desc" data-t="relay.desc">Connect via relay for best reliability in your region.</p>';
  } else if (opts.isFirst && !opts.hasRelays) {
    html += '<p class="card-desc" data-t="primary.desc">Recommended — fastest and most reliable connection. Use this first.</p>';
  } else if (opts.hasRelays && opts.isFirst) {
    html += '<p class="card-desc" data-t="direct.desc">Direct connection — use if relay is unavailable.</p>';
  } else if (proto.key === 'xhttp') {
    html += '<p class="card-desc" data-t="xhttp.desc">Alternative — use if Primary doesn\'t work. More hidden from censors.</p>';
  } else if (proto.key === 'wss') {
    html += '<p class="card-desc" data-t="backup.desc">Fallback — routes through CDN. Use only if both above fail.</p>';
  }

  if (opts.isHero) {
    /* ---- Hero layout: QR prominent, then actions ---- */
    html += '<div class="card-body">';

    /* QR code — always visible, prominent */
    if (proto.qr_b64 && isValidBase64(proto.qr_b64)) {
      html += '<div class="qr"><img src="data:image/png;base64,' + proto.qr_b64 + '" alt="QR code" loading="lazy"></div>';
    }

    html += '<div class="card-controls">';

    /* Open in App button */
    html += '<div class="card-actions">';
    if (platform === 'ios') {
      var idx = iosButtonIndex++;
      html += '<a href="#" data-ios-idx="' + idx + '" data-url="' + escapeHtml(proto.url) + '" onclick="event.preventDefault();tryOpenIOS(' + idx + ')" class="open-btn" data-t="open">Open in App</a>';
    } else {
      var openUrl = buildOpenUrl(proto.url, platform);
      html += '<a href="' + escapeHtml(openUrl) + '" class="open-btn" data-t="open">Open in App</a>';
    }
    if (navigator.share) {
      html += '<button class="share-btn" onclick="shareUrl(\'' + escapeHtml(proto.url).replace(/'/g, '') + '\')" data-t="share">Share</button>';
    }
    html += '</div>';

    /* Secondary actions: copy link */
    html += '<div class="card-tools">';
    html += '<button class="copy-link-btn" onclick="copyToClipboard(\'' + escapeHtml(proto.url).replace(/'/g, '') + '\')">';
    html += ICON_COPY;
    html += '<span data-t="copy.link">Copy link</span>';
    html += '</button>';
    html += '</div>';

    /* Show raw link */
    html += '<details class="url-section"><summary data-t="show.raw">Show raw link</summary>';
    html += '<div class="url" onclick="copyToClipboard(this.getAttribute(\'data-url\'))" data-url="' + escapeHtml(proto.url) + '">';
    html += escapeHtml(proto.url);
    html += '<span class="url-hint"><span data-t="copy.hint">tap to copy</span></span>';
    html += '</div>';
    html += '</details>';

    html += '</div>'; /* card-controls */
    html += '</div>'; /* card-body */

  } else {
    /* ---- Same layout as hero, just without card-hero class ---- */
    html += '<div class="card-body">';

    /* QR code — always visible */
    if (proto.qr_b64 && isValidBase64(proto.qr_b64)) {
      html += '<div class="qr"><img src="data:image/png;base64,' + proto.qr_b64 + '" alt="QR code" loading="lazy"></div>';
    }

    html += '<div class="card-controls">';

    /* Open in App button */
    html += '<div class="card-actions">';
    if (platform === 'ios') {
      var idx2 = iosButtonIndex++;
      html += '<a href="#" data-ios-idx="' + idx2 + '" data-url="' + escapeHtml(proto.url) + '" onclick="event.preventDefault();tryOpenIOS(' + idx2 + ')" class="open-btn" data-t="open">Open in App</a>';
    } else {
      var openUrl2 = buildOpenUrl(proto.url, platform);
      html += '<a href="' + escapeHtml(openUrl2) + '" class="open-btn" data-t="open">Open in App</a>';
    }
    if (navigator.share) {
      html += '<button class="share-btn" onclick="shareUrl(\'' + escapeHtml(proto.url).replace(/'/g, '') + '\')" data-t="share">Share</button>';
    }
    html += '</div>';

    /* Secondary actions: copy link */
    html += '<div class="card-tools">';
    html += '<button class="copy-link-btn" onclick="copyToClipboard(\'' + escapeHtml(proto.url).replace(/'/g, '') + '\')">';
    html += ICON_COPY;
    html += '<span data-t="copy.link">Copy link</span>';
    html += '</button>';
    html += '</div>';

    /* Show raw link */
    html += '<details class="url-section"><summary data-t="show.raw">Show raw link</summary>';
    html += '<div class="url" onclick="copyToClipboard(this.getAttribute(\'data-url\'))" data-url="' + escapeHtml(proto.url) + '">';
    html += escapeHtml(proto.url);
    html += '<span class="url-hint"><span data-t="copy.hint">tap to copy</span></span>';
    html += '</div>';
    html += '</details>';

    html += '</div>'; /* card-controls */
    html += '</div>'; /* card-body */
  }

  html += '</div>'; /* card */
  return html;
}

function renderAppsCard(apps, platform) {
  if (!apps || !apps.length) return '';
  var isReturning = 'serviceWorker' in navigator && navigator.serviceWorker.controller;
  var html = '';
  if (isReturning) {
    /* Returning user: collapse app card */
    html += '<details class="more-options"><summary data-t="apps">Client Apps</summary>';
  }
  html += '<div class="card">';
  html += '<div style="font-size:.78rem;font-weight:600;margin-bottom:4px" data-t="apps">Client Apps</div>';
  html += '<p class="card-desc" data-t="apps.desc">Install one, then tap "Open in App" or scan the QR code.</p>';
  html += '<div class="apps">';

  var osMap = {
    ios: 'iOS', android: 'Android',
    windows: 'Windows', macos: 'All platforms', linux: 'All platforms',
  };
  var detectedOs = osMap[platform] || 'All platforms';

  for (var i = 0; i < apps.length; i++) {
    var a = apps[i];
    var detected = (a.platform === detectedOs) ? ' detected' : '';
    html += '<a class="app' + detected + '" href="' + escapeHtml(a.url) + '" target="_blank" data-os="' + escapeHtml(a.platform) + '">';
    html += escapeHtml(a.name);
    html += '<span>' + escapeHtml(a.platform) + '</span>';
    html += '</a>';
  }
  html += '</div></div>';
  if (isReturning) html += '</details>';
  return html;
}

/* -----------------------------------------------------------------------
 * i18n
 * ----------------------------------------------------------------------- */
var currentLang = null;

function switchLang(lang) {
  currentLang = lang;
  try { localStorage.setItem('meridian-lang', lang); } catch (e) {}
  /* Re-render the entire page — English text is baked into renderPage(),
     so we can't just swap data-t values; we need a full rebuild. */
  if (window._meridianConfig) {
    renderPage(window._meridianConfig);
  }
}

function detectLang() {
  try {
    var saved = localStorage.getItem('meridian-lang');
    if (saved && (saved === 'en' || T[saved])) return saved;
  } catch (e) {}
  var bl = (navigator.language || '').slice(0, 2);
  return T[bl] ? bl : null;
}

function highlightActiveLang() {
  var lang = currentLang || 'en';
  document.querySelectorAll('.lang-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.getAttribute('data-lang') === lang);
  });
}

function applyI18n(clientName) {
  currentLang = detectLang();
  if (!currentLang) { currentLang = 'en'; highlightActiveLang(); return; }
  var dict = T[currentLang];
  if (!dict) { highlightActiveLang(); return; }
  document.querySelectorAll('[data-t]').forEach(function(el) {
    var k = el.dataset.t;
    var v = dict[k];
    if (v) {
      if (k === 'trust.named' && isPersonalName(clientName)) {
        el.textContent = v.replace('{name}', capitalize(clientName));
      } else {
        el.textContent = v;
      }
      if (k === 'title' && isPersonalName(clientName)) {
        el.textContent += ' — ' + capitalize(clientName);
      }
    }
  });
  if (currentLang === 'fa') {
    document.documentElement.dir = 'rtl';
  } else {
    document.documentElement.dir = 'ltr';
  }
  highlightActiveLang();
}

/* -----------------------------------------------------------------------
 * Utilities
 * ----------------------------------------------------------------------- */
function escapeHtml(s) {
  if (!s) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(s));
  return div.innerHTML;
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

function extractUuid(protocols) {
  if (!protocols || !protocols.length) return '';
  for (var i = 0; i < protocols.length; i++) {
    var m = protocols[i].url.match(/vless:\/\/([0-9a-fA-F-]{36})@/);
    if (m && protocols[i].url.indexOf('reality') > -1) return m[1];
  }
  var fm = protocols[0].url.match(/vless:\/\/([0-9a-fA-F-]{36})@/);
  return fm ? fm[1] : '';
}

/* -----------------------------------------------------------------------
 * Service Worker + Persistent storage
 * ----------------------------------------------------------------------- */
function registerSW() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('../pwa/sw.js', { scope: '../' }).catch(function() {});
}

function requestPersistentStorage() {
  if (navigator.storage && navigator.storage.persist) {
    navigator.storage.persist().catch(function() {});
  }
}

/* -----------------------------------------------------------------------
 * Expose globals
 * ----------------------------------------------------------------------- */
window.copyToClipboard = copyToClipboard;
window.handleInstallClick = handleInstallClick;
window.dismissInstallBanner = dismissInstallBanner;
window.tryOpenIOS = tryOpenIOS;
window.shareUrl = shareUrl;
window.sharePageUrl = sharePageUrl;
window.switchLang = switchLang;

/* -----------------------------------------------------------------------
 * Init
 * ----------------------------------------------------------------------- */
function init() {
  registerSW();
  requestPersistentStorage();

  fetch('config.json')
    .then(function(r) {
      if (!r.ok) throw new Error('config.json fetch failed');
      return r.json();
    })
    .then(function(config) {
      window._meridianConfig = config;
      renderPage(config);
    })
    .catch(function() {
      var app = document.getElementById('app');
      if (app) {
        app.innerHTML = '<div class="hdr"><h1>Connection Setup</h1>' +
          '<p style="color:var(--tx2)">Could not load configuration. Please reload the page.</p></div>';
      }
    });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
