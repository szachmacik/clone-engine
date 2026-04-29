# HOLON-META: {"morphic_field":"agent-state:4c67a2b1-6830-44ec-97b1-7c8f93722add"}
"""
Clone Engine — ofshore.dev
URL → pełna analiza → 6 warstw kodu
Uczy się wzorców z każdego klona
"""
import asyncio, json, os, re, hashlib, time
import httpx
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Clone Engine", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BRAIN_ROUTER  = os.getenv("BRAIN_ROUTER_URL", "https://brain-router.ofshore.dev")
ROUTER_KEY    = os.getenv("ROUTER_KEY", "")
SUPABASE_URL  = os.getenv("SUPABASE_URL", "https://blgdhfcosqjzrutncbbr.supabase.co")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_KEY", "")
TAVILY_KEY    = os.getenv("TAVILY_API_KEY", "")

SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

# ── Models ────────────────────────────────────────────────────────
class CloneRequest(BaseModel):
    url: str                              # URL produktu do sklonowania
    clone_name: Optional[str] = None      # Nazwa klona (default: domena)
    custom_domain: Optional[str] = None  # np. agent.ofshore.dev
    workspace: Optional[str] = "ofshore"
    depth: Optional[str] = "full"        # full | quick | ui_only

# ── MAIN: Clone pipeline ──────────────────────────────────────────
@app.post("/clone/stream")
async def clone_stream(req: CloneRequest):
    async def generate():
        async with httpx.AsyncClient(timeout=180) as client:
            clone_id = hashlib.md5(f"{req.url}{time.time()}".encode()).hexdigest()[:8]
            name = req.clone_name or extract_domain(req.url)

            yield sse("start", {"clone_id": clone_id, "name": name, "url": req.url})

            # ── PHASE 1: ANALYZE ─────────────────────────────────
            yield sse("phase", {"phase": 1, "name": "Analiza produktu", "icon": "🔍"})

            # Sprawdź wzorce z poprzednich klonów
            patterns = await load_patterns(client, req.url)
            if patterns:
                yield sse("patterns_found", {"count": len(patterns), "reusing": True})

            # Research URL
            analysis = await analyze_product(client, req.url, patterns)
            yield sse("analysis", {
                "product_name": analysis["name"],
                "category": analysis["category"],
                "features_count": len(analysis["features"]),
                "tech_stack": analysis["tech_stack"],
                "modules": [f["name"] for f in analysis["features"][:8]]
            })

            # ── PHASE 2: SQL SCHEMA ──────────────────────────────
            yield sse("phase", {"phase": 2, "name": "Generuję SQL schema", "icon": "🗄️"})
            sql = await gen_sql(client, analysis, name)
            yield sse("file_ready", {"layer": "sql", "lines": sql.count('\n'), "preview": sql[:200]})

            # ── PHASE 3: FASTAPI BACKEND ─────────────────────────
            yield sse("phase", {"phase": 3, "name": "Generuję FastAPI backend", "icon": "⚙️"})
            api = await gen_api(client, analysis, name)
            yield sse("file_ready", {"layer": "api", "lines": api.count('\n'), "endpoints": count_endpoints(api)})

            # ── PHASE 4: n8n WORKFLOWS ───────────────────────────
            yield sse("phase", {"phase": 4, "name": "Generuję n8n workflows", "icon": "⚡"})
            n8n = await gen_n8n(client, analysis, name)
            n8n_data = json.loads(n8n)
            yield sse("file_ready", {"layer": "n8n", "workflows": len(n8n_data.get("workflows", [n8n_data])) if isinstance(n8n_data, list) else 1})

            # ── PHASE 5: UI ──────────────────────────────────────
            yield sse("phase", {"phase": 5, "name": "Generuję UI (HTML/CSS/JS)", "icon": "🎨"})
            ui = await gen_ui(client, analysis, name, req.custom_domain)
            yield sse("file_ready", {"layer": "ui", "lines": ui.count('\n'), "modules": len(analysis["features"])})

            # ── PHASE 6: CF WORKER ───────────────────────────────
            yield sse("phase", {"phase": 6, "name": "Generuję Cloudflare Worker", "icon": "☁️"})
            worker = await gen_worker(client, analysis, name, req.custom_domain)
            yield sse("file_ready", {"layer": "worker", "lines": worker.count('\n')})

            # ── PHASE 7: DEPLOY CONFIG ───────────────────────────
            yield sse("phase", {"phase": 7, "name": "Generuję deploy config", "icon": "🚀"})
            deploy = gen_deploy(analysis, name, req.custom_domain or f"{name.lower()}.ofshore.dev")
            yield sse("file_ready", {"layer": "deploy"})

            # ── SAVE FILES ───────────────────────────────────────
            files = {
                f"01_schema_{name}.sql": sql,
                f"02_api_{name}.py": api,
                f"03_n8n_{name}.json": n8n,
                f"04_ui_{name}.html": ui,
                f"05_worker_{name}.js": worker,
                f"06_deploy_{name}.md": deploy,
            }

            import os
            out_dir = f"/mnt/user-data/outputs/clone-{clone_id}"
            os.makedirs(out_dir, exist_ok=True)
            for fname, content in files.items():
                with open(f"{out_dir}/{fname}", "w") as f:
                    f.write(content)

            # ── SAVE PATTERN (learning) ──────────────────────────
            await save_pattern(client, req.url, analysis, clone_id)
            yield sse("pattern_saved", {"clone_id": clone_id})

            # ── DONE ─────────────────────────────────────────────
            yield sse("done", {
                "clone_id": clone_id,
                "name": name,
                "files": list(files.keys()),
                "output_dir": out_dir,
                "deploy_target": req.custom_domain or f"{name.lower()}.ofshore.dev",
                "features": len(analysis["features"]),
                "time_saved": "~40 hours manual work"
            })
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/clone")
async def clone_sync(req: CloneRequest):
    """Non-streaming clone"""
    results = {}
    async with httpx.AsyncClient(timeout=180) as client:
        name = req.clone_name or extract_domain(req.url)
        patterns = await load_patterns(client, req.url)
        analysis = await analyze_product(client, req.url, patterns)

        results["sql"]    = await gen_sql(client, analysis, name)
        results["api"]    = await gen_api(client, analysis, name)
        results["n8n"]    = await gen_n8n(client, analysis, name)
        results["ui"]     = await gen_ui(client, analysis, name, req.custom_domain)
        results["worker"] = await gen_worker(client, analysis, name, req.custom_domain)
        results["deploy"] = gen_deploy(analysis, name, req.custom_domain or f"{name.lower()}.ofshore.dev")
        results["analysis"] = analysis

        await save_pattern(client, req.url, analysis, "sync")

    return results

