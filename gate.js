(function(){
  var PASS_HASH = 'a571463a3aeaddb2d45bde4c97ceaad80e8a2454a6fc1462a99e31c3343a9dfe';
  var KEY = 'pro_access_token';
  var EXPIRY_KEY = 'pro_access_expiry';
  var TYPE_KEY = 'pro_access_type';
  var CHECK_KEY = 'pro_access_lastcheck';
  var API_URL = 'https://investtools.pro/api/check';
  var RECHECK_MS = 60 * 60 * 1000; // токен перепроверяется на сервере не чаще раза в час

  function sha256(str) {
    return crypto.subtle.digest('SHA-256', new TextEncoder().encode(str)).then(function(buf) {
      return Array.from(new Uint8Array(buf)).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    });
  }

  function localStillValid() {
    var token = localStorage.getItem(KEY);
    var expiry = localStorage.getItem(EXPIRY_KEY);
    return !!(token && expiry && new Date(expiry) > new Date());
  }

  function clearAccess() {
    localStorage.removeItem(KEY);
    localStorage.removeItem(EXPIRY_KEY);
    localStorage.removeItem(TYPE_KEY);
    localStorage.removeItem(CHECK_KEY);
  }

  // Возвращает Promise<boolean>. Пароль — чисто локально (ключ Екатерины).
  // Токен — перепроверяется на сервере не чаще раза в час; если сервер сказал «истёк/нет» — доступ снимается.
  function checkAccess() {
    if (!localStillValid()) return Promise.resolve(false);

    var type = localStorage.getItem(TYPE_KEY);
    if (type !== 'token') {
      // пароль или старые записи без типа — оставляем локальную логику
      return Promise.resolve(true);
    }

    var last = parseInt(localStorage.getItem(CHECK_KEY) || '0', 10);
    if (Date.now() - last < RECHECK_MS) {
      // недавно проверяли — пускаем без обращения к серверу
      return Promise.resolve(true);
    }

    // пора перепроверить токен на сервере
    var token = localStorage.getItem(KEY);
    return verifyToken(token).then(function(res) {
      if (res.valid) {
        localStorage.setItem(EXPIRY_KEY, res.expires_at);
        localStorage.setItem(CHECK_KEY, String(Date.now()));
        return true;
      }
      // токен истёк или отозван на сервере — снимаем доступ
      clearAccess();
      return false;
    }).catch(function() {
      // сервер недоступен — не выкидываем человека, доверяем локальному сроку
      return true;
    });
  }

  function verifyToken(token) {
    return fetch(API_URL + '?token=' + encodeURIComponent(token))
      .then(function(r) { return r.json(); })
      .catch(function() { return { valid: false }; });
  }

  function showGate() {
    document.body.style.display = 'none';
    var overlay = document.createElement('div');
    overlay.id = 'proGate';
    overlay.innerHTML =
      '<div style="font-family:DM Sans,system-ui,sans-serif;max-width:400px;margin:80px auto;padding:2rem;background:#fff;border-radius:14px;border:1px solid #E5E4DF;text-align:center">' +
      '<h2 style="font-size:1.2rem;margin-bottom:0.5rem">PRO-доступ</h2>' +
      '<p style="font-size:0.85rem;color:#6B6A65;margin-bottom:1.5rem">Введите токен или пароль</p>' +
      '<input type="text" id="proPass" placeholder="Токен или пароль" style="font-family:JetBrains Mono,monospace;font-size:0.95rem;padding:0.6rem 1rem;border:1px solid #E5E4DF;border-radius:10px;width:100%;margin-bottom:0.75rem;outline:none;text-align:center">' +
      '<br><button id="proBtn" style="font-family:DM Sans,sans-serif;font-size:0.9rem;font-weight:500;padding:0.6rem 2rem;border:none;border-radius:10px;background:#2D5A3D;color:#fff;cursor:pointer;margin-bottom:1rem">Войти</button>' +
      '<div id="proErr" style="font-size:0.78rem;color:#B44040;min-height:1.2em"></div>' +
      '<div style="margin-top:1.5rem;padding-top:1rem;border-top:1px solid #F3F2EE">' +
      '<p style="font-size:0.82rem;color:#6B6A65;margin-bottom:0.75rem">Нет доступа?</p>' +
      '<a href="https://t.me/k_invest_channel_bot" target="_blank" style="font-size:0.85rem;color:#2D5A3D;font-weight:500">Оформить PRO →</a>' +
      '</div></div>';
    overlay.style.cssText = 'position:fixed;inset:0;background:#FAFAF8;z-index:99999;overflow-y:auto';
    document.documentElement.appendChild(overlay);
    document.getElementById('proBtn').onclick = function() { tryLogin(); };
    document.getElementById('proPass').onkeydown = function(e) { if (e.key === 'Enter') tryLogin(); };
    document.getElementById('proPass').focus();
  }

  function unlock() {
    var gate = document.getElementById('proGate');
    if (gate) gate.remove();
    document.body.style.display = '';
  }

  function tryLogin() {
    var input = document.getElementById('proPass').value.trim();
    if (!input) {
      document.getElementById('proErr').textContent = 'Введите токен или пароль';
      return;
    }
    document.getElementById('proErr').textContent = 'Проверяю...';

    // Try as password first (legacy)
    sha256(input).then(function(hash) {
      if (hash === PASS_HASH) {
        localStorage.setItem(KEY, hash);
        localStorage.setItem(TYPE_KEY, 'password');
        var exp = new Date();
        exp.setDate(exp.getDate() + 35);
        localStorage.setItem(EXPIRY_KEY, exp.toISOString());
        unlock();
        return;
      }
      // Try as token via API
      var token = input.toUpperCase();
      verifyToken(token).then(function(res) {
        if (res.valid) {
          localStorage.setItem(KEY, token);
          localStorage.setItem(TYPE_KEY, 'token');
          localStorage.setItem(EXPIRY_KEY, res.expires_at);
          localStorage.setItem(CHECK_KEY, String(Date.now()));
          unlock();
        } else {
          document.getElementById('proErr').textContent = res.reason === 'expired' ? 'Срок действия истёк' : 'Неверный токен или пароль';
          document.getElementById('proPass').value = '';
          document.getElementById('proPass').focus();
        }
      });
    });
  }

  function hideBody() {
    if (document.body) {
      document.body.style.display = 'none';
    } else {
      document.addEventListener('DOMContentLoaded', function(){ document.body.style.display = 'none'; });
    }
  }

  function revealBody() {
    if (document.body) document.body.style.display = '';
    else document.addEventListener('DOMContentLoaded', function(){ document.body.style.display = ''; });
  }

  function boot() {
    hideBody(); // прячем контент сразу, пока идёт проверка — чтобы PRO не мелькнул
    checkAccess().then(function(ok) {
      if (ok) { revealBody(); return; }
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', showGate);
      } else {
        showGate();
      }
    });
  }

  boot();
})();
