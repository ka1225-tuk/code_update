import time, socket, sys, threading
from pathlib import Path

import cv2, numpy as np, torch, requests
from flask import Flask, Response, render_template_string, jsonify
from flask import Response as FlaskResponse
from picamera2 import Picamera2
from utils.general import non_max_suppression, scale_boxes


FRIEND_HOST = "http://192.168.137.61:8000"  
POST_TIMEOUT = 2
PUSH_ON_CHANGE_ONLY = True

YOLO_DIR = "/home/kangbm/yolov5_repo"
WEIGHTS  = "/home/kangbm/yolov5_repo/best.torchscript"
IMG_SZ   = 416
CONF_TH  = 0.35
IOU_TH   = 0.45
NAMES    = ["green", "red", "yellow"]
COLORS   = {0:(0,255,0), 1:(0,0,255), 2:(0,255,255)}

latest_jpeg = None
jpeg_lock   = threading.Lock()

state_lock = threading.Lock()
state = {"ts":0.0, "top":None, "counts":{"red":0,"green":0,"yellow":0}}

_last_pushed = None
_last_local_top = None
_push_lock = threading.Lock()

def letterbox(im, new_shape, stride=32):
    h, w = im.shape[:2]
    r = min(new_shape/h, new_shape/w)
    new_unpad = (int(round(w*r)), int(round(h*r)))
    dw, dh = new_shape - new_unpad[0], new_shape - new_unpad[1]
    dw //= 2; dh //= 2
    im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    im = cv2.copyMakeBorder(im, dh, dh, dw, dw, cv2.BORDER_CONSTANT, value=(114,114,114))
    return im, r, (dw, dh)

def preprocess(frame, imgsz, device):
    im, r, (dw, dh) = letterbox(frame, imgsz)
    im = im[:, :, ::-1].transpose(2,0,1).copy()
    im = torch.from_numpy(im).to(device).float() / 255.0
    im = im.unsqueeze(0)
    return im, r, (dw, dh)

def postprocess(pred, frame_shape):
    if isinstance(pred, (list, tuple)): pred = pred[0]
    if isinstance(pred, torch.Tensor) and pred.dim() == 3: pred = pred[0]
    pred = pred.unsqueeze(0) if pred.dim()==2 else pred
    det = non_max_suppression(pred, CONF_TH, IOU_TH, classes=None, agnostic=False, max_det=1000)[0]
    if det is not None and len(det):
        det[:, :4] = scale_boxes((IMG_SZ, IMG_SZ), det[:, :4], frame_shape).round()
    return det

def draw_boxes(frame, det):
    if det is None or len(det)==0: return frame
    for *xyxy, conf, cls in det:
        x1,y1,x2,y2 = map(int, xyxy)
        c = int(cls.item())
        name = NAMES[c] if 0 <= c < len(NAMES) else str(c)
        color = COLORS.get(c, (255,255,255))
        cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
        cv2.putText(frame, f"{name} {float(conf):.2f}", (x1, max(15,y1-5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return frame

def push_to_friend(color: str):
    """POST /updateState?value=<color> 로 전송"""
    global _last_pushed
    with _push_lock:
        if PUSH_ON_CHANGE_ONLY and _last_pushed == color:
            return
        try:
            url = f"{FRIEND_HOST}/updateState"
            res = requests.post(url, params={"value": color}, timeout=POST_TIMEOUT)
            if res.ok:
                _last_pushed = color
                print(f"[PUSH] {color} -> friend OK")
            else:
                print(f"[PUSH] HTTP {res.status_code} from friend")
        except Exception as e:
            print(f"[PUSH] failed: {e}")

app = Flask(__name__)

@app.get("/")
def index():
    html = f"""
    <html>
      <head><title>YOLOv5 Stream</title></head>
      <body style="margin:0;background:#111;color:#eee;font-family:sans-serif;">
        <div style="padding:10px">YOLOv5 TorchScript Stream</div>
        <img src="/stream" style="width:100%;max-width:960px;display:block;margin:0 auto;border:3px solid #444"/>
        <div style="padding:10px">
          Local JSON: <a href="/state">/state</a> |
          Local TEXT: <a href="/state.txt">/state.txt</a><br/>
          Friend server: <code>{FRIEND_HOST}</code>
        </div>
      </body>
    </html>
    """
    return render_template_string(html)

@app.get("/stream")
def stream():
    return Response(mjpeg_generator(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.get("/state")
def get_state_json():
    with state_lock:
        return jsonify(state)

@app.get("/state.txt")
def get_state_text():
    with state_lock:
        color = state["top"] or "none"
    return FlaskResponse(color, mimetype="text/plain")

def mjpeg_generator():
    global latest_jpeg
    while True:
        with jpeg_lock:
            buf = latest_jpeg
        if buf is not None:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf + b"\r\n")
        else:
            time.sleep(0.01)

def camera_loop():
    global latest_jpeg, _last_local_top
    device = torch.device("cpu")
    model  = torch.jit.load(WEIGHTS, map_location=device)
    model.eval()
    print(f"[INFO] TorchScript loaded: {WEIGHTS}")

    try:
        picam2 = Picamera2()
        picam2.configure(picam2.create_preview_configuration(main={"size": (640,480)}))
        picam2.start()
        print("[INFO] camera started. Ctrl+C to stop.")
    except Exception as e:
        print("[ERROR] Camera init failed:", e)
        sys.exit(2)

    try:
        last_emit = 0.8
        out_path = Path(YOLO_DIR) / "_last.jpg"

        while True:
            frame = picam2.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            im, r, dwdh = preprocess(frame, IMG_SZ, device)
            with torch.inference_mode():
                pred = model(im)

            det = postprocess(pred, frame.shape[:2])

            new_top = None
            if det is not None and len(det):
                areas = []
                for *xyxy, conf, cls in det:
                    x1,y1,x2,y2 = map(int, xyxy)
                    areas.append(((x2-x1)*(y2-y1), int(cls.item())))
                if areas:
                    _, cls_idx = max(areas, key=lambda x: x[0])
                    if 0 <= cls_idx < len(NAMES):
                        new_top = NAMES[cls_idx]

            now = time.time()
            if now - last_emit >= 0.8:
                if new_top is None:
                    new_top = "none"
                with state_lock:
                    state["top"] = new_top
                    state["ts"] = now
                    if new_top in state["counts"]:
                        state["counts"][new_top] += 1

                if (not PUSH_ON_CHANGE_ONLY) or (_last_local_top != new_top):
                    push_to_friend(new_top)
                    _last_local_top = new_top

                last_emit = now

            out = draw_boxes(frame.copy(), det)
            cv2.imwrite(str(out_path), out)
            ok, enc = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                with jpeg_lock:
                    latest_jpeg = enc.tobytes()

    except KeyboardInterrupt:
        print("[INFO] stopped.")
    finally:
        try: picam2.stop()
        except: pass

def find_free_port(start=8080, tries=10):
    p = start
    for _ in range(tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", p))
            s.close()
            return p
        except OSError:
            p += 1
            s.close()
    raise RuntimeError("No free port found")

if __name__ == "__main__":
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    port = find_free_port(8080, 10)
    print(f"[INFO] Serving on 0.0.0.0:{port} | friend: {FRIEND_HOST} | local state: /state.txt")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
