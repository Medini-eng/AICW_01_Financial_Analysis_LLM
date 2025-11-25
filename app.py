import os
import logging
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from groq import Groq

# load .env explicitly from project folder
here = os.path.dirname(__file__)
env_path = os.path.join(here, ".env")
load_dotenv(dotenv_path=env_path, override=False)

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Allow frontend or localhost UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ---------------------------
# HELPERS
# ---------------------------
def categorize(desc: str) -> str:
    if desc is None:
        return "Others"
    desc = str(desc).lower()
    if "salary" in desc:
        return "Income"
    if "fuel" in desc or "diesel" in desc:
        return "Fuel"
    if "zomato" in desc or "swiggy" in desc or "restaurant" in desc:
        return "Food"
    if "amazon" in desc or "flipkart" in desc:
        return "Shopping"
    if "mutual fund" in desc or "sip" in desc:
        return "Investments"
    if "upi" in desc or "transfer" in desc or "google pay" in desc or "gpay" in desc:
        return "Transfers"
    return "Others"


def _detect_columns(df: pd.DataFrame):
    cols = [c.strip() for c in df.columns]
    cols_lower = [c.lower() for c in cols]

    # Description-like
    desc_candidates = [c for c in cols if c.lower() in ("description", "narration", "details", "remarks", "particulars")]
    if not desc_candidates:
        for i, c in enumerate(cols_lower):
            if "desc" in c or "narr" in c or "particular" in c:
                desc_candidates = [cols[i]]
                break

    # Amount-like
    amt_candidates = [c for c in cols if "amount" in c.lower() or c.lower() in ("amount", "amt", "value", "debit", "credit")]
    if not amt_candidates:
        for i, c in enumerate(cols_lower):
            if "amt" in c or "debit" in c or "credit" in c or "balance" in c:
                amt_candidates = [cols[i]]
                break

    # Date-like
    date_candidates = [c for c in cols if "date" in c.lower() or "txn date" in c.lower() or "transaction date" in c.lower()]

    return desc_candidates[0] if desc_candidates else None, amt_candidates[0] if amt_candidates else None, (date_candidates[0] if date_candidates else None)


# ---------------------------
# PROCESS TRANSACTION EXCEL
# ---------------------------
def process_transactions(file_path: str):
    try:
        if file_path.lower().endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path, engine="openpyxl")
    except Exception as e:
        raise ValueError(f"Failed to read file: {e}")

    if df.empty:
        raise ValueError("Uploaded file contains no data.")

    df.columns = df.columns.str.strip()
    desc_col, amt_col, date_col = _detect_columns(df)

    if not desc_col or not amt_col:
        raise ValueError(f"Could not detect required columns. Found columns: {list(df.columns)}. Need Description-like and Amount-like columns.")

    df["Description"] = df[desc_col].fillna("").astype(str)
    try:
        df["Amount"] = pd.to_numeric(df[amt_col], errors="coerce")
    except Exception:
        df["Amount"] = pd.to_numeric(df.get(amt_col, pd.Series([0]*len(df))), errors="coerce")

    debit_col = None
    credit_col = None
    for c in df.columns:
        cl = c.lower()
        if "debit" == cl:
            debit_col = c
        if "credit" == cl:
            credit_col = c
    if debit_col and credit_col:
        if df["Amount"].isna().all():
            df["Amount"] = pd.to_numeric(df[credit_col], errors="coerce").fillna(0) - pd.to_numeric(df[debit_col], errors="coerce").fillna(0)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)

    if date_col and date_col in df.columns:
        try:
            df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
        except Exception:
            df["Date"] = pd.to_datetime(df[date_col].astype(str), errors="coerce")
    else:
        for cand in ("Date", "date", "Txn Date", "Transaction Date"):
            if cand in df.columns:
                try:
                    df["Date"] = pd.to_datetime(df[cand], errors="coerce")
                    break
                except Exception:
                    continue

    if "Date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
        monthly_summary = {k: float(v) for k, v in df.groupby("Month")["Amount"].sum().to_dict().items()}
    else:
        df["Month"] = None
        monthly_summary = {}

    if "Category" not in df.columns:
        df["Category"] = df["Description"].apply(categorize)
    else:
        df["Category"] = df["Category"].fillna("").replace("", df["Description"].apply(categorize))

    category_summary = {k: float(v) for k, v in df.groupby("Category")["Amount"].sum().to_dict().items()}

    summary = {
        "total_income": float(df[df["Amount"] > 0]["Amount"].sum()),
        "total_expense": float(df[df["Amount"] < 0]["Amount"].sum()),
        "net_balance": float(df["Amount"].sum()),
        "monthly_summary": monthly_summary,
        "category_summary": category_summary,
        "rows": int(len(df))
    }

    return df, summary


