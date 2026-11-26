from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Voice & Vision Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_AUDIO_BYTES = 12 * 1024 * 1024  # 12 MB


@app.get("/", response_class=HTMLResponse)
def home():
    html_path = Path("index.html")
    if not html_path.exists():
        return HTMLResponse(
            "<h1>ملف index.html غير موجود في المستودع</h1>",
            status_code=404,
        )
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat_endpoint(
    message: str = Form(""),
    image: UploadFile | None = File(default=None),
):
    clean_message = message.strip()
    image_meta = None

    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            return JSONResponse(
                status_code=400,
                content={"error": f"نوع الصورة غير مدعوم: {image.content_type}"},
            )

        raw_bytes = await image.read()
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            return JSONResponse(
                status_code=400,
                content={"error": "حجم الصورة يتجاوز الحد المسموح (8 ميجابايت)."},
            )

        image_meta = {
            "filename": image.filename or "image",
            "content_type": image.content_type,
            "size_kb": round(len(raw_bytes) / 1024, 1),
        }
        # نقطة ربط نموذج الرؤية (Vision): مرّر raw_bytes و clean_message هنا

    if not clean_message and image_meta is None:
        return JSONResponse(
            status_code=400,
            content={"error": "أرسل نصاً أو صورة على الأقل."},
        )

    prompt = clean_message or "اشرح محتوى هذه الصورة."
    reply = f"وصلت رسالتك: «{prompt}»"
    if image_meta:
        reply += (
            f" | الصورة: {image_meta['filename']} "
            f"({image_meta['content_type']}، {image_meta['size_kb']} KB)."
        )

    return {"reply": reply, "image": image_meta}


@app.post("/api/voice")
async def voice_endpoint(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    if not audio_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": "الملف الصوتي فارغ."},
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return JSONResponse(
            status_code=400,
            content={"error": "حجم المقطع الصوتي يتجاوز 12 ميجابايت."},
        )

    size_kb = round(len(audio_bytes) / 1024, 1)
    # نقطة ربط STT + LLM: حوّل audio_bytes لنص ثم ولّد الرد
    transcript = f"تسجيل صوتي ({audio.content_type or 'audio/webm'}، {size_kb} KB)"
    reply = f"تم استلام تسجيلك الصوتي ({size_kb} KB). جاهز لربط محرك التفريغ الصوتي والرد الذكي."

    return {"transcript": transcript, "reply": reply}


@app.websocket("/ws/live-voice")
async def live_voice_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            packet = await websocket.receive()
            if "bytes" in packet and packet["bytes"]:
                await websocket.send_json({
                    "event": "chunk_received",
                    "bytes": len(packet["bytes"]),
                })
            elif "text" in packet and packet["text"]:
                await websocket.send_json({
                    "event": "control_received",
                    "message": packet["text"],
                })
    except WebSocketDisconnect:
        pass