@app.get("/patterns")
async def get_patterns():
    """Lista wszystkich nauczonych wzorców"""
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/autonomous.clone_patterns?order=created_at.desc&limit=50",
            headers=SB
        )
        return r.json()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "clone-engine", "version": "1.0"}

# ================================================================
# PHASE 1: ANALYZE — rozkłada produkt na features
# ================================================================
async def analyze_product(client: httpx.AsyncClient, url: str, patterns: list) -> dict:
    """
    Analizuje produkt pod URL:
    1. Pobiera stronę (Tavily)
    2. Claude extrahuje features, tech stack, routing, DB schema
    3. Łączy z wzorcami z poprzednich klonów
    """

    # Szukaj przez Tavily
    search_data = ""
    if TAVILY_KEY:
        try:
            r = await client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_KEY,
                "query": f"site:{url} features pricing API documentation",
                "max_results": 5
            }, timeout=15)
            results = r.json().get("results", [])
            search_data = "\n".join([f"• {x['title']}: {x['content'][:300]}" for x in results[:5]])
        except:
            search_data = f"URL: {url}"

    # Wzorce z poprzednich klonów
    patterns_context = ""
    if patterns:
        patterns_context = f"\n\nWzorce z podobnych klonów:\n" + "\n".join([
            f"- {p.get('product_url','')}: {p.get('category','')}, {p.get('features_count',0)} features"
            for p in patterns[:3]
        ])

    prompt = f"""Analizujesz produkt SaaS pod adresem: {url}

Dane z web:
{search_data}
{patterns_context}

Zwróć TYLKO JSON (bez markdown):
{{
  "name": "NazwaAplikacji",
  "category": "ai_workspace|crm|ecommerce|analytics|productivity|...",
  "description": "1 zdanie co to robi",
  "tech_stack": ["React", "FastAPI", "PostgreSQL"],
  "features": [
    {{
      "name": "Feature Name",
      "description": "co robi",
      "db_tables": ["table1", "table2"],
      "api_endpoints": ["/endpoint1", "/endpoint2"],
      "ui_module": "ModuleName",
      "n8n_trigger": "webhook|schedule|manual",
      "priority": 1
    }}
  ],
  "auth": "jwt|oauth|api_key",
  "billing": "credits|subscription|freemium",
  "integrations": ["gmail", "slack", "notion"],
  "deployment": "docker|k8s|serverless"
}}

Zwróć minimum 8 features, maximum 20. Posortuj po priority (1=najważniejszy)."""

    resp = await brain_call(client, prompt, "sonnet")
    try:
        clean = re.sub(r'```json|```', '', resp).strip()
        data = json.loads(clean)
        data["source_url"] = url
        return data
    except:
        return {
            "name": extract_domain(url),
            "category": "saas",
            "description": f"Clone of {url}",
            "tech_stack": ["FastAPI", "React", "PostgreSQL"],
            "features": [{"name": "Core", "description": "Main feature", "db_tables": ["core_data"], "api_endpoints": ["/api/v1/core"], "ui_module": "Core", "n8n_trigger": "webhook", "priority": 1}],
            "auth": "jwt",
            "billing": "subscription",
            "integrations": [],
            "deployment": "docker",
            "source_url": url
        }

