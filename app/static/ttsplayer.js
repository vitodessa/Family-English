/* Переиспользуемый плеер озвучки текста.
 *
 * Зачем: раньше пауза делала speechSynthesis.cancel() → при возобновлении
 * всё начиналось СНАЧАЛА. Здесь текст режется на предложения и проигрывается
 * по очереди: пауза запоминает текущее предложение, продолжение идёт с него,
 * а ⏮/⏭ перематывают по предложениям. Если задан реальный аудиофайл и он
 * доступен (ElevenLabs) — показываем нативный <audio controls> с полной
 * перемоткой; иначе работает голос браузера (SpeechSynthesis).
 *
 * Использование: TTSPlayer.mount(el, {text, audioSrc, slow});
 */
(function () {
  function splitSentences(text) {
    var parts = (text || "").replace(/\s+/g, " ").trim().match(/[^.!?]+[.!?]*/g);
    parts = (parts || []).map(function (s) { return s.trim(); }).filter(Boolean);
    return parts.length ? parts : (text ? [text.trim()] : []);
  }

  function mount(el, opts) {
    opts = opts || {};
    var parts = splitSentences(opts.text);
    if (!parts.length) { el.style.display = "none"; return; }

    el.classList.add("ttsp");
    el.innerHTML =
      '<div class="ttsp-row">' +
      '  <button type="button" class="btn ttsp-nav" data-a="rew" title="Предыдущее предложение">⏮</button>' +
      '  <button type="button" class="btn primary ttsp-play" data-a="play">▶️ Слушать</button>' +
      '  <button type="button" class="btn ttsp-nav" data-a="fwd" title="Следующее предложение">⏭</button>' +
      '  <label class="muted ttsp-speed">Скорость ' +
      '    <select data-a="speed">' +
      '      <option value="0.7">🐢 медленно</option>' +
      '      <option value="0.85">🚶 средне</option>' +
      '      <option value="1.0">🏃 обычно</option>' +
      '    </select>' +
      '  </label>' +
      '</div>' +
      '<div class="ttsp-prog muted"></div>' +
      '<audio class="ttsp-audio" data-a="audio" preload="auto" hidden></audio>';

    var playBtn = el.querySelector('[data-a="play"]');
    var rewBtn = el.querySelector('[data-a="rew"]');
    var fwdBtn = el.querySelector('[data-a="fwd"]');
    var speedSel = el.querySelector('[data-a="speed"]');
    var prog = el.querySelector(".ttsp-prog");
    var audio = el.querySelector('[data-a="audio"]');

    speedSel.value = opts.slow ? "0.7" : "0.85";
    function rate() { return parseFloat(speedSel.value) || 1; }

    var mode = "tts";      // 'tts' | 'audio'
    var idx = 0;           // текущее предложение
    var playing = false;
    var gen = 0;           // токен поколения: гасит устаревшие onend после cancel/паузы

    function renderProg() {
      if (mode !== "tts") return;
      prog.textContent = "Предложение " + (idx + 1) + " / " + parts.length;
    }
    function renderPlay() {
      playBtn.textContent = playing ? "⏸ Пауза" : (idx > 0 && !playing ? "▶️ Продолжить" : "▶️ Слушать");
    }

    // ---- Голос браузера (SpeechSynthesis) ----
    function speakFrom(i) {
      var myGen = ++gen;
      idx = i;
      renderProg();
      var u = new SpeechSynthesisUtterance(parts[i]);
      u.lang = "en-US";
      u.rate = rate();
      u.onend = function () {
        if (myGen !== gen) return;            // устаревший вызов — игнор
        if (i + 1 < parts.length) { speakFrom(i + 1); }
        else { playing = false; idx = 0; renderPlay(); renderProg(); }
      };
      u.onerror = function () {
        if (myGen !== gen) return;
        if (i + 1 < parts.length) { speakFrom(i + 1); }
        else { playing = false; renderPlay(); }
      };
      try { window.speechSynthesis.cancel(); } catch (e) {}
      try { window.speechSynthesis.speak(u); } catch (e) {}
    }
    function ttsPlayPause() {
      if (playing) { gen++; try { window.speechSynthesis.cancel(); } catch (e) {} playing = false; renderPlay(); return; }
      playing = true; renderPlay();
      speakFrom(idx);
    }
    function ttsStep(delta) {
      var ni = Math.min(parts.length - 1, Math.max(0, idx + delta));
      idx = ni; renderProg();
      if (playing) speakFrom(idx); else renderPlay();
    }

    // ---- Нативный аудиофайл (если доступен) ----
    function enableNative() {
      mode = "audio";
      el.querySelector(".ttsp-row").style.display = "none";
      prog.style.display = "none";
      audio.hidden = false;
      audio.controls = true;               // родная перемотка/пауза/продолжение
      audio.playbackRate = rate();
      audio.style.width = "100%";
    }

    // ---- Обработчики ----
    playBtn.onclick = function () { if (mode === "tts") ttsPlayPause(); };
    rewBtn.onclick = function () { if (mode === "tts") ttsStep(-1); };
    fwdBtn.onclick = function () { if (mode === "tts") ttsStep(1); };
    speedSel.onchange = function () {
      if (mode === "audio") { audio.playbackRate = rate(); return; }
      if (playing) speakFrom(idx);         // применить скорость сразу
    };

    // Попробовать реальный аудиофайл; если заработает — переключимся на него.
    if (opts.audioSrc) {
      audio.addEventListener("canplay", function () { if (mode === "tts") enableNative(); }, { once: true });
      audio.addEventListener("error", function () { /* остаёмся на голосе браузера */ });
      audio.src = opts.audioSrc;
    }

    // Остановить речь при уходе со страницы
    window.addEventListener("pagehide", function () { try { window.speechSynthesis.cancel(); } catch (e) {} });

    renderProg();
    renderPlay();
  }

  window.TTSPlayer = { mount: mount };
})();
