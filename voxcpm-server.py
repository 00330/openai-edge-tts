"""
本地声音克隆 TTS 服务（VoxCPM-0.5B，纯 CPU，完全免费）
- Web 控制台：上传自己的声音 → 输入文字 → 生成
- OpenAI 兼容：POST /v1/audio/speech
"""
import os, io, json, time, uuid, threading, shutil, traceback
import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ROOT, "models", "VoxCPM-0.5B")
VOICE_DIR = os.path.join(ROOT, "voices")
os.makedirs(VOICE_DIR, exist_ok=True)

PORT = int(os.getenv("VOXCPM_PORT", "5052"))
API_KEY = os.getenv("VOXCPM_API_KEY", "")
DEFAULT_STEPS = int(os.getenv("VOXCPM_STEPS", "8"))

# ---------- 绕过 torchcodec / ffmpeg ----------
import torch, torchaudio

def _sf_load(path, **kw):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(data.T.copy()), sr

torchaudio.load = _sf_load

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response, HTMLResponse, JSONResponse
import uvicorn

app = FastAPI(title="VoxCPM Local TTS")
MODEL = None
MODEL_SR = 16000
LOCK = threading.Lock()
READY = {"ok": False, "loading": True, "error": None, "load_seconds": None}


def load_model():
    global MODEL, MODEL_SR
    t0 = time.time()
    try:
        from voxcpm import VoxCPM
        MODEL = VoxCPM.from_pretrained(MODEL_DIR, load_denoiser=False)
        MODEL_SR = MODEL.tts_model.sample_rate
        READY.update(ok=True, loading=False, load_seconds=round(time.time() - t0, 1))
        print(f"[model] loaded in {time.time()-t0:.1f}s, sr={MODEL_SR}", flush=True)
    except Exception as e:
        READY.update(ok=False, loading=False, error=str(e))
        traceback.print_exc()


threading.Thread(target=load_model, daemon=True).start()


# ---------- 音色库 ----------
def voice_path(vid):
    return os.path.join(VOICE_DIR, vid)

def list_voices():
    out = []
    for vid in sorted(os.listdir(VOICE_DIR)):
        meta_f = os.path.join(voice_path(vid), "meta.json")
        if os.path.isfile(meta_f):
            with open(meta_f, encoding="utf-8") as f:
                out.append(json.load(f))
    return out

def get_voice(vid):
    meta_f = os.path.join(voice_path(vid), "meta.json")
    if not os.path.isfile(meta_f):
        raise HTTPException(404, f"voice not found: {vid}")
    with open(meta_f, encoding="utf-8") as f:
        return json.load(f)


def synth(text, voice_id, steps=None):
    if not READY["ok"]:
        raise HTTPException(503, "model not ready: " + str(READY.get("error") or "loading"))
    steps = steps or DEFAULT_STEPS
    v = get_voice(voice_id)
    ref = os.path.join(voice_path(voice_id), "ref.wav")
    with LOCK:
        wav = MODEL.generate(
            text=text,
            prompt_wav_path=ref,
            prompt_text=v["transcript"],
            cfg_value=2.0,
            inference_timesteps=steps,
        )
    return np.asarray(wav, dtype=np.float32), MODEL_SR


def wav_bytes(wav, sr):
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ---------- 路由 ----------
@app.get("/health")
def health():
    return READY


@app.get("/api/voices")
def api_voices():
    return {"voices": list_voices()}


@app.post("/api/voices")
async def add_voice(
    name: str = Form(...),
    transcript: str = Form(...),
    file: UploadFile = File(...),
):
    vid = uuid.uuid4().hex[:10]
    d = voice_path(vid)
    os.makedirs(d, exist_ok=True)
    raw = await file.read()
    tmp = os.path.join(d, "upload.bin")
    with open(tmp, "wb") as f:
        f.write(raw)
    try:
        data, sr = sf.read(tmp, dtype="float32", always_2d=True)
    except Exception as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, f"无法解析音频（支持 wav/flac/ogg）: {e}")
    mono = data.mean(axis=1)
    if sr != 16000:
        # 简易重采样
        import librosa
        mono = librosa.resample(mono, orig_sr=sr, target_sr=16000)
    sf.write(os.path.join(d, "ref.wav"), mono, 16000, subtype="PCM_16")
    os.remove(tmp)

    meta = {
        "id": vid,
        "name": name,
        "transcript": transcript,
        "duration": round(len(mono) / 16000, 2),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


@app.delete("/api/voices/{vid}")
def del_voice(vid: str):
    get_voice(vid)
    shutil.rmtree(voice_path(vid), ignore_errors=True)
    return {"ok": True}


@app.get("/api/preview/{vid}")
def preview(vid: str):
    p = os.path.join(voice_path(vid), "ref.wav")
    if not os.path.isfile(p):
        raise HTTPException(404)
    return Response(open(p, "rb").read(), media_type="audio/wav")


@app.post("/api/speak")
async def api_speak(req: Request):
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    vid = body.get("voice_id")
    steps = body.get("steps")
    t0 = time.time()
    wav, sr = synth(text, vid, steps)
    dur = len(wav) / sr
    return Response(
        wav_bytes(wav, sr),
        media_type="audio/wav",
        headers={
            "X-Gen-Seconds": f"{time.time()-t0:.1f}",
            "X-Audio-Seconds": f"{dur:.2f}",
            "X-RTF": f"{(time.time()-t0)/dur:.2f}",
        },
    )


@app.post("/v1/audio/speech")
async def openai_speech(req: Request):
    if API_KEY:
        auth = req.headers.get("authorization", "")
        if auth != f"Bearer {API_KEY}":
            raise HTTPException(401, "invalid api key")
    body = await req.json()
    text = (body.get("input") or "").strip()
    if not text:
        raise HTTPException(400, "input is required")
    vid = body.get("voice") or (list_voices()[0]["id"] if list_voices() else None)
    if not vid:
        raise HTTPException(400, "no voice profile; upload one first")
    wav, sr = synth(text, vid)
    return Response(wav_bytes(wav, sr), media_type="audio/wav")


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "voxcpm-0.5b", "object": "model", "owned_by": "local"}]}


@app.get("/", response_class=HTMLResponse)
def index():
    p = os.path.join(ROOT, "voxcpm_ui.html")
    return open(p, encoding="utf-8").read()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