# ================================================================
# PHASE 2: SQL SCHEMA
# ================================================================
async def gen_sql(client: httpx.AsyncClient, analysis: dict, name: str) -> str:
    features_desc = json.dumps(analysis["features"][:10], indent=2)

    prompt = f"""Generujesz kompletne SQL schema dla self-hosted klonu: {analysis['name']} ({analysis['description']})

Features do zmapowania:
{features_desc}

Auth: {analysis['auth']}
Billing: {analysis['billing']}

Wygeneruj PEŁNE SQL (PostgreSQL + Supabase):
1. Wszystkie tabele dla każdego feature z DB tables
2. Tabele systemowe: users, sessions, workspaces, billing_usage, audit_log
3. RLS policies (Row Level Security) dla multi-tenant
4. Indeksy na kluczowych kolumnach
5. RPC functions dla najważniejszych operacji
6. pgvector dla shared_knowledge jeśli AI workspace
7. pg_cron jobs jeśli scheduled features

Nazwa schematu: public (główne) + autonomous (AI/agent tabele)
Styl: production-ready, z komentarzami, constraints, default values

Zwróć TYLKO czysty SQL bez markdown."""

    return await brain_call(client, prompt, "sonnet", max_tokens=4000)

# ================================================================
# PHASE 3: FASTAPI BACKEND
# ================================================================
async def gen_api(client: httpx.AsyncClient, analysis: dict, name: str) -> str:
    endpoints = []
    for f in analysis["features"][:10]:
        endpoints.extend(f.get("api_endpoints", []))

    prompt = f"""Generujesz kompletny FastAPI backend dla: {analysis['name']}

Endpoints do implementacji: {json.dumps(endpoints[:20])}
Auth: {analysis['auth']}
Billing: {analysis['billing']}
Integracje: {analysis['integrations']}

Wygeneruj PEŁNY main.py:
1. Wszystkie CRUD endpoints dla każdego feature
2. Auth middleware (JWT z Supabase)
3. Streaming SSE endpoint /chat/stream (jeśli AI feature)
4. Webhook endpoints
5. Background tasks dla długich operacji
6. Rate limiting
7. CORS
8. Health check
9. Integracja z brain-router (https://brain-router.ofshore.dev)
10. Supabase client (SUPABASE_URL + SUPABASE_SERVICE_KEY z env)

Stack: FastAPI + httpx + pydantic
Zwróć TYLKO czysty Python bez markdown."""

    return await brain_call(client, prompt, "sonnet", max_tokens=4000)

