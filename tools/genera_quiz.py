"""Genera data/quizzes.json dai materiali estratti in materiali/cache/.

- Preserva fedelmente le domande dei test di autovalutazione del professore,
  determinando la risposta esatta, spiegando la norma e collegando eventuali
  esempi fatti a lezione.
- Genera quiz aggiuntivi da lezioni PDF, appunti e registrazioni audio,
  integrando gli esempi e gli interventi dei professori nelle spiegazioni.

Uso:
  python3 tools/genera_quiz.py
"""
import hashlib, json, os, re, time, warnings
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

ROOT_APP = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_APP / ".env")
CACHE_DIR = ROOT_APP / "materiali" / "cache"
QUIZ_CACHE = CACHE_DIR / "quizzes_parts"
QUIZ_CACHE.mkdir(parents=True, exist_ok=True)
SUM_CACHE = CACHE_DIR / "summaries_parts"
SUM_CACHE.mkdir(parents=True, exist_ok=True)
OUT_FILE = ROOT_APP / "data" / "quizzes.json"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

MODEL_PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
MODELS_FALLBACK = [
    MODEL_PRIMARY,
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
]

SUBJECT_META = {
    "Diritto Privato": {"id": "privato", "prof": "Prof. Nicolò Cevolani"},
    "Diritto Costituzionale": {"id": "costituzionale", "prof": "Prof.ssa Caterina Domenicali"},
    "Legal English": {"id": "legal-english", "prof": "Prof. Alessandro Russo"},
}

client = None


def get_client():
    global client
    if client is None:
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=60000),
        )
    return client


def call_gemini(prompt: str):
    cfg = types.GenerateContentConfig(response_mime_type="application/json")
    last_err = None
    for round_idx in range(3):
        for modello in MODELS_FALLBACK:
            try:
                r = get_client().models.generate_content(model=modello, contents=prompt, config=cfg)
                return json.loads(r.text)
            except Exception as e:
                last_err = e
                time.sleep(10 + round_idx * 10)
    raise RuntimeError(f"Gemini fallito: {last_err}")


def qid(subject_id: str, text: str) -> str:
    return f"{subject_id}_{hashlib.md5(text.encode()).hexdigest()[:10]}"


def load_examples_by_subject():
    by_subj = {s: [] for s in SUBJECT_META}
    audio_dir = CACHE_DIR / "audio"
    if audio_dir.exists():
        for f in sorted(audio_dir.glob("*.json")):
            d = json.loads(f.read_text())
            s = d.get("subject")
            if s in by_subj:
                for ex in d.get("prof_examples", []):
                    by_subj[s].append({
                        "topic": ex.get("concept") or ex.get("title") or "Esempio a lezione",
                        "text": f"{ex.get('title', '')}: {ex.get('text', '')}".strip(": "),
                        "source": ex.get("source") or d.get("filename", ""),
                    })
    app_dir = CACHE_DIR / "appunti"
    if app_dir.exists():
        for f in sorted(app_dir.glob("*.json")):
            d = json.loads(f.read_text())
            s = d.get("subject")
            if s in by_subj:
                for ex in d.get("examples", []):
                    by_subj[s].append({
                        "topic": d.get("topic", "Appunti"),
                        "text": ex,
                        "source": ", ".join(d.get("files", [])),
                    })
    return by_subj


def format_examples_hint(examples, limit=12):
    if not examples:
        return "Nessun esempio audio ancora disponibile."
    lines = []
    for e in examples[:limit]:
        t = e.get("topic") or e.get("concept") or e.get("title") or "Esempio"
        txt = e.get("text", "")
        src = e.get("source", "")
        lines.append(f"- [{t}] {txt} (Fonte: {src})")
    return "\n".join(lines)


