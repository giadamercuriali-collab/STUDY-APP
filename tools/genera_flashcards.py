"""Genera 5-6 flashcard chiare (1 domanda -> 1 risposta secca) per ogni scheda in data/quizzes.json.

Salva in cache incrementale in materiali/cache/flashcards_parts/ e aggiorna data/quizzes.json.
"""
import json, os, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

ROOT_APP = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_APP / ".env")
FC_CACHE = ROOT_APP / "materiali" / "cache" / "flashcards_parts"
FC_CACHE.mkdir(parents=True, exist_ok=True)
QUIZZES_FILE = ROOT_APP / "data" / "quizzes.json"

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
                return json.loads(r.text)
            except Exception as e:
                last_err = e
                time.sleep(6 + round_idx * 8)
    raise RuntimeError(f"Gemini fallito: {last_err}")


def gen_for_card(subj_name: str, card: dict):
    cid = card["id"]
    out_file = FC_CACHE / f"{cid}.json"
    if out_file.exists():
        return cid, json.loads(out_file.read_text())

    if subj_name == "Legal English":
        prompt = f"""Sei un docente di Legal English (livello B2).
Crea 6 flashcard chiare e dirette per studiare l'argomento: "{card['topic']}".
Regole:
- Ogni flashcard deve testare UN SOLO termine, clausola o false friend (niente elenchi lunghi).
- "front": domanda breve (es. "What does 'consideration' mean in English contract law?" oppure "Come si dice in Legal English 'forza maggiore'?").
- "back": risposta secca e chiara in 1-3 righe (traduzione + significato/uso pratico).

CONTENUTO SCHEDA:
{json.dumps(card, ensure_ascii=False)[:8000]}

Rispondi SOLO in JSON:
{{"flashcards": [{{"front": "...", "back": "..."}}]}}"""
    else:
        prompt = f"""Sei un docente universitario di {subj_name}.
Crea 6 flashcard efficaci per studiare l'argomento: "{card['topic']}".
Regole fondamentali:
- Regola d'oro: 1 domanda chiara = 1 risposta secca (niente muri di testo o elenchi lunghi sul retro!).
- "front": una domanda precisa come all'esame orale (es. "Qual è la differenza tra norma dispositiva e norma imperativa?", "Quando si applica il criterio cronologico?", "Quali effetti produce l'annullamento rispetto all'abrogazione?").
- "back": risposta sintetica, chiara e completa in 2-3 righe (cita l'articolo o un micro-esempio se utile).

CONTENUTO SCHEDA:
{json.dumps(card, ensure_ascii=False)[:8000]}

Rispondi SOLO in JSON:
{{"flashcards": [{{"front": "...", "back": "..."}}]}}"""

    res = call_gemini(prompt)
    if isinstance(res, list):
        cards = res
    else:
        cards = res.get("flashcards", [])
    out_file.write_text(json.dumps(cards, ensure_ascii=False, indent=1))
    return cid, cards


def main():
    data = json.loads(QUIZZES_FILE.read_text())
    jobs = []
    for subj in data["subjects"]:
        for card in subj.get("summaries", []):
            jobs.append((subj["name"], card))

    print(f"Totale schede da elaborare: {len(jobs)}", flush=True)
    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(gen_for_card, s, c): (s, c["topic"]) for s, c in jobs}
        for fut in as_completed(futs):
            s, topic = futs[fut]
            done += 1
            try:
                cid, cards = fut.result()
                results[cid] = cards
                if done % 15 == 0 or done == len(jobs):
                    print(f"[{done}/{len(jobs)}] {s} -> {topic[:50]} ({len(cards)} fc)", flush=True)
            except Exception as e:
                print(f"[ERR {done}/{len(jobs)}] {topic}: {e}", flush=True)

    for subj in data["subjects"]:
        for card in subj.get("summaries", []):
            if card["id"] in results and results[card["id"]]:
                card["flashcards"] = results[card["id"]]

    QUIZZES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    total_fc = sum(len(c.get("flashcards", [])) for s in data["subjects"] for c in s.get("summaries", []))
    print(f"FATTO! Salvate {total_fc} flashcard in {QUIZZES_FILE}", flush=True)


if __name__ == "__main__":
    main()