# ================================================================
# PHASE 4: n8n WORKFLOWS
# ================================================================
async def gen_n8n(client: httpx.AsyncClient, analysis: dict, name: str) -> str:
    triggers = [f.get("n8n_trigger", "webhook") for f in analysis["features"][:6]]
    integrations = analysis.get("integrations", [])

    prompt = f"""Generujesz n8n workflow JSON dla: {analysis['name']}

Features z triggerami: {json.dumps([(f['name'], f.get('n8n_trigger','webhook')) for f in analysis['features'][:8]])}
Integracje: {integrations}

Wygeneruj kompletny n8n workflow JSON który:
1. Ma webhook trigger na /webhook/{name.lower()}-main
2. Obsługuje główne akcje produktu
3. Używa brain-router (https://brain-router.ofshore.dev) jako AI brain
4. Zapisuje do Supabase (https://blgdhfcosqjzrutncbbr.supabase.co)
5. Wysyła notyfikacje Telegram do Guardian (chat_id: 8149345223)
6. Ma error handling i retry logic

Zwróć TYLKO czysty JSON workflow bez markdown."""

    result = await brain_call(client, prompt, "haiku", max_tokens=3000)
    # Validate JSON
    try:
        json.loads(re.sub(r'```json|```', '', result).strip())
        return re.sub(r'```json|```', '', result).strip()
    except:
        return json.dumps({
            "name": f"{name} Main Workflow",
            "nodes": [],
            "connections": {},
            "settings": {"executionOrder": "v1"},
            "tags": [{"name": name.lower()}, {"name": "clone"}]
        }, indent=2)

# ================================================================
# PHASE 5: UI
# ================================================================
async def gen_ui(client: httpx.AsyncClient, analysis: dict, name: str, domain: Optional[str]) -> str:
    modules = [f["name"] for f in analysis["features"][:8]]
    nav_items = "\n".join([f'<div class="nav-item" onclick="setModule(\'{m.lower().replace(\" \",\"_\")}\')">{m}</div>' for m in modules])

    prompt = f"""Generujesz kompletny single-file HTML/CSS/JS UI dla klonu: {analysis['name']}
Opis: {analysis['description']}
Moduły: {modules}
Domena: {domain or f'{name.lower()}.ofshore.dev'}

WYMAGANIA:
1. Single file HTML (wszystkie style i JS inline)
2. Ciemny motyw (bg: #09090b, accent: #7c3aed)
3. Lewy sidebar z modułami (jak Genspark)
4. Chat panel główny z SSE streaming
5. Panel outputów po prawej
6. Input area z tool buttons
7. Responsywny (mobile-first)
8. Łączy się z: https://{domain or f'{name.lower()}.ofshore.dev'}/chat/stream
9. Google Fonts (Geist lub Space Grotesk)
10. Każdy moduł ma własny placeholder/opis w empty state

Generuj PEŁNY HTML bez skracania. Min 400 linii.
Zwróć TYLKO czysty HTML bez markdown."""

    return await brain_call(client, prompt, "sonnet", max_tokens=5000)

# ================================================================
# PHASE 6: CLOUDFLARE WORKER
# ================================================================
async def gen_worker(client: httpx.AsyncClient, analysis: dict, name: str, domain: Optional[str]) -> str:
    prompt = f"""Generujesz Cloudflare Worker dla klonu: {analysis['name']}

Worker pełni rolę edge layer:
1. Auth middleware (JWT verification z Supabase)
2. Rate limiting per user (100 req/min)
3. Routing do FastAPI backend
4. Static assets serving (UI HTML)
5. CORS headers
6. Health endpoint /health
7. Request logging do Supabase

Backend URL: https://{name.lower()}-api.ofshore.dev
Supabase URL: https://blgdhfcosqjzrutncbbr.supabase.co

Zwróć TYLKO czysty JavaScript (ES modules) bez markdown."""

    return await brain_call(client, prompt, "haiku", max_tokens=2000)

