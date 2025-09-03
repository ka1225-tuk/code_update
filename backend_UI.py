# backend_UI.py
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

# ───────────────────────────────────────────────────────────
# 📱 휴대폰에서 볼 화면 (모바일 앱 느낌의 UI로 개선)
# ───────────────────────────────────────────────────────────
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
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="badge" id="badge">신호 대기중</div>
      <div id="emoji" class="emoji">⌛</div>
      <div id="signal" class="msg">대기중...</div>
      <div class="hint">초록불 신호가 오면 자동으로 갱신됩니다.</div>
    </div>
  </div>

  <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
  <script>
    const $emoji  = document.getElementById('emoji');
    const $signal = document.getElementById('signal');
    const $badge  = document.getElementById('badge');

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
  </script>
</body>
</html>
"""

# 메인 페이지: 폰/브라우저가 접속하는 화면
@app.route('/')
def index():
    return render_template_string(html_page)

# 신호 전송 엔드포인트: 노트북/다른 터미널에서 POST로 호출
@app.route('/send', methods=['POST'])
def send_signal():
    msg = request.form.get("msg", "신호 없음")
    socketio.emit('signal', msg)   # 연결된 모든 클라이언트에 즉시 전송
    return f"Sent: {msg}"

if __name__ == '__main__':
    # 같은 와이파이의 다른 기기(폰)에서도 접속 가능하게 host 지정
    socketio.run(app, host="0.0.0.0", port=5000)
