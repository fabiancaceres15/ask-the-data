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
def get_model(_client):
    # If you set MODEL in Secrets, use that exact model
    if "MODEL" in st.secrets:
        return st.secrets["MODEL"]
    # Otherwise prefer a "lite" model because it's usually less busy
    names = [m.name.replace("models/", "") for m in _client.models.list()]
    lite = [n for n in names if "flash-lite" in n]
    return lite[0] if lite else "gemini-3.8-flash"


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
MODEL = get_model(client)
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


# ---------- AI helper with retries ----------
LAST_ERROR = {"msg": ""}


def call_ai(prompt):
    for attempt in range(5):
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            text = r.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception as e:
            LAST_ERROR["msg"] = str(e)
            # Only wait and retry if the server is busy; other errors won't fix themselves
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e):
                time.sleep(5 * (attempt + 1))
            elif isinstance(e, json.JSONDecodeError):
                continue
            else:
                break
    return None


# ---------- Main logic ----------
def ask(question):
    prompt = (
        f"You are a careful SQL expert. SQLite database:\n{schema}\n"
        f"Question: {question}\n{RULES}"
    )
    plan = call_ai(prompt)
    if plan is None:
        return None, None, f"The AI call failed (model: {MODEL}).\n\nError: {LAST_ERROR['msg']}"

    fixes = []
    for _ in range(3):
        try:
            result = pd.read_sql(plan["sql"], conn)
            return plan, result, fixes
        except Exception as e:
            fixes.append(f"`{plan['sql']}` failed: {e}")
            plan = call_ai(
                prompt + f"\n\nYour last query:\n{plan['sql']}\nfailed with:\n{e}\nFix it."
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
                y=alt.Y(f"{label}:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False)),
                tooltip=[label, alt.Tooltip(value, format=",.0f")],
            )
            .properties(height=max(200, 35 * len(result)))
        )
        st.altair_chart(chart, use_container_width=True)


# ---------- Page layout ----------
st.markdown(
    "**Try:** *Who are the 10 most valuable players from Spain?* · "
    "*Which clubs spent the most on transfers?* · "
    "*Which league has the most expensive players on average?*"
)

question = st.text_input("Your question")

if st.button("Ask", type="primary") and question:
    with st.spinner("Thinking..."):
        plan, result, extra = ask(question)

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
            use_container_width=True,
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
