"""
Genspark Clone — CZYSTY 1:1
Dokładnie te same providery co Genspark.
Zero brain-router. Zero Supabase ofshore. Zero usprawniania.
To jest emulator — ma zachowywać się identycznie jak oryginał.
"""
import asyncio, json, os, re, time, uuid
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="Genspark Clone 1:1", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ================================================================
# PROVIDERY — IDENTYCZNE JAK GENSPARK
# Żadnych zamienników. Jeśli brak klucza → error jak u Genspark.
# ================================================================

# AI Models — Genspark używa Claude jako główny orchestrator
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")   # Claude Opus 4.6 / Sonnet 4.6
OPENAI_KEY      = os.getenv("OPENAI_API_KEY", "")       # GPT-5.4, DALL-E 3, Whisper, Realtime
GOOGLE_KEY      = os.getenv("GOOGLE_API_KEY", "")       # Gemini 3.1 Pro, Imagen 4, Veo 3

# Image models
TOGETHER_KEY    = os.getenv("TOGETHER_API_KEY", "")     # FLUX Pro Ultra / FLUX.1-schnell
FAL_KEY         = os.getenv("FAL_API_KEY", "")          # Kling, Runway, Luma, PixVerse, Ideogram, Recraft

# Phone calls — DOKŁADNIE jak Genspark (Twilio press release z 03.02.2026)
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_NUMBER   = os.getenv("TWILIO_PHONE_NUMBER", "")  # Twilio numer wychodzący

# Search — Genspark używa Tavily/Perplexity
TAVILY_KEY      = os.getenv("TAVILY_API_KEY", "")

# Meeting bots — headless browser (Genspark własna implementacja)
BROWSERLESS_URL = os.getenv("BROWSERLESS_URL", "http://browserless:3000")

# Local DB — tylko dla sandboxa (nie Supabase ofshore, osobna instancja)
SANDBOX_DB_URL  = os.getenv("SANDBOX_DB_URL", "")       # własna Postgres dla sandboxa

# ================================================================
# CREDIT SYSTEM — dokładnie jak Genspark
# Free: 100/dzień | Plus: 10K/mies | Pro: 125K/mies
# ================================================================
CREDIT_COSTS = {
    "chat":          0,    # Genspark: 0 kredytów na paid
    "image":         0,    # Genspark: 0 kredytów na paid plans
    "slides":      300,
    "sheets":      200,
    "docs":        150,
    "video":       400,
    "sparkpage":   200,
    "call_minute":  50,    # per minuta
    "meeting":      50,
    "voice":        10,
    "search":        0,
}

# ================================================================
# SUPER AGENT — ReAct loop, Claude jako orchestrator
# Dokładnie jak Genspark opisał Kay Zhu (CTO)
# ================================================================
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: str = "claude-opus-4-6"  # Genspark: Claude Opus 4.6 jako primary
    files: Optional[List[str]] = []

@app.post("/v1/chat")
async def chat(req: ChatRequest):
    """Non-streaming — Genspark też ma ten endpoint"""
    async with httpx.AsyncClient(timeout=120) as client:
        result = await claude_call(client, req.message, req.model)
        return {"content": result, "model": req.model}