# ---------------------------
# LLM QUERY ENGINE
# ---------------------------
def ask_ai(df: pd.DataFrame, user_question: str) -> str:
    if client is None or not GROQ_MODEL:
        raise RuntimeError(
            "Groq API key or model not configured. Set GROQ_API_KEY and GROQ_MODEL in your environment. "
            "See https://console.groq.com/docs/deprecations for supported models."
        )

    try:
        df_json = df.to_json(orient="records")
        if len(df_json) > 35000:
            df_json = df.tail(200).to_json(orient="records")
    except Exception:
        df_json = "[]"

    prompt = (
        "You are a Financial Spending Analysis AI.\n"
        "You are given a user's bank transaction history in JSON format:\n\n"
        f"{df_json}\n\n"
        f"The user asks: \"{user_question}\"\n\n"
        "Analyze the data carefully and return:\n"
        "- A clear answer to the question\n"
        "- Exact numbers if required\n"
        "- Additional insights & warnings\n"
        "- Spending optimization tips\n\n"
        "The answer must be simple and accurate."
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = None
        if hasattr(response, "choices") and response.choices:
            first = response.choices[0]
            if isinstance(first, dict):
                msg = first.get("message") or first.get("text") or first
                if isinstance(msg, dict):
                    content = msg.get("content") or msg.get("text")
                elif isinstance(msg, str):
                    content = msg
            else:
                msg = getattr(first, "message", None) or getattr(first, "text", None) or first
                if isinstance(msg, dict):
                    content = msg.get("content") or msg.get("text")
                else:
                    content = getattr(msg, "content", None) or getattr(msg, "text", None)
        if content:
            return content
        return str(response)
    except Exception as e:
        logging.exception("LLM request failed")
        msg = str(e)
        if "decommission" in msg.lower() or "model_decommissioned" in msg.lower():
            raise RuntimeError(
                "Configured Groq model appears decommissioned. Update GROQ_MODEL to a supported model (see https://console.groq.com/docs/deprecations). "
                f"Original error: {msg}"
            )
        raise RuntimeError(f"LLM request failed: {msg}")


# ---------------------------
# API ENDPOINTS
# ---------------------------
@app.post("/upload/")
async def upload_excel(file: UploadFile):
    filename = file.filename or "uploaded_file"
    if not any(filename.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload .xlsx, .xls, or .csv")

    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    try:
        df, summary = process_transactions(file_path)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logging.exception("Processing failed")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    try:
        df.to_pickle("transactions.pkl")
    except Exception:
        logging.exception("Could not save transactions.pkl")

    return {"message": "File uploaded & processed successfully!", "summary": summary}


@app.get("/query/")
async def query_financial(question: str):
    if client is None:
        raise HTTPException(status_code=503, detail="Groq API key not configured on server.")

    try:
        df = pd.read_pickle("transactions.pkl")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No processed transactions found. Upload first.")
    except Exception as e:
        logging.exception("Failed to load transactions.pkl")
        raise HTTPException(status_code=500, detail=f"Failed to load saved transactions: {e}")

    try:
        answer = ask_ai(df, question)
    except RuntimeError as re:
        raise HTTPException(status_code=502, detail=str(re))
    except Exception as e:
        logging.exception("ask_ai failed")
        raise HTTPException(status_code=500, detail=f"AI query failed: {e}")

    return {"question": question, "answer": answer}


# ---------------------------
# SIMPLE HTML DASHBOARD
# ---------------------------
DASH_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>FinTech Buddy</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body{font-family:Inter,Segoe UI,Arial;margin:24px;background:#f6f8fa;color:#111;}
    .card{background:#fff;padding:18px;border-radius:8px;box-shadow:0 6px 18px rgba(16,24,40,0.06);max-width:900px;margin:auto;}
    h1{margin:0 0 12px;font-size:20px}
    .row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
    input[type="file"]{padding:6px}
    button{background:#2563eb;color:#fff;border:0;padding:8px 12px;border-radius:6px;cursor:pointer}
    textarea{width:100%;height:110px;padding:8px;border-radius:6px;border:1px solid #e5e7eb}
    pre{background:#0f172a;color:#e6eef8;padding:12px;border-radius:6px;overflow:auto}
    .muted{color:#6b7280;font-size:13px}
  </style>
</head>
<body>
  <div class="card">
    <h1>FinTech Buddy</h1>
    <p class="muted">Upload your transaction file (CSV / XLSX) then ask questions.</p>

    <div>
      <label><strong>1) Upload transactions</strong></label>
      <div class="row">
        <input id="file" type="file" accept=".csv,.xlsx,.xls" />
        <button id="uploadBtn">Upload & Process</button>
        <div id="uploadStatus" class="muted"></div>
      </div>
      <pre id="uploadResult" style="display:none"></pre>
    </div>

    <hr/>

    <div>
      <label><strong>2) Ask a question</strong></label>
      <div class="row">
        <input id="question" type="text" style="flex:1;padding:8px;border-radius:6px;border:1px solid #e5e7eb" placeholder="How much did I spend on food?" />
        <button id="askBtn">Ask AI</button>
      </div>
      <div id="answerArea" style="margin-top:12px;display:none">
        <label class="muted">AI Answer:</label>
        <pre id="answerText"></pre>
      </div>
    </div>

    <hr/>

    <div class="muted">Debug endpoints: <code>/upload/</code> and <code>/query/?question=...</code></div>
  </div>

<script>
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('file');
const uploadStatus = document.getElementById('uploadStatus');
const uploadResult = document.getElementById('uploadResult');
const askBtn = document.getElementById('askBtn');
const questionInput = document.getElementById('question');
const answerArea = document.getElementById('answerArea');
const answerText = document.getElementById('answerText');

uploadBtn.addEventListener('click', async () => {
  const f = fileInput.files[0];
  if (!f) { uploadStatus.textContent = 'Select a file first.'; return; }
  uploadStatus.textContent = 'Uploading...';
  uploadResult.style.display = 'none';
  const form = new FormData();
  form.append('file', f, f.name);
  try {
    const res = await fetch('/upload/', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) {
      uploadStatus.textContent = 'Error: ' + (data.detail || JSON.stringify(data));
    } else {
      uploadStatus.textContent = 'Success';
      uploadResult.style.display = 'block';
      uploadResult.textContent = JSON.stringify(data.summary, null, 2);
    }
  } catch (e) {
    uploadStatus.textContent = 'Upload failed: ' + e;
  }
});

askBtn.addEventListener('click', async () => {
  const q = questionInput.value.trim();
  if (!q) { answerArea.style.display='block'; answerText.textContent = 'Enter a question.'; return; }
  answerArea.style.display='block';
  answerText.textContent = 'Querying...';
  try {
    const url = '/query/?' + new URLSearchParams({ question: q });
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) {
      answerText.textContent = 'Error: ' + (data.detail || JSON.stringify(data));
    } else {
      answerText.textContent = data.answer || JSON.stringify(data, null, 2);
    }
  } catch (e) {
    answerText.textContent = 'Query failed: ' + e;
  }
});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=DASH_HTML, status_code=200)


# ---------------------------
# STARTUP / DEBUG
# ---------------------------
@app.on_event("startup")
def _reload_env_and_log():
    here = os.path.dirname(__file__)
    env_path = os.path.join(here, ".env")
    load_dotenv(dotenv_path=env_path, override=True)

    global GROQ_API_KEY, GROQ_MODEL, client
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL")
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

    def _mask(s):
        if not s:
            return None
        return s[:4] + "..." + s[-4:] if len(s) > 8 else "****"

    logging.info(f"[startup] GROQ_MODEL={GROQ_MODEL}; GROQ_API_KEY_present={bool(GROQ_API_KEY)}; GROQ_API_KEY_masked={_mask(GROQ_API_KEY)}")

@app.get("/_env")
def _get_env():
    return {"groq_model": GROQ_MODEL, "groq_key_present": bool(GROQ_API_KEY)}
