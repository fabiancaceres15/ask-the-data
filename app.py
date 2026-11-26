import gzip
import json
import os
import shutil
import sqlite3
import time

import altair as alt
import pandas as pd
import streamlit as st
from google import genai

# ---------- Page setup ----------
st.set_page_config(page_title="Ask the Data: Soccer", page_icon="⚽")
st.title("⚽ Ask the Data")
st.caption(
    "Ask a question about soccer players, clubs, and transfers in plain English. "
    "The AI writes the SQL, runs it, and shows its work so you can check it."
)


# ---------- Connections (cached so they only load once) ----------
@st.cache_resource
def get_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


@st.cache_resource
def get_models(_client):
    # A list of models to try, in order. If one is busy, the app moves to the next.
    models = []
    if "MODEL" in st.secrets:
        models.append(st.secrets["MODEL"])  # your chosen model goes first
    # Skip special models (image, audio, voice, etc.) that can't answer text questions
    skip = ["image", "tts", "audio", "live", "native", "embedding", "robotics", "computer-use"]
    names = []
    try:
        for m in _client.models.list():
            name = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", None) or ["generateContent"]
            if "generateContent" in actions and not any(s in name for s in skip):
                names.append(name)
    except Exception:
        pass
    # Backups: "lite" models first (fastest), then regular "flash" models
    for n in names:
        if "flash-lite" in n and n not in models:
            models.append(n)
    for n in names:
        if "flash" in n and "lite" not in n and n not in models:
            models.append(n)
    return models[:4] or ["gemini-3.8-flash"]


