"""Scraping + LLM logic. No UI code here, so it is easy to test."""
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openai import APIConnectionError, APIStatusError, OpenAI

# ---------------------------------------------------------------- providers
PROVIDERS = {
    "Google Gemini (free)": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env": "GEMINI_API_KEY",
        "help": "Get a free key at aistudio.google.com/apikey",
    },
    "Ollama (runs on your PC, no key, no account)": {
        "base_url": "http://localhost:11434/v1",
        "env": "",
        "help": "Install from ollama.com, then in a terminal run: ollama pull llama3.2",
        "ctx_chars": 6000,
    },
    "Mistral (free Experiment plan)": {
        "base_url": "https://api.mistral.ai/v1",
        "env": "MISTRAL_API_KEY",
        "help": "Key at console.mistral.ai (choose the free Experiment plan)",
    },
    "Cerebras (free)": {
        "base_url": "https://api.cerebras.ai/v1",
        "env": "CEREBRAS_API_KEY",
        "help": "Free key at cloud.cerebras.ai",
    },
    "Groq (free)": {
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "help": "Get a free key at console.groq.com/keys",
    },
}
SKIP_WORDS = ["image", "tts", "embed", "live", "audio", "whisper", "guard", "robotics",
              "computer-use", "veo", "imagen", "transcribe", "native", "playai", "aqa"]


def make_client(provider: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=PROVIDERS[provider]["base_url"], api_key=(api_key or "").strip() or "not-needed", timeout=90)


def list_models(client: OpenAI, provider: str) -> list:
    """Ask the provider which models THIS key can use (avoids stale hard-coded names)."""
    ids = [m.id.replace("models/", "") for m in client.models.list()]
    ids = [i for i in ids if not any(w in i.lower() for w in SKIP_WORDS)]
    if provider.startswith("Google"):
        ids = [i for i in ids if "gemini" in i.lower() and "flash" in i.lower()]
        ids.sort(key=lambda i: (0 if "lite" in i else 1, i))  # lite models first
    else:
        ids.sort()
    return ids


# ------------------------------------------------------------------ LLM call
def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:260]


def ask(client: OpenAI, models: list, prompt: str, max_tokens: int = 4000):
    """Try each model in order. Returns (text, model_used).
    503/500 -> retry same model; 429/404/400/empty -> move to next model."""
    problems = []
    for model in models:
        for attempt in range(3):
            try:
                r = client.chat.completions.create(
                    model=model, temperature=0.3, max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}])
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return text, model
                problems.append(f"{model}: empty reply")
                break
            except APIStatusError as e:
                code = getattr(e, "status_code", 0)
                if code in (401, 403):
                    raise RuntimeError("API key rejected. Check that you pasted the whole key.") from e
                if code >= 500 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                problems.append(f"{model}: HTTP {code} {_short(e)}")
                break  # 429 / 404 / 400 / persistent 5xx -> next model
            except APIConnectionError as e:
                raise RuntimeError("Cannot reach the provider. Check your internet connection.") from e
    raise RuntimeError("All models failed.\n" + "\n".join(problems[-4:]))


# ----------------------------------------------------------------- analysis
GROUNDING = ("Use ONLY the website text provided. If something is not stated write "
             "'Not found on site'. Mark inferences with '(inferred)'. Be concise and specific.")

PROMPT = """You are a founder's-office analyst. Using the website text below, write THREE sections
about {name}, each starting with its marker line exactly as shown.

===BRIEF===
A one-page executive brief with these markdown headings:
## What they do
## Who they sell to
## Stage & traction signals
## Hiring signals
## Confidence (High/Medium/Low + one line why)

===BOTTLENECKS===
The 3 most likely operational bottlenecks. For each: **Bottleneck**, **Evidence** (from the site),
**Suggested fix**, **Confidence**.

===OUTREACH===
A cold email (max 120 words) with a subject line to the founders. Sender: {sender}. Goal: {goal}.
Open with one concrete observation about {name}, link it to ONE thing the sender can do, end with
a low-friction ask. No flattery or buzzwords.

{grounding}

WEBSITE TEXT:
{context}"""

MARKERS = [("===BRIEF===", "brief"), ("===BOTTLENECKS===", "bottlenecks"), ("===OUTREACH===", "outreach")]


def split_sections(text: str) -> dict:
    out = {"brief": "", "bottlenecks": "", "outreach": ""}
    if all(m in text for m, _ in MARKERS):
        for i, (m, key) in enumerate(MARKERS):
            a = text.index(m) + len(m)
            b = text.index(MARKERS[i + 1][0]) if i + 1 < len(MARKERS) else len(text)
            out[key] = text[a:b].strip()
    else:
        out["brief"] = text
        out["bottlenecks"] = out["outreach"] = "(The model did not split sections. See the Brief tab.)"
    return out


def analyse(client, models, name, context, sender, goal):
    text, used = ask(client, models, PROMPT.format(
        name=name, context=context, grounding=GROUNDING, sender=sender, goal=goal))
    res = split_sections(text)
    res["model_used"] = used
    return res


# ----------------------------------------------------------------- scraping
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgent/2.0)"}
LABELS = {
    "about": ["about", "company", "who-we-are", "our-story", "team"],
    "product": ["product", "solutions", "platform", "features", "services", "how-it-works"],
    "careers": ["careers", "jobs", "join", "hiring"],
    "customers": ["customers", "case-stud", "clients", "partners"],
}
MAX_CHARS = 3000


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    return r.text


def _clean(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        t.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    desc = (meta.get("content") or "").strip() if meta else ""
    body = " ".join(soup.get_text(" ").split())
    return f"TITLE: {title}\nMETA: {desc}\nBODY: {body}"[:MAX_CHARS]


def scrape(url: str) -> dict:
    """Never raises. Returns {'url','pages':{label:text},'errors':[...]}."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    res = {"url": url, "pages": {}, "errors": []}
    try:
        home = _get(url)
    except Exception as e:
        res["errors"].append(f"Could not open the site: {_short(e)}")
        return res
    res["pages"]["home"] = _clean(home)
    soup, host, seen = BeautifulSoup(home, "html.parser"), urlparse(url).netloc, {}
    for a in soup.find_all("a", href=True):
        full = urljoin(url, a["href"]).split("#")[0]
        if urlparse(full).netloc != host:
            continue
        path = urlparse(full).path.lower()
        for label, keys in LABELS.items():
            if label not in seen and any(k in path for k in keys):
                seen[label] = full
    for label, link in seen.items():
        try:
            res["pages"][label] = _clean(_get(link))
        except Exception as e:
            res["errors"].append(f"{label} page failed: {_short(e)}")
    return res


def to_context(scraped: dict, limit: int = 16000) -> str:
    """Join pages, splitting a total character budget evenly (small local models have short memory)."""
    pages = scraped["pages"]
    each = max(500, limit // max(1, len(pages)))
    return "\n\n".join(f"### {k.upper()} PAGE\n{v[:each]}" for k, v in pages.items())
