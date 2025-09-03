# backend_UI_Tmap.py
from flask import Flask, render_template_string, request, jsonify, Response
from flask_socketio import SocketIO
from pywebpush import webpush, WebPushException
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ▼ gen_vapid.py에서 생성한 키로 교체하세요
VAPID_PUBLIC  = "BHtWP8B34KzKv7JOOxmb9sT186YiR-x27i0ibL0dnf7sc_TERLV-AGq7nS0lfa2A4yuVY6qW6jROtelP7g2LXz8"
VAPID_PRIVATE = "Lo97JNrh7xcKOG3kXVP6W_oJ9iKq6advezMViSz6FzY"
VAPID_CLAIMS  = {"sub": "mailto:you@example.com"}  # 임의 이메일

# 데모: 메모리에 구독 저장(실전은 파일/DB)
SUBSCRIPTIONS = []  # 각 항목은 브라우저가 준 subscription JSON

# ─────────────────────────────────────────────
# 메인 UI (모바일 앱 느낌)
# ─────────────────────────────────────────────
html_page = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0ea5e9">
  <title>신호 알림</title>
  <style>
    html,body{height:100%;margin:0;background:#0b1020;color:#e6f3ff;
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Apple SD Gothic Neo,Noto Sans KR,sans-serif}
    .wrap{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
      padding:calc(env(safe-area-inset-top,0) + 20px) 16px calc(env(safe-area-inset-bottom,0) + 32px)}
    .card{width:100%;max-width:520px;border-radius:24px;background:#111a32;
      box-shadow:0 10px 30px rgba(0,0,0,.3);padding:28px;text-align:center}
    .badge{display:inline-block;padding:6px 12px;border-radius:9999px;background:#1b2a52;color:#9cc7ff;
      font-size:12px;letter-spacing:.4px;margin-bottom:8px}
    .emoji{font-size:86px;line-height:1;margin:10px 0 4px}
    .msg{font-size:20px;font-weight:700;margin:6px 0 18px}
    .hint{opacity:.7;font-size:13px}
    .row{margin-top:16px; display:flex; gap:8px; justify-content:center; flex-wrap:wrap}
    button{background:#0ea5e9;border:none;color:white;padding:10px 14px;border-radius:12px;font-weight:700}
    button.muted{background:#334155}
    #pushState{font-size:12px;opacity:.8;margin-top:8px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="badge" id="badge">신호 대기중</div>
      <div id="emoji" class="emoji">⌛</div>
      <div id="signal" class="msg">대기중...</div>
      <div class="hint">초록불 신호가 오면 자동으로 갱신됩니다.</div>
      <div class="row">
        <button id="reqPerm">알림 권한 요청</button>
        <button id="testLocal" class="muted">로컬 테스트(화면만)</button>
      </div>
      <div id="pushState"></div>
    </div>
  </div>

  <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
  <script>
    const $emoji  = document.getElementById('emoji');
    const $signal = document.getElementById('signal');
    const $badge  = document.getElementById('badge');
    const $state  = document.getElementById('pushState');

    // ── Socket.IO: 페이지 열려 있을 때 실시간 갱신 ─────────────────────
    const socket = io();
    socket.on('connect', () => {
      $emoji.textContent = '📶';
      $signal.textContent = '연결됨';
      $badge.textContent = '서버 연결됨';
    });
    socket.on('signal', (msg) => {
      $emoji.textContent = '🟢';
      $signal.textContent = msg || '초록불 신호가 켜졌습니다!';
      $badge.textContent = '신호 수신';
    });
    socket.on('disconnect', () => {
      $emoji.textContent = '⚠️';
      $signal.textContent = '연결 끊김';
      $badge.textContent = '재연결 시도';
    });

    // ── PWA/웹푸시: 백그라운드에서도 배너 알림 ─────────────────────
    // base64url → Uint8Array
    function b64urlToUint8Array(base64String){
      const padding = '='.repeat((4 - base64String.length % 4) % 4);
      const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
      const raw = atob(base64);
      const output = new Uint8Array(raw.length);
      for(let i=0;i<raw.length;++i) output[i] = raw.charCodeAt(i);
      return output;
    }

    async function ensureServiceWorker(){
      if(!('serviceWorker' in navigator)){ 
        $state.textContent = '서비스워커 미지원 브라우저'; 
        return null; 
      }
      try {
        const reg = await navigator.serviceWorker.register('/sw.js');
        return reg;
      } catch(e){
        $state.textContent = 'SW 등록 실패: ' + e;
        return null;
      }
    }

    async function requestNotifyPermission(){
      try{
        const perm = await Notification.requestPermission();
        return perm; // 'granted' | 'denied' | 'default'
      }catch(e){
        return 'denied';
      }
    }

    async function subscribePush(){
      const reg = await ensureServiceWorker();
      if(!reg) return;

      // 서버에서 VAPID 공개키 받기
      const r = await fetch('/vapid-public');
      const {key} = await r.json();

      // 구독 생성
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: b64urlToUint8Array(key)
      });

      // 서버에 구독 저장
      await fetch('/subscribe', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(sub)
      });
      $state.textContent = '푸시 구독 완료';
    }

    // 버튼 동작
    document.getElementById('reqPerm').onclick = async ()=>{
      const sw = await ensureServiceWorker();
      if(!sw){ return; }
      const perm = await requestNotifyPermission();
      if(perm === 'granted'){
        await subscribePush();
      } else {
        $state.textContent = '알림 권한 거부됨';
      }
    };

    // 화면만 즉시 테스트
    document.getElementById('testLocal').onclick = ()=>{
      $emoji.textContent = '🟢'; 
      $signal.textContent = '로컬 테스트: 초록불 신호!';
      $badge.textContent = '로컬 테스트';
    };
  </script>
