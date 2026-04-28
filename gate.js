<!-- 
  Password gate for PRO calculators.
  Add this at the very top of each PRO calculator HTML file, right after <body>:
  
  <script src="../gate.js"></script>
  
  The gate.js checks localStorage for a valid token. 
  If not found, shows password prompt.
-->
(function(){
  // ===== CHANGE PASSWORD HERE =====
  var PASS_HASH = 'a571463a3aeaddb2d45bde4c97ceaad80e8a2454a6fc1462a99e31c3343a9dfe'; // SHA-256 of password
  // To generate hash for your password, open browser console and run:
  // crypto.subtle.digest('SHA-256', new TextEncoder().encode('YOUR_PASSWORD')).then(h=>console.log(Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')))
  // ================================

  var KEY = 'pro_access_token';
  var EXPIRY_KEY = 'pro_access_expiry';

  function sha256(str) {
    return crypto.subtle.digest('SHA-256', new TextEncoder().encode(str)).then(function(buf) {
      return Array.from(new Uint8Array(buf)).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    });
  }

  function checkAccess() {
    var token = localStorage.getItem(KEY);
    var expiry = localStorage.getItem(EXPIRY_KEY);
    if (token === PASS_HASH && expiry && new Date(expiry) > new Date()) {
      return true;
    }
    return false;
  }

  function showGate() {
    document.body.style.display = 'none';
    var overlay = document.createElement('div');
    overlay.id = 'proGate';
    overlay.innerHTML = 
      '<div style="font-family:DM Sans,system-ui,sans-serif;max-width:400px;margin:80px auto;padding:2rem;background:#fff;border-radius:14px;border:1px solid #E5E4DF;text-align:center">' +
      '<h2 style="font-size:1.2rem;margin-bottom:0.5rem">PRO-доступ</h2>' +
      '<p style="font-size:0.85rem;color:#6B6A65;margin-bottom:1.5rem">Этот калькулятор доступен по подписке</p>' +
      '<input type="password" id="proPass" placeholder="Введите пароль" style="font-family:JetBrains Mono,monospace;font-size:0.95rem;padding:0.6rem 1rem;border:1px solid #E5E4DF;border-radius:10px;width:100%;margin-bottom:0.75rem;outline:none;text-align:center">' +
      '<br><button id="proBtn" style="font-family:DM Sans,sans-serif;font-size:0.9rem;font-weight:500;padding:0.6rem 2rem;border:none;border-radius:10px;background:#2D5A3D;color:#fff;cursor:pointer;margin-bottom:1rem">Войти</button>' +
      '<div id="proErr" style="font-size:0.78rem;color:#B44040;min-height:1.2em"></div>' +
      '<div style="margin-top:1.5rem;padding-top:1rem;border-top:1px solid #F3F2EE">' +
      '<p style="font-size:0.82rem;color:#6B6A65;margin-bottom:0.75rem">Нет подписки?</p>' +
      '<a href="../index.html#pricing" style="font-size:0.85rem;color:#2D5A3D;font-weight:500">Оформить PRO-доступ →</a>' +
      '</div></div>';
    overlay.style.cssText = 'position:fixed;inset:0;background:#FAFAF8;z-index:99999;overflow-y:auto';
    document.documentElement.appendChild(overlay);

    document.getElementById('proBtn').onclick = function() { tryLogin(); };
    document.getElementById('proPass').onkeydown = function(e) { if (e.key === 'Enter') tryLogin(); };
    document.getElementById('proPass').focus();
  }

  function tryLogin() {
    var pass = document.getElementById('proPass').value;
    sha256(pass).then(function(hash) {
      if (hash === PASS_HASH) {
        localStorage.setItem(KEY, hash);
        // Token valid for 35 days
        var exp = new Date();
        exp.setDate(exp.getDate() + 35);
        localStorage.setItem(EXPIRY_KEY, exp.toISOString());
        var gate = document.getElementById('proGate');
        if (gate) gate.remove();
        document.body.style.display = '';
      } else {
        document.getElementById('proErr').textContent = 'Неверный пароль';
        document.getElementById('proPass').value = '';
        document.getElementById('proPass').focus();
      }
    });
  }

  if (!checkAccess()) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', showGate);
    } else {
      showGate();
    }
  }
})();
