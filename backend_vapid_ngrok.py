# 파일: backend_vapid_ngrok.py (실험중)
# 기능: Flask + Socket.IO + WebPush(VAPID) + ngrok
#      전경(보이는 중) TTS 읽기 / 배경 헤드업 푸시
#      ✅ 상태별 이모지(🔴🟡🟢)
#      ✅ 같은 상태 연속 입력 무시
#      ✅ "처음 바뀔 때만" TTS (상태가 변경된 순간 1회만 읽기)

from flask import Flask, render_template_string, request, jsonify, Response
from flask_socketio import SocketIO
from pywebpush import webpush, WebPushException
import json, sys, threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── VAPID (본인 키로 교체) ─────────────────────────────────
VAPID_PUBLIC  = "BHtWP8B34KzKv7JOOxmb9sT186YiR-x27i0ibL0dnf7sc_TERLV-AGq7nS0lfa2A4yuVY6qW6jROtelP7g2LXz8"
VAPID_PRIVATE = "Lo97JNrh7xcKOG3kXVP6W_oJ9iKq6advezMViSz6FzY"
VAPID_CLAIMS  = {"sub": "mailto:you@example.com"}

# ── 메모리 저장 ────────────────────────────────────────────
SUBSCRIPTIONS = []
LAST_STATE = None   # 'red' | 'yellow' | 'green' 추적

# ── HTML ──────────────────────────────────────────────────
html_page = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>신호 알림</title>
</head>
<body style="background:#0b1020;color:white;text-align:center;font-family:sans-serif">
  <h2 id="badge">신호 대기중</h2>
  <div id="emoji" style="font-size:80px">⌛</div>
  <p id="signal">대기중...</p>
  <button id="reqPerm">알림 권한 요청</button>
  <button id="testLocal">로컬 테스트</button>
  <div id="pushState" style="margin-top:8px;opacity:.8"></div>

<script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
<script>
const $emoji=document.getElementById('emoji');
const $signal=document.getElementById('signal');
const $badge=document.getElementById('badge');
const $state=document.getElementById('pushState');

