# FinTech Buddy — Setup & Run

Short: FastAPI backend + simple HTML dashboard to upload transaction files and query an LLM (Groq).

## Requirements
- Python 3.10+ (Windows)
- Internet access for Groq API
- A Groq API key and a supported model name

## Install (PowerShell)
From project root (d:\AICW_01_1\Fin_Tech_Buddy_Analysis_Lora):
```powershell
python -m pip install --upgrade pip
pip install fastapi uvicorn python-dotenv pandas openpyxl groq requests
```

## .env (DO NOT COMMIT)
Create or edit `.env` in the project root. Remove any extraneous lines (no commands).
Example:
```
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```
Important:
- Rotate any API key that has been exposed.
- Add `.env` to `.gitignore`.

## Start server (PowerShell)
Temporarily set env vars in the current shell (recommended, avoids committing secrets):
```powershell
$Env:GROQ_API_KEY = "your_groq_api_key_here"
$Env:GROQ_MODEL   = "llama-3.3-70b-versatile"
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Then open: http://127.0.0.1:8000/ (HTML dashboard)

## Endpoints
- GET / -> Dashboard (upload file + ask questions)
- POST /upload/ -> Upload .csv/.xlsx/.xls (field name `file`)
- GET /query/?question=... -> Ask AI (requires a processed upload first)
- GET /_env -> Debug: shows loaded model and whether key is present (safe, does not return key)

Curl examples:
```bash
curl -F "file=@transactions.xlsx" http://127.0.0.1:8000/upload/
curl "http://127.0.0.1:8000/query/?question=How%20much%20did%20I%20spend%20on%20food"
curl http://127.0.0.1:8000/_env
```

## Where files are stored
- uploads/ — saved uploaded files
- transactions.pkl — persisted processed DataFrame (created after successful upload)

## Troubleshooting
- If FastAPI shows the old model or missing key: stop uvicorn, ensure `.env` updated, then restart the server.
- If you see 502 with LLM errors:
  - Check `/ _env` to verify model loaded.
  - Read server terminal logs for detailed tracebacks.
- If upload fails: ensure `openpyxl` is installed for `.xlsx` files.

## Security notes (short)
- DO NOT commit API keys. Rotate any exposed keys immediately.
- Use environment variables or a secrets manager in production.

If you want, I can also add:
- `requirements.txt`
- a git-safe `.env.example`
- unit tests for `process_transactions`

```// filepath: d:\AICW_01_1\Fin_Tech_Buddy_Analysis_Lora\README.md
# FinTech Buddy — Setup & Run

Short: FastAPI backend + simple HTML dashboard to upload transaction files and query an LLM (Groq).

## Requirements
- Python 3.10+ (Windows)
- Internet access for Groq API
- A Groq API key and a supported model name

## Install (PowerShell)
From project root (d:\AICW_01_1\Fin_Tech_Buddy_Analysis_Lora):
```powershell
python -m pip install --upgrade pip
pip install fastapi uvicorn python-dotenv pandas openpyxl groq requests
```

## .env (DO NOT COMMIT)
Create or edit `.env` in the project root. Remove any extraneous lines (no commands).
Example:
```
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```
Important:
- Rotate any API key that has been exposed.
- Add `.env` to `.gitignore`.

## Start server (PowerShell)
Temporarily set env vars in the current shell (recommended, avoids committing secrets):
```powershell
$Env:GROQ_API_KEY = "your_groq_api_key_here"
$Env:GROQ_MODEL   = "llama-3.3-70b-versatile"
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Then open: http://127.0.0.1:8000/ (HTML dashboard)

## Endpoints
- GET / -> Dashboard (upload file + ask questions)
- POST /upload/ -> Upload .csv/.xlsx/.xls (field name `file`)
- GET /query/?question=... -> Ask AI (requires a processed upload first)
- GET /_env -> Debug: shows loaded model and whether key is present (safe, does not return key)

Curl examples:
```bash
curl -F "file=@transactions.xlsx" http://127.0.0.1:8000/upload/
curl "http://127.0.0.1:8000/query/?question=How%20much%20did%20I%20spend%20on%20food"
curl http://127.0.0.1:8000/_env
```

## Where files are stored
- uploads/ — saved uploaded files
- transactions.pkl — persisted processed DataFrame (created after successful upload)

## Troubleshooting
- If FastAPI shows the old model or missing key: stop uvicorn, ensure `.env` updated, then restart the server.
- If you see 502 with LLM errors:
  - Check `/ _env` to verify model loaded.
  - Read server terminal logs for detailed tracebacks.
- If upload fails: ensure `openpyxl` is installed for `.xlsx` files.

## Security notes (short)
- DO NOT commit API keys. Rotate any exposed keys immediately.
- Use environment variables or a secrets manager in production.

If you want, I can also add:
- `requirements.txt`
- a git-safe `.env.example`
- unit tests for `process_transactions`