@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming — SSE jak Genspark"""
    async def generate():
        async with httpx.AsyncClient(timeout=120) as client:
            # Genspark: ReAct loop z backtracking
            scratchpad = []
            final_answer = None
            cycle = 0

            while cycle < 6 and not final_answer:
                cycle += 1
                yield sse("thinking", {"cycle": cycle})

                # Claude jako orchestrator (jak Genspark)
                plan = await claude_call(client,
                    build_react_prompt(req.message, scratchpad),
                    "claude-haiku-4-5-20251001"  # Haiku do planowania, Opus do syntezy
                )
                parsed = parse_react(plan)

                if parsed.get("final_answer"):
                    final_answer = parsed["final_answer"]
                    break

                action = parsed.get("action", "none")
                action_input = parsed.get("action_input", "")

                yield sse("step", {
                    "cycle": cycle,
                    "thought": parsed.get("thought", "")[:150],
                    "action": action,
                    "input": action_input[:80]
                })

                obs = await execute_tool(client, action, action_input)
                yield sse("observation", {"result": str(obs)[:300]})
                scratchpad.append({"cycle": cycle, "action": action, "obs": obs})

            # Synteza — Genspark używa Opus do finalnej odpowiedzi
            if not final_answer:
                yield sse("synthesizing", {})
                obs_text = "\n".join([f"{s['action']}: {s['obs'][:200]}" for s in scratchpad])
                final_answer = await claude_call(client,
                    f"Odpowiedz na: {req.message}\n\nDane:\n{obs_text}",
                    "claude-opus-4-6"
                )

            yield sse("answer", {"content": final_answer})
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ================================================================
# IMAGE STUDIO — wszystkie modele które Genspark ma
# ================================================================
class ImageRequest(BaseModel):
    prompt: str
    model: str = "flux-schnell"
    # Genspark models:
    # flux-schnell | flux-pro | flux-pro-ultra | flux-1-1-pro
    # dall-e-3 | gpt-image-1
    # imagen-4 | seedream-v4-5
    # ideogram-v3 | recraft-v3
    # nano-banana-pro (Genspark własny - niedostępny, fallback: flux)
    width: int = 1024
    height: int = 1024
    aspect_ratio: str = "1:1"
    negative_prompt: Optional[str] = None
    steps: int = 4

@app.post("/v1/images/generate")
async def generate_image(req: ImageRequest):
    async with httpx.AsyncClient(timeout=60) as client:
        url = None
        model_used = req.model

        # FLUX (Together.ai) — główny provider jak Genspark
        if req.model in ["flux-schnell", "flux-pro", "flux-pro-ultra", "flux-1-1-pro"]:
            model_map = {
                "flux-schnell":   "black-forest-labs/FLUX.1-schnell-Free",
                "flux-pro":       "black-forest-labs/FLUX.1-pro",
                "flux-pro-ultra": "black-forest-labs/FLUX.1.1-pro",
                "flux-1-1-pro":   "black-forest-labs/FLUX.1.1-pro"
            }
            r = await client.post("https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {TOGETHER_KEY}"},
                json={
                    "model": model_map[req.model],
                    "prompt": req.prompt,
                    "width": req.width, "height": req.height,
                    "steps": req.steps, "n": 1
                }
            )
            url = r.json()["data"][0]["url"]

        # DALL-E / GPT-Image (OpenAI)
        elif req.model in ["dall-e-3", "gpt-image-1"]:
            r = await client.post("https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                json={
                    "model": req.model,
                    "prompt": req.prompt,
                    "n": 1,
                    "size": f"{req.width}x{req.height}",
                    "quality": "hd"
                }
            )
            url = r.json()["data"][0]["url"]

        # Imagen 4 (Google)
        elif req.model in ["imagen-4"]:
            # Via fal.ai (Google Imagen)
            r = await client.post("https://fal.run/fal-ai/imagen4",
                headers={"Authorization": f"Key {FAL_KEY}"},
                json={"prompt": req.prompt, "image_size": {"width": req.width, "height": req.height}}
            )
            url = r.json().get("images", [{}])[0].get("url")

        # Seedream (ByteDance)
        elif req.model == "seedream-v4-5":
            r = await client.post("https://fal.run/fal-ai/seedream-v4-5",
                headers={"Authorization": f"Key {FAL_KEY}"},
                json={"prompt": req.prompt}
            )
            url = r.json().get("images", [{}])[0].get("url")

        # Ideogram V3
        elif req.model == "ideogram-v3":
            r = await client.post("https://fal.run/fal-ai/ideogram/v3",
                headers={"Authorization": f"Key {FAL_KEY}"},
                json={"prompt": req.prompt, "aspect_ratio": req.aspect_ratio}
            )
            url = r.json().get("images", [{}])[0].get("url")

        # Recraft V3
        elif req.model == "recraft-v3":
            r = await client.post("https://fal.run/fal-ai/recraft-v3",
                headers={"Authorization": f"Key {FAL_KEY}"},
                json={"prompt": req.prompt, "style": "realistic_image"}
            )
            url = r.json().get("images", [{}])[0].get("url")

        return {
            "id": str(uuid.uuid4()),
            "url": url,
            "model": model_used,
            "prompt": req.prompt,
            "credits_used": CREDIT_COSTS["image"]
        }

# ================================================================
# VIDEO — wszystkie modele które Genspark ma
# ================================================================
class VideoRequest(BaseModel):
    prompt: str
    model: str = "kling-v2"
    # Genspark models:
    # sora-2 | sora-2-pro (OpenAI)
    # veo-3 | veo-3-1 (Google)
    # kling-v2 | kling-v2-5 | kling-v2-6 (Kuaishou via fal.ai)
    # runway-gen4-turbo (Runway via fal.ai)
    # luma-dream-machine (Luma AI via fal.ai)
    # pixverse-v4 | pixverse-v5 (PixVerse via fal.ai)
    # hailuo-02 | hailuo-2-3 (MiniMax via fal.ai)
    # seedance-pro | seedance-lite (ByteDance via fal.ai)
    # wan-v2-2 (Alibaba via fal.ai)
    aspect_ratio: str = "16:9"
    duration_sec: int = 5
    input_image_url: Optional[str] = None  # image-to-video

@app.post("/v1/videos/generate")
async def generate_video(req: VideoRequest):
    async with httpx.AsyncClient(timeout=300) as client:
        url = None

        fal_models = {
            "kling-v2":         "fal-ai/kling-video/v2/text-to-video",
            "kling-v2-5":       "fal-ai/kling-video/v2-5/text-to-video",
            "kling-v2-6":       "fal-ai/kling-video/v2-6/text-to-video",
            "runway-gen4-turbo":"fal-ai/runway-gen4/turbo",
            "luma-dream":       "fal-ai/luma-dream-machine",
            "pixverse-v4":      "fal-ai/pixverse/v4",
            "pixverse-v5":      "fal-ai/pixverse/v5",
            "hailuo-02":        "fal-ai/minimax/video-01",
            "seedance-pro":     "fal-ai/seedance/pro",
            "wan-v2-2":         "fal-ai/wan/v2.2/text-to-video",
        }

        if req.model in fal_models:
            payload = {
                "prompt": req.prompt,
                "aspect_ratio": req.aspect_ratio,
                "duration": str(req.duration_sec)
            }
            if req.input_image_url:
                payload["image_url"] = req.input_image_url
            r = await client.post(f"https://fal.run/{fal_models[req.model]}",
                headers={"Authorization": f"Key {FAL_KEY}"},
                json=payload
            )
            url = r.json().get("video", {}).get("url")

        elif req.model in ["sora-2", "sora-2-pro"] and OPENAI_KEY:
            # Sora via OpenAI (wymaga dostępu)
            r = await client.post("https://api.openai.com/v1/videos/generations",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                json={"model": req.model, "prompt": req.prompt,
                      "size": req.aspect_ratio.replace(":", "x"),
                      "duration": req.duration_sec}
            )
            url = r.json().get("data", [{}])[0].get("url")

        elif req.model in ["veo-3", "veo-3-1"] and GOOGLE_KEY:
            # Veo via Google AI (wymaga API access)
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:generateVideo?key={GOOGLE_KEY}",
                json={"prompt": {"text": req.prompt}}
            )
            url = r.json().get("videoMetadata", {}).get("videoUri")

        return {
            "id": str(uuid.uuid4()),
            "url": url,
            "model": req.model,
            "status": "ready" if url else "failed",
            "credits_used": CREDIT_COSTS["video"]
        }

# ================================================================
# PHONE CALLS — Twilio + OpenAI Realtime (DOKŁADNIE jak Genspark)
# Source: BusinessWire 03.02.2026 — "Genspark Uses Twilio"
# ================================================================
class CallRequest(BaseModel):
    to_number: str
    purpose: str
    voice: str = "alloy"   # OpenAI voice
    language: str = "pl"

@app.post("/v1/calls/initiate")
async def initiate_call(req: CallRequest):
    """
    Genspark flow:
    1. Twilio outbound call do numeru
    2. TwiML → Connect → Stream (WebSocket)
    3. WebSocket → OpenAI Realtime API
    4. Shadow model monitoruje przez message queue
    5. Transcript + summary po zakończeniu
    """
    import base64
    call_id = str(uuid.uuid4())

    # Twilio outbound call — identycznie jak Genspark
    auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json",
            headers={"Authorization": f"Basic {auth}"},
            data={
                "To": req.to_number,
                "From": TWILIO_NUMBER,
                # TwiML URL — łączy z OpenAI Realtime przez WebSocket
                "Url": f"https://genspark.ofshore.dev/v1/calls/{call_id}/twiml",
                "Method": "POST"
            }
        )
        twilio_data = r.json()

    return {
        "call_id": call_id,
        "twilio_sid": twilio_data.get("sid"),
        "status": twilio_data.get("status"),
        "to": req.to_number,
        "purpose": req.purpose
    }

@app.api_route("/v1/calls/{call_id}/twiml", methods=["GET", "POST"])
async def call_twiml(call_id: str):
    """
    TwiML który Twilio wykonuje.
    Łączy rozmowę z OpenAI Realtime API przez WebSocket.
    IDENTYCZNIE jak Genspark.
    """
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://genspark.ofshore.dev/v1/calls/{call_id}/media-stream">
            <Parameter name="call_id" value="{call_id}"/>
        </Stream>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

# WebSocket handler dla OpenAI Realtime (Twilio media stream)
# Wymaga websockets library — pełna implementacja w osobnym pliku
@app.get("/v1/calls/{call_id}/status")
async def call_status(call_id: str):
    return {"call_id": call_id, "status": "calling"}

# ================================================================
# AI SLIDES
# ================================================================
class SlidesRequest(BaseModel):
    prompt: str
    slide_count: int = 10
    mode: str = "professional"  # professional | creative (Nano Banana Pro)
    aspect_ratio: str = "16:9"

@app.post("/v1/slides/generate")
async def generate_slides(req: SlidesRequest):
    async with httpx.AsyncClient(timeout=120) as client:
        # Claude Sonnet jako planer (jak Genspark)
        structure_prompt = f"""Stwórz prezentację na temat: {req.prompt}