def generate_from_prof_test(pdf_data, examples):
    out_file = QUIZ_CACHE / f"proftest_{hashlib.md5(pdf_data['filename'].encode()).hexdigest()[:10]}.json"
    if out_file.exists():
        return json.loads(out_file.read_text())
    print(f"[QUIZ-TEST-PROF] {pdf_data['filename']}", flush=True)
    prompt = f"""Analizza questo test di autovalutazione del professore di {pdf_data['subject']} ({pdf_data['filename']}).
Estrai TUTTI i quesiti a risposta multipla esattamente come formulati nel testo, individuando la risposta esatta secondo il diritto vigente.
Per ogni quesito:
- Scrivi una spiegazione giuridica chiara (citando gli articoli di legge pertinenti se applicabile).
- Se tra gli esempi del professore qui sotto ce n'è uno pertinente all'argomento, riportalo nel campo "prof_example" per aiutare a ricordare il concetto; altrimenti lascia "".

ESEMPI DALLE LEZIONI DISPONIBILI:
{format_examples_hint(examples, 20)}

TESTO DEL TEST:
{pdf_data['text'][:45000]}

Rispondi SOLO in JSON:
{{
  "questions": [
    {{
      "topic": "Titolo lezione / argomento",
      "question": "Testo della domanda",
      "options": ["opzione a", "opzione b", "opzione c", "opzione d"],
      "correct": 0,
      "explanation": "Spiegazione chiara del perché è corretta e perché le altre sono errate.",
      "prof_example": "",
      "source_type": "prof_test",
      "source_detail": "{pdf_data['filename']}"
    }}
  ]
}}"""
    res = call_gemini(prompt)
    out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def generate_from_lesson_text(subj, title, text, source_detail, examples, num_q=8):
    key = hashlib.md5(f"{subj}:{source_detail}:{title}".encode()).hexdigest()[:12]
    out_file = QUIZ_CACHE / f"lesson_{key}.json"
    if out_file.exists():
        return json.loads(out_file.read_text())
    print(f"[QUIZ-LEZIONE] {subj} -> {source_detail}", flush=True)
    if subj == "Legal English":
        prompt = f"""Sei un docente universitario di Legal English (livello B2, Giurisprudenza Unibo).
L'obiettivo dello studente è IMPARARE L'INGLESE GIURIDICO, la terminologia tecnica inglese, le espressioni contrattuali/processuali e i "false friends" rispetto all'italiano.
Dai seguenti appunti/trascrizione della lezione crea {num_q} domande a risposta multipla (4 opzioni, una sola corretta).
Regole fondamentali:
- Scrivi le DOMANDE e le 4 OPZIONI in INGLESE (es. significato di un termine giuridico inglese, completamento di una clausola contrattuale, traduzione corretta EN↔IT, riconoscimento di false friends come 'eventually', 'jurisprudence', 'instance', 'execute', 'consideration', ecc.).
- Scrivi "explanation" in ITALIANO (spiegando il significato esatto del termine/espressione inglese, l'uso nei contratti o nel Common Law e perché le altre opzioni sono errate).
- Nel campo "prof_example" riporta l'esempio, la frase o la precisazione fatta dal professore a lezione (se presente nella lista o nel testo).

ESEMPI E INTERVENTI DEL PROFESSORE:
{format_examples_hint(examples, 15)}

MATERIALE ({source_detail}):
{text[:35000]}

Rispondi SOLO in JSON:
{{
  "questions": [
    {{
      "topic": "{title}",
      "question": "English question...",
      "options": ["option A", "option B", "option C", "option D"],
      "correct": 0,
      "explanation": "Spiegazione in italiano del termine/uso inglese...",
      "prof_example": "esempio o frase del prof collegata se pertinente, altrimenti stringa vuota",
      "source_type": "ai_generated",
      "source_detail": "{source_detail}"
    }}
  ]
}}"""
    else:
        prompt = f"""Sei un docente universitario di {subj}. Dai seguenti materiali di studio crea {num_q} domande a risposta multipla (4 opzioni, una sola corretta) utili per preparare l'esame.
Regole importanti:
- Domande chiare, precise, non banali (includi anche piccoli casi pratici stile esame).
- Ogni spiegazione deve chiarire il concetto giuridico/tecnico.
- Quando pertinenti, integra e cita nel campo "prof_example" gli esempi pratici o gli interventi fatti dal professore a lezione (vedi lista sotto).

ESEMPI E INTERVENTI DEL PROFESSORE:
{format_examples_hint(examples, 15)}

MATERIALE ({source_detail}):
{text[:35000]}

Rispondi SOLO in JSON:
{{
  "questions": [
    {{
      "topic": "{title}",
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "correct": 0,
      "explanation": "...",
      "prof_example": "esempio pratico collegato se pertinente, altrimenti stringa vuota",
      "source_type": "ai_generated",
      "source_detail": "{source_detail}"
    }}
  ]
}}"""
    res = call_gemini(prompt)
    out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


