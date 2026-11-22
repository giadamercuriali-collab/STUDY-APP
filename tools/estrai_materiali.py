"""Estrae contenuti da PDF, Word, testo, foto di appunti e registrazioni audio.

Salva i risultati in materiali/cache/ (ignorato da Git) in modo incrementale:
se lo script viene rilanciato, salta i file già elaborati.

Uso:
  python3 tools/estrai_materiali.py --solo-test-prof
  python3 tools/estrai_materiali.py --solo-pdf
  python3 tools/estrai_materiali.py --solo-appunti
  python3 tools/estrai_materiali.py --solo-audio
  python3 tools/estrai_materiali.py --tutto
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time, warnings, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader
import imageio_ffmpeg

warnings.filterwarnings("ignore")

ROOT_APP = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_APP / ".env")
CACHE_DIR = ROOT_APP / "materiali" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UNI_DIR = Path("/Users/giada/Library/Mobile Documents/com~apple~CloudDocs/Università")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MODEL_PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
MODELS_FALLBACK = [
    MODEL_PRIMARY,
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
]

EXCLUDE_DIRS = {"Doc per iscrizione", "Doc per iscrizione ", "Pagamenti 2026", "Prenotazioni esami", "Prenotazioni esami "}

client = None


def get_client():
    global client
    if client is None:
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=90000),
        )
    return client


def call_gemini(contents, json_mode=True):
    cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    last_err = None
    for round_idx in range(3):
        for modello in MODELS_FALLBACK:
            try:
                r = get_client().models.generate_content(model=modello, contents=contents, config=cfg)
                return json.loads(r.text) if json_mode else r.text
            except Exception as e:
                last_err = e
                time.sleep(10 + round_idx * 10)
    raise RuntimeError(f"Gemini fallito dopo vari tentativi: {last_err}")


def file_key(path: Path) -> str:
    h = hashlib.md5(str(path).encode()).hexdigest()[:10]
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", path.stem)[:40]
    return f"{safe}_{h}"


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf_text(path: Path, max_pages=None) -> str:
    reader = PdfReader(str(path))
    pages = reader.pages[:max_pages] if max_pages else reader.pages
    parts = []
    for i, page in enumerate(pages, 1):
        txt = (page.extract_text() or "").strip()
        if txt:
            parts.append(f"[Pag. {i}]\n{txt}")
    return "\n\n".join(parts)


def extract_pptx_text(path: Path) -> str:
    parts = []
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")],
            key=lambda x: int(re.search(r"slide(\d+)\.xml", x).group(1)),
        )
        for i, s in enumerate(slides, 1):
            root = ET.fromstring(z.read(s))
            txt = " ".join(t.text for t in root.iter() if t.tag.endswith("}t") and t.text).strip()
            if txt:
                parts.append(f"[Slide {i}]\n{txt}")
    return "\n\n".join(parts)


def process_pdfs():
    out_dir = CACHE_DIR / "pdfs"
    out_dir.mkdir(exist_ok=True)
    targets = []
    # Diritto privato
    dp = UNI_DIR / "Diritto privato "
    if dp.exists():
        for p in sorted(dp.rglob("*.pdf")):
            targets.append(("Diritto Privato", p))
    # Diritto costituzionale
    dc = UNI_DIR / "Diritto Costituzionale "
    if dc.exists():
        for p in sorted(dc.rglob("*.pdf")):
            targets.append(("Diritto Costituzionale", p))
    # Legal English (PDF + PPTX)
    le = UNI_DIR / "Legal English"
    if le.exists():
        for p in sorted(le.rglob("*")):
            if p.suffix.lower() in {".pdf", ".pptx"}:
                targets.append(("Legal English", p))
    # Testi (escludendo i manuali enormi > 30MB se non serve, o estraendo a blocchi; qui li includiamo tutti tranne file personali)
    testi = UNI_DIR / "Testi"
    if testi.exists():
        for p in sorted(testi.rglob("*.pdf")):
            low = str(p).lower()
            if "privato" in low:
                subj = "Diritto Privato"
            elif "pubblico" in low or "costituz" in low or "fonti" in low or "stato" in low or "unione" in low or "ordinamento" in low:
                subj = "Diritto Costituzionale"
            else:
                subj = "Altro"
            targets.append((subj, p))
    # PDF extra in Registrazioni
    reg_pdf = UNI_DIR / "Registrazioni" / "11 costituzionale .pdf"
    if reg_pdf.exists():
        targets.append(("Diritto Costituzionale", reg_pdf))

    for subj, p in targets:
        if any(ex in p.parts for ex in EXCLUDE_DIRS):
            continue
        out_file = out_dir / f"{file_key(p)}.json"
        if out_file.exists():
            continue
        print(f"[PDF] {subj} -> {p.name}", flush=True)
        try:
            text = extract_pptx_text(p) if p.suffix.lower() == ".pptx" else extract_pdf_text(p)
            is_test = "autovalutazione" in p.name.lower()
            data = {
                "subject": subj,
                "filename": p.name,
                "path": str(p),
                "is_prof_test": is_test,
                "chars": len(text),
                "text": text,
            }
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        except Exception as e:
            print(f"  Errore PDF {p.name}: {e}", flush=True)


def process_notes_images():
    out_dir = CACHE_DIR / "appunti"
    out_dir.mkdir(exist_ok=True)
    folders = [(UNI_DIR / "Appunti", "batch"), (UNI_DIR / "Registrazioni", "reg_batch")]
    for folder, prefix in folders:
        if not folder.exists():
            continue
        imgs = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}])
        batch_size = 4
        for i in range(0, len(imgs), batch_size):
            batch = imgs[i : i + batch_size]
            key = f"{prefix}_{i:03d}_{batch[0].stem[:30]}"
            out_file = out_dir / f"{key}.json"
            if out_file.exists():
                continue
            print(f"[APPUNTI] {batch[0].name} .. ({len(batch)} foto)", flush=True)
            parts = [
                """Trascrivi e organizza questi appunti universitari (Giurisprudenza: Diritto Privato, Diritto Costituzionale o Legal English).