Liczba slajdów: {req.slide_count}, Tryb: {req.mode}

Odpowiedz TYLKO valid JSON:
{{
  "title": "...",
  "theme": "professional|dark|minimal|colorful",
  "slides": [
    {{
      "index": 1,
      "title": "...",
      "content": ["bullet 1", "bullet 2"],
      "layout": "title|bullets|image|split|quote",
      "speaker_notes": "...",
      "image_prompt": "krótki opis obrazu (jeśli potrzebny)"
    }}
  ]
}}"""

        result = await claude_call(client, structure_prompt, "claude-sonnet-4-6", 3000)
        try:
            data = json.loads(re.sub(r'```json|```', '', result).strip())
        except:
            data = {"title": req.prompt, "slides": []}

        # Creative mode: generuj obrazy FLUX dla każdego slajdu
        if req.mode == "creative" and TOGETHER_KEY:
            for slide in data.get("slides", [])[:5]:
                if slide.get("image_prompt"):
                    img_r = await client.post(
                        "https://api.together.xyz/v1/images/generations",
                        headers={"Authorization": f"Bearer {TOGETHER_KEY}"},
                        json={
                            "model": "black-forest-labs/FLUX.1-schnell-Free",
                            "prompt": slide["image_prompt"],
                            "width": 1280, "height": 720, "steps": 4, "n": 1
                        }
                    )
                    slide["image_url"] = img_r.json()["data"][0]["url"]

        slide_id = str(uuid.uuid4())
        return {
            "id": slide_id,
            "title": data.get("title"),
            "slides": data.get("slides", []),
            "slide_count": len(data.get("slides", [])),
            "export": {
                "pptx": f"/v1/slides/{slide_id}/export/pptx",
                "pdf":  f"/v1/slides/{slide_id}/export/pdf",
                "web":  f"https://spark.ofshore.dev/s/{slide_id}"
            },
            "credits_used": CREDIT_COSTS["slides"]
        }

@app.post("/v1/slides/{slide_id}/factcheck/{slide_index}")
async def factcheck_slide(slide_id: str, slide_index: int, claim: str):
    """Fact check per slajd — jak Genspark (82% accuracy, 8.3 citations avg)"""
    async with httpx.AsyncClient(timeout=20) as client:
        sources = []
        if TAVILY_KEY:
            r = await client.post("https://api.tavily.com/search",
                json={"api_key": TAVILY_KEY, "query": claim, "max_results": 3})
            sources = r.json().get("results", [])

        verdict = await claude_call(client,
            f"Weryfikuj twierdzenie: '{claim}'\nŹródła: {json.dumps(sources[:3])}\n\nOdpowiedz JSON: {{verdict, confidence, source_url, explanation}}",
            "claude-haiku-4-5-20251001"
        )
        try:
            return json.loads(re.sub(r'```json|```', '', verdict).strip())
        except:
            return {"verdict": "unverified", "confidence": 0}

# ================================================================
# AI SHEETS
# ================================================================
class SheetsRequest(BaseModel):
    prompt: str
    sources: Optional[List[str]] = []

@app.post("/v1/sheets/generate")
async def generate_sheets(req: SheetsRequest):
    async with httpx.AsyncClient(timeout=90) as client:
        scraped = ""
        for url in req.sources[:3]:
            try:
                r = await client.post(f"{BROWSERLESS_URL}/content",
                    json={"url": url, "gotoOptions": {"waitUntil": "networkidle2"}},
                    timeout=15)
                scraped += f"\n{url}:\n{r.text[:1000]}"
            except:
                pass

        result = await claude_call(client,
            f"Stwórz arkusz danych: {req.prompt}\n{scraped}\n\nOdpowiedz JSON: {{title, headers, rows (max 50), analysis_python_code, chart_type}}",
            "claude-sonnet-4-6", 2000
        )
        try:
            data = json.loads(re.sub(r'```json|```', '', result).strip())
        except:
            data = {"title": req.prompt, "headers": [], "rows": []}

        sheet_id = str(uuid.uuid4())
        return {
            "id": sheet_id,
            "title": data.get("title"),
            "headers": data.get("headers", []),
            "rows": data.get("rows", []),
            "row_count": len(data.get("rows", [])),
            "analysis_code": data.get("analysis_python_code", ""),
            "chart_type": data.get("chart_type", "bar"),
            "export": {
                "xlsx": f"/v1/sheets/{sheet_id}/export/xlsx",
                "csv":  f"/v1/sheets/{sheet_id}/export/csv"
            },
            "credits_used": CREDIT_COSTS["sheets"]
        }

# ================================================================
# AI DOCS
# ================================================================
class DocsRequest(BaseModel):
    prompt: str
    template: Optional[str] = None
    source_image_url: Optional[str] = None  # photo-driven design jak Genspark

@app.post("/v1/docs/generate")
async def generate_docs(req: DocsRequest):
    async with httpx.AsyncClient(timeout=90) as client:
        style_hint = ""
        if req.source_image_url:
            style_hint = f"\nInspiruj się stylem z: {req.source_image_url}"

        content = await claude_call(client,
            f"Napisz profesjonalny dokument: {req.prompt}{style_hint}\n\nFormat: Markdown z nagłówkami ##, listami, pogrubieniami. Minimum 500 słów.",
            "claude-sonnet-4-6", 3000
        )

        doc_id = str(uuid.uuid4())
        return {
            "id": doc_id,
            "title": req.prompt[:60],
            "content_md": content,
            "word_count": len(content.split()),
            "export": {
                "pdf":  f"/v1/docs/{doc_id}/export/pdf",
                "docx": f"/v1/docs/{doc_id}/export/docx",
                "md":   f"/v1/docs/{doc_id}/export/md"
            },
            "credits_used": CREDIT_COSTS["docs"]
        }

# ================================================================
# SPARKPAGES
# ================================================================
class SparkpageRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    source_url: Optional[str] = None

@app.post("/v1/sparkpages/generate")
async def generate_sparkpage(req: SparkpageRequest):
    async with httpx.AsyncClient(timeout=90) as client:
        source_hint = ""
        if req.source_url:
            try:
                r = await client.post(f"{BROWSERLESS_URL}/content",
                    json={"url": req.source_url}, timeout=20)
                source_hint = f"\nOdtwórz podobną stronę do: {req.source_url}\nHTML ref: {r.text[:2000]}"
            except:
                source_hint = f"\nInspiruj się: {req.source_url}"

        html = await claude_call(client,
            f"Stwórz kompletną stronę HTML: {req.prompt}{source_hint}\n\nSingle file, CSS inline, Tailwind CDN, nowoczesny design, responsywny. Tylko HTML, bez markdown.",
            "claude-sonnet-4-6", 5000
        )

        slug = f"{str(uuid.uuid4())[:8]}"
        return {
            "id": str(uuid.uuid4()),
            "slug": slug,
            "title": req.title or req.prompt[:60],
            "public_url": f"https://spark.ofshore.dev/{slug}",
            "html": html,
            "credits_used": CREDIT_COSTS["sparkpage"]
        }

# ================================================================
# VOICE — Whisper STT (jak Genspark Speakly)
# ================================================================
@app.post("/v1/voice/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = "pl"):
    audio_bytes = await audio.read()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": (audio.filename or "audio.webm", audio_bytes, audio.content_type or "audio/webm")},
            data={"model": "whisper-1", "language": language}
        )
        return {"transcript": r.json().get("text", ""), "language": language}

# ================================================================
# WEB SEARCH — Tavily (jak Genspark)
# ================================================================
@app.get("/v1/search")
async def search(q: str, max_results: int = 5):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": q, "max_results": max_results})
        return r.json()

# ================================================================
# HEALTH — pokaż które providery aktywne
# ================================================================
@app.get("/health")
async def health():
    return {
        "service": "genspark-clone-1:1",
        "providers": {
            "claude_anthropic":     bool(ANTHROPIC_KEY),
            "gpt_openai":          bool(OPENAI_KEY),
            "gemini_google":       bool(GOOGLE_KEY),
            "flux_together":       bool(TOGETHER_KEY),
            "kling_runway_fal":    bool(FAL_KEY),
            "twilio_calls":        bool(TWILIO_SID and TWILIO_TOKEN),
            "whisper_voice":       bool(OPENAI_KEY),
            "tavily_search":       bool(TAVILY_KEY),
            "browserless":         True,
        },
        "credit_costs": CREDIT_COSTS
    }

# ================================================================
# HELPERS — Claude direct (NIE brain-router)
# ================================================================
async def claude_call(client: httpx.AsyncClient, prompt: str, model: str, max_tokens: int = 1500) -> str:
    """Direct Anthropic API — jak Genspark (NIE przez brain-router)"""
    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=60
    )
    data = r.json()
    return data.get("content", [{}])[0].get("text", "")

async def execute_tool(client: httpx.AsyncClient, action: str, action_input: str) -> str:
    """Narzędzia dostępne w ReAct loop — jak Genspark 80+ tools"""
    if "search" in action and TAVILY_KEY:
        r = await client.post("https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": action_input, "max_results": 3}, timeout=10)
        results = r.json().get("results", [])
        return "\n".join([f"• {x['title']}: {x['content'][:200]}" for x in results[:3]])

    if "browser" in action or "page" in action:
        try:
            r = await client.post(f"{BROWSERLESS_URL}/content",
                json={"url": action_input, "gotoOptions": {"waitUntil": "networkidle2"}}, timeout=15)
            return r.text[:1000]
        except:
            return "Błąd pobierania strony"

    # Fallback: Claude reasoning
    return await claude_call(client, f"Wykonaj: {action} z input: {action_input}", "claude-haiku-4-5-20251001")

def build_react_prompt(question: str, scratchpad: list) -> str:
    scratch = "\n".join([f"Step {s['cycle']}: {s['action']} → {s['obs'][:150]}" for s in scratchpad])
    return f"""Pytanie: {question}

Dostępne narzędzia: web_search, browser_fetch, image_generate, code_execute, none

{scratch if scratch else ''}

Odpowiedz:
Thought: [co myślisz]
Action: [narzędzie lub "none"]
Action Input: [co przekazać]

LUB:
Final Answer: [odpowiedź]"""

def parse_react(text: str) -> dict:
    if fa := re.search(r'Final Answer:\s*(.+)', text, re.DOTALL | re.I):
        return {"final_answer": fa.group(1).strip()}
    result = {}
    if th := re.search(r'Thought:\s*(.+?)(?=\nAction:|$)', text, re.DOTALL | re.I):
        result["thought"] = th.group(1).strip()
    if ac := re.search(r'Action:\s*(.+?)(?=\nAction Input:|$)', text, re.DOTALL | re.I):
        result["action"] = ac.group(1).strip().lower()
    if ai := re.search(r'Action Input:\s*(.+?)(?=\nThought:|$)', text, re.DOTALL | re.I):
        result["action_input"] = ai.group(1).strip()
    return result

def sse(t: str, d: dict) -> str:
    return f"data: {json.dumps({'type': t, **d})}\n\n"