MONTHS_IT = {
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
}
REG_ROOT = Path("/Users/giada/Library/Mobile Documents/com~apple~CloudDocs/Università/Registrazioni")


def extract_date_meta(source: str, is_lesson_pdf: bool = False):
    """Ricava data cronologica e etichetta leggibile da nome file o metadati."""
    s = source.split("#")[0]
    # 1. Formato YYYY-MM-DD nel nome (es. PHOTO-2026-10-18, AUDIO-2026-10-29)
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        return f"{y:04d}-{mo:02d}-{d:02d}", f"{d} {MONTHS_IT.get(mo, mo)} {y}"
    # 2. Formato DDMM o DMM (es. 1611, 2109, 2409, 411, 211)
    m = re.match(r"^(?:LE\s+|DC\s+)?(\d{1,2})(\d{2})(?:\D|$)", s, re.I) or re.search(r"\b(\d{2})(09|10|11|12)\b", s)
    if m:
        d, mo = int(m[1]), int(m[2])
        if 1 <= d <= 31 and mo in (9, 10, 11, 12):
            return f"2026-{mo:02d}-{d:02d}", f"{d} {MONTHS_IT[mo]} 2026"
    # 3. Lezione numerata (es. "1. Argomenti...", "18. La responsabilità...")
    m = re.match(r"^(\d{1,2})\.\s", s)
    if m and is_lesson_pdf:
        n = int(m[1])
        return f"1000-00-{n:02d}", f"Lezione {n}"
    # 4. Data di creazione del file originale in Registrazioni/
    orig = REG_ROOT / s
    if orig.exists():
        import datetime
        dt = datetime.datetime.fromtimestamp(orig.stat().st_birthtime)
        if dt.year >= 2026:
            return dt.strftime("%Y-%m-%d"), f"{dt.day} {MONTHS_IT.get(dt.month, dt.month)} {dt.year}"
    return "9999-99-99", "Materiali e Dispense"


