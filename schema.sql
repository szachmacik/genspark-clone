-- ================================================================
-- Genspark Clone — ofshore.dev
-- 1:1 feature parity schema
-- Każda tabela = jeden feature Genspark
-- ================================================================

-- ── USERS & WORKSPACES ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS genspark.users (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    email           text UNIQUE NOT NULL,
    name            text,
    avatar_url      text,
    plan            text DEFAULT 'free',  -- free|plus|pro|teams|enterprise
    credits         int DEFAULT 100,      -- daily credits (Genspark: 100/day free)
    credits_reset_at timestamptz DEFAULT now() + interval '1 day',
    monthly_credits int DEFAULT 0,        -- plan credits
    settings        jsonb DEFAULT '{}'
);

-- Workspace (Teams feature)
CREATE TABLE IF NOT EXISTS genspark.workspaces (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    name            text NOT NULL,
    owner_id        uuid REFERENCES genspark.users(id),
    plan            text DEFAULT 'teams',
    member_count    int DEFAULT 1,
    settings        jsonb DEFAULT '{}'
);

-- ── CHAT SESSIONS (Super Agent) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS genspark.sessions (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    workspace_id    uuid,
    title           text,
    agent_type      text DEFAULT 'super_agent',
    -- super_agent|slides|sheets|docs|developer|image|video|phone
    status          text DEFAULT 'active',
    message_count   int DEFAULT 0,
    tokens_used     int DEFAULT 0,
    credits_used    int DEFAULT 0
);

CREATE TABLE IF NOT EXISTS genspark.messages (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id      uuid REFERENCES genspark.sessions(id),
    created_at      timestamptz DEFAULT now(),
    role            text NOT NULL,        -- user|assistant|tool|system
    content         text,
    tool_calls      jsonb DEFAULT '[]',
    tool_results    jsonb DEFAULT '[]',
    model_used      text,
    tokens          int DEFAULT 0,
    step_number     int DEFAULT 0         -- ReAct step
);

-- ── AI SLIDES ───────────────────────────────────────────────────
-- Genspark: prompt → structured slides → PPTX/PDF/web
CREATE TABLE IF NOT EXISTS genspark.slides (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    session_id      uuid REFERENCES genspark.sessions(id),
    user_id         uuid REFERENCES genspark.users(id),
    title           text,
    prompt          text,
    mode            text DEFAULT 'professional', -- professional|creative
    slide_count     int DEFAULT 10,
    aspect_ratio    text DEFAULT '16:9',
    slides_json     jsonb DEFAULT '[]',
    -- [{title, content, layout, speaker_notes, fact_check_status}]
    pptx_url        text,
    pdf_url         text,
    web_url         text,               -- public sparkpage URL
    thumbnail_url   text,
    status          text DEFAULT 'generating',
    credits_used    int DEFAULT 300,
    fact_checked    boolean DEFAULT false
);

-- ── AI SHEETS ───────────────────────────────────────────────────
-- Genspark: NL → data table + charts + Jupyter analysis
CREATE TABLE IF NOT EXISTS genspark.sheets (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    session_id      uuid REFERENCES genspark.sessions(id),
    user_id         uuid REFERENCES genspark.users(id),
    title           text,
    prompt          text,
    headers         text[] DEFAULT '{}',
    rows            jsonb DEFAULT '[]',
    charts          jsonb DEFAULT '[]',  -- [{type, data, title}]
    analysis_code   text,               -- Python/pandas code
    analysis_output text,
    xlsx_url        text,
    csv_url         text,
    status          text DEFAULT 'generating',
    credits_used    int DEFAULT 200,
    row_count       int DEFAULT 0
);

-- ── AI DOCS ─────────────────────────────────────────────────────
-- Genspark: prompt → rich text doc (dual format: rich + markdown)
CREATE TABLE IF NOT EXISTS genspark.docs (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    session_id      uuid REFERENCES genspark.sessions(id),
    user_id         uuid REFERENCES genspark.users(id),
    title           text,
    prompt          text,
    content_md      text,               -- Markdown version
    content_html    text,               -- Rich text version
    template_used   text,
    word_count      int DEFAULT 0,
    pdf_url         text,
    docx_url        text,
    status          text DEFAULT 'generating',
    credits_used    int DEFAULT 150
);

-- ── IMAGE STUDIO ─────────────────────────────────────────────────
-- Genspark: FLUX Pro Ultra, DALL-E, Imagen 4, Ideogram, Recraft
CREATE TABLE IF NOT EXISTS genspark.images (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    session_id      uuid REFERENCES genspark.sessions(id),
    user_id         uuid REFERENCES genspark.users(id),
    prompt          text NOT NULL,
    negative_prompt text,
    -- Provider (Genspark uses all these)
    model           text DEFAULT 'flux-schnell',
    -- flux-schnell|flux-pro|flux-pro-ultra|dall-e-3|
    -- imagen-4|ideogram-v3|recraft-v3|seedream
    provider        text DEFAULT 'together', -- together|openai|google|fal|replicate
    width           int DEFAULT 1024,
    height          int DEFAULT 1024,
    aspect_ratio    text DEFAULT '1:1',
    steps           int DEFAULT 4,
    style_preset    text,
    image_url       text,
    thumbnail_url   text,
    status          text DEFAULT 'generating',
    credits_used    int DEFAULT 50,     -- Genspark: 0 credits on paid plans
    generation_ms   int
);