function speak(text){
  if(document.visibilityState!=='visible') return; // 전경에서만
  if(!('speechSynthesis' in window)) return;
  const u=new SpeechSynthesisUtterance(text);
  u.lang='ko-KR';
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

const EMOJI = { red:'🔴', yellow:'🟡', green:'🟢', transition:'🟢' };

// 서버가 {text, state, tts}로 보냄
const socket=io();
socket.on('signal', payload=>{
  const p = (typeof payload==='string') ? {text:payload,state:null,tts:false} : payload;
  $emoji.textContent = EMOJI[p.state] || '🟢';
  $signal.textContent = p.text || '신호 업데이트';
  $badge.textContent = '신호 수신';
  if(p.tts) speak(p.text);
});

// Web Push 구독
function b64urlToUint8Array(s){const p='='.repeat((4-s.length%4)%4);const b=(s+p).replace(/-/g,'+').replace(/_/g,'/');const r=atob(b);const o=new Uint8Array(r.length);for(let i=0;i<r.length;i++)o[i]=r.charCodeAt(i);return o;}
async function ensureSW(){ if(!('serviceWorker' in navigator)){ $state.textContent='서비스워커 미지원'; return null;} return await navigator.serviceWorker.register('/sw.js'); }
async function subscribePush(){
  const reg=await ensureSW(); if(!reg) return;
  const r=await fetch('/vapid-public'); const {key}=await r.json();
  const sub=await reg.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:b64urlToUint8Array(key)});
  await fetch('/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sub)});
  $state.textContent='푸시 구독 완료';
}
document.getElementById('reqPerm').onclick=async()=>{ const perm=await Notification.requestPermission(); if(perm==='granted') await subscribePush(); else $state.textContent='알림 권한 거부됨'; };
document.getElementById('testLocal').onclick=()=>{ $emoji.textContent='🟢'; $signal.textContent='테스트 신호'; $badge.textContent='테스트'; };
</script>
</body>
</html>
"""

# ── 라우트 ────────────────────────────────────────────────
@app.route('/')
def index(): return render_template_string(html_page)

@app.route('/vapid-public')
def vapid_public(): return jsonify({"key": VAPID_PUBLIC})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    sub=request.get_json(silent=True)
    if sub and 'endpoint' in sub and not any(s.get('endpoint')==sub['endpoint'] for s in SUBSCRIPTIONS):
        SUBSCRIPTIONS.append(sub)
    return ('',204)

# 입력 텍스트 → (state, text, state_for_emoji)
def normalize_input(user_text: str):
    t = (user_text or '').strip().lower().replace(' ', '')
    if t in ('red->green','redgreen','r->g'):
        # 전이 케이스(특별 메시지, 이모지는 green/transition)
        return ('green',  '신호가 바뀌었습니다. 출발하세요!', 'transition')
    if t=='red':    return ('red',    '빨간불입니다!',  'red')
    if t=='yellow': return ('yellow', '노란불입니다!', 'yellow')
    if t=='green':  return ('green',  '초록불입니다!', 'green')
    return (None, user_text or '신호 업데이트', None)

@app.route('/send', methods=['POST'])
def send_signal():
    global LAST_STATE
    raw = request.form.get("msg","")
    next_state, text, state_for_emoji = normalize_input(raw)

    # ✅ 같은 상태 연속 입력 무시 (red/yellow/green만)
    if next_state in ('red','yellow','green') and LAST_STATE == next_state:
        print(f"[skip] same state '{next_state}'")
        return f"Skipped (same state: {next_state})"

    # ✅ "처음 바뀐 순간"에만 TTS 켜기
    # - 최초 입력(LAST_STATE=None)도 '바뀐 것'으로 간주 → TTS on
    speak_once = False
    if next_state in ('red','yellow','green'):
        if LAST_STATE != next_state:
            speak_once = True
        LAST_STATE = next_state  # 상태 갱신

    # 전경 UI(+선택 TTS)용 페이로드
    payload = {"text": text, "state": state_for_emoji or next_state, "tts": speak_once}
    socketio.emit('signal', payload)

    # 배경 푸시(배너)
    push_to_all("신호 알림", text)

    print(f"[sent] state={next_state} text={text} tts={speak_once}")
    return f"Sent: {text}"

def push_to_all(title,body):
    for s in SUBSCRIPTIONS[:]:
        try:
            webpush(
              subscription_info=s,
              data=json.dumps({"title":title,"body":body}),
              vapid_private_key=VAPID_PRIVATE,
              vapid_claims=VAPID_CLAIMS,
              ttl=60
            )
        except WebPushException:
            try: SUBSCRIPTIONS.remove(s)
            except: pass

# ── Service Worker (헤드업 유도) ───────────────────────────
@app.route('/sw.js')
def service_worker():
    js = """
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>self.clients.claim());
self.addEventListener('push',e=>{
  let data={}; try{data=e.data.json();}catch(err){}
  const title=data.title||'신호 알림';
  const body=data.body||'업데이트';
  const opt={ body, vibrate:[200,80,200], requireInteraction:true, tag:'signal' };
  e.waitUntil(self.registration.showNotification(title,opt));
});
self.addEventListener('notificationclick',e=>{
  e.notification.close(); e.waitUntil(clients.openWindow('/'));
});
"""
    return Response(js, mimetype='text/javascript')

# ── ngrok & 콘솔 트리거 ───────────────────────────────────
def maybe_start_ngrok():
    try:
        from pyngrok import ngrok
        url = ngrok.connect(5000, bind_tls=True).public_url
        print("[ngrok] ready:", url)
    except Exception as e:
        print("[ngrok skipped]", e)

def stdin_trigger_loop():
    print("Type one: red | yellow | green | red->green | (free text)")
    for line in sys.stdin:
        text=line.strip()
        if not text: continue
        with app.test_request_context('/send', method='POST', data={'msg':text}):
            send_signal()

if __name__=="__main__":
    threading.Thread(target=maybe_start_ngrok,daemon=True).start()
    threading.Thread(target=stdin_trigger_loop,daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
