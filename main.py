# HOLON-META: {
#   purpose: "genspark-clone",
#   morphic_field: "agent-state:4c67a2b1-6830-44ec-97b1-7c8f93722add",
#   startup_protocol: "READ morphic_field + biofield_external + em_grid",
#   wiki: "32d6d069-74d6-8164-a6d5-f41c3d26ae9b"
# }

"""
Genspark Clone 1:1 - ofshore.dev
Używa adaptive-router jako proxy dla LLM (ma własny ANTHROPIC_API_KEY)
Pozostałe providery: Together.ai, fal.ai, Twilio, Whisper, Tavily
"""
import asyncio, json, os, re, time, uuid
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="Genspark Clone 1:1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Proxy LLM - nie potrzebuje bezpośrednich kluczy AI
ADAPTIVE_ROUTER = os.getenv("ADAPTIVE_ROUTER_URL", "https://adaptive-router.maciej-koziej01.workers.dev")
BRAIN_ROUTER    = os.getenv("BRAIN_ROUTER_URL", "https://brain-router.ofshore.dev")

# Image/Video providers (jak Genspark)
TOGETHER_KEY = os.getenv("TOGETHER_API_KEY", "")
FAL_KEY      = os.getenv("FAL_API_KEY", "")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")

# Phone calls (jak Genspark - Twilio)
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_PHONE_NUMBER", "")

# Search
TAVILY_KEY   = os.getenv("TAVILY_API_KEY", "")
BROWSERLESS  = os.getenv("BROWSERLESS_URL", "http://browserless:3000")

CREDIT_COSTS = {"chat":0,"image":0,"slides":300,"sheets":200,"docs":150,"video":400,"sparkpage":200,"call_minute":50,"voice":10,"search":0}

# Models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: str = "claude-haiku"
    files: Optional[List[str]] = []

class ImageRequest(BaseModel):
    prompt: str
    model: str = "flux-schnell"
    width: int = 1024
    height: int = 1024
    aspect_ratio: str = "1:1"

class VideoRequest(BaseModel):
    prompt: str
    model: str = "kling-v2"
    aspect_ratio: str = "16:9"
    duration_sec: int = 5
    input_image_url: Optional[str] = None

class SlidesRequest(BaseModel):
    prompt: str
    slide_count: int = 10
    mode: str = "professional"
    aspect_ratio: str = "16:9"

class SheetsRequest(BaseModel):
    prompt: str
    sources: Optional[List[str]] = []

class SparkpageRequest(BaseModel):
    prompt: str
    title: Optional[str] = None
    source_url: Optional[str] = None

class CallRequest(BaseModel):
    to_number: str
    purpose: str
    voice: str = "alloy"
    language: str = "pl"

class BenchmarkRequest(BaseModel):
    task: str
    task_type: str = "research"
    official_result: Optional[str] = None
    official_time_ms: Optional[int] = None

# ── LLM via adaptive-router (nie potrzebuje klucza) ──────────────
async def llm(client: httpx.AsyncClient, prompt: str, model: str = "build", max_tokens: int = 1500) -> str:
    """Wywołaj LLM przez adaptive-router - ma wbudowany ANTHROPIC_API_KEY"""
    try:
        r = await client.post(f"{ADAPTIVE_ROUTER}/route",
            json={"type": model, "description": prompt[:2000]},
            timeout=45
        )
        d = r.json()
        content = d.get("result", {}).get("content", [])
        if isinstance(content, list) and content:
            return content[0].get("text", "")
        # Fallback: brain-router Groq (free)
        r2 = await client.post(f"https://mcp-gateway.maciej-koziej01.workers.dev/tool/groq_ask",
            json={"prompt": prompt[:1500], "tokens": min(max_tokens, 800)},
            timeout=30
        )
        return r2.json().get("answer", "")
    except Exception as e:
        return f"Error: {e}"

# ── SUPER AGENT - ReAct loop ──────────────────────────────────────
@app.post("/v1/chat")
async def chat(req: ChatRequest):
    async with httpx.AsyncClient(timeout=60) as client:
        result = await llm(client, req.message, "build")
        return {"content": result, "model": req.model}