-- ── VIDEO GENERATION ────────────────────────────────────────────
-- Genspark: Sora 2, Veo 3.1, Kling V2.5, Runway, Luma, PixVerse
CREATE TABLE IF NOT EXISTS genspark.videos (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    session_id      uuid REFERENCES genspark.sessions(id),
    user_id         uuid REFERENCES genspark.users(id),
    prompt          text NOT NULL,
    model           text DEFAULT 'kling-v2',
    -- sora-2|veo-3|kling-v2|runway-gen4|luma-dream|pixverse-v4|
    -- hailuo-2|seedance-pro|wan-v2
    provider        text DEFAULT 'fal',  -- fal|replicate|openai|google|kling
    aspect_ratio    text DEFAULT '16:9',
    duration_sec    int DEFAULT 5,
    input_image_url text,               -- image-to-video
    video_url       text,
    thumbnail_url   text,
    status          text DEFAULT 'generating',
    credits_used    int DEFAULT 300,
    generation_ms   int
);

-- ── SPARKPAGES ──────────────────────────────────────────────────
-- Genspark: prompt → full HTML page → public URL
CREATE TABLE IF NOT EXISTS genspark.sparkpages (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    title           text NOT NULL,
    prompt          text,
    html_content    text NOT NULL,
    slug            text UNIQUE NOT NULL,
    is_public       boolean DEFAULT true,
    public_url      text,               -- spark.ofshore.dev/{slug}
    views           int DEFAULT 0,
    source_url      text,               -- jeśli rekonstrukcja istniejącej strony
    citations       jsonb DEFAULT '[]', -- [{claim, source_url, verified}]
    status          text DEFAULT 'published'
);

-- ── PHONE CALLS ─────────────────────────────────────────────────
-- Genspark: Twilio + OpenAI Realtime API (dual-layer)
CREATE TABLE IF NOT EXISTS genspark.calls (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    -- Twilio data
    twilio_call_sid text,
    to_number       text NOT NULL,
    from_number     text,               -- Twilio number
    -- Task
    purpose         text NOT NULL,      -- cel połączenia
    system_prompt   text,              -- instrukcje dla agenta głosowego
    voice_id        text DEFAULT 'alloy', -- alloy|echo|nova|shimmer
    language        text DEFAULT 'pl',
    -- OpenAI Realtime
    realtime_session_id text,
    -- Wynik
    status          text DEFAULT 'pending',
    -- pending|calling|connected|completed|failed
    duration_sec    int,
    transcript      text,
    summary         text,
    action_items    jsonb DEFAULT '[]',
    recording_url   text,
    credits_used    int DEFAULT 100,
    -- Metryki (jak Genspark: 94.3% success rate)
    call_outcome    text  -- success|no_answer|voicemail|error
);

-- ── MEETING BOTS ────────────────────────────────────────────────
-- Genspark: Playwright bot dołącza do Meet/Zoom/Teams
CREATE TABLE IF NOT EXISTS genspark.meetings (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    meeting_url     text NOT NULL,      -- Google Meet/Zoom/Teams link
    calendar_event_id text,
    platform        text,               -- meet|zoom|teams
    title           text,
    scheduled_at    timestamptz,
    status          text DEFAULT 'scheduled',
    -- scheduled|joining|recording|done|failed
    transcript      text,
    summary         text,
    action_items    jsonb DEFAULT '[]',
    participants    text[] DEFAULT '{}',
    notion_page_id  text,
    recording_url   text,
    credits_used    int DEFAULT 50
);

-- ── VOICE SESSIONS (Speakly) ────────────────────────────────────
-- Genspark: Whisper STT → Super Agent → response
CREATE TABLE IF NOT EXISTS genspark.voice_sessions (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    session_id      uuid REFERENCES genspark.sessions(id),
    audio_duration_sec float,
    language        text DEFAULT 'pl',
    transcript      text,               -- Whisper output
    response_text   text,               -- Agent response
    response_audio_url text,            -- TTS output
    credits_used    int DEFAULT 10
);

-- ── WORKFLOWS ───────────────────────────────────────────────────
-- Genspark: ~20 apps, NL-defined, schedule/webhook/calendar triggers
CREATE TABLE IF NOT EXISTS genspark.workflows (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    name            text NOT NULL,
    description     text,
    trigger_type    text,  -- schedule|webhook|email|calendar|manual
    trigger_config  jsonb DEFAULT '{}',
    steps           jsonb NOT NULL,    -- NL-defined steps
    apps_used       text[] DEFAULT '{}',
    n8n_workflow_id text,
    is_active       boolean DEFAULT true,
    run_count       int DEFAULT 0,
    last_run_at     timestamptz,
    last_run_status text
);

