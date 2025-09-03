# backend.py
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

# 📱 휴대폰에서 볼 화면 (HTML)
html_page = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>신호 알림</title></head>
<body>
<h2>대기중...</h2>
<div id="signal"></div>
<script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
<script>
  var socket = io();
  socket.on('signal', function(msg) {
    document.getElementById("signal").innerHTML = "🟢 " + msg;
  });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(html_page)

@app.route('/send', methods=['POST'])
def send_signal():
    msg = request.form.get("msg", "신호 없음")
    socketio.emit('signal', msg)   # 모든 클라이언트에 전송
    return f"Sent: {msg}"

if __name__ == '__main__':
    # host="0.0.0.0" → 같은 와이파이의 다른 기기에서도 접근 가능
    socketio.run(app, host="0.0.0.0", port=5000)
