# GiuriQuiz — App di Studio per Giurisprudenza

Web app mobile-first (PWA) ottimizzata per iPhone e utilizzabile anche offline dalla schermata Home.

## Funzionalità
- **Quiz per materia e argomento:** Diritto Privato, Diritto Costituzionale, Legal English.
- **Test del professore integrati:** preserva i quesiti di autovalutazione con spiegazione normativa.
- **Esempi e interventi dei prof dalle lezioni:** ogni spiegazione integra gli esempi pratici ascoltati nelle registrazioni, con sezione dedicata per cercarli e ripassarli.
- **Ripasso automatico degli errori:** salva localmente su iPhone le risposte errate per ripeterle.
- **Funziona offline:** installabile su iPhone da Safari via *Condividi → Aggiungi alla schermata Home*.

## Aggiornare i quiz con nuovi materiali (dal Mac)
1. Inserisci la tua chiave Gemini in `.env` (`GEMINI_API_KEY=...`, file ignorato da Git).
2. Estrai i nuovi materiali (PDF, foto appunti, registrazioni audio):
   ```bash
   python3 tools/estrai_materiali.py --tutto
   ```
3. Rigenera il database dei quiz:
   ```bash
   python3 tools/genera_quiz.py
   ```
4. Carica su GitHub solo l'app e `data/quizzes.json` (i file pesanti e `.env` restano esclusi grazie a `.gitignore`).

