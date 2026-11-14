"""Riconosce la materia di una registrazione ascoltando alcuni campioni audio con Gemini.

Uso: python3 tools/riconosci_materia.py file1.m4a file2.m4a ...
Stampa una riga JSON per file.
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

PROMPT = """Sei un assistente che classifica registrazioni di lezioni universitarie (Giurisprudenza, Unibo).
Ricevi alcuni brevi campioni presi da punti diversi della STESSA registrazione.
Regole fornite dalla studentessa:
- Voce FEMMINILE che tiene la lezione -> "Diritto Costituzionale" (prof.ssa Caterina Domenicali)
- Voce MASCHILE che parla prevalentemente in INGLESE -> "Legal English" (prof. Alessandro Russo)
- Voce MASCHILE più giovanile, in italiano -> "Diritto Privato" (prof. Nicolò Cevolani)
Usa anche gli argomenti trattati (contratti/obbligazioni/proprietà = Privato; Costituzione/fonti/Stato/Parlamento = Costituzionale).
Se non è una lezione (rumore, conversazione privata, silenzio) usa "Non è una lezione".
Rispondi SOLO con JSON: {"materia": "...", "confidenza": "alta|media|bassa", "motivo": "breve frase in italiano", "argomento": "argomento principale se riconoscibile"}"""


import re, warnings
warnings.filterwarnings("ignore")
import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def durata(p):
    err = subprocess.run([FFMPEG, "-i", p], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0


def campioni(p, tmp, n=3, sec=60):
    d = durata(p)
    starts = [max(0, d * f - sec / 2) for f in ((0.15, 0.5, 0.85) if d > 3 * sec else (0,))][:n]
    files = []
    for i, s in enumerate(starts):
        o = os.path.join(tmp, f"c{i}.mp3")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(s), "-t", str(sec), "-i", p, "-ac", "1", "-b:a", "48k", o], check=True)
        files.append(o)
    return d, files


def classifica(p):
    with tempfile.TemporaryDirectory() as tmp:
        d, cs = campioni(p, tmp)
        parts = [types.Part.from_bytes(data=open(c, "rb").read(), mime_type="audio/mp3") for c in cs]
        modelli = [MODEL, "gemini-3-flash-preview", "gemini-flash-lite-latest"] * 2
        for tentativo, modello in enumerate(modelli):
            try:
                r = client.models.generate_content(model=modello, contents=[PROMPT, *parts],
                                                   config=types.GenerateContentConfig(response_mime_type="application/json"))
                res = json.loads(r.text); res["modello"] = modello
                break
            except Exception as e:
                res = {"materia": "Errore", "motivo": str(e)[:200]}
                time.sleep(5)
    res.update(file=os.path.basename(p), durata_min=round(d / 60))
    return res


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(classifica(p), ensure_ascii=False), flush=True)