# ================================================================
# PHASE 7: DEPLOY CONFIG
# ================================================================
def gen_deploy(analysis: dict, name: str, domain: str) -> str:
    return f"""# {name} — Deploy Guide
## Klon: {analysis['name']} ({analysis['description']})
## Wygenerowano przez Clone Engine — ofshore.dev

---

## Stack
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: Single-file HTML (Cloudflare Worker serving)
- **Database**: Supabase (PostgreSQL)
- **Automation**: n8n
- **Edge**: Cloudflare Workers
- **Deployment**: Coolify (DigitalOcean 178.62.246.169)

---

## Kroki wdrożenia

### 1. SQL → Supabase
```
Supabase → SQL Editor → wklej 01_schema_{name}.sql → Run
```

### 2. Coolify → nowa aplikacja FastAPI
```
Coolify → New → Dockerfile
Domain: {domain}
Port: 8000
```

**Env vars:**
```
BRAIN_ROUTER_URL=https://brain-router.ofshore.dev
ROUTER_KEY=<Vault: brain_router_key>
SUPABASE_URL=https://blgdhfcosqjzrutncbbr.supabase.co
SUPABASE_SERVICE_KEY=<Vault>
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn httpx pydantic
COPY 02_api_{name}.py main.py
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Cloudflare Worker
```
CF Dashboard → Workers → New Worker
Wklej: 05_worker_{name}.js
Route: {domain}/*
```

### 4. n8n → Import workflow
```
n8n.ofshore.dev → Import JSON → 03_n8n_{name}.json → Activate
```

### 5. DNS (Cloudflare)
```
A record: {domain.split('.')[0]} → 178.62.246.169
```

### 6. Test
```bash
curl https://{domain}/health
curl -X POST https://{domain}/chat -d '{{"message": "test"}}'
```

---

## Features zaimplementowane
{chr(10).join([f'- {f["name"]}: {f["description"]}' for f in analysis["features"][:10]])}

---

## Integracje
{', '.join(analysis.get('integrations', [])) or 'brak wymaganych'}

---

## Następny krok: OnePass
Po wdrożeniu → dodaj Maciej's OnePass
→ jeden klik aktywuje pełną sieć ofshore.dev
"""

# ================================================================
# PATTERN LEARNING — system zapamiętuje wzorce
# ================================================================
async def load_patterns(client: httpx.AsyncClient, url: str) -> list:
    """Szuka wzorców z podobnych produktów"""
    domain = extract_domain(url)
    try:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/autonomous.clone_patterns?order=created_at.desc&limit=10",
            headers=SB
        )
        patterns = r.json() if r.status_code == 200 else []
        return [p for p in patterns if isinstance(p, dict)]
    except:
        return []

async def save_pattern(client: httpx.AsyncClient, url: str, analysis: dict, clone_id: str):
    """Zapisuje wzorzec do nauki"""
    try:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/autonomous.clone_patterns",
            headers={**SB, "Prefer": "return=minimal"},
            json={
                "clone_id": clone_id,
                "product_url": url,
                "product_name": analysis.get("name"),
                "category": analysis.get("category"),
                "features_count": len(analysis.get("features", [])),
                "tech_stack": analysis.get("tech_stack", []),
                "integrations": analysis.get("integrations", []),
                "feature_names": [f["name"] for f in analysis.get("features", [])],
                "analysis_json": json.dumps(analysis)
            }
        )
    except:
        pass

# ── Helpers ───────────────────────────────────────────────────────
def extract_domain(url: str) -> str:
    match = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+)', url)
    return match.group(1).capitalize() if match else "Clone"

def count_endpoints(code: str) -> int:
    return len(re.findall(r'@app\.(get|post|put|delete|patch)', code))

async def brain_call(client: httpx.AsyncClient, prompt: str, model: str = "sonnet", max_tokens: int = 2000) -> str:
    try:
        r = await client.post(f"{BRAIN_ROUTER}/v1/chat",
            headers={"x-router-key": ROUTER_KEY, "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
            timeout=90
        )
        return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"-- Error: {e} --"

def sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"