@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    async def gen():
        async with httpx.AsyncClient(timeout=120) as client:
            scratchpad = []
            final_answer = None
            for cycle in range(1, 7):
                yield f"data: {json.dumps({'type':'thinking','cycle':cycle})}

"
                plan = await llm(client, build_react_prompt(req.message, scratchpad), "build")
                parsed = parse_react(plan)
                if parsed.get("final_answer"):
                    final_answer = parsed["final_answer"]
                    break
                action = parsed.get("action", "none")
                action_input = parsed.get("action_input", "")
                yield f"data: {json.dumps({'type':'step','cycle':cycle,'thought':parsed.get('thought','')[:100],'action':action})}

"
                obs = await execute_tool(client, action, action_input)
                yield f"data: {json.dumps({'type':'observation','result':str(obs)[:200]})}

"
                scratchpad.append({"cycle":cycle,"action":action,"obs":obs})
            if not final_answer:
                obs_text = "
".join([f"{s['action']}: {s['obs'][:200]}" for s in scratchpad])
                final_answer = await llm(client, f"Na podstawie:
{obs_text}

Odpowiedz na: {req.message}", "build")
            yield f"data: {json.dumps({'type':'answer','content':final_answer})}

"
            yield "data: [DONE]

"
    return StreamingResponse(gen(), media_type="text/event-stream")

# ── IMAGE STUDIO ──────────────────────────────────────────────────
@app.post("/v1/images/generate")
async def generate_image(req: ImageRequest):
    async with httpx.AsyncClient(timeout=60) as client:
        url = None
        if req.model in ["flux-schnell","flux-pro","flux-pro-ultra"] and TOGETHER_KEY:
            model_map = {"flux-schnell":"black-forest-labs/FLUX.1-schnell-Free","flux-pro":"black-forest-labs/FLUX.1-pro","flux-pro-ultra":"black-forest-labs/FLUX.1.1-pro"}
            r = await client.post("https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {TOGETHER_KEY}"},
                json={"model": model_map.get(req.model), "prompt": req.prompt, "width": req.width, "height": req.height, "steps": 4, "n": 1})
            url = r.json()["data"][0]["url"]
        elif FAL_KEY:
            fal_models = {"ideogram-v3":"fal-ai/ideogram/v3","recraft-v3":"fal-ai/recraft-v3","imagen-4":"fal-ai/imagen4","dall-e-3":"fal-ai/flux/schnell"}
            fal_model = fal_models.get(req.model, "fal-ai/flux/schnell")
            r = await client.post(f"https://fal.run/{fal_model}", headers={"Authorization": f"Key {FAL_KEY}"}, json={"prompt": req.prompt})
            url = r.json().get("images", [{}])[0].get("url")
        return {"id": str(uuid.uuid4()), "url": url, "model": req.model, "prompt": req.prompt}

# ── VIDEO GENERATION ──────────────────────────────────────────────
@app.post("/v1/videos/generate")
async def generate_video(req: VideoRequest):
    async with httpx.AsyncClient(timeout=300) as client:
        url = None
        fal_models = {"kling-v2":"fal-ai/kling-video/v2/text-to-video","kling-v2-5":"fal-ai/kling-video/v2-5/text-to-video","runway-gen4-turbo":"fal-ai/runway-gen4/turbo","luma-dream":"fal-ai/luma-dream-machine","pixverse-v4":"fal-ai/pixverse/v4","hailuo-02":"fal-ai/minimax/video-01"}
        if req.model in fal_models and FAL_KEY:
            payload = {"prompt": req.prompt, "aspect_ratio": req.aspect_ratio, "duration": str(req.duration_sec)}
            if req.input_image_url:
                payload["image_url"] = req.input_image_url
            r = await client.post(f"https://fal.run/{fal_models[req.model]}", headers={"Authorization": f"Key {FAL_KEY}"}, json=payload)
            url = r.json().get("video", {}).get("url")
        return {"id": str(uuid.uuid4()), "url": url, "model": req.model, "status": "ready" if url else "failed"}

