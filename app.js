(() => {
  const STORAGE_KEY = 'giuriquiz_progress_v1';
  const THEME_KEY = 'giuriquiz_theme';

  const state = {
    data: null,
    view: 'home',
    subjectId: null,
    quiz: null, // { title, questions, index, score, answered, selected, sessionWrong }
    progress: loadProgress(),
  };

  const mainEl = document.getElementById('main-content');
  const titleEl = document.getElementById('header-title');
  const backBtn = document.getElementById('btn-back');
  const themeBtn = document.getElementById('btn-theme');

  function loadProgress() {
    try {
      const p = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
      return { answered: p.answered || {}, wrongIds: p.wrongIds || [], studiedIds: p.studiedIds || [] };
    } catch {
      return { answered: {}, wrongIds: [], studiedIds: [] };
    }
  }

  function saveProgress() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.progress));
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
  }

  themeBtn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(THEME_KEY, next);
    themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
  });

  backBtn.addEventListener('click', () => {
    if (state.view === 'lesson_detail') {
      openLessons(state.subjectId);
    } else if (state.view === 'quiz' || state.view === 'results') {
      if (state.subjectId) openSubject(state.subjectId);
      else openHome();
    } else {
      openHome();
    }
  });

  function setHeader(title, showBack) {
    titleEl.textContent = title;
    backBtn.classList.toggle('hidden', !showBack);
  }

  function esc(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function allQuestions() {
    const out = [];
    for (const subj of state.data.subjects) {
      for (const q of subj.questions) out.push({ ...q, subjectName: subj.name, subjectId: subj.id });
    }
    return out;
  }

  function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function openHome() {
    state.view = 'home';
    state.subjectId = null;
    state.quiz = null;
    setHeader('GiuriQuiz', false);

    const all = allQuestions();
    const total = all.length;
    const answeredCount = Object.keys(state.progress.answered).length;
    const correctCount = Object.values(state.progress.answered).filter(Boolean).length;
    const acc = answeredCount ? Math.round((correctCount / answeredCount) * 100) : 0;
    const wrongCount = state.progress.wrongIds.length;
    const totalExamples = state.data.subjects.reduce((s, x) => s + (x.examples?.length || 0), 0);
    const totalSummaries = state.data.subjects.reduce((s, x) => s + (x.summaries?.length || 0), 0);

    let html = `
      <div class="stats-grid">
        <div class="stat-box">
          <div class="stat-val">${answeredCount}/${total}</div>
          <div class="stat-lbl">Completate</div>
        </div>
        <div class="stat-box">
          <div class="stat-val">${acc}%</div>
          <div class="stat-lbl">Precisione</div>
        </div>
        <div class="stat-box">
          <div class="stat-val">${wrongCount}</div>
          <div class="stat-lbl">Da ripassare</div>
        </div>
      </div>

      <div class="action-row">
        <button class="btn btn-primary" id="btn-review-wrong" ${wrongCount ? '' : 'disabled'}>
          🔁 Ripassa errori (${wrongCount})
        </button>
        <button class="btn btn-secondary" id="btn-lessons">
          📅 Lezioni & Flashcard
        </button>
      </div>
      <div class="action-row">
        <button class="btn btn-secondary" id="btn-summaries">
          📖 Schede studio (${totalSummaries})
        </button>
        <button class="btn btn-secondary" id="btn-examples">
          💡 Esempi prof (${totalExamples})
        </button>
      </div>

      <div class="section-title">Materie</div>
    `;

    for (const subj of state.data.subjects) {
      const qCount = subj.questions.length;
      const done = subj.questions.filter((q) => q.id in state.progress.answered).length;
      const pct = qCount ? Math.round((done / qCount) * 100) : 0;
      html += `
        <div class="card subject-card" data-subj="${esc(subj.id)}">
          <div class="subject-head">
            <div>
              <div class="subject-name">${esc(subj.name)}</div>
              <div class="subject-prof">${esc(subj.prof || '')}</div>
            </div>
            <span class="badge">${qCount} domande</span>
          </div>
          <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
          <div class="source-caption">${done} di ${qCount} risposte date (${pct}%) · ${(subj.examples || []).length} esempi dalle lezioni</div>
        </div>
      `;
    }

    mainEl.innerHTML = html;

    document.getElementById('btn-review-wrong').addEventListener('click', () => {
      const wrongSet = new Set(state.progress.wrongIds);
      const qs = all.filter((q) => wrongSet.has(q.id));
      if (qs.length) startQuiz('Ripasso errori', shuffle(qs));
    });

    document.getElementById('btn-lessons').addEventListener('click', () => openLessons(null));
    document.getElementById('btn-summaries').addEventListener('click', () => openSummaries(null));
    document.getElementById('btn-examples').addEventListener('click', openExamples);

    mainEl.querySelectorAll('.subject-card').forEach((el) => {
      el.addEventListener('click', () => openSubject(el.dataset.subj));
    });
  }

  function openSubject(subjectId) {
    const subj = state.data.subjects.find((s) => s.id === subjectId);
    if (!subj) return openHome();
    state.view = 'subject';
    state.subjectId = subjectId;
    setHeader(subj.name, true);

    const topicsMap = new Map();
    for (const q of subj.questions) {
      const t = q.topic || 'Generale';
      if (!topicsMap.has(t)) topicsMap.set(t, []);
      topicsMap.get(t).push(q);
    }

    const profTests = subj.questions.filter((q) => q.source_type === 'prof_test');
    const wrongInSubj = subj.questions.filter((q) => state.progress.wrongIds.includes(q.id));

    let html = `
      <div class="card">
        <div class="subject-head">
          <div>
            <div class="subject-name">${esc(subj.name)}</div>
            <div class="subject-prof">${esc(subj.prof || '')}</div>
          </div>
          <span class="badge">${subj.questions.length} domande</span>
        </div>
        <div class="action-row" style="margin-top:14px">
          <button class="btn btn-primary" id="btn-sim-20" ${subj.questions.length ? '' : 'disabled'}>🎯 Simulazione (20)</button>
          <button class="btn btn-secondary" id="btn-prof-only" ${profTests.length ? '' : 'disabled'}>📝 Test prof (${profTests.length})</button>
        </div>
        <div class="action-row" style="margin-top:10px">
          <button class="btn btn-secondary" id="btn-subj-lessons" ${(subj.summaries || []).length ? '' : 'disabled'}>
            📅 Lezioni & Flashcard
          </button>
          <button class="btn btn-secondary" id="btn-subj-summaries" ${(subj.summaries || []).length ? '' : 'disabled'}>
            📖 Schede (${(subj.summaries || []).length})
          </button>
        </div>
        ${wrongInSubj.length ? `<button class="btn btn-secondary btn-block" id="btn-subj-wrong" style="margin-top:10px">🔁 Ripassa errori della materia (${wrongInSubj.length})</button>` : ''}
      </div>

      <div class="section-title">Argomenti e Lezioni</div>
    `;

    if (!topicsMap.size) {
      html += `<div class="empty-state card">Nessun quiz ancora generato per questa materia.</div>`;
    } else {
      for (const [topic, qs] of topicsMap.entries()) {
        const done = qs.filter((q) => q.id in state.progress.answered).length;
        html += `
          <div class="topic-item" data-topic="${esc(topic)}">
            <div>
              <div style="font-weight:600">${esc(topic)}</div>
              <div class="topic-meta">${done}/${qs.length} completate</div>
            </div>
            <span class="badge">${qs.length}</span>
          </div>
        `;
      }
    }

    mainEl.innerHTML = html;

    document.getElementById('btn-sim-20').addEventListener('click', () => {
      startQuiz(`${subj.name} — Simulazione`, shuffle(subj.questions).slice(0, 20));
    });

    document.getElementById('btn-prof-only').addEventListener('click', () => {
      startQuiz(`${subj.name} — Test del Professore`, profTests);
    });

    document.getElementById('btn-subj-lessons').addEventListener('click', () => {
      openLessons(subj.id);
    });

    document.getElementById('btn-subj-summaries').addEventListener('click', () => {
      openSummaries(subj.id);
    });

    const wrongBtn = document.getElementById('btn-subj-wrong');
    if (wrongBtn) {
      wrongBtn.addEventListener('click', () => startQuiz(`${subj.name} — Errori`, shuffle(wrongInSubj)));
    }

    mainEl.querySelectorAll('.topic-item').forEach((el) => {
      el.addEventListener('click', () => {
        const t = el.dataset.topic;
        startQuiz(t, topicsMap.get(t));
      });
    });
  }

  function startQuiz(title, questions) {
    state.view = 'quiz';
    state.quiz = {
      title,
      questions,
      index: 0,
      score: 0,
      answered: false,
      selected: -1,
      sessionWrong: [],
    };
    renderQuestion();
  }

  function renderQuestion() {
    const qz = state.quiz;
    const q = qz.questions[qz.index];
    setHeader(qz.title, true);

    const pct = Math.round(((qz.index + (qz.answered ? 1 : 0)) / qz.questions.length) * 100);
    const letters = ['A', 'B', 'C', 'D', 'E'];
    const isProfTest = q.source_type === 'prof_test';

    let html = `
      <div class="quiz-header">
        <span>Domanda ${qz.index + 1} di ${qz.questions.length}</span>
        <span class="badge ${isProfTest ? 'prof-test' : ''}">${isProfTest ? '📝 Test Prof' : '✨ AI + Lezione'}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>

      <div class="card">
        <div class="source-caption">${esc(q.topic || '')}</div>
        <div class="question-text">${esc(q.question)}</div>
        <div class="options-list">
          ${q.options.map((opt, idx) => {
            let cls = 'option-btn';
            if (qz.answered) {
              if (idx === q.correct) cls += ' correct';
              else if (idx === qz.selected) cls += ' wrong';
            }
            return `
              <button class="${cls}" data-idx="${idx}" ${qz.answered ? 'disabled' : ''}>
                <span class="option-letter">${letters[idx] || idx + 1}</span>
                <span>${esc(opt)}</span>
              </button>
            `;
          }).join('')}
        </div>
      </div>
    `;

    if (qz.answered) {
      const ok = qz.selected === q.correct;
      html += `
        <div class="feedback-box">
          <div class="feedback-status ${ok ? 'ok' : 'err'}">
            ${ok ? '✅ Risposta esatta!' : '❌ Risposta errata'}
          </div>
          <div>${esc(q.explanation || 'Nessuna spiegazione disponibile.')}</div>
          ${q.prof_example ? `
            <div class="prof-example-box">
              <div class="prof-example-title">💡 Esempio / intervento del prof a lezione</div>
              <div>${esc(q.prof_example)}</div>
            </div>
          ` : ''}
          ${q.source_detail ? `<div class="source-caption">Fonte: ${esc(q.source_detail)}</div>` : ''}
          <button class="btn btn-primary btn-block" id="btn-next">
            ${qz.index + 1 < qz.questions.length ? 'Prossima domanda →' : 'Vedi risultati →'}
          </button>
        </div>
      `;
    }

    mainEl.innerHTML = html;

    if (!qz.answered) {
      mainEl.querySelectorAll('.option-btn').forEach((btn) => {
        btn.addEventListener('click', () => selectAnswer(Number(btn.dataset.idx)));
      });
    } else {
      document.getElementById('btn-next').addEventListener('click', () => {
        if (qz.index + 1 < qz.questions.length) {
          qz.index++;
          qz.answered = false;
          qz.selected = -1;
          renderQuestion();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
          renderResults();
        }
      });
    }
  }

  function selectAnswer(idx) {
    const qz = state.quiz;
    const q = qz.questions[qz.index];
    qz.answered = true;
    qz.selected = idx;
    const ok = idx === q.correct;
    if (ok) qz.score++;
    else qz.sessionWrong.push(q);

    state.progress.answered[q.id] = ok;
    const wrongSet = new Set(state.progress.wrongIds);
    if (ok) wrongSet.delete(q.id);
    else wrongSet.add(q.id);
    state.progress.wrongIds = Array.from(wrongSet);
    saveProgress();

    renderQuestion();
  }

  function renderResults() {
    state.view = 'results';
    const qz = state.quiz;
    const total = qz.questions.length;
    const pct = total ? Math.round((qz.score / total) * 100) : 0;
    setHeader('Risultato', true);

    let html = `
      <div class="card" style="text-align:center">
        <div style="font-size:2.4rem;font-weight:800;color:var(--accent)">${qz.score} / ${total}</div>
        <div style="color:var(--muted);margin-bottom:16px">Precisione: ${pct}%</div>
        <div class="action-row">
          <button class="btn btn-secondary" id="btn-back-menu">Torna indietro</button>
          <button class="btn btn-primary" id="btn-retry-wrong" ${qz.sessionWrong.length ? '' : 'disabled'}>
            Ripeti errori (${qz.sessionWrong.length})
          </button>
        </div>
      </div>
    `;

    if (qz.sessionWrong.length) {
      html += `<div class="section-title">Domande da rivedere</div>`;
      for (const q of qz.sessionWrong) {
        html += `
          <div class="card">
            <div style="font-weight:600;margin-bottom:6px">${esc(q.question)}</div>
            <div style="color:var(--ok);font-size:0.9rem;margin-bottom:6px">✓ ${esc(q.options[q.correct])}</div>
            <div style="font-size:0.88rem;color:var(--muted)">${esc(q.explanation || '')}</div>
            ${q.prof_example ? `<div class="prof-example-box" style="margin-top:8px"><div class="prof-example-title">💡 Esempio del prof</div>${esc(q.prof_example)}</div>` : ''}
          </div>
        `;
      }
    }

    mainEl.innerHTML = html;
    document.getElementById('btn-back-menu').addEventListener('click', () => {
      if (state.subjectId) openSubject(state.subjectId);
      else openHome();
    });
    const retryBtn = document.getElementById('btn-retry-wrong');
    if (retryBtn && qz.sessionWrong.length) {
      retryBtn.addEventListener('click', () => startQuiz(`${qz.title} — Errori`, qz.sessionWrong));
    }
  }

  function openExamples() {
    state.view = 'examples';
    setHeader('Esempi dei Professori', true);

    const allEx = [];
    for (const s of state.data.subjects) {
      for (const ex of s.examples || []) {
        allEx.push({ ...ex, subject: s.name });
      }
    }

    mainEl.innerHTML = `
      <input type="search" id="ex-search" class="search-input" placeholder="Cerca un argomento, parola chiave o lezione..." />
      <div id="ex-list" style="display:flex;flex-direction:column;gap:12px"></div>
    `;

    const listEl = document.getElementById('ex-list');
    const searchEl = document.getElementById('ex-search');

    function renderList(filter) {
      const f = filter.trim().toLowerCase();
      const filtered = allEx.filter((e) =>
        !f ||
        (e.topic || '').toLowerCase().includes(f) ||
        (e.text || '').toLowerCase().includes(f) ||
        (e.subject || '').toLowerCase().includes(f)
      );
      if (!filtered.length) {
        listEl.innerHTML = `<div class="empty-state card">Nessun esempio trovato.</div>`;
        return;
      }
      listEl.innerHTML = filtered.slice(0, 80).map((e) => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:6px">
            <span class="badge prof-test">${esc(e.subject)}</span>
            <span class="source-caption">${esc(e.source || '')}</span>
          </div>
          <div style="font-weight:700;margin-bottom:4px">${esc(e.topic || 'Esempio a lezione')}</div>
          <div style="font-size:0.92rem">${esc(e.text)}</div>
        </div>
      `).join('');
    }

    renderList('');
    searchEl.addEventListener('input', () => renderList(searchEl.value));
  }

  function openSummaries(initialSubjectId) {
    state.view = 'summaries';
    setHeader('Schede Riassuntive', true);

    let activeSubj = initialSubjectId || 'all';
    const allCards = [];
    for (const s of state.data.subjects) {
      for (const c of s.summaries || []) {
        allCards.push({ ...c, subjectId: s.id, subjectName: s.name });
      }
    }

    mainEl.innerHTML = `
      <div class="chips-row" id="sum-chips">
        <button class="chip ${activeSubj === 'all' ? 'active' : ''}" data-id="all">Tutte (${allCards.length})</button>
        ${state.data.subjects.map((s) => `
          <button class="chip ${activeSubj === s.id ? 'active' : ''}" data-id="${esc(s.id)}">
            ${esc(s.name)} (${(s.summaries || []).length})
          </button>
        `).join('')}
      </div>
      <input type="search" id="sum-search" class="search-input" placeholder="Cerca un argomento o articolo (es. contratto, art. 1321)..." />
      <div id="sum-list" style="display:flex;flex-direction:column;gap:12px"></div>
    `;

    const listEl = document.getElementById('sum-list');
    const searchEl = document.getElementById('sum-search');

    function renderCards() {
      const f = searchEl.value.trim().toLowerCase();
      const studiedSet = new Set(state.progress.studiedIds);
      const filtered = allCards.filter((c) => {
        if (activeSubj !== 'all' && c.subjectId !== activeSubj) return false;
        if (!f) return true;
        return (
          (c.topic || '').toLowerCase().includes(f) ||
          (c.key_points || []).join(' ').toLowerCase().includes(f) ||
          (c.schema || []).map((n) => `${n.nodo} ${(n.figli || []).join(' ')}`).join(' ').toLowerCase().includes(f) ||
          (c.norme || []).join(' ').toLowerCase().includes(f) ||
          (c.prof_tip || '').toLowerCase().includes(f)
        );
      });

      if (!filtered.length) {
        listEl.innerHTML = `<div class="empty-state card">Nessuna scheda trovata. Le schede complete arriveranno al termine dell'elaborazione dei materiali.</div>`;
        return;
      }

      listEl.innerHTML = filtered.map((c) => {
        const isStudied = studiedSet.has(c.id);
        return `
          <div class="card summary-card ${isStudied ? 'studied' : ''}" data-card="${esc(c.id)}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px">
              <span class="badge">${esc(c.subjectName)}</span>
              <button class="btn btn-secondary btn-sm btn-toggle-studied" data-id="${esc(c.id)}">
                ${isStudied ? '✅ Ripassata' : 'Segna ripassata'}
              </button>
            </div>
            <div style="font-size:1.05rem;font-weight:700">${esc(c.topic)}</div>
            <ul class="summary-points">
              ${(c.key_points || []).map((pt) => `<li>${esc(pt)}</li>`).join('')}
            </ul>
            ${(c.schema && c.schema.length) ? `
              <div class="view-tabs" data-tabs="${esc(c.id)}">
                <button class="view-tab active" data-mode="diagram">🗺️ Diagramma</button>
                <button class="view-tab" data-mode="outline">🗂️ Schema</button>
              </div>
              <div class="diagram-wrap" data-pane="diagram">
                <div class="diag-root">${esc(c.topic)}</div>
                <div class="diag-arrow">▼</div>
                <div class="diag-branches">
                  ${c.schema.map((n, idx) => `
                    <div class="diag-branch c${idx % 4}">
                      <div class="diag-branch-head">${esc(n.nodo)}</div>
                      ${(n.figli && n.figli.length) ? `
                        <div class="diag-leaves">
                          ${n.figli.map((fg) => `<div class="diag-leaf">${esc(fg)}</div>`).join('')}
                        </div>
                      ` : ''}
                    </div>
                  `).join('')}
                </div>
              </div>
              <div class="schema-box hidden" data-pane="outline" style="display:none">
                <div class="schema-title">🗂️ Schema riassuntivo</div>
                ${c.schema.map((n) => `
                  <div class="schema-node">
                    <div class="schema-parent">${esc(n.nodo)}</div>
                    ${(n.figli && n.figli.length) ? `
                      <ul class="schema-children">
                        ${n.figli.map((fg) => `<li>${esc(fg)}</li>`).join('')}
                      </ul>
                    ` : ''}
                  </div>
                `).join('')}
              </div>
            ` : ''}
            ${(c.norme && c.norme.length) ? `
              <div class="norme-row">
                ${c.norme.map((n) => `<span class="norma-pill">${esc(n)}</span>`).join('')}
              </div>
            ` : ''}
            ${c.prof_tip ? `
              <div class="prof-example-box" style="margin-top:10px">
                <div class="prof-example-title">💡 Nota / esempio del prof</div>
                <div>${esc(c.prof_tip)}</div>
              </div>
            ` : ''}
            ${c.source ? `<div class="source-caption" style="margin-top:8px">Fonte: ${esc(c.source)}</div>` : ''}
          </div>
        `;
      }).join('');

      listEl.querySelectorAll('.btn-toggle-studied').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.id;
          const set = new Set(state.progress.studiedIds);
          if (set.has(id)) set.delete(id);
          else set.add(id);
          state.progress.studiedIds = Array.from(set);
          saveProgress();
          renderCards();
        });
      });

      listEl.querySelectorAll('.view-tabs').forEach((tabs) => {
        tabs.querySelectorAll('.view-tab').forEach((tab) => {
          tab.addEventListener('click', () => {
            const card = tabs.closest('.summary-card');
            const mode = tab.dataset.mode;
            tabs.querySelectorAll('.view-tab').forEach((t) => t.classList.remove('active'));
            tab.classList.add('active');
            card.querySelector('[data-pane="diagram"]').style.display = mode === 'diagram' ? 'flex' : 'none';
            card.querySelector('[data-pane="outline"]').style.display = mode === 'outline' ? 'block' : 'none';
          });
        });
      });
    }

    document.getElementById('sum-chips').querySelectorAll('.chip').forEach((ch) => {
      ch.addEventListener('click', () => {
        activeSubj = ch.dataset.id;
        document.getElementById('sum-chips').querySelectorAll('.chip').forEach((x) => x.classList.remove('active'));
        ch.classList.add('active');
        renderCards();
      });
    });

    searchEl.addEventListener('input', renderCards);
    renderCards();
  }

  function buildFlashcardsForLesson(subj, card) {
    if (card.flashcards && card.flashcards.length) return card.flashcards;
    const fc = [];
    for (const n of card.schema || []) {
      if (n.nodo && (n.figli || []).length) {
        fc.push({
          front: `${card.topic}\n\n${n.nodo}`,
          back: n.figli.map((x) => `• ${x}`).join('\n'),
        });
      }
    }
    for (const pt of card.key_points || []) {
      const arrow = pt.split('→');
      if (arrow.length === 2) {
        fc.push({ front: arrow[0].trim(), back: arrow[1].trim() });
      }
    }
    const src = (card.source || '').split('#')[0];
    for (const q of subj.questions || []) {
      if (src && q.source_detail && q.source_detail.includes(src)) {
        fc.push({
          front: q.question,
          back: `✓ ${q.options[q.correct]}\n\n${q.explanation || ''}`,
        });
      }
    }
    if (card.prof_tip) {
      fc.push({
        front: `💡 Esempio del prof su: ${card.topic}`,
        back: card.prof_tip,
      });
    }
    if (!fc.length && (card.key_points || []).length) {
      fc.push({ front: card.topic, back: card.key_points.join('\n• ') });
    }
    return fc;
  }

  function openLessons(initialSubjectId) {
    state.view = 'lessons';
    setHeader('Lezioni & Flashcard', true);
    let activeSubj = initialSubjectId || state.data.subjects[0]?.id || 'privato';

    mainEl.innerHTML = `
      <div class="chips-row" id="les-chips">
        ${state.data.subjects.map((s) => `
          <button class="chip ${activeSubj === s.id ? 'active' : ''}" data-id="${esc(s.id)}">
            ${esc(s.name)} (${(s.summaries || []).length})
          </button>
        `).join('')}
      </div>
      <input type="search" id="les-search" class="search-input" placeholder="Filtra per data o argomento..." />
      <div id="les-list" class="lesson-day-group"></div>
    `;

    const listEl = document.getElementById('les-list');
    const searchEl = document.getElementById('les-search');

    function renderList() {
      const subj = state.data.subjects.find((s) => s.id === activeSubj);
      if (!subj) return;
      const f = searchEl.value.trim().toLowerCase();
      const cards = [...(subj.summaries || [])].sort((a, b) =>
        (a.sort_key || '9999').localeCompare(b.sort_key || '9999')
      );
      const filtered = cards.filter((c) =>
        !f ||
        (c.topic || '').toLowerCase().includes(f) ||
        (c.date_label || '').toLowerCase().includes(f) ||
        (c.source || '').toLowerCase().includes(f)
      );
      if (!filtered.length) {
        listEl.innerHTML = `<div class="empty-state card">Nessuna lezione trovata.</div>`;
        return;
      }

      let html = '';
      let lastDay = null;
      filtered.forEach((c, idx) => {
        const day = c.date_label || 'Materiali e Dispense';
        if (day !== lastDay) {
          lastDay = day;
          html += `<div class="day-header">📅 ${esc(day)}</div>`;
        }
        const fcCount = buildFlashcardsForLesson(subj, c).length;
        html += `
          <div class="topic-item" data-cidx="${idx}">
            <div style="min-width:0">
              <div style="font-weight:600">${esc(c.topic)}</div>
              <div class="topic-meta">${esc(c.source || '')} · 🃏 ${fcCount} flashcard</div>
            </div>
            <span class="badge">Apri →</span>
          </div>
        `;
      });
      listEl.innerHTML = html;

      listEl.querySelectorAll('.topic-item').forEach((el) => {
        el.addEventListener('click', () => openLessonDetail(subj, filtered[Number(el.dataset.cidx)]));
      });
    }

    document.getElementById('les-chips').querySelectorAll('.chip').forEach((ch) => {
      ch.addEventListener('click', () => {
        activeSubj = ch.dataset.id;
        document.getElementById('les-chips').querySelectorAll('.chip').forEach((x) => x.classList.remove('active'));
        ch.classList.add('active');
        renderList();
      });
    });
    searchEl.addEventListener('input', renderList);
    renderList();
  }

  function openLessonDetail(subj, card) {
    state.view = 'lesson_detail';
    state.subjectId = subj.id;
    setHeader(card.date_label ? `${subj.name} · ${card.date_label}` : subj.name, true);
    const flashcards = buildFlashcardsForLesson(subj, card);
    const srcBase = (card.source || '').split('#')[0];
    const relatedExamples = (subj.examples || []).filter((e) =>
      srcBase && e.source && e.source.includes(srcBase)
    );

    let fcIdx = 0;
    let mode = 'flashcards'; // flashcards | summary | examples

    function render() {
      let body = `
        <div class="card">
          <div class="source-caption">${esc(card.date_label || subj.name)} · ${esc(card.source || '')}</div>
          <div style="font-size:1.08rem;font-weight:700;margin-top:4px">${esc(card.topic)}</div>
          <div class="view-tabs" style="margin-top:12px">
            <button class="view-tab ${mode === 'flashcards' ? 'active' : ''}" data-m="flashcards">🃏 Flashcard (${flashcards.length})</button>
            <button class="view-tab ${mode === 'summary' ? 'active' : ''}" data-m="summary">📖 Scheda & Diagramma</button>
            <button class="view-tab ${mode === 'examples' ? 'active' : ''}" data-m="examples">💡 Prof (${relatedExamples.length})</button>
          </div>
        </div>
      `;

      if (mode === 'flashcards') {
        const cur = flashcards[fcIdx] || { front: card.topic, back: 'Nessuna flashcard' };
        body += `
          <div class="quiz-header">
            <span>Flashcard ${fcIdx + 1} di ${flashcards.length}</span>
            <span class="badge">Tocca per girare</span>
          </div>
          <div class="flashcard-stage" id="fc-stage">
            <div class="flashcard-inner">
              <div class="flashcard-face">
                <div class="flashcard-label">Domanda / Concetto</div>
                <div class="flashcard-body" style="white-space:pre-line">${esc(cur.front)}</div>
                <div class="flashcard-hint">👆 Tocca la carta per vedere la risposta</div>
              </div>
              <div class="flashcard-face flashcard-back">
                <div class="flashcard-label" style="color:var(--accent)">Risposta / Sintesi</div>
                <div class="flashcard-body" style="white-space:pre-line;font-size:0.96rem">${esc(cur.back)}</div>
                <div class="flashcard-hint">👆 Tocca per tornare al fronte</div>
              </div>
            </div>
          </div>
          <div class="fc-controls">
            <button class="btn btn-secondary" id="fc-prev" ${fcIdx === 0 ? 'disabled' : ''}>← Prec</button>
            <button class="btn btn-secondary" id="fc-flip">🔄 Gira</button>
            <button class="btn btn-primary" id="fc-next" ${fcIdx >= flashcards.length - 1 ? 'disabled' : ''}>Succ →</button>
          </div>
        `;
      } else if (mode === 'summary') {
        body += `
          <div class="card">
            <ul class="summary-points">
              ${(card.key_points || []).map((pt) => `<li>${esc(pt)}</li>`).join('')}
            </ul>
            ${(card.schema && card.schema.length) ? `
              <div class="diagram-wrap">
                <div class="diag-root">${esc(card.topic)}</div>
                <div class="diag-arrow">▼</div>
                <div class="diag-branches">
                  ${card.schema.map((n, idx) => `
                    <div class="diag-branch c${idx % 4}">
                      <div class="diag-branch-head">${esc(n.nodo)}</div>
                      ${(n.figli && n.figli.length) ? `
                        <div class="diag-leaves">
                          ${n.figli.map((fg) => `<div class="diag-leaf">${esc(fg)}</div>`).join('')}
                        </div>
                      ` : ''}
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}
            ${(card.norme && card.norme.length) ? `
              <div class="norme-row">
                ${card.norme.map((n) => `<span class="norma-pill">${esc(n)}</span>`).join('')}
              </div>
            ` : ''}
            ${card.prof_tip ? `
              <div class="prof-example-box" style="margin-top:10px">
                <div class="prof-example-title">💡 Nota / esempio del prof</div>
                <div>${esc(card.prof_tip)}</div>
              </div>
            ` : ''}
          </div>
        `;
      } else {
        if (!relatedExamples.length && !card.prof_tip) {
          body += `<div class="card empty-state">Nessun esempio audio collegato specificamente a questo file.</div>`;
        } else {
          if (card.prof_tip) {
            body += `<div class="card"><div class="prof-example-box"><div class="prof-example-title">💡 Nota sintetica del prof</div>${esc(card.prof_tip)}</div></div>`;
          }
          body += relatedExamples.map((e) => `
            <div class="card">
              <div style="font-weight:700;margin-bottom:4px">${esc(e.topic || 'Esempio a lezione')}</div>
              <div style="font-size:0.92rem">${esc(e.text)}</div>
            </div>
          `).join('');
        }
      }

      mainEl.innerHTML = body;

      mainEl.querySelectorAll('.view-tab').forEach((t) => {
        t.addEventListener('click', () => {
          mode = t.dataset.m;
          render();
        });
      });

      if (mode === 'flashcards') {
        const stage = document.getElementById('fc-stage');
        stage.addEventListener('click', () => stage.classList.toggle('flipped'));
        document.getElementById('fc-flip').addEventListener('click', () => stage.classList.toggle('flipped'));
        document.getElementById('fc-prev').addEventListener('click', () => {
          if (fcIdx > 0) { fcIdx--; render(); }
        });
        document.getElementById('fc-next').addEventListener('click', () => {
          if (fcIdx < flashcards.length - 1) { fcIdx++; render(); }
        });
      }
    }

    render();
  }

  async function init() {
    initTheme();
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js').catch(() => {});
    }
    try {
      const res = await fetch('./data/quizzes.json');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      state.data = await res.json();
      openHome();
    } catch (err) {
      mainEl.innerHTML = `<div class="card empty-state">Impossibile caricare i quiz (${esc(err.message)}).</div>`;
    }
  }

  init();
})();