-- ── AI DRIVE (storage) ──────────────────────────────────────────
-- Genspark: 1GB-1TB per plan, stores all generated outputs
CREATE TABLE IF NOT EXISTS genspark.drive_files (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    name            text NOT NULL,
    file_type       text,              -- slides|sheets|doc|image|video|sparkpage|other
    file_url        text NOT NULL,     -- R2 URL
    thumbnail_url   text,
    size_bytes      bigint DEFAULT 0,
    source_id       uuid,              -- ID z odpowiedniej tabeli
    source_type     text,             -- 'slides'|'images'|etc
    folder          text DEFAULT '/',
    is_public       boolean DEFAULT false,
    share_url       text
);

-- ── FACT CHECKS ─────────────────────────────────────────────────
-- Genspark: cross-model verification, 8.3 citations avg
CREATE TABLE IF NOT EXISTS genspark.fact_checks (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    checked_at      timestamptz DEFAULT now(),
    source_id       uuid,              -- slides/docs id
    source_type     text,
    claim           text NOT NULL,
    verdict         text,   -- verified|unverified|false|needs_source
    confidence      float,
    source_url      text,
    source_title    text,
    checked_by      text DEFAULT 'claude'  -- model który sprawdzał
);

-- ── CREDIT USAGE LOG ────────────────────────────────────────────
-- Genspark: credit-based system
CREATE TABLE IF NOT EXISTS genspark.credit_log (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz DEFAULT now(),
    user_id         uuid REFERENCES genspark.users(id),
    operation       text NOT NULL,
    credits_used    int NOT NULL,
    credits_before  int,
    credits_after   int,
    source_id       uuid,
    source_type     text,
    model_used      text
);

-- ── BENCHMARK RESULTS ───────────────────────────────────────────
-- Porównanie: oficjalny Genspark vs klon
CREATE TABLE IF NOT EXISTS genspark.benchmarks (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    run_at          timestamptz DEFAULT now(),
    task_description text NOT NULL,
    task_type       text,
    -- Oficjalny Genspark
    official_time_ms int,
    official_result  text,
    official_credits int,
    -- Klon
    clone_time_ms   int,
    clone_result     text,
    clone_credits    int,
    -- Ocena ślepa przez Claude
    blind_winner     text,  -- 'official'|'clone'|'tie'
    blind_reasoning  text,
    quality_official float,  -- 0-1
    quality_clone    float,
    -- Ukryte przewagi
    hidden_advantage text,   -- co klon wiedział więcej
    advantage_score  float   -- jak dużo pomogło
);

-- ================================================================
-- SCHEMA genspark (osobny od autonomous)
-- ================================================================

-- Indeksy
CREATE INDEX IF NOT EXISTS sessions_user_idx ON genspark.sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS messages_session_idx ON genspark.messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS slides_user_idx ON genspark.slides(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS images_user_idx ON genspark.images(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS calls_user_idx ON genspark.calls(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS sparkpages_slug_idx ON genspark.sparkpages(slug);
CREATE INDEX IF NOT EXISTS drive_user_idx ON genspark.drive_files(user_id, file_type);

-- RPC: Odejmij kredyty
CREATE OR REPLACE FUNCTION genspark.use_credits(
    p_user_id uuid, p_amount int, p_operation text,
    p_source_id uuid DEFAULT NULL, p_source_type text DEFAULT NULL
)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE v_credits int;
BEGIN
    SELECT credits INTO v_credits FROM genspark.users WHERE id = p_user_id;
    IF v_credits < p_amount THEN RETURN false; END IF;

    UPDATE genspark.users SET credits = credits - p_amount WHERE id = p_user_id;

    INSERT INTO genspark.credit_log
        (user_id, operation, credits_used, credits_before, credits_after, source_id, source_type)
    VALUES (p_user_id, p_operation, p_amount, v_credits, v_credits - p_amount, p_source_id, p_source_type);

    RETURN true;
END; $$;

-- RPC: Reset daily credits
CREATE OR REPLACE FUNCTION genspark.reset_daily_credits()
RETURNS void LANGUAGE sql AS $$
    UPDATE genspark.users
    SET credits = CASE plan
        WHEN 'free'  THEN 100
        WHEN 'plus'  THEN 10000
        WHEN 'pro'   THEN 125000
        ELSE 10000
    END,
    credits_reset_at = now() + interval '1 day'
    WHERE credits_reset_at <= now();
$$;

-- pg_cron: reset credits daily
SELECT cron.schedule('reset-genspark-credits', '0 0 * * *', 'SELECT genspark.reset_daily_credits()');
