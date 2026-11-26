"""Company & Lead Research Agent (v2). Run: streamlit run app.py"""
import io
import os

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import PROVIDERS, analyse, ask, list_models, make_client, scrape, to_context

st.set_page_config(page_title="Company Research Agent", page_icon="🔎", layout="wide")
st.title("🔎 Company & Lead Research Agent")
st.caption("Company list → 1-page briefs, bottleneck analysis, outreach drafts.")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("1. Connect an AI")
    provider = st.selectbox("Provider", list(PROVIDERS))
    cfg = PROVIDERS[provider]
    st.caption(cfg["help"])
    needs_key = bool(cfg["env"])
    api_key = ""
    if needs_key:
        api_key = st.text_input("API key", value=os.getenv(cfg["env"], ""), type="password")
    ready = (not needs_key) or bool(api_key)

    mkey = f"models::{provider}"
    # Auto-load the model list once per key, so retired model names never get used.
    tried = f"tried::{provider}::{api_key[-6:]}"
    if ready and mkey not in st.session_state and not st.session_state.get(tried):
        st.session_state[tried] = True
        try:
            with st.spinner("Loading your available models…"):
                st.session_state[mkey] = list_models(make_client(provider, api_key), provider)
        except Exception as e:
            st.warning(f"Could not load models automatically: {' '.join(str(e).split())[:160]}")
    if st.button("Load my available models", disabled=not ready):
        try:
            st.session_state[mkey] = list_models(make_client(provider, api_key), provider)
            st.success(f"Found {len(st.session_state[mkey])} models.")
        except Exception as e:
            st.error(f"Could not load models: {' '.join(str(e).split())[:200]}")
    models = st.session_state.get(mkey, [])
    if models:
        first = st.selectbox("Preferred model", models)
        # Fallback order: your pick first, then every other model from the list.
        model_order = [first] + [m for m in models if m != first]
    else:
        manual = st.text_input("Model (or click 'Load my available models')",
                               {"Google": "gemini-3.5-flash-lite", "Ollama": "llama3.2", "Mistral": "mistral-small-latest",
                                "Cerebras": "llama3.1-8b"}.get(provider.split()[0], "llama-3.3-70b-versatile"))
        model_order = [manual]

    if st.button("Test connection", disabled=not ready):
        with st.spinner("Testing…"):
            try:
                text, used = ask(make_client(provider, api_key), model_order[:5], "Reply with the single word OK.", 50)
                st.success(f"Working. Model used: {used}")
            except Exception as e:
                st.error(str(e))

    st.header("2. Outreach context")
    sender = st.text_area("About you (1-3 lines)",
                          "M.Sc. Computer Science graduate with ML internship experience, moving into "
                          "strategy/ops. I build AI tools that speed up research and operations work.", height=110)
    goal = st.text_input("Goal of outreach", "Start a conversation about a Founder's Office / Ops role")

# --------------------------------------------------------------------- main
st.subheader("Add companies")
t1, t2 = st.tabs(["Paste list", "Upload CSV"])
companies = []
with t1:
    raw = st.text_area("One per line: Name, URL", "Zepto, https://www.zeptonow.com", height=130)
    for line in raw.splitlines():
        if "," in line:
            n, u = line.split(",", 1)
            if n.strip() and u.strip():
                companies.append((n.strip(), u.strip()))
with t2:
    up = st.file_uploader("CSV with columns: name,url", type="csv")
    if up:
        df = pd.read_csv(up)
        df.columns = [c.strip().lower() for c in df.columns]
        companies = list(zip(df["name"].astype(str), df["url"].astype(str)))
        st.dataframe(df, use_container_width=True)

if st.button("Research companies", type="primary", disabled=not companies):
    if not ready:
        st.error("Paste your API key in the sidebar first.")
        st.stop()
    client, results, bar = make_client(provider, api_key), [], st.progress(0.0)
    for i, (name, url) in enumerate(companies, 1):
        with st.status(f"{name}: working…", expanded=False) as status:
            sc = scrape(url)
            if not sc["pages"]:
                status.update(label=f"{name}: could not open website", state="error")
                results.append({"name": name, "url": url, "error": "; ".join(sc["errors"]), "scraped": ""})
            else:
                try:
                    out = analyse(client, model_order, name, to_context(sc, cfg.get('ctx_chars', 16000)), sender, goal)
                    results.append({"name": name, "url": url, "pages": list(sc["pages"]), **out})
                    status.update(label=f"{name}: done ({out['model_used']})", state="complete")
                except Exception as e:
                    status.update(label=f"{name}: AI step failed", state="error")
                    results.append({"name": name, "url": url, "error": str(e), "scraped": to_context(sc, cfg.get('ctx_chars', 16000))})
        bar.progress(i / len(companies))
    st.session_state["results"] = results

results = st.session_state.get("results", [])
if results:
    st.subheader("Results")
    md = []
    for r in results:
        with st.expander(f"{r['name']} · {r['url']}", expanded=len(results) == 1):
            if "brief" not in r:
                st.error(r["error"])
                if r.get("scraped"):
                    st.info("The website was read fine; only the AI step failed. Scraped text below.")
                    st.text_area("Scraped text", r["scraped"], height=200, key=f"s_{r['name']}")
                continue
            a, b, c = st.tabs(["Executive brief", "Bottlenecks", "Outreach draft"])
            a.markdown(r["brief"]); b.markdown(r["bottlenecks"]); c.markdown(r["outreach"])
            st.caption(f"Pages used: {', '.join(r['pages'])} · Model: {r['model_used']} · Review before sending.")
            md.append(f"# {r['name']}\n{r['url']}\n\n{r['brief']}\n\n## Bottlenecks\n{r['bottlenecks']}\n\n## Outreach draft\n{r['outreach']}\n")
    if md:
        st.download_button("Download all as Markdown", "\n---\n".join(md), "research_briefs.md")
        buf = io.StringIO()
        pd.DataFrame([{k: r.get(k) for k in ("name", "url", "brief", "bottlenecks", "outreach")} for r in results if "brief" in r]).to_csv(buf, index=False)
        st.download_button("Download as CSV", buf.getvalue(), "research_briefs.csv")