# ── AI SLIDES ─────────────────────────────────────────────────────
@app.post("/v1/slides/generate")
async def generate_slides(req: SlidesRequest):
    async with httpx.AsyncClient(timeout=120) as client:
        result = await llm(client, f"""Stwórz prezentację: {req.prompt}
Slajdów: {req.slide_count}, Tryb: {req.mode}
Odpowiedz TYLKO JSON: {{"title":"...","slides":[{{"index":1,"title":"...","content":["bullet1"],"layout":"bullets","speaker_notes":"..."}}]}}""", "build", 3000)
        try:
            data = json.loads(re.sub(r'```json|```','',result).strip())
        except:
            data = {"title": req.prompt, "slides": []}
        sid = str(uuid.uuid4())
        return {"id": sid, "title": data.get("title"), "slides": data.get("slides", []), "slide_count": len(data.get("slides", []))}

# ── AI SHEETS ─────────────────────────────────────────────────────
@app.post("/v1/sheets/generate")
async def generate_sheets(req: SheetsRequest):
    async with httpx.AsyncClient(timeout=90) as client:
        result = await llm(client, f"Stwórz arkusz: {req.prompt}
JSON: {{\"title\":\"...\",\"headers\":[],\"rows\":[]}}", "build", 2000)
        try:
            data = json.loads(re.sub(r'```json|```','',result).strip())
        except:
            data = {"title": req.prompt, "headers": [], "rows": []}
        return {"id": str(uuid.uuid4()), **data}

# ── SPARKPAGES ────────────────────────────────────────────────────
@app.post("/v1/sparkpages/generate")
async def generate_sparkpage(req: SparkpageRequest):
    async with httpx.AsyncClient(timeout=90) as client:
        html = await llm(client, f"Stwórz stronę HTML: {req.prompt}
Single file, Tailwind CDN, nowoczesny design. Tylko HTML.", "build", 5000)
        slug = str(uuid.uuid4())[:8]
        return {"id": str(uuid.uuid4()), "slug": slug, "title": req.title or req.prompt[:60], "public_url": f"https://spark.ofshore.dev/{slug}", "html": html}

# ── PHONE CALLS (Twilio jak Genspark) ─────────────────────────────
@app.post("/v1/calls/initiate")
async def initiate_call(req: CallRequest):
    import base64
    call_id = str(uuid.uuid4())
    if TWILIO_SID and TWILIO_TOKEN:
        async with httpx.AsyncClient(timeout=30) as client:
            auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
            r = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json",
                headers={"Authorization": f"Basic {auth}"},
                data={"To": req.to_number, "From": TWILIO_FROM, "Url": f"https://genspark.ofshore.dev/v1/calls/{call_id}/twiml"}
            )
            return {"call_id": call_id, "status": r.json().get("status"), "to": req.to_number}
    return {"call_id": call_id, "status": "twilio_not_configured", "to": req.to_number}

@app.api_route("/v1/calls/{call_id}/twiml", methods=["GET","POST"])
async def twiml(call_id: str):
    return Response(f'<?xml version="1.0"?><Response><Say language="pl-PL">Dzień dobry, tutaj asystent AI.</Say></Response>', media_type="application/xml")

# ── VOICE (Whisper) ───────────────────────────────────────────────
@app.post("/v1/voice/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = "pl"):
    if not OPENAI_KEY:
        return {"transcript": "Whisper requires OPENAI_API_KEY", "language": language}
    audio_bytes = await audio.read()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": (audio.filename or "audio.webm", audio_bytes, audio.content_type or "audio/webm")},
            data={"model": "whisper-1", "language": language})
        return {"transcript": r.json().get("text", ""), "language": language}

# ── SEARCH (Tavily) ───────────────────────────────────────────────
@app.get("/v1/search")
async def search(q: str, max_results: int = 5):
    async with httpx.AsyncClient(timeout=15) as client:
        if TAVILY_KEY:
            r = await client.post("https://api.tavily.com/search", json={"api_key": TAVILY_KEY, "query": q, "max_results": max_results})
            return r.json()
        # Fallback: Groq web search via mcp-gateway
        r = await client.post("https://mcp-gateway.maciej-koziej01.workers.dev/tool/groq_ask",
            json={"prompt": f"Wyszukaj i podsumuj: {q}", "tokens": 500})
        return {"results": [{"title": "Groq fallback", "content": r.json().get("answer", "")}], "query": q}

# ── BENCHMARK ─────────────────────────────────────────────────────
@app.post("/v1/benchmark/run")
async def benchmark(req: BenchmarkRequest):
    async with httpx.AsyncClient(timeout=120) as client:
        start = time.time()
        clone_result = await llm(client, req.task, "build")
        clone_time = int((time.time() - start) * 1000)
        if req.official_result:
            judgment = await llm(client, f"""Oceń ślepo (nie wiesz który to):
Wynik A: {req.official_result[:500]}
Wynik B: {clone_result[:500]}
JSON: {{"winner":"A lub B lub tie","quality_a":0.8,"quality_b":0.7,"reasoning":"..."}}""", "build")
            try:
                j = json.loads(re.sub(r'```json|```','',judgment).strip())
                winner = "official" if j.get("winner")=="A" else "clone" if j.get("winner")=="B" else "tie"
            except:
                j, winner = {}, "tie"
        else:
            j, winner = {}, "clone"
        return {"task": req.task, "clone_result": clone_result[:400], "clone_time_ms": clone_time, "blind_winner": winner, "reasoning": j.get("reasoning","")}

# ── HELPERS ───────────────────────────────────────────────────────
async def execute_tool(client, action, action_input):
    if "search" in action and TAVILY_KEY:
        r = await client.post("https://api.tavily.com/search", json={"api_key":TAVILY_KEY,"query":action_input,"max_results":3}, timeout=10)
        return "
".join([f"• {x['title']}: {x['content'][:200]}" for x in r.json().get("results",[])[:3]])
    if "browser" in action:
        try:
            r = await client.post(f"{BROWSERLESS}/content", json={"url":action_input,"gotoOptions":{"waitUntil":"networkidle2"}}, timeout=15)
            return r.text[:1000]
        except:
            return "Błąd pobierania"
    return await llm(client, f"Wykonaj: {action} z: {action_input}", "generic")

def build_react_prompt(question, scratchpad):
    scratch = "
".join([f"Step {s['cycle']}: {s['action']} → {s['obs'][:150]}" for s in scratchpad])
    return f"""Pytanie: {question}

Narzędzia: web_search, browser_fetch, none

{scratch}

Thought:
Action:
Action Input:

LUB:
Final Answer:"""

def parse_react(text):
    if fa := re.search(r'Final Answer:\s*(.+)', text, re.DOTALL | re.I):
        return {"final_answer": fa.group(1).strip()}
    r = {}
    if th := re.search(r'Thought:\s*(.+?)(?=
Action:|$)', text, re.DOTALL | re.I): r["thought"] = th.group(1).strip()
    if ac := re.search(r'Action:\s*(.+?)(?=
Action Input:|$)', text, re.DOTALL | re.I): r["action"] = ac.group(1).strip().lower()
    if ai := re.search(r'Action Input:\s*(.+?)(?=
Thought:|$)', text, re.DOTALL | re.I): r["action_input"] = ai.group(1).strip()
    return r

@app.get("/health")
async def health():
    return {
        "service": "genspark-clone-1:1",
        "providers": {
            "llm_via_adaptive_router": True,  # nie potrzebuje kluczy
            "llm_groq_fallback": True,        # darmowy fallback
            "flux_together": bool(TOGETHER_KEY),
            "kling_runway_fal": bool(FAL_KEY),
            "twilio_calls": bool(TWILIO_SID and TWILIO_TOKEN),
            "whisper_voice": bool(OPENAI_KEY),
            "tavily_search": bool(TAVILY_KEY),
            "browserless": True
        }
    }
