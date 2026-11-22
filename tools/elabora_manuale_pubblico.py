"""Elabora il manuale 'Corso di diritto pubblico' (Barbera, Fusaro, Caruso)
escludendo esattamente i paragrafi indicati dalla docente di Diritto Costituzionale,
e genera quiz, schede+diagrammi e flashcard per ogni capitolo.

Uso: python3 tools/elabora_manuale_pubblico.py
"""
import hashlib, json, os, re, time, warnings
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

ROOT_APP = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_APP / ".env")
MANUAL_JSON = ROOT_APP / "materiali" / "cache" / "pdfs" / "Corso_di_diritto_pubblico_52af6219e6.json"
OUT_CACHE = ROOT_APP / "materiali" / "cache" / "manuale_pubblico"
OUT_CACHE.mkdir(parents=True, exist_ok=True)
QUIZZES_FILE = ROOT_APP / "data" / "quizzes.json"

MODELS_FALLBACK = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
    os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
    "gemini-3-flash-preview",
]

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=60000),
)

# Esclusioni esatte indicate dalla prof.ssa Caterina Domenicali
CHAPTERS = [
    ("I", "Cap. I — L'ordinamento giuridico e il diritto pubblico", []),
    ("II", "Cap. II — Lo Stato", ["2"]),
    ("III", "Cap. III — La Costituzione", ["2", "3", "7"]),
    ("IV", "Cap. IV — L'ordinamento internazionale", ["5", "6", "7"]),
    ("V", "Cap. V — L'ordinamento dell'Unione europea", ["2", "3", "7"]),
    ("VI", "Cap. VI — Le fonti del diritto", ["15", "16"]),
    ("VII", "Cap. VII — La tutela della persona e i diritti fondamentali", ["6"]),
    ("VIII", "Cap. VIII — Il catalogo dei diritti", ["2.2", "2.3", "2.6", "4", "5.1", "5.3"]),
    ("IX", "Cap. IX — I doveri costituzionali", ["2", "4"]),
    ("X", "Cap. X — La sovranità popolare e il diritto di voto", ["5", "6", "7", "8", "9", "10.3", "10.4", "11"]),
    ("XI", "Cap. XI — Il Parlamento", []),
    ("XII", "Cap. XII — Il Presidente della Repubblica", []),
    ("XIII", "Cap. XIII — Il Governo della Repubblica", []),
    ("XIV", "Cap. XIV — I governi regionali e locali", ["1", "2", "3", "6.2", "6.3", "6.4", "10", "11", "12"]),
    ("XV", "Cap. XV — Le pubbliche amministrazioni", ["6"]),
    ("XVI", "Cap. XVI — Il sistema giudiziario", ["8"]),
    ("XVII", "Cap. XVII — La giustizia costituzionale", ["11", "12"]),
    ("XVIII", "Cap. XVIII — L'ordinamento italiano e la sua evoluzione (lettura)", []),
]


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
                time.sleep(8 + round_idx * 10)
    raise RuntimeError(f"Gemini fallito: {last_err}")


def split_pages_by_chapter(full_text: str):
    """Divide le pagine dopo l'indice per capitolo usando i tag [ROMAN, ...] o la progressione."""
    pages = re.split(r"(?=\[Pag\. \d+\])", full_text)
    roman_order = [c[0] for c in CHAPTERS]
    roman_idx = {r: i for i, r in enumerate(roman_order)}
    by_chap = {r: [] for r in roman_order}
    cur_idx = 0

    for pg in pages:
        m_num = re.match(r"\[Pag\. (\d+)\]", pg)
        if not m_num or int(m_num.group(1)) < 8:
            continue
        # Cerca intestazione capitolo nei primi 250 char della pagina
        head = pg[:250]
        m_ch = re.search(r"[\[\(\{]\s*(XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)\s*[,\s\d\.\]\)\}]", head)
        if m_ch and m_ch.group(1) in roman_idx:
            cand = roman_idx[m_ch.group(1)]
            if cur_idx <= cand <= cur_idx + 2:
                cur_idx = cand
        by_chap[roman_order[cur_idx]].append(pg)
    return {r: "\n".join(ps) for r, ps in by_chap.items()}


def filter_excluded_paragraphs(text: str, excluded: list) -> str:
    if not excluded:
        return text
    # Rimuove le sezioni che iniziano con "\n<par>. <TITOLO MAIUSCOLO>" fino al paragrafo successivo
    excl_set = set(excluded)
    # Match paragraph headings like "\n2. L'EVOLUZIONE..." or "\n2.2. LA LIBERTÀ..."
    pat = re.compile(r"\n(\d+(?:\.\d+)?)\.\s+([A-ZÀÈÉÌÒÙ][A-ZÀÈÉÌÒÙ0-9\s,'’\-:]{4,})")
    matches = list(pat.finditer(text))
    if not matches:
        return text
    out = []
    pos = 0
    for i, m in enumerate(matches):
        par = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if start > pos:
            out.append(text[pos:start])
        if par not in excl_set:
            out.append(text[start:end])
        pos = end
    return "".join(out)