def generate_summary_card(subj, title, text, source_detail, examples):
    key = hashlib.md5(f"sum:{subj}:{source_detail}:{title}".encode()).hexdigest()[:12]
    out_file = SUM_CACHE / f"sum_{key}.json"
    if out_file.exists():
        return json.loads(out_file.read_text())
    print(f"[SCHEDA] {subj} -> {title}", flush=True)
    if subj == "Legal English":
        prompt = f"""Crea una scheda di studio di LEGAL ENGLISH (livello B2) focalizzata su TERMINOLOGIA INGLESE, ESPRESSIONI GIURIDICHE e TRADUZIONE per l'argomento: "{title}".
Regole:
- "topic": titolo bilingue sintetico (Inglese + Italiano).
- "key_points": 5-7 voci in formato glossario/regola d'uso, es. '"Consideration" → controprestazione / corrispettivo (elemento essenziale del contratto nel Common Law)'. Includi eventuali False Friends.
- "schema": 2-4 macro-gruppi (es. "1. Key Legal Terms", "2. Contract Clauses & Collocations", "3. False Friends / Pitfalls") ciascuno con 2-5 sotto-voci brevi "Termine inglese = significato".
- "norme": 3-6 espressioni o parole chiave inglesi fondamentali da memorizzare.
- "prof_tip": eventuale esempio o precisazione linguistica fatta dal professore a lezione, altrimenti "".

ESEMPI DEL PROFESSORE:
{format_examples_hint(examples, 10)}

MATERIALE ({source_detail}):
{text[:30000]}

Rispondi SOLO in JSON:
{{
  "topic": "{title}",
  "key_points": ["..."],
  "schema": [
    {{
      "nodo": "1. Key Terminology",
      "figli": ["term = significato", "..."]
    }}
  ],
  "norme": ["English phrase 1", "English term 2"],
  "prof_tip": "",
  "source": "{source_detail}"
}}"""
    else:
        prompt = f"""Crea una scheda riassuntiva sintetica con SCHEMA GERARCHICO per studiare rapidamente l'argomento di {subj}: "{title}".
Regole:
- Massimo 5-6 punti chiave sintetici, dritti al punto (definizioni, regole, eccezioni).
- Crea uno "schema" visivo ad albero (2-4 macro-nodi principali, ciascuno con 2-5 sotto-punti sintetici con parole chiave, distinzioni ed esiti).
- Elenca gli articoli di legge o fonti principali in "norme" (se presenti, altrimenti []).
- Se tra gli esempi del professore qui sotto ce n'è uno utile per capire l'argomento, sintetizzalo in "prof_tip", altrimenti "".

ESEMPI DEL PROFESSORE:
{format_examples_hint(examples, 10)}

MATERIALE ({source_detail}):
{text[:30000]}

Rispondi SOLO in JSON:
{{
  "topic": "{title}",
  "key_points": ["punto 1", "punto 2"],
  "schema": [
    {{
      "nodo": "1. Concetto principale",
      "figli": ["sotto-punto A", "sotto-punto B"]
    }}
  ],
  "norme": ["Art. ..."],
  "prof_tip": "",
  "source": "{source_detail}"
}}"""
    res = call_gemini(prompt)
    if isinstance(res, list):
        res = res[0] if res else {}
    res["id"] = f"sum_{key}"
    sk, dl = extract_date_meta(source_detail, is_lesson_pdf=bool(re.match(r"^\d{1,2}\.\s", source_detail)))
    res["sort_key"] = sk
    res["date_label"] = dl
    out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def build_all():
    examples_by_subj = load_examples_by_subject()
    subjects_out = {
        s: {"id": meta["id"], "name": s, "prof": meta["prof"], "questions": [], "examples": examples_by_subj[s], "summaries": []}
        for s, meta in SUBJECT_META.items()
    }

    # 1. PDF (prima i test di autovalutazione del prof, poi le lezioni/slide, saltando manuali > 150k char qui o prendendo solo i primi capitoli se necessario)
    pdf_dir = CACHE_DIR / "pdfs"
    if pdf_dir.exists():
        for f in sorted(pdf_dir.glob("*.json")):
            d = json.loads(f.read_text())
            s = d.get("subject")
            if s not in subjects_out or not d.get("text"):
                continue
            if "programma" in d.get("filename", "").lower():
                continue
            if d.get("is_prof_test"):
                res = generate_from_prof_test(d, examples_by_subj[s])
            elif d.get("chars", 0) <= 120000:
                topic = Path(d["filename"]).stem
                res = generate_from_lesson_text(s, topic, d["text"], d["filename"], examples_by_subj[s], num_q=6)
                subjects_out[s]["summaries"].append(generate_summary_card(s, topic, d["text"], d["filename"], examples_by_subj[s]))
            elif s == "Legal English":
                txt = d["text"]
                step = 32000
                for idx, start in enumerate(range(0, len(txt), step), 1):
                    part_txt = txt[start : start + step]
                    topic = f"{Path(d['filename']).stem} (Parte {idx})"
                    res_p = generate_from_lesson_text(s, topic, part_txt, f"{d['filename']}#p{idx}", examples_by_subj[s], num_q=6)
                    subjects_out[s]["summaries"].append(generate_summary_card(s, topic, part_txt, f"{d['filename']}#p{idx}", examples_by_subj[s]))
                    q_list_p = res_p if isinstance(res_p, list) else res_p.get("questions", [])
                    for q in q_list_p:
                        q["id"] = qid(subjects_out[s]["id"], q["question"])
                        subjects_out[s]["questions"].append(q)
                    time.sleep(1.5)
                continue
            else:
                # Manuali lunghi: salta per non saturare la quota gratuita (le lezioni + test + registrazioni sono già complete)
                continue
            q_list = res if isinstance(res, list) else res.get("questions", [])
            for q in q_list:
                q["id"] = qid(subjects_out[s]["id"], q["question"])
                subjects_out[s]["questions"].append(q)
            time.sleep(1.5)

    # 2. Registrazioni audio (riassunti + esempi del prof)
    audio_dir = CACHE_DIR / "audio"
    if audio_dir.exists():
        for f in sorted(audio_dir.glob("*.json")):
            d = json.loads(f.read_text())
            s = d.get("subject")
            if s not in subjects_out or not d.get("summary"):
                continue
            topic = (d.get("topics") or [Path(d["filename"]).stem])[0]
            res = generate_from_lesson_text(s, f"Lezione: {topic}", d["summary"], d["filename"], d.get("prof_examples", []), num_q=5)
            subjects_out[s]["summaries"].append(generate_summary_card(s, topic, d["summary"], d["filename"], d.get("prof_examples", [])))
            q_list = res if isinstance(res, list) else res.get("questions", [])
            for q in q_list:
                q["id"] = qid(subjects_out[s]["id"], q["question"])
                subjects_out[s]["questions"].append(q)
            time.sleep(1.5)

    # 3. Appunti fotografati
    app_dir = CACHE_DIR / "appunti"
    if app_dir.exists():
        for f in sorted(app_dir.glob("*.json")):
            d = json.loads(f.read_text())
            s = d.get("subject")
            if s not in subjects_out or not d.get("transcription"):
                continue
            res = generate_from_lesson_text(
                s,
                f"Appunti: {d.get('topic', 'Generale')}",
                d["transcription"],
                ", ".join(d.get("files", [])),
                examples_by_subj[s],
                num_q=4,
            )
            subjects_out[s]["summaries"].append(generate_summary_card(s, d.get("topic", "Appunti"), d["transcription"], ", ".join(d.get("files", [])), examples_by_subj[s]))
            q_list = res if isinstance(res, list) else res.get("questions", [])
            for q in q_list:
                q["id"] = qid(subjects_out[s]["id"], q["question"])
                subjects_out[s]["questions"].append(q)
            time.sleep(1.5)

    for s_obj in subjects_out.values():
        for q in s_obj["questions"]:
            if not q.get("sort_key") or not q.get("date_label"):
                sk, dl = extract_date_meta(q.get("source_detail", ""), is_lesson_pdf=bool(re.match(r"^\d{1,2}\.\s", q.get("source_detail", ""))))
                q["sort_key"] = sk
                q["date_label"] = dl
        s_obj["questions"].sort(key=lambda q: (q.get("sort_key", "9999"), q.get("topic", "")))
        for c in s_obj["summaries"]:
            if not c.get("sort_key") or not c.get("date_label"):
                sk, dl = extract_date_meta(c.get("source", ""), is_lesson_pdf=bool(re.match(r"^\d{1,2}\.\s", c.get("source", ""))))
                c["sort_key"] = sk
                c["date_label"] = dl
        s_obj["summaries"].sort(key=lambda c: (c.get("sort_key", "9999"), c.get("topic", "")))

    final = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "subjects": list(subjects_out.values()),
    }
    OUT_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=1))
    total_q = sum(len(x["questions"]) for x in final["subjects"])
    print(f"FATTO! Salvato {OUT_FILE} con {total_q} domande totali.")


if __name__ == "__main__":
    build_all()