Rispondi SOLO in JSON con questa struttura:
{
  "subject": "Diritto Privato | Diritto Costituzionale | Legal English | Altro",
  "topic": "Titolo sintetico dell'argomento",
  "transcription": "Testo ordinato e leggibile degli appunti",
  "examples": ["eventuali esempi o casi pratici annotati"]
}"""
            ]
            for img in batch:
                mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
                parts.append(types.Part.from_bytes(data=img.read_bytes(), mime_type=mime))
            try:
                res = call_gemini(parts, json_mode=True)
                if isinstance(res, list):
                    res = res[0] if res else {}
                res["files"] = [b.name for b in batch]
                out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1))
            except Exception as e:
                print(f"  Errore appunti batch {i}: {e}", flush=True)
            time.sleep(2)


def audio_duration(p: Path) -> float:
    err = subprocess.run([FFMPEG, "-i", str(p)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def split_audio_chunks(p: Path, tmp: Path, chunk_sec=900):
    """Converte e spezza l'audio in blocchi mp3 leggeri (mono 32k) da max 15 minuti."""
    dur = audio_duration(p)
    chunks = []
    start = 0
    idx = 0
    while start < max(dur, 1):
        out = tmp / f"chunk_{idx:02d}.mp3"
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-ss", str(start), "-t", str(chunk_sec), "-i", str(p), "-ac", "1", "-b:a", "32k", str(out)],
            check=True,
        )
        if out.exists() and out.stat().st_size > 1000:
            chunks.append((idx, start, out))
        start += chunk_sec
        idx += 1
        if dur <= 0:
            break
    return dur, chunks


def process_audio():
    out_dir = CACHE_DIR / "audio"
    out_dir.mkdir(exist_ok=True)
    reg_dir = UNI_DIR / "Registrazioni"
    subject_folders = {
        "DIRITTO PRIVATO ": "Diritto Privato",
        "DIRITTO COSTITUZIONALE ": "Diritto Costituzionale",
        "LEGAL ENGLISH": "Legal English",
    }
    seen_md5 = set()
    for folder_name, subj in subject_folders.items():
        folder = reg_dir / folder_name
        if not folder.exists():
            continue
        files = sorted([p for p in folder.iterdir() if p.suffix.lower() in {".m4a", ".mp4", ".mp3", ".wav"}])
        for p in files:
            out_file = out_dir / f"{file_key(p)}.json"
            if out_file.exists():
                continue
            h = md5_file(p)
            if h in seen_md5:
                print(f"[AUDIO-SKIP-DUP] {p.name}", flush=True)
                continue
            seen_md5.add(h)
            print(f"[AUDIO] {subj} -> {p.name}", flush=True)
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dur, chunks = split_audio_chunks(p, Path(tmp))
                    chunk_summaries = []
                    all_examples = []
                    topics = []
                    for idx, start_sec, chunk_path in chunks:
                        prompt = f"""Ascolta questo segmento (minuto {start_sec//60} in poi) della lezione di {subj}.
Estrai:
1. L'argomento principale trattato.
2. I concetti giuridici/tecnici spiegati in modo chiaro.
3. TUTTI gli esempi pratici, casi concreti, aneddoti o interventi/precisazioni fatte dal professore durante la spiegazione (questo è fondamentale per lo studio!).

Rispondi SOLO in JSON:
{{
  "topic": "argomento del segmento",
  "summary": "riassunto chiaro e dettagliato dei concetti spiegati",
  "prof_examples": [
    {{
      "title": "titolo breve dell'esempio",
      "concept": "concetto giuridico collegato",
      "text": "descrizione completa dell'esempio o intervento del prof"
    }}
  ]
}}"""
                        part = types.Part.from_bytes(data=chunk_path.read_bytes(), mime_type="audio/mp3")
                        res = call_gemini([prompt, part], json_mode=True)
                        if res.get("topic"):
                            topics.append(res["topic"])
                        if res.get("summary"):
                            chunk_summaries.append(res["summary"])
                        for ex in res.get("prof_examples", []):
                            ex["source"] = p.name
                            all_examples.append(ex)
                        time.sleep(1.5)

                data = {
                    "subject": subj,
                    "filename": p.name,
                    "duration_min": round(dur / 60),
                    "topics": topics,
                    "summary": "\n\n".join(chunk_summaries),
                    "prof_examples": all_examples,
                }
                out_file.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            except Exception as e:
                print(f"  Errore audio {p.name}: {e}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-pdf", action="store_true")
    ap.add_argument("--solo-appunti", action="store_true")
    ap.add_argument("--solo-audio", action="store_true")
    ap.add_argument("--tutto", action="store_true")
    args = ap.parse_args()

    if args.solo_pdf or args.tutto:
        process_pdfs()
    if args.solo_appunti or args.tutto:
        process_notes_images()
    if args.solo_audio or args.tutto:
        process_audio()
    if not any([args.solo_pdf, args.solo_appunti, args.solo_audio, args.tutto]):
        ap.print_help()