def process_chapter(idx: int, roman: str, title: str, excluded: list, text: str, prof_examples_hint: str):
    out_file = OUT_CACHE / f"cap_{idx:02d}_{roman}.json"
    if out_file.exists():
        return json.loads(out_file.read_text())

    clean_text = filter_excluded_paragraphs(text, excluded)
    if len(clean_text.strip()) < 200:
        return None

    is_last = roman == "XVIII"
    num_q = 4 if is_last else 7
    excl_note = f" (esclusi i paragrafi: {', '.join(excluded)})" if excluded else ""
    print(f"[MANUALE] {title}{excl_note} | {len(clean_text)} char", flush=True)

    prompt = f"""Sei un docente universitario di Diritto Costituzionale (Unibo, Corso GIPA).
Dal seguente capitolo del manuale "Barbera - Fusaro - Caruso, Corso di diritto pubblico"{excl_note}: "{title}"
genera materiale di studio completo e fedele al testo e alla Costituzione italiana:
1. {num_q} domande a risposta multipla ("questions") con 4 opzioni (1 sola corretta), citando gli articoli della Costituzione o le fonti pertinenti nella spiegazione ("explanation") e collegando se pertinente uno degli esempi della prof.ssa Domenicali ("prof_example").
2. Una scheda riassuntiva ("summary") con:
   - "key_points": 5-6 punti sintetici e chiari,
   - "schema": 2-4 macro-nodi ad albero con sotto-punti,
   - "norme": articoli della Costituzione / leggi principali citati (es. "Art. 1 Cost.", "Art. 138 Cost."),
   - "prof_tip": eventuale collegamento/esempio della prof, altrimenti "".
3. 6 flashcard ("flashcards") in formato 1 domanda chiara -> 1 risposta secca (2-3 righe max).

ESEMPI DELLA PROF.SSA DOMENICALI DISPONIBILI:
{prof_examples_hint}

TESTO DEL CAPITOLO:
{clean_text[:38000]}

Rispondi SOLO in JSON:
{{
  "questions": [
    {{
      "topic": "{title}",
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "correct": 0,
      "explanation": "...",
      "prof_example": "",
      "source_type": "ai_generated",
      "source_detail": "Corso di diritto pubblico — {title}"
    }}
  ],
  "summary": {{
    "topic": "{title}",
    "key_points": ["..."],
    "schema": [{{"nodo": "...", "figli": ["..."]}}],
    "norme": ["Art. ... Cost."],
    "prof_tip": "",
    "source": "Corso di diritto pubblico — {title}"
  }},
  "flashcards": [
    {{"front": "...", "back": "..."}}
  ]
}}"""
    res = call_gemini(prompt)
    if isinstance(res, list):
        res = res[0] if res else {}
    out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def main():
    if not MANUAL_JSON.exists():
        print("Manuale non trovato in cache.")
        return
    manual_data = json.loads(MANUAL_JSON.read_text())
    by_chap = split_pages_by_chapter(manual_data["text"])

    quizzes_data = json.loads(QUIZZES_FILE.read_text())
    cost_subj = next(s for s in quizzes_data["subjects"] if s["id"] == "costituzionale")
    ex_hint = "\n".join(
        f"- [{e.get('topic','')}] {e.get('text','')}" for e in (cost_subj.get("examples") or [])[:15]
    ) or "Nessuno"

    # Rimuove eventuali vecchi elementi del manuale prima di reinserire quelli aggiornati
    cost_subj["questions"] = [q for q in cost_subj["questions"] if "Corso di diritto pubblico" not in q.get("source_detail", "")]
    cost_subj["summaries"] = [c for c in cost_subj["summaries"] if "Corso di diritto pubblico" not in c.get("source", "")]

    added_q, added_s, added_fc = 0, 0, 0
    for idx, (roman, title, excluded) in enumerate(CHAPTERS, 1):
        txt = by_chap.get(roman, "")
        try:
            res = process_chapter(idx, roman, title, excluded, txt, ex_hint)
        except Exception as e:
            print(f"[ERR {roman}] {e}", flush=True)
            continue
        if not res:
            continue
        sort_key = f"0500-00-{idx:02d}"
        date_label = f"Manuale · Cap. {roman}"
        for q in res.get("questions", []):
            q["id"] = f"costituzionale_{hashlib.md5(q['question'].encode()).hexdigest()[:10]}"
            q["sort_key"] = sort_key
            q["date_label"] = date_label
            cost_subj["questions"].append(q)
            added_q += 1
        sm = res.get("summary")
        if sm:
            sm["id"] = f"sum_man_{idx:02d}_{roman}"
            sm["sort_key"] = sort_key
            sm["date_label"] = date_label
            sm["flashcards"] = res.get("flashcards", [])
            cost_subj["summaries"].append(sm)
            added_s += 1
            added_fc += len(sm["flashcards"])
        time.sleep(1.5)

    cost_subj["questions"].sort(key=lambda q: (q.get("sort_key", "9999"), q.get("topic", "")))
    cost_subj["summaries"].sort(key=lambda c: (c.get("sort_key", "9999"), c.get("topic", "")))

    QUIZZES_FILE.write_text(json.dumps(quizzes_data, ensure_ascii=False, indent=1))
    print(f"FATTO! Aggiunte al manuale: {added_q} domande, {added_s} schede, {added_fc} flashcard.", flush=True)


if __name__ == "__main__":
    main()

