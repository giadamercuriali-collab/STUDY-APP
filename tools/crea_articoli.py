"""Estrae tutti gli articoli citati in data/quizzes.json e genera data/articles.json per la consultazione offline.

Uso: python3 tools/crea_articoli.py
"""
import json, os, re, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

ROOT_APP = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_APP / ".env")
QUIZZES_FILE = ROOT_APP / "data" / "quizzes.json"
ARTICLES_FILE = ROOT_APP / "data" / "articles.json"

MODELS_FALLBACK = [
    os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
]

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=60000),
)


def call_gemini(prompt: str):
    cfg = types.GenerateContentConfig(response_mime_type="application/json")
    last_err = None
    for round_idx in range(3):
        for modello in MODELS_FALLBACK:
            try:
                r = client.models.generate_content(model=modello, contents=prompt, config=cfg)
                if r.text:
                    return json.loads(r.text)
            except Exception as e:
                last_err = e
                time.sleep(6 + round_idx * 8)
    raise RuntimeError(f"Gemini fallito: {last_err}")


def collect_articles():
    data = json.loads(QUIZZES_FILE.read_text())
    found = set()
    for subj in data["subjects"]:
        hint = "cost" if subj["id"] == "costituzionale" else "cc"
        blob = json.dumps(subj, ensure_ascii=False)
        for m in re.finditer(
            r"\bartt?\.?\s+\d+(?:\s*(?:bis|ter|quater|quinquies|sexies))?(?:\s*(?:,|e)\s*\d+(?:\s*(?:bis|ter|quater))?)*\s*(?:c\.c\.|Cost\.|c\.p\.c\.|c\.p\.|disp\.?\s*prel\.?)?",
            blob,
            re.I,
        ):
            raw = m.group(0)
            low = raw.lower()
            if "cost" in low:
                code = "cost"
            elif "c.c" in low or "cod. civ" in low:
                code = "cc"
            elif "c.p.c" in low:
                code = "cpc"
            elif "c.p." in low:
                code = "cp"
            else:
                code = hint
            for n in re.findall(r"\d+(?:\s*(?:bis|ter|quater|quinquies|sexies))?", raw, re.I):
                found.add((code, re.sub(r"\s+", " ", n.lower().strip())))
    return sorted(found)


def fetch_batch(batch):
    items_str = ", ".join(f"{c}:{n}" for c, n in batch)
    prompt = f"""Fornisci la rubrica e il testo (fedele o sintesi normativa accurata comma per comma, in italiano) dei seguenti articoli del Codice Civile (cc), della Costituzione Italiana (cost), Codice di Procedura Civile (cpc) o Codice Penale (cp):
{items_str}

Rispondi SOLO in JSON con oggetto:
{{
  "articles": {{
    "cc:1321": {{"code": "Codice Civile", "num": "1321", "title": "Nozione", "text": "Il contratto è l'accordo di due o più parti per costituire, regolare o estinguere tra loro un rapporto giuridico patrimoniale."}}
  }}
}}"""
    res = call_gemini(prompt)
    return res.get("articles", {}) if isinstance(res, dict) else {}


def main():
    existing = json.loads(ARTICLES_FILE.read_text()) if ARTICLES_FILE.exists() else {}
    all_keys = collect_articles()
    missing = [(c, n) for c, n in all_keys if f"{c}:{n}" not in existing]
    print(f"Articoli citati: {len(all_keys)} | Mancanti: {len(missing)}", flush=True)
    batch_size = 12
    batches = [missing[i : i + batch_size] for i in range(0, len(missing), batch_size)]

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(fetch_batch, b): i for i, b in enumerate(batches, 1)}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                arts = fut.result()
                existing.update(arts)
                print(f"[{idx}/{len(batches)}] Aggiunti {len(arts)} articoli (totale {len(existing)})", flush=True)
            except Exception as e:
                print(f"[ERR batch {idx}] {e}", flush=True)

    ARTICLES_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=1))
    print(f"FATTO! Salvato {ARTICLES_FILE} con {len(existing)} articoli.", flush=True)


if __name__ == "__main__":
    main()

