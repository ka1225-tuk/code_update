
#!/usr/bin/env python3
# test.py (노트북) | Flask + Socket.IO + WebPush(VAPID) + ngrok
# - 콘솔에 [ngrok] ready: https://.... 출력
# - /send (form/json 모두 허용)
# - 같은 상태 반복 무시, red->green 전환 시 TTS 1회

from flask import Flask, render_template_string, request, jsonify, Response
from flask_socketio import SocketIO
from pywebpush import webpush, WebPushException
import json, sys, threading, os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── VAPID (테스트 키: 필요시 교체) ───────────────────────────
VAPID_PUBLIC  = "BHtWP8B34KzKv7JOOxmb9sT186YiR-x27i0ibL0dnf7sc_TERLV-AGq7nS0lfa2A4yuVY6qW6jROtelP7g2LXz8"
VAPID_PRIVATE = "Lo97JNrh7xcKOG3kXVP6W_oJ9iKq6advezMViSz6FzY"
VAPID_CLAIMS  = {"sub": "mailto:you@example.com"}

SUBSCRIPTIONS = []
LAST_STATE    = None
NGROK_URL     = None

# ── 간단 UI ─────────────────────────────────────────────────
html_page = """
<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>신호 알림</title></head>
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
function speak(text){ if(document.visibilityState!=='visible') return;
  if(!('speechSynthesis' in window)) return;
  const u=new SpeechSynthesisUtterance(text); u.lang='ko-KR';
  speechSynthesis.cancel(); speechSynthesis.speak(u); }
const EMOJI={ red:'🔴', yellow:'🟡', green:'🟢', transition:'🟢' };
const socket=io();
socket.on('signal', p=>{ p=(typeof p==='string')?{text:p,state:null,tts:false}:p;
  $emoji.textContent=EMOJI[p.state]||'🟢';
  $signal.textContent=p.text||'신호 업데이트';
  $badge.textContent='신호 수신';
  if(p.tts) speak(p.text); });
function b64urlToUint8Array(s){const p='='.repeat((4-s.length%4)%4);const b=(s+p).replace(/-/g,'+').replace(/_/g,'/');const r=atob(b);const o=new Uint8Array(r.length);for(let i=0;i<r.length;i++)o[i]=r.charCodeAt(i);return o;}
async function ensureSW(){ if(!('serviceWorker' in navigator)){ $state.textContent='서비스워커 미지원'; return null;} return await navigator.serviceWorker.register('/sw.js'); }
async function subscribePush(){ const reg=await ensureSW(); if(!reg) return;
  const r=await fetch('/vapid-public'); const {key}=await r.json();
  const sub=await reg.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:b64urlToUint8Array(key)});
  await fetch('/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sub)});
  $state.textContent='푸시 구독 완료'; }
document.getElementById('reqPerm').onclick=async()=>{ const perm=await Notification.requestPermission(); if(perm==='granted') await subscribePush(); else $state.textContent='알림 권한 거부됨'; };
document.getElementById('testLocal').onclick=()=>{ $emoji.textContent='🟢'; $signal.textContent='테스트 신호'; $badge.textContent='테스트'; };
</script>
</body></html>
"""

@app.route("/")                 
def index():         
    return render_template_string(html_page)
@app.route("/vapid-public")     
def vapid_public():  
    return jsonify({"key": VAPID_PUBLIC})

@app.route("/subscribe", methods=["POST"])
def subscribe():
    sub=request.get_json(silent=True)
    if sub and "endpoint" in sub and not any(s.get("endpoint")==sub["endpoint"] for s in SUBSCRIPTIONS):
        SUBSCRIPTIONS.append(sub)
    return ("",204)

def normalize_input(user_text:str):
    t=(user_text or "").strip().lower().replace(" ","")
    if t in ("red->green","redgreen","r->g"): return ("green","신호가 바뀌었습니다. 출발하세요!","transition")
    if t=="red":    return ("red","빨간불입니다!","red")
    if t=="yellow": return ("yellow","노란불입니다!","yellow")
    if t=="green":  return ("green","초록불입니다!","green")
    return (None, user_text or "신호 업데이트", None)

@app.route("/send", methods=["POST"])
def send_signal():
    global LAST_STATE
    raw = request.form.get("msg")
    if raw is None:
        data = request.get_json(silent=True) or {}
        raw = data.get("msg","")
    nxt, text, emo = normalize_input(raw)
    if nxt in ("red","yellow","green") and LAST_STATE == nxt:
        print(f"[skip] same state '{nxt}'"); return f"Skipped (same state: {nxt})"
    tts = (LAST_STATE != nxt) if nxt in ("red","yellow","green") else False
    if nxt in ("red","yellow","green"): LAST_STATE = nxt
    payload = {"text": text, "state": emo or nxt, "tts": tts}
    socketio.emit("signal", payload)
    push_to_all("신호 알림", text)
    print(f"[sent] state={nxt} text={text} tts={tts}")
    return f"Sent: {text}"

def push_to_all(title, body):
    for s in SUBSCRIPTIONS[:]:
        try:
            webpush(subscription_info=s, data=json.dumps({"title":title,"body":body}),
                    vapid_private_key=VAPID_PRIVATE, vapid_claims=VAPID_CLAIMS, ttl=60)
        except WebPushException:
            try: SUBSCRIPTIONS.remove(s)
            except: pass

@app.route("/sw.js")
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
  e.notification.close(); e.waitUntil(self.clients.openWindow('/'));
});
"""
    return Response(js, mimetype="text/javascript")

def maybe_start_ngrok():
    # 실행 시 ngrok https 터널 생성 + 콘솔 출력
    global NGROK_URL
    try:
        from pyngrok import ngrok, conf
        token=os.environ.get("NGROK_AUTHTOKEN","").strip()
        if token: conf.get_default().auth_token = token
        for t in ngrok.get_tunnels():
            try: ngrok.disconnect(t.public_url)
            except: pass
        tunnel = ngrok.connect(5000, bind_tls=True)
        NGROK_URL = tunnel.public_url
        print("[ngrok] ready:", NGROK_URL)
    except Exception as e:
        print("[ngrok skipped]", e)

def stdin_trigger_loop():
    # 터미널에서 직접 red/yellow/green 입력해 테스트 가능(옵션)
    print("Type: red | yellow | green | red->green | (free text)")
    for line in sys.stdin:
        txt=line.strip()
        if not txt: continue
        with app.test_request_context("/send", method="POST", data={"msg":txt}):
            send_signal()

if __name__=="__main__":
    threading.Thread(target=maybe_start_ngrok, daemon=True).start()
    threading.Thread(target=stdin_trigger_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