@st.cache_resource
def get_conn():
    # The database is stored zipped (.gz) to fit GitHub's size limit.
    # Unzip it the first time the app starts.
    if not os.path.exists("soccer_small.db"):
        with gzip.open("soccer_small.db.gz", "rb") as f_in, open("soccer_small.db", "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return sqlite3.connect("soccer_small.db", check_same_thread=False)


@st.cache_data
def get_schema(_conn):
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", _conn)
    schema = ""
    for t in tables["name"]:
        cols = pd.read_sql(f"PRAGMA table_info({t})", _conn)
        schema += f"{t}: {', '.join(cols['name'])}\n"
    return schema


client = get_client()
MODELS = get_models(client)
conn = get_conn()
schema = get_schema(conn)

RULES = """Rules:
- Use only the tables and columns listed.
- Always SELECT the numbers used to rank, filter, or count, so the user can check the answer.
- Use LIMIT 50 or less.
Return JSON with these keys:
  "sql": the SQLite query
  "explanation": one plain-English sentence on how the query answers the question
  "confidence": "high", "medium", or "low"
  "warning": any assumption or data issue the user should know about, or "" if none"""


# ---------- AI helper: switches models instead of waiting ----------
LAST_ERROR = {"msg": ""}


def call_ai(prompt, log):
    # Go through the model list twice. If a model fails, jump straight to the next one.
    for round_num in range(2):
        for model in MODELS:
            try:
                log(f"Asking {model}...")
                r = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                text = r.text.strip().replace("```json", "").replace("```", "")
                return json.loads(text)
            except Exception as e:
                LAST_ERROR["msg"] = f"{model}: {e}"
                busy = any(code in str(e) for code in ["503", "UNAVAILABLE", "429"])
                log(f"{model} is busy, trying another model..." if busy
                    else f"{model} failed, trying another model...")
        # Every model failed this round, so wait a little before one more try
        if round_num == 0:
            log("All models busy. Waiting 5 seconds...")
            time.sleep(5)
    return None


# ---------- Main logic ----------
@st.cache_resource
def get_saved_answers():
    # Shared by everyone using the app. Saves AI calls (and your free daily limit).
    return {}


def ask(question, log):
    saved = get_saved_answers()
    key = question.strip().lower()
    if key in saved:
        log("This question was asked before. Using the saved answer (no AI call needed).")
        plan = saved[key]
        return plan, pd.read_sql(plan["sql"], conn), []

    prompt = (
        f"You are a careful SQL expert. SQLite database:\n{schema}\n"
        f"Question: {question}\n{RULES}"
    )
    plan = call_ai(prompt, log)
    if plan is None:
        msg = LAST_ERROR["msg"]
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            return None, None, (
                "The app has used up its free AI limit for today. "
                "It resets at midnight Pacific time (3 AM Eastern). "
                "Questions that were already asked still work.\n\n"
                f"Models tried: {', '.join(MODELS)}"
            )
        return None, None, f"All AI models failed or were busy. Try again in a minute.\n\nModels tried: {', '.join(MODELS)}\n\nLast error: {msg}"

    fixes = []
    for _ in range(3):
        try:
            log("Running the SQL on the database...")
            result = pd.read_sql(plan["sql"], conn)
            saved[key] = plan  # save it so the same question is free next time
            return plan, result, fixes
        except Exception as e:
            fixes.append(f"`{plan['sql']}` failed: {e}")
            log("The SQL had an error. Asking the AI to fix it...")
            plan = call_ai(
                prompt + f"\n\nYour last query:\n{plan['sql']}\nfailed with:\n{e}\nFix it.",
                log,
            )
            if plan is None:
                break
    return None, None, "Couldn't get a working query. Try rewording your question."


def show_chart(result):
    # Draw a bar chart when there's one text column and one number column
    text_cols = result.select_dtypes(include="object").columns
    num_cols = result.select_dtypes(include="number").columns
    if len(result) > 1 and len(text_cols) >= 1 and len(num_cols) >= 1:
        label, value = text_cols[0], num_cols[0]
        chart = (
            alt.Chart(result)
            .mark_bar()
            .encode(
                x=alt.X(f"{value}:Q", title=value, axis=alt.Axis(format=",.0f")),
                # Biggest at the top, and show every name (don't hide any labels)
                y=alt.Y(f"{label}:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False)),
                tooltip=[label, alt.Tooltip(value, format=",.0f")],
            )
            .properties(height=max(200, 35 * len(result)))
        )
        st.altair_chart(chart, width="stretch")


# ---------- Page layout ----------
st.markdown(
    "**Try:** *Who are the 10 most valuable players from Spain?* · "
    "*Which clubs spent the most on transfers?* · "
    "*Which league has the most expensive players on average?*"
)

question = st.text_input("Your question")

if st.button("Ask", type="primary") and question:
    start = time.time()
    # Show live progress so the user knows what's happening while they wait
    with st.status("Working on it...", expanded=True) as status:
        plan, result, extra = ask(question, status.write)
        seconds = time.time() - start
        status.update(
            label=f"Done in {seconds:.1f} seconds" if plan else "Something went wrong",
            state="complete" if plan else "error",
            expanded=False,
        )

    if plan is None:
        st.error(extra)
    else:
        if extra:
            with st.expander("🔧 The AI fixed its own SQL"):
                for f in extra:
                    st.write(f)

        st.subheader("Answer")
        # Show big numbers with commas (1,372,795,000 instead of 1372795000)
        st.dataframe(
            result.style.format(precision=0, thousands=","),
            width="stretch",
        )
        show_chart(result)

        st.subheader("How it got this")
        st.write(plan["explanation"])
        conf = plan.get("confidence", "medium")
        badge = {"high": st.success, "medium": st.info, "low": st.warning}.get(conf, st.info)
        badge(f"Confidence: {conf}")
        if plan.get("warning"):
            st.warning(f"⚠️ {plan['warning']}")
        if result.empty:
            st.warning("⚠️ No rows came back. The names or filters may not match the data.")

        with st.expander("Show the SQL"):
            st.code(plan["sql"], language="sql")

st.divider()
st.caption(
    "Built by Fabian Caceres Torres · Data: Transfermarkt via Kaggle · "
    "AI answers can be wrong, so always check the numbers."
)