</body>
</html>
"""

# 메인 페이지
@app.route('/')
def index():
    return render_template_string(html_page)

# Socket.IO + 웹푸시를 동시에 쏘는 전송 엔드포인트
@app.route('/send', methods=['POST'])
def send_signal():
    msg = request.form.get("msg", "초록불 신호가 켜졌습니다!")
    # 1) 열려있는 페이지 실시간 갱신
    socketio.emit('signal', msg)
    # 2) 푸시 배너(백그라운드)
    push_to_all("신호 바뀜", msg)
    return f"Sent: {msg}"

# ── 웹푸시 관련 라우트 ───────────────────────────────────────────
@app.route('/vapid-public')
def vapid_public():
    return jsonify({"key": VAPID_PUBLIC})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    sub = request.get_json(silent=True)
    if not sub or 'endpoint' not in sub:
        return ("Bad subscription", 400)
    # 중복 제거(같은 endpoint는 1개만)
    if not any(s.get('endpoint') == sub['endpoint'] for s in SUBSCRIPTIONS):
        SUBSCRIPTIONS.append(sub)
    return ('', 204)

def push_to_all(title, body):
    for s in SUBSCRIPTIONS[:]:
        try:
            webpush(
                subscription_info=s,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims=VAPID_CLAIMS
            )
        except WebPushException as e:
            # 더 이상 유효하지 않은 구독 제거
            try:
                SUBSCRIPTIONS.remove(s)
            except ValueError:
                pass

# 서비스워커(JS) 제공
@app.route('/sw.js')
def service_worker():
    js = """
self.addEventListener('install', (e)=>{ self.skipWaiting(); });
self.addEventListener('activate', (e)=>{ self.clients.claim(); });

// 푸시 수신 → 배너 알림
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data.json(); } catch(e){}
  const title = data.title || '신호 알림';
  const body  = data.body  || '초록불 신호가 켜졌습니다!';
  event.waitUntil(self.registration.showNotification(title, {
    body,
    // 아이콘은 없으면 무시됨(원하면 /static/icon-192.png 추가)
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png',
    vibrate: [80,30,80],
    tag: 'signal',
    renotify: true,
    requireInteraction: false
  }));
});

self.addEventListener('notificationclick', (e)=>{
  e.notification.close();
  e.waitUntil(clients.openWindow('/'));
});
"""
    return Response(js, mimetype='text/javascript')

if __name__ == '__main__':
    # 같은 와이파이에서 접근 가능
    socketio.run(app, host="0.0.0.0", port=5000)
