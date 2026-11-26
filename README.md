# ⚽ Ask the Data

**Ask questions about soccer data in plain English. An AI writes the SQL, runs it, and shows its work so you can check the answer.**

<img width="994" height="700" alt="Screenshot 2026-11-25 at 10 09 29 PM" src="https://github.com/user-attachments/assets/b3f8ca12-7de2-4367-97ae-26d563dd96c9" />
<img width="1042" height="676" alt="Screenshot 2026-11-25 at 10 09 50 PM" src="https://github.com/user-attachments/assets/de04eab4-642e-496e-8703-df84de52643d" />

🔗 **Live app:** [ask-the-data.streamlit.app](https://ask-the-data-vswupsnmapp2ueh3xkybhfn.streamlit.app/)

---

## What it does

Type a question like *"Which clubs spent the most on transfers?"* and the app:

1. **Writes a SQL query** using Google's Gemini AI
2. **Runs it** on a SQLite database of Transfermarkt players, clubs, competitions, and transfers
3. **Shows the answer** as a table and a sorted bar chart
4. **Shows its work** so you can decide whether to trust it

## Why I built it this way: the AI checks itself

AI tools often give answers that *look* right but aren't. While testing, I asked *"How many players does Barcelona have?"* twice. The AI used two different methods, got two different answers, and said it was "high confidence" both times.

So I built in checks:

| Feature | What it does |
|---|---|
| **Shows the numbers** | Every answer includes the values used to rank or count, so you can verify them |
| **Explains itself** | A one-sentence, plain-English summary of how the query answers the question |
| **Confidence rating** | The AI rates itself high, medium, or low |
| **Warnings** | Flags assumptions and data gaps (for example, *"transfers with undisclosed fees are excluded"*) |
| **Shows the SQL** | The exact query is one click away |
| **Fixes its own mistakes** | If a query fails, the error goes back to the AI so it can fix it, up to 3 tries |

## Built to handle real-world problems

- **Model fallback:** If one AI model is busy or out of quota, the app switches to another one automatically.
- **Saved answers:** Repeat questions are answered instantly from saved results, with no AI call needed.
- **Live progress:** Shows each step while it works, plus how long the answer took.

## Try these questions

- Who are the 10 most valuable players from Spain?
- Which clubs spent the most on transfers?
- Which league has the most expensive players on average?
- Which 10 clubs have the most valuable squads?

## Tech stack

- **Python** with **pandas** for data handling
- **SQLite** for the database
- **Google Gemini API** to turn questions into SQL
- **Streamlit** for the web app, hosted on Streamlit Community Cloud
- **Altair** for charts

## Data

[Transfermarkt "player-scores" dataset](https://www.kaggle.com/datasets/davidcariboo/player-scores) from Kaggle. The app uses four tables: `players`, `clubs`, `transfers`, and `competitions`. The database is stored zipped (`soccer_small.db.gz`) to fit GitHub's file size limit and is unzipped when the app starts.

## Limitations

- **AI answers can be wrong.** That's why the app shows its work. Always check the numbers.
- **Free tier limits:** The free Gemini API allows a limited number of requests per day. If the limit is reached, new questions stop working until it resets (saved questions still work).
- **Data gaps:** Some transfer fees are missing or undisclosed, so spending totals may be lower than the real amounts.

## Run it yourself

```bash
git clone https://github.com/fabiancaceres15/ask-the-data.git
cd ask-the-data
pip install -r requirements.txt
```

Create a file at `.streamlit/secrets.toml` with your free API key from [Google AI Studio](https://aistudio.google.com):

```toml
GEMINI_API_KEY = "your-key-here"
```

Then run:

```bash
streamlit run app.py
```

---

**Built by Fabian Caceres Torres** · Information Science, UNC Chapel Hill
