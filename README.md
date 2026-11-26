# Company & Lead Research Agent

Turn a raw list of companies into 1-page executive briefs, operational bottleneck
analyses, and tailored outreach drafts, in minutes, using a free LLM.

## The problem
Founders and ops teams spend hours per company on manual research before a call,
pitch, or partnership. The work is repetitive, inconsistent, and rarely documented.

## How it works
1. **Ingest**: paste a list or upload a CSV (`name,url`)
2. **Scrape**: BeautifulSoup reads the homepage plus about / product / careers / customers pages
3. **Analyse**: one LLM call per company returns a brief, 3 likely bottlenecks, and an outreach draft
4. **Export**: Markdown or CSV for Notion / Sheets

## Design choices
- **Grounded outputs**: only scraped text is used; gaps are written as "Not found on site", inferences are labelled.
- **Resilient by design**: the app asks the provider which models your key can use and automatically falls back to the next model on quota, overload, or retired-model errors.
- **Fails gracefully**: if the AI step fails, the scraped text is still shown.
- **Human in the loop**: nothing is sent automatically.

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
```
In the sidebar: pick a provider (Gemini, Groq, Mistral, Cerebras, or Ollama with no key) and paste its free key →
**Load my available models** → **Test connection** → research companies.
Optional: rename `.env.example` to `.env` to store the key.

## Results
- Research time per company: [X min manual → Y min]
- Tested on [N] companies across [sectors]

## Limitations & next steps
JavaScript-rendered sites return thin text (next: Playwright fallback); no per-claim
source citations yet; free-tier daily quotas cap volume.
