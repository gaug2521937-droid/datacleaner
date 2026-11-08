/* ==================================================================
   DataCleaner · 04-actions.js — действия, модальные сценарии,
   AI-поток, «Самопроверка», привязка событий и запуск приложения.
   ================================================================== */

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) { /* переходим к запасному способу */ }
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e) { return false; }
  }

  function letterText(subject, body) { return 'Тема: ' + subject + '\n\n' + body; }

  function download(name, text, mime) {
    try {
      var blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1200);
      return true;
    } catch (e) { return false; }
  }

  /* ---------------------------- новый запрос ---------------------------- */
  function openNewRequestModal() {
    if (!state.brokers.length) { toast('Каталог не загружен', 'bad'); return; }
    var options = state.brokers.map(function (b) {
      return '<option value="' + esc(b.id) + '">' + esc(b.name) + ' · ' +
        esc(CATEGORY_LABELS[b.category] || b.category) + (b.custom ? ' · свой' : '') + '</option>';
    }).join('');
    var html = '<div class="field"><label for="nr-broker">Сервис</label><select id="nr-broker">' + options + '</select></div>' +
      '<div class="field"><label for="nr-lang">Язык письма</label><select id="nr-lang">' +
      '<option value="">Автоматически (по языку сервиса)</option>' +
      '<option value="ru">Русский — ст. 14 и 21 152-ФЗ, срок 30 дней</option>' +
      '<option value="en">English — GDPR Art. 17 и CCPA</option></select></div>' +
      '<div class="banner info" style="margin:0">' + ICONS.info +
      '<div>Письмо собирается локально: ФИО, email и телефоны подставляются в текст на вашем устройстве и в AI не отправляются. ' +
      'Пустые поля в письмо не попадают.</div></div>';
    openModal('Новый запрос', html, [
      {
        label: 'Создать', cls: 'primary', icon: 'mail', onClick: async function (btn) {
          var brokerId = $('#nr-broker').value;
          var lang = $('#nr-lang').value || null;
          btn.disabled = true;
          try {
            var res = await Api.createRequest(brokerId, lang);
            closeModal();
            renderRequests();
            toast('Запрос создан: ' + (res.request ? res.request.broker_name : brokerId));
            if (state.settings && state.settings.autopilot && state.settings.autopilot.auto_send) {
              toast('Автопилот включён — заберу черновик на следующем цикле', 'warn', 6000);
            }
            await showLetter(res.request.id);
          } catch (e) {
            toast('Не удалось создать запрос: ' + e.message, 'bad', 6000);
            btn.disabled = false;
          }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  /* ------------------------------ письмо ------------------------------ */
  async function showLetter(id) {
    try {
      var data = await Api.getRequestFull(id);
      var letter = data.letter || {};
      var req = data.request || {};
      var body = '<div class="inline" style="margin-bottom:10px">' +
        '<span class="pill ' + (STATUS_CLASS[req.status] || 'neutral') + '">' + esc(STATUS_LABELS[req.status] || req.status) + '</span>' +
        '<span class="badge lang">' + esc((letter.language || 'ru') === 'en' ? 'EN · GDPR / CCPA' : 'RU · 152-ФЗ') + '</span>' +
        (req.to_email ? '<span class="badge lang">' + esc(req.to_email) + '</span>' : '<span class="badge lang">отправка через форму</span>') +
        '</div>' +
        '<div class="field"><label>Тема</label><div class="letter" style="max-height:none">' + esc(letter.subject || req.subject || '') + '</div></div>' +
        '<div class="letter" style="max-height:340px">' + esc(letter.body || req.body || '') + '</div>' +
        ((data.events || []).length ? '<h3 style="margin:16px 0 8px;font-size:13px">История</h3><div class="dl-list" style="max-height:170px">' +
          data.events.map(function (ev) {
            return '<div class="dl"><span class="pill neutral">' + esc(ev.type) + '</span>' +
              '<span class="nm">' + esc(ev.note || (ev.from_status + ' → ' + ev.to_status)) + '</span>' +
              '<span class="dt">' + esc(fmtDateTime(ev.at)) + '</span></div>';
          }).join('') + '</div>' : '');

      var buttons = [
        {
          label: 'Копировать', icon: 'copy', onClick: async function () {
            var ok = await copyText(letterText(letter.subject || '', letter.body || ''));
            toast(ok ? 'Письмо в буфере обмена' : 'Не удалось скопировать — выделите текст вручную', ok ? 'ok' : 'warn');
          }
        },
        {
          label: 'Скачать .txt', onClick: function () {
            download('datacleaner-request-' + id + '.txt', letterText(letter.subject || '', letter.body || ''));
            toast('Файл письма сохранён');
          }
        }
      ];
      if (req.to_email && (letter.subject || req.subject)) {
        buttons.splice(1, 0, {
          label: 'Открыть в почте', icon: 'send', onClick: function () {
            try {
              var firstEmail = listOf(state.profile.emails)[0] || '';
              var reply = firstEmail ? '&body=' + encodeURIComponent((letter.body || '') + '\n\n— \n' + firstEmail) : '';
              var url = 'mailto:' + encodeURIComponent(req.to_email) + '?subject=' + encodeURIComponent(letter.subject || '') + reply;
              window.open(url, '_blank');
            } catch (e) { toast('Почтовый клиент не открылся', 'warn'); }
          }
        });
      }
      buttons.push({ label: 'Закрыть', cls: 'ghost', onClick: closeModal });
      openModal(req.broker_name || 'Письмо', body, buttons);
    } catch (e) {
      toast('Не удалось открыть письмо: ' + e.message, 'bad', 6000);
    }
  }

  function showLetterResult(title, letter, hint) {
    var body = '<div class="badge lang" style="margin-bottom:10px">' +
      esc((letter.language || 'ru') === 'en' ? 'EN' : 'RU') + ' · ' + esc(letter.kind || 'letter') + '</div>' +
      '<div class="field"><label>Тема</label><div class="letter" style="max-height:none">' + esc(letter.subject || '') + '</div></div>' +
      '<div class="letter" style="max-height:340px">' + esc(letter.body || '') + '</div>' +
      (hint ? '<div class="banner info" style="margin:12px 0 0">' + ICONS.info + '<div>' + esc(hint) + '</div></div>' : '');
    openModal(title, body, [
      {
        label: 'Копировать', icon: 'copy', onClick: async function () {
          var ok = await copyText(letterText(letter.subject || '', letter.body || ''));
          toast(ok ? 'Текст в буфере обмена' : 'Скопируйте вручную', ok ? 'ok' : 'warn');
        }
      },
      {
        label: 'Скачать .txt', onClick: function () {
          download('datacleaner-' + (letter.kind || 'letter') + '.txt', letterText(letter.subject || '', letter.body || ''));
        }
      },
      { label: 'Закрыть', cls: 'ghost', onClick: closeModal }
    ]);
  }

  /* ---------------------------- свой сервис ---------------------------- */
  function openAddBrokerModal() {
    var html = '<div class="row">' +
      '<div class="field"><label for="nb-name">Название</label><input id="nb-name" type="text" placeholder="ООО «Ромашка»"></div>' +
      '<div class="field"><label for="nb-cat">Категория</label><select id="nb-cat">' +
      '<option value="data_broker">Брокер данных</option><option value="people_search">People-search</option>' +
      '<option value="marketing">Маркетинг</option><option value="search">Поисковик</option></select></div></div>' +
      '<div class="row">' +
      '<div class="field"><label for="nb-method">Способ</label><select id="nb-method">' +
      '<option value="email">Письмо на email</option><option value="form">Форма на сайте</option>' +
      '<option value="manual">Вручную</option></select></div>' +
      '<div class="field"><label for="nb-lang">Язык письма</label><select id="nb-lang">' +
      '<option value="ru">Русский (152-ФЗ)</option><option value="en">English (GDPR)</option></select></div></div>' +
      '<div class="row">' +
      '<div class="field"><label for="nb-email">Email для требований</label><input id="nb-email" type="text" placeholder="privacy@example.com"></div>' +
      '<div class="field"><label for="nb-url">Сайт / страница формы</label><input id="nb-url" type="text" placeholder="https://example.com/privacy"></div></div>' +
      '<div class="field"><label for="nb-notes">Заметка</label><input id="nb-notes" type="text" placeholder="Например: форма в разделе «Privacy»"></div>';
    openModal('Свой сервис', html, [
      {
        label: 'Добавить', cls: 'primary', onClick: async function () {
          var name = clean($('#nb-name').value);
          if (!name) { toast('Укажите название', 'warn'); return; }
          var email = clean($('#nb-email').value);
          var url = clean($('#nb-url').value);
          var method = $('#nb-method').value;
          if (method === 'email' && !email) { toast('Для отправки письмом нужен email', 'warn'); return; }
          var id = 'custom-' + String(name).toLowerCase().replace(/[^a-z0-9а-я]+/gi, '-').slice(0, 40) + '-' + Date.now().toString(36);
          try {
            await Api.addBroker({
              id: id, name: name, category: $('#nb-cat').value, method: method,
              email: email, url: url, language: $('#nb-lang').value,
              notes: clean($('#nb-notes').value), deadline_days: $('#nb-lang').value === 'en' ? 30 : 30
            });
            closeModal();
            renderCatalog();
            toast('Сервис добавлен в каталог');
          } catch (e) { toast('Ошибка: ' + e.message, 'bad', 6000); }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  /* --------------------------- действия по запросу --------------------------- */
  async function actSend(id) {
    try {
      var res = await Api.send(id);
      renderRequests();
      var note = res.detail || 'Готово';
      toast(note, res.ok === false ? 'warn' : 'ok', 7000);
      if (res.dry_run) {
        /* Письмо не ушло (DRY_RUN или отправка через форму) — сразу показываем текст,
           чтобы его можно было скопировать и отправить из своей почты. */
        await showLetter(id);
      }
      if (state.demo) state.demo = null;
    } catch (e) { toast('Не удалось отправить: ' + e.message, 'bad', 7000); }
  }

  async function actStatus(id, status) {
    try {
      await Api.setStatus(id, status);
      renderRequests();
      toast('Статус: ' + (STATUS_LABELS[status] || status));
      if (state.demo) state.demo = null;
    } catch (e) { toast('Не удалось изменить статус: ' + e.message, 'bad', 7000); }
  }

  async function actNote(id) {
    var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0] || {};
    var html = '<div class="field"><label for="note-text">Заметка к запросу</label>' +
      '<textarea id="note-text" rows="4">' + esc(req.note || '') + '</textarea>' +
      '<div class="help">Например: «ответили, просят скан паспорта — отказать, ст. 20 152-ФЗ».</div></div>';
    openModal('Заметка · ' + (req.broker_name || ''), html, [
      {
        label: 'Сохранить', cls: 'primary', onClick: async function () {
          try {
            await Api.setStatus(id, null, clean($('#note-text').value));
            closeModal(); renderRequests(); toast('Заметка сохранена');
          } catch (e) { toast('Ошибка: ' + e.message, 'bad'); }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  async function actFollowup(id) {
    try {
      var res = await Api.followup(id);
      renderRequests();
      if (res.letter) {
        showLetterResult('Повторное требование', res.letter, res.detail);
      } else {
        toast(res.detail || 'Напоминание отправлено', res.ok ? 'ok' : 'warn', 7000);
      }
    } catch (e) { toast('Не удалось отправить напоминание: ' + e.message, 'bad', 7000); }
  }

  async function actComplaint(id) {
    try {
      var res = await Api.complaint(id);
      if (res.letter) showLetterResult('Жалоба регулятору', res.letter, res.hint);
      else toast(res.detail || 'Жалоба собрана');
    } catch (e) { toast('Не удалось собрать жалобу: ' + e.message, 'bad', 7000); }
  }

  async function actDelete(id) {
    var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0] || {};
    openModal('Удалить запрос?', '<p class="tiny">Запрос «' + esc(req.broker_name || '') + '» и его история будут удалены безвозвратно.</p>', [
      {
        label: 'Удалить', cls: 'danger', icon: 'trash', onClick: async function () {
          try {
            await Api.deleteRequest(id);
            closeModal(); renderRequests(); toast('Запрос удалён');
            if (state.demo) state.demo = null;
          } catch (e) { toast('Ошибка: ' + e.message, 'bad'); }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  /* ------------------------------- автоотправка ------------------------------- */
  async function actSendAll() {
    try {
      var res = await Api.bulkSend();
      renderRequests();
      var sentN = (res.sent || []).length, failN = (res.failed || []).length;
      toast(res.detail || ('Отправлено: ' + sentN + ', ошибок: ' + failN), failN ? 'warn' : 'ok', 7000);
      if (res.dry_run) toast('DRY_RUN=1: письма остались на сервере. Подключите SMTP в «Автопилоте» и выключите DRY_RUN.', 'warn', 9000);
      if (state.demo) state.demo = null;
    } catch (e) { toast('Ошибка отправки: ' + e.message, 'bad', 7000); }
  }

  async function actRunPilot() {
    try {
      var res = await Api.runAutopilot();
      if (!res.ok && res.detail) { toast(res.detail, 'warn', 7000); return; }
      renderPilotLog();
      if (state.view === 'requests') renderRequests();
      var rep = res.report || {};
      var sent = (rep.sent || []).length, fup = (rep.followups || []).length, err = (rep.errors || []).length;
      toast('Автопилот: отправлено ' + sent + ', напоминаний ' + fup + (err ? ', ошибок ' + err : '') + (rep.skipped ? ' · ' + rep.skipped : ''),
        err ? 'warn' : 'ok', 8000);
      if (state.demo) state.demo = null;
      await renderDashboard();
    } catch (e) { toast('Автопилот не отработал: ' + e.message, 'bad', 7000); }
  }

  /* --------------------------- настройки: почта --------------------------- */
  function smtpPayload() {
    var pass = $('#smtp-pass').value;
    var smtp = {
      host: clean($('#smtp-host').value),
      port: Number(clean($('#smtp-port').value) || 587),
      user: clean($('#smtp-user').value),
      from_addr: clean($('#smtp-from').value) || clean($('#smtp-user').value),
      from_name: clean($('#smtp-from-name').value) || 'DataCleaner',
      use_ssl: $('#smtp-ssl').checked,
      use_starttls: $('#smtp-starttls').checked
    };
    if (pass) smtp.password = pass;
    return { smtp: smtp };
  }

  /* ------------------------- вход через Google (OAuth) ------------------------- */
  async function actGoogleConnect() {
    if (!state.server) {
      toast('Вход через Google работает в серверной версии: в локальном режиме письма отправляются из вашей почты вручную.', 'warn', 8000);
      return;
    }
    var g = (state.settings || {}).google || {};
    if (!g.configured) {
      openModal('Как включить вход через Google', '' +
        '<p class="tiny">Один раз настраивается владельцем сервиса — 5 минут в Google Cloud, после этого вход для вас в один клик.</p>' +
        '<ol class="tiny" style="padding-left:18px;line-height:1.9;margin:10px 0">' +
        '<li><a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener noreferrer">Создать проект</a> в Google Cloud.</li>' +
        '<li>APIs &amp; Services → Library → включить <b>Gmail API</b>.</li>' +
        '<li>OAuth consent screen → External → добавить свой адрес в <b>Test users</b>, scope <span class="code">gmail.send</span>.</li>' +
        '<li>Credentials → Create credentials → <b>OAuth client ID</b> → Web application → Authorized redirect URI:<br>' +
        '<span class="code">' + esc(g.redirect_uri || (location.origin + '/api/mail/google/callback')) + '</span></li>' +
        '<li>В Render → Environment добавить <span class="code">GOOGLE_CLIENT_ID</span> и ' +
        '<span class="code">GOOGLE_CLIENT_SECRET</span> → Save.</li>' +
        '</ol>' +
        '<p class="tiny">После этого вернитесь сюда и нажмите «Войти через Google». Пароль вводится на странице Google, ' +
        'приложение его не видит.</p>', [
          { label: 'Понятно', cls: 'primary', onClick: closeModal }
        ]);
      return;
    }
    try {
      var res = await http('POST', 'api/mail/google/start', {});
      if (!res.ok || !res.auth_url) { toast(res.detail || 'Не удалось начать вход', 'bad', 8000); return; }
      var win = window.open(res.auth_url, '_blank', 'noopener');
      if (!win) { window.location.href = res.auth_url; return; }
      toast('Введите пароль Google в открывшемся окне и разрешите отправку писем', 'warn', 9000);
      /* ждём возврата: сервер запишет токен, интерфейс подхватит статус */
      var tries = 0;
      var timer = setInterval(async function () {
        tries += 1;
        try {
          var st = await http('GET', 'api/mail/google/status');
          if (st.connected) {
            clearInterval(timer);
            await reloadSettings();
            renderGoogleCard(); renderMailStatus(); renderDryRunTip(); paintPilotStrip();
            toast('Google подключён: письма будут уходить с ' + (st.email || 'вашего ящика'), 'ok', 9000);
          }
        } catch (e) { /* игнорируем, ждём дальше */ }
        if (tries > 60) clearInterval(timer);
      }, 3000);
    } catch (e) { toast('Ошибка входа: ' + e.message, 'bad', 8000); }
  }

  async function actGoogleDisconnect() {
    try {
      var res = await http('POST', 'api/mail/google/disconnect', {});
      await reloadSettings();
      renderGoogleCard(); renderMailStatus(); renderDryRunTip(); paintPilotStrip();
      toast(res.detail || 'Google отключён');
    } catch (e) { toast('Ошибка: ' + e.message, 'bad', 7000); }
  }

  async function reloadSettings() {
    try {
      state.settings = await http('GET', 'api/settings');
      state.serverMeta = await http('GET', 'api/health');
    } catch (e) { /* настройки недоступны — не критично */ }
  }

  async function actSaveSmtp(silent) {
    try {
      var payload = smtpPayload();
      var res = await Api.saveSettings(payload);
      state.settings = res;
      $('#smtp-pass').value = '';
      renderAutopilot();
      if (state.view === 'dashboard') paintPilotStrip();
      if (!silent) toast('Почта сохранена' + (state.settings.resolved && state.settings.resolved.ready ? ' — автопилот готов отправлять' : ''));
      return true;
    } catch (e) {
      toast('Не удалось сохранить: ' + e.message, 'bad', 7000);
      return false;
    }
  }

  async function actTestSmtp(sendTest) {
    var okSave = await actSaveSmtp(true);
    if (!okSave) return;
    toast('Проверяю SMTP…', 'warn', 2500);
    try {
      var res = await Api.testSmtp({ send_test: !!sendTest, probe_to: clean($('#smtp-from').value) || null });
      var via = res.transport === 'smtp' ? 'SMTP' : (res.transport ? 'HTTPS-API (' + res.transport + ')' : '');
      if (res.ok) toast((via ? via + ': ' : '') + (res.detail || 'Соединение установлено'), 'ok', 8000);
      else toast(res.detail || 'Не удалось подключиться', 'bad', 12000);
      if (res.dry_run && sendTest) toast('DRY_RUN=1: тестовое письмо не отправлено', 'warn', 7000);
    } catch (e) { toast('Проверка не удалась: ' + e.message, 'bad', 8000); }
  }

  async function actSavePilot() {
    try {
      var payload = {
        autopilot: {
          auto_send: $('#ap-autosend').checked,
          followup_enabled: $('#ap-followup').checked,
          followup_days: Math.max(1, Math.min(365, Number(clean($('#ap-days').value) || 30))),
          interval_minutes: Math.max(5, Math.min(1440, Number(clean($('#ap-interval').value) || 15)))
        }
      };
      state.settings = await Api.saveSettings(payload);
      renderAutopilot();
      paintPilotStrip();
      toast('Режимы сохранены');
      if (!(state.settings.resolved && state.settings.resolved.ready) && payload.autopilot.auto_send) {
        toast('Автоотправка включена, но почта не подключена — письма будут копиться в «Отправлено» с пометкой об ошибке.', 'warn', 9000);
      }
    } catch (e) { toast('Ошибка: ' + e.message, 'bad', 7000); }
  }

  /* ---------------------------------- AI ---------------------------------- */
  function aiContext() {
    try {
      var s = computeStats(state.requests, { profileFilled: Api.profileFilled() });
      return {
        requests_total: s.kpi.total, sent: s.kpi.sent, waiting: s.kpi.waiting,
        overdue: s.kpi.overdue, deleted: s.kpi.deleted, refused: s.kpi.refused,
        drafts: s.kpi.drafts, deletion_rate: s.kpi.deletion_rate,
        avg_response_days: s.kpi.avg_response_days,
        categories: s.categories || s.by_category || []
      };
    } catch (e) { return null; }
  }

  function pushChat(role, content) {
    var msg = { role: role, content: content, streaming: false };
    state.chat.push(msg);
    renderAI();
    return msg;
  }

  function chatHistory() {
    return state.chat
      .filter(function (m) { return m.role === 'user' || (m.role === 'assistant' && !m.streaming); })
      .map(function (m) { return { role: m.role, content: m.content }; });
  }

  function abortAi() {
    if (state.abort) { try { state.abort.abort(); } catch (e) { /* ignore */ } }
    state.abort = null;
    state.aiStreaming = false;
  }

  async function askStream(question) {
    var kinds = detectPII(question);
    if (kinds.length) { pushChat('system', piiWarning(kinds)); return; }

    pushChat('user', question);
    var botMsg = pushChat('assistant', '');
    botMsg.streaming = true;
    state.aiStreaming = true;
    renderAI();

    if (!state.server) {
      var res = await Api.ask(question, chatHistory().slice(0, -2));
      botMsg.streaming = false;
      state.aiStreaming = false;
      if (res.ok) {
        botMsg.content = res.answer;
      } else {
        state.chat = state.chat.filter(function (m) { return m !== botMsg; });
        pushChat('system', res.notConfigured ? (res.hint || 'AI не настроен') : (res.message || 'Не удалось получить ответ'));
      }
      Store.set(K.chat, state.chat.slice(-40));
      renderAI();
      return;
    }

    var ctrl = new AbortController();
    state.abort = ctrl;
    var timer = setTimeout(function () { ctrl.abort(); }, 120000);
    try {
      var resp = await fetch('api/assistant/stream', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' },
          accessToken() ? { 'X-Access-Token': accessToken() } : {}),
        body: JSON.stringify({ question: question, history: chatHistory().slice(0, -2), mode: state.aiMode, context: aiContext() }),
        signal: ctrl.signal
      });
      if (resp.status === 401) { abortAi(); showAccessModal(); return; }
      if (!resp.ok || !resp.body) {
        var txt = '';
        try { txt = await resp.text(); } catch (e) { /* ignore */ }
        throw new Error('HTTP ' + resp.status + (txt ? ' · ' + txt.slice(0, 140) : ''));
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        var parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].trim();
          if (line.indexOf('data:') !== 0) continue;
          var obj = null;
          try { obj = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }
          if (obj.delta) { botMsg.content += obj.delta; renderAI(); }
          else if (obj.blocked) { botMsg.content = obj.warning || 'Запрос заблокирован PII-фильтром.'; }
          else if (obj.not_configured) { botMsg.content = obj.hint || 'AI не настроен на сервере.'; }
          else if (obj.error_body || obj.error) {
            botMsg.content = (obj.error_body && (obj.error_body.message || obj.error_body)) || obj.message || 'Ошибка AI-провайдера.';
            if (typeof botMsg.content !== 'string') botMsg.content = JSON.stringify(botMsg.content);
          } else if (obj.done && obj.cached) { /* кэш сервера */ }
        }
      }
      botMsg.streaming = false;
      if (!botMsg.content) botMsg.content = 'Модель вернула пустой ответ. Попробуйте переформулировать вопрос.';
      state.aiStreaming = false;
      state.abort = null;
      Store.set(K.chat, state.chat.slice(-40));
      renderAI();
    } catch (err) {
      clearTimeout(timer);
      botMsg.streaming = false;
      state.aiStreaming = false;
      state.abort = null;
      if (err && err.name === 'AbortError') {
        if (!botMsg.content) botMsg.content = 'Запрос отменён.';
      } else {
        botMsg.content = botMsg.content || ('Ошибка: ' + (err.message || 'неизвестная'));
      }
      renderAI();
    } finally {
      clearTimeout(timer);
    }
  }

  function openAiSettingsModal() {
    if (state.server) {
      openModal('AI на сервере', '<div class="banner info" style="margin:0">' + ICONS.info +
        '<div>В серверном режиме ключ AI задаётся переменными окружения <span class="code">LLM_BASE_URL</span>, ' +
        '<span class="code">LLM_API_KEY</span>, <span class="code">LLM_MODEL</span> — и в браузер не попадает. ' +
        'Измените их в панели хостинга (Render → Environment) и перезапустите сервис.</div></div>' +
        '<div class="kv" style="margin-top:12px"><dt>Статус</dt><dd>' + (state.llmServer.configured ? 'подключён' : 'не настроен') + '</dd>' +
        '<dt>Модель</dt><dd>' + esc(state.llmServer.model || '—') + '</dd>' +
        '<dt>Провайдер</dt><dd>' + esc(state.llmServer.base_url_host || '—') + '</dd></div>',
        [{ label: 'Понятно', cls: 'primary', onClick: closeModal }]);
      return;
    }
    var html = '<div class="field"><label for="llm-base">Base URL (OpenAI-совместимый)</label>' +
      '<input id="llm-base" type="text" value="' + esc(state.llm.base_url || '') + '" placeholder="https://provider.com/v1"></div>' +
      '<div class="field"><label for="llm-key">API-ключ</label>' +
      '<input id="llm-key" type="password" value="' + esc(state.llm.api_key || '') + '" placeholder="sk-...">' +
      '<div class="help">Ключ хранится только в localStorage этого браузера и уходит напрямую провайдеру.</div></div>' +
      '<div class="field"><label for="llm-model">Модель</label>' +
      '<input id="llm-model" type="text" value="' + esc(state.llm.model || '') + '" placeholder="gpt-6-luna"></div>' +
      '<div class="banner info" style="margin:0">' + ICONS.info +
      '<div>Если провайдер не разрешает CORS, запрос из браузера не пройдёт — используйте серверную версию DataCleaner.</div></div>';
    openModal('Настройки AI', html, [
      {
        label: 'Сохранить', cls: 'primary', onClick: async function () {
          try {
            await Api.saveLlm({
              base_url: clean($('#llm-base').value),
              api_key: clean($('#llm-key').value),
              model: clean($('#llm-model').value)
            });
            closeModal(); renderAI(); refreshModels(true);
            toast('Настройки AI сохранены');
          } catch (e) { toast('Ошибка: ' + e.message, 'bad'); }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  async function refreshModels(silent) {
    try {
      var res = await Api.models();
      if (!(res && res.models && res.models.length) && !silent) {
        toast('Список моделей недоступен: ' + ((res && res.detail) || 'AI не настроен'), 'warn', 6000);
      }
      renderAI();
    } catch (e) { if (!silent) toast('Модели: ' + e.message, 'warn'); }
  }

  /* -------------------------------- профиль -------------------------------- */
  function readProfileForm() {
    return {
      full_name: clean($('#pf-name').value),
      emails: listOf($('#pf-emails').value),
      phones: listOf($('#pf-phones').value),
      city: clean($('#pf-city').value),
      birth_year: clean($('#pf-birth').value),
      address: clean($('#pf-address').value),
      language: $('#pf-lang').value
    };
  }

  async function actSaveProfile(previewOnly) {
    var p = readProfileForm();
    if (p.birth_year && !/^\d{4}$/.test(p.birth_year)) { toast('Год рождения — четыре цифры', 'warn'); return; }
    if (p.emails.length) {
      var bad = p.emails.filter(function (e) { return !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e); });
      if (bad.length) { toast('Похоже на ошибку в email: ' + bad[0], 'warn', 6000); return; }
    }
    if (previewOnly) { state.profile = p; renderProfilePreview(p); return; }
    try {
      var res = await Api.saveProfile(p);
      state.profile = p;
      state.profileUpdated = new Date().toISOString();
      renderProfile();
      toast(res.detail || 'Профиль сохранён');
    } catch (e) { toast('Не удалось сохранить: ' + e.message, 'bad', 7000); }
  }

  async function actExport(copy) {
    try {
      var data = await Api.exportData();
      if (copy) {
        var ok = await copyText(JSON.stringify(data, null, 2));
        toast(ok ? 'JSON скопирован в буфер' : 'Не удалось скопировать', ok ? 'ok' : 'warn');
        return;
      }
      var stamp = isoDay(todayDate());
      download('datacleaner-export-' + stamp + '.json', JSON.stringify(data, null, 2), 'application/json');
      toast('Файл экспорта сохранён. В нём персональные данные — храните аккуратно.', 'warn', 8000);
    } catch (e) { toast('Экспорт не удался: ' + e.message, 'bad', 7000); }
  }

  function actWipe() {
    var html = '<div class="banner info" style="margin:0">' + ICONS.warn +
      '<div>Будут удалены: профиль, все запросы с письмами и историей, свои сервисы, чат с AI. ' +
      (state.server ? 'Данные в базе SQLite на сервере.' : 'Данные в localStorage этого браузера.') +
      ' Отменить это нельзя.</div></div>' +
      '<div class="field" style="margin-top:14px"><label for="wipe-confirm">Введите DELETE для подтверждения</label>' +
      '<input id="wipe-confirm" type="text" placeholder="DELETE" autocomplete="off"></div>';
    openModal('Удалить все данные?', html, [
      {
        label: 'Удалить навсегда', cls: 'danger', icon: 'trash', onClick: async function () {
          if (clean($('#wipe-confirm').value).toUpperCase() !== 'DELETE') { toast('Введите DELETE', 'warn'); return; }
          try {
            var res = await Api.wipe();
            closeModal();
            state.demo = null;
            state.chat = [];
            state.settings = await Api.getSettings().catch(function () { return state.settings; });
            renderProfile(); renderRequests(); renderCatalog(); renderAI();
            await renderDashboard();
            toast(res.detail || 'Все данные удалены');
          } catch (e) { toast('Ошибка очистки: ' + e.message, 'bad', 7000); }
        }
      },
      { label: 'Отмена', cls: 'ghost', onClick: closeModal }
    ]);
  }

  /* ------------------------------ код доступа ------------------------------ */
  function showAccessModal() {
    var html = '<div class="banner info" style="margin:0">' + ICONS.info +
      '<div>Сервер защищён кодом доступа (ACCESS_TOKEN). Он хранится только в этом браузере.</div></div>' +
      '<div class="field" style="margin-top:14px"><label for="access-code">Код доступа</label>' +
      '<input id="access-code" type="password" placeholder="dc-…" autocomplete="off" autofocus></div>';
    openModal('Нужен код доступа', html, [
      {
        label: 'Войти', cls: 'primary', onClick: function () {
          var code = clean($('#access-code').value);
          if (!code) { toast('Введите код', 'warn'); return; }
          Store.set(K.token, code);
          closeModal();
          boot();
        }
      }
    ]);
  }

  /* ------------------------------ самопроверка ------------------------------ */
  function selfTest() {
    var results = [];
    function check(name, fn) {
      try {
        var out = fn();
        if (out === true) results.push({ name: name, pass: true, detail: 'ok' });
        else results.push({ name: name, pass: false, detail: typeof out === 'string' ? out : 'проверка не пройдена' });
      } catch (e) {
        results.push({ name: name, pass: false, detail: 'исключение: ' + e.message });
      }
    }

    var fullProfile = {
      full_name: 'Иван Иванов', emails: ['ivan@example.com'], phones: ['+7 900 000-00-00'],
      city: 'Петрозаводск', birth_year: '1990', address: 'ул. Ленина, 1', language: 'ru'
    };
    var emptyProfile = { full_name: '', emails: [], phones: [], city: '', birth_year: '', address: '', language: 'ru' };
    var ruBroker = { id: 'ru', name: 'ООО «Пример»', category: 'data_broker', method: 'email', email: 'privacy@example.ru', language: 'ru', deadline_days: 30 };
    var enBroker = { id: 'en', name: 'Spokeo', category: 'people_search', method: 'form', url: 'https://example.com', email: '', language: 'en', deadline_days: 45 };

    check('RU-письмо ссылается на ст. 14 и ст. 21 152-ФЗ', function () {
      var l = buildRuLetter(fullProfile, ruBroker);
      if (l.body.indexOf('статьи 14') === -1) return 'нет ссылки на ст. 14';
      if (l.body.indexOf('статьи 21') === -1) return 'нет ссылки на ст. 21';
      return true;
    });

    check('RU-письмо содержит срок 30 дней', function () {
      return buildRuLetter(fullProfile, ruBroker).body.indexOf('30 дней') !== -1 ? true : 'срок 30 дней не найден';
    });

    check('EN-письмо ссылается на Art. 17 GDPR и CCPA', function () {
      var l = buildEnLetter(fullProfile, enBroker);
      if (l.body.indexOf('Article 17 GDPR') === -1) return 'нет Article 17 GDPR';
      if (l.body.indexOf('CCPA') === -1) return 'нет CCPA';
      if (l.body.indexOf('§1798.105') === -1) return 'нет §1798.105';
      return true;
    });

    check('Язык письма берётся из сервиса, явный выбор его переопределяет', function () {
      if (buildLetter(fullProfile, enBroker).language !== 'en') return 'EN-сервис дал не английское письмо';
      if (buildLetter(fullProfile, ruBroker).language !== 'ru') return 'RU-сервис дал не русское письмо';
      if (buildLetter(fullProfile, enBroker, 'ru').language !== 'ru') return 'явный язык не переопределил язык сервиса';
      return true;
    });

    check('Пустые поля не попадают в письмо', function () {
      var body = buildRuLetter(emptyProfile, ruBroker).body;
      var bad = ['Адрес:', 'Город:', 'Год рождения:', 'Номер телефона:', 'Адрес электронной почты:', 'undefined', 'null'];
      for (var i = 0; i < bad.length; i++) {
        if (body.indexOf(bad[i]) !== -1) return 'в письме встретилось «' + bad[i] + '»';
      }
      return true;
    });

    check('Заполненные поля попадают в письмо', function () {
      var body = buildRuLetter(fullProfile, ruBroker).body;
      return (body.indexOf('Иван Иванов') !== -1 && body.indexOf('ivan@example.com') !== -1 && body.indexOf('ул. Ленина, 1') !== -1)
        ? true : 'не все поля подставлены';
    });

    check('Письмо без профиля остаётся корректным', function () {
      var l = buildEnLetter({}, enBroker);
      if (/undefined|NaN/.test(l.body + l.subject)) return 'в письме есть undefined/NaN';
      if (l.body.indexOf('a data subject') === -1) return 'нет подстановки «a data subject»';
      return true;
    });

    check('Повторное требование ссылается на истёкший срок', function () {
      var f = buildFollowup(fullProfile, ruBroker, 'ru', new Date(2026, 10, 8), '2026-09-01T10:00:00Z');
      if (f.subject.indexOf('Повторное') === -1) return 'нет пометки «Повторное»';
      if (f.body.indexOf('21 152-ФЗ') === -1) return 'нет ссылки на ст. 21 152-ФЗ';
      if (f.body.indexOf('30 дней') === -1) return 'нет срока 30 дней';
      if (f.body.indexOf('2026-09-01') === -1) return 'не подставлена дата первого требования';
      if (/undefined|NaN/.test(f.body)) return 'undefined/NaN в тексте';
      return true;
    });

    check('Жалоба в Роскомнадзор собирается без AI', function () {
      var c = buildLocalComplaint(fullProfile, { broker_name: 'Spokeo', sent_at: '2026-09-01T10:00:00Z', language: 'ru' });
      if (c.body.indexOf('Роскомнадзор') === -1) return 'нет адресата';
      if (c.body.indexOf('13.11') === -1) return 'нет статьи КоАП';
      if (/undefined|NaN/.test(c.body)) return 'undefined/NaN в тексте';
      return true;
    });

    check('PII-фильтр ловит email', function () {
      return detectPII('как удалить a@b.co?').indexOf('email') !== -1 ? true : 'email не найден';
    });

    check('PII-фильтр ловит телефон в разных формах', function () {
      var forms = ['+7 900 123-45-67', '+79001234567', '8 (900) 123-45-67'];
      for (var i = 0; i < forms.length; i++) {
        if (detectPII('мой номер ' + forms[i]).indexOf('phone') === -1) return 'не поймал: ' + forms[i];
      }
      return true;
    });

    check('PII-фильтр не блокирует обычный вопрос', function () {
      return detectPII('Как сослаться на ст. 21 152-ФЗ?').length === 0 ? true : 'ложное срабатывание';
    });

    check('PII-фильтр не падает на пустом вводе', function () {
      return (Array.isArray(detectPII('')) && detectPII(null).length === 0) ? true : 'ошибка на пустом вводе';
    });

    check('Статистика: KPI считаются верно', function () {
      var t = new Date(2026, 10, 8);
      var reqs = [
        { id: 1, status: 'deleted', broker_category: 'people_search', method: 'form', sent_at: '2026-09-20T10:00:00Z', responded_at: '2026-09-25T10:00:00Z', deleted_at: '2026-09-27T10:00:00Z', deadline_at: '2026-10-20' },
        { id: 2, status: 'deleted', broker_category: 'data_broker', method: 'email', sent_at: '2026-10-10T10:00:00Z', responded_at: '2026-10-15T10:00:00Z', deleted_at: '2026-10-16T10:00:00Z', deadline_at: '2026-11-09' },
        { id: 3, status: 'sent', broker_category: 'marketing', method: 'email', sent_at: '2026-09-30T10:00:00Z', deadline_at: '2026-10-30' },
        { id: 4, status: 'draft', broker_category: 'search', method: 'form' }
      ];
      var s = computeStats(reqs, { today: t, profileFilled: true });
      if (s.kpi.sent !== 3) return 'sent = ' + s.kpi.sent + ', ожидалось 3';
      if (s.kpi.deleted !== 2) return 'deleted = ' + s.kpi.deleted;
      if (s.kpi.overdue !== 1) return 'overdue = ' + s.kpi.overdue;
      if (s.kpi.drafts !== 1) return 'drafts = ' + s.kpi.drafts;
      if (s.kpi.deletion_rate !== 66.7) return 'deletion_rate = ' + s.kpi.deletion_rate + ', ожидалось 66.7';
      if (s.kpi.avg_response_days == null) return 'среднее время ответа не посчитано';
      return true;
    });

    check('Статистика: активность за 14 дней', function () {
      var t = new Date(2026, 10, 8);
      var reqs = [
        { id: 1, status: 'sent', method: 'email', broker_category: 'search', sent_at: '2026-11-08T09:00:00Z', deadline_at: '2026-12-08' },
        { id: 2, status: 'sent', method: 'email', broker_category: 'search', sent_at: '2026-11-08T11:00:00Z', deadline_at: '2026-12-08' },
        { id: 3, status: 'sent', method: 'email', broker_category: 'search', sent_at: '2026-10-26T11:00:00Z', deadline_at: '2026-11-25' }
      ];
      var s = computeStats(reqs, { today: t });
      if (s.activity.length !== 14) return 'дней в серии: ' + s.activity.length;
      var sum = s.activity.reduce(function (a, b) { return a + b.count; }, 0);
      if (sum !== 3) return 'сумма столбцов = ' + sum;
      if (s.activity[13].count !== 2) return 'за сегодня ожидалось 2';
      return true;
    });

    check('Дедлайн 30 дней: ожидание и просрочка', function () {
      var t = new Date(2026, 10, 8);
      var d1 = isoDay(addDays(t, 30));
      var s = computeStats([{ id: 1, status: 'sent', method: 'email', broker_category: 'search', sent_at: t.toISOString(), deadline_at: d1 }], { today: t });
      if (s.kpi.waiting !== 1) return 'waiting = ' + s.kpi.waiting;
      if (s.deadlines[0].days_left !== 30) return 'days_left = ' + s.deadlines[0].days_left;
      return true;
    });

    check('Статистика на пустом списке не даёт NaN', function () {
      var s = computeStats([]);
      var bad = Object.keys(s.kpi).some(function (k) { return typeof s.kpi[k] === 'number' && isNaN(s.kpi[k]); });
      if (bad) return 'в KPI есть NaN';
      if (s.tips.length !== 1) return 'ожидалась одна подсказка, получено ' + s.tips.length;
      return true;
    });

    check('Воронка: разрешённые и запрещённые переходы', function () {
      if (!canTransition('draft', 'sent')) return 'draft → sent должен быть разрешён';
      if (!canTransition('sent', 'responded')) return 'sent → responded должен быть разрешён';
      if (!canTransition('refused', 'draft')) return 'refused → draft («Повторить») должен быть разрешён';
      if (canTransition('deleted', 'sent')) return 'deleted → sent должен быть запрещён';
      return true;
    });

    check('Демо-статистика собирается и не содержит ПД', function () {
      var t = new Date(2026, 10, 8);
      var demo = buildDemoRequests(t);
      var s = computeStats(demo, { today: t, demo: true });
      if (demo.length !== 12) return 'записей: ' + demo.length;
      if (!s.kpi.deleted || !s.kpi.overdue) return 'демо не даёт ни удалений, ни просрочек';
      if (JSON.stringify(demo).indexOf('@') !== -1) return 'в демо-данных есть email';
      return true;
    });

    check('Экранирование HTML в выводе', function () {
      var out = esc('<script>alert(1)<\/script>');
      return (out.indexOf('<') === -1 && out.indexOf('&lt;') !== -1) ? true : 'экранирование не работает';
    });

    check('Сериализация состояния (JSON round-trip)', function () {
      var obj = { profile: fullProfile, requests: [{ id: 1, status: 'draft' }] };
      var back = JSON.parse(JSON.stringify(obj));
      return (back.profile.full_name === fullProfile.full_name && back.requests[0].status === 'draft')
        ? true : 'round-trip сломан';
    });

    check('Хранилище: запись, чтение, удаление', function () {
      var probe = 'dc.selftest.' + Date.now();
      var okWrite = Store.set(probe, { a: 1 });
      var back = Store.get(probe, null);
      Store.del(probe);
      if (!okWrite || !back || back.a !== 1) return 'запись/чтение не работает';
      return true;
    });

    var passed = results.filter(function (r) { return r.pass; }).length;
    var html = '<div class="pill ' + (passed === results.length ? 'ok' : 'bad') + '" style="margin-bottom:12px">' +
      passed + ' из ' + results.length + ' проверок пройдено</div>' +
      '<div class="stack" style="gap:8px;max-height:52vh;overflow:auto">' + results.map(function (r) {
        return '<div class="dl"><span class="pill ' + (r.pass ? 'ok' : 'bad') + '">' + (r.pass ? 'OK' : 'FAIL') + '</span>' +
          '<span class="nm" style="white-space:normal">' + esc(r.name) +
          (r.pass ? '' : '<br><span style="color:#fda4af">' + esc(r.detail) + '</span>') + '</span></div>';
      }).join('') + '</div>' +
      '<p class="tiny" style="margin-top:12px">Проверяются тексты писем (152-ФЗ, GDPR, CCPA), повторное требование и жалоба, ' +
      'пустые поля, PII-фильтр, KPI и воронка, дедлайн 30 дней, серия активности, переходы статусов, экранирование HTML и хранилище.</p>';
    openModal('Самопроверка логики', html, [{ label: 'Закрыть', cls: 'primary', onClick: closeModal }]);
    if (passed === results.length) toast('Самопроверка: все ' + results.length + ' проверок пройдены', 'ok');
    else toast('Самопроверка: ошибок — ' + (results.length - passed), 'bad', 6000);
  }

  /* ============================== ОБНОВЛЕНИЕ ============================== */
  async function refreshData() {
    if (state.server) {
      var rq = await http('GET', 'api/requests');
      state.requests = (rq && rq.items) || [];
    } else {
      state.requests = localRequests();
    }
    renderRequests();
    renderCatalog();
  }

  function renderBadge() {
    var badge = $('#mode-badge');
    if (!badge) return;
    var ready = state.settings && state.settings.resolved && state.settings.resolved.ready;
    badge.classList.toggle('live', !!state.server);
    badge.innerHTML = '<span class="dot"></span><span class="txt">' +
      (state.server ? ('сервер · ' + (ready ? 'почта ок' : 'без почты')) : 'локальный режим') + '</span>';
    badge.title = state.server
      ? 'Серверная версия: FastAPI + SQLite, автоотправка доступна'
      : 'Браузерный режим: данные в localStorage, письма отправляются вами';
  }

  /* ================================ СОБЫТИЯ ================================ */
  function bind() {
    $('#nav').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-view]');
      if (btn) navigate(btn.dataset.view);
    });
    $('#bottom-nav').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-view]');
      if (btn) navigate(btn.dataset.view);
    });
    $('#brand').addEventListener('click', function () { navigate('dashboard'); });
    $('#modal-close').addEventListener('click', closeModal);
    $('#modal').addEventListener('click', function (e) { if (e.target.id === 'modal') closeModal(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && $('#modal').classList.contains('open')) closeModal();
    });

    $('#btn-self-test').addEventListener('click', selfTest);

    $('#btn-demo').addEventListener('click', async function () {
      try {
        state.demo = await Api.demoStats();
        if (state.view !== 'dashboard') navigate('dashboard');
        paintDashboard(state.demo);
        toast('Загружена демо-статистика: данные не сохранены');
      } catch (e) { toast('Не удалось загрузить демо: ' + e.message, 'bad'); }
    });

    ['#btn-new-request-top', '#btn-new-request', '#btn-new-request-2'].forEach(function (sel) {
      var el = $(sel);
      if (el) el.addEventListener('click', openNewRequestModal);
    });
    $('#btn-add-broker').addEventListener('click', openAddBrokerModal);
    $('#btn-send-all').addEventListener('click', actSendAll);

    $('#status-filters').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-status]');
      if (!btn) return;
      state.filterStatus = btn.dataset.status;
      $$('#status-filters .chip').forEach(function (c) { c.classList.toggle('active', c === btn); });
      renderRequests();
    });

    $('#cat-filters').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-cat]');
      if (!btn) return;
      state.filterCat = btn.dataset.cat;
      $$('#cat-filters .chip').forEach(function (c) { c.classList.toggle('active', c === btn); });
      renderCatalog();
    });

    $('#broker-list').addEventListener('click', async function (e) {
      var btn = e.target.closest('button[data-act]');
      if (!btn) return;
      if (btn.dataset.act === 'create') {
        try {
          var res = await Api.createRequest(btn.dataset.broker, null);
          renderCatalog(); renderRequests();
          toast('Запрос создан');
          await showLetter(res.request.id);
          if (state.settings && state.settings.autopilot && state.settings.autopilot.auto_send) {
            toast('Автоотправка включена: черновик уйдёт на следующем цикле автопилота', 'warn', 7000);
          }
        } catch (err) { toast('Ошибка: ' + err.message, 'bad', 6000); }
      }
      if (btn.dataset.act === 'goto-request') navigate('requests');
      if (btn.dataset.act === 'del-broker') {
        try {
          await Api.deleteBroker(btn.dataset.broker);
          renderCatalog(); toast('Сервис удалён из каталога');
        } catch (err) { toast('Ошибка: ' + err.message, 'bad'); }
      }
    });

    $('#request-list').addEventListener('click', async function (e) {
      var btn = e.target.closest('button[data-act]');
      if (!btn) return;
      var id = btn.dataset.id;
      var act = btn.dataset.act;
      if (act === 'send') actSend(id);
      else if (act === 'status') actStatus(id, btn.dataset.status);
      else if (act === 'view') showLetter(id);
      else if (act === 'note') actNote(id);
      else if (act === 'followup') actFollowup(id);
      else if (act === 'complaint') actComplaint(id);
      else if (act === 'del') actDelete(id);
    });

    $('#pilot-toggle').addEventListener('change', async function () {
      var on = this.checked;
      try {
        state.settings = await Api.saveSettings({ autopilot: Object.assign({}, state.settings.autopilot, { auto_send: on }) });
        paintPilotStrip();
        renderAutopilot();
        toast(on ? 'Автоотправка включена' : 'Автоотправка выключена');
      } catch (e) { toast('Ошибка: ' + e.message, 'bad'); this.checked = !on; }
    });
    $('#pilot-run').addEventListener('click', actRunPilot);
    $('#pilot-open').addEventListener('click', function () { navigate('autopilot'); });

    $('#google-connect').addEventListener('click', actGoogleConnect);
    $('#google-disconnect').addEventListener('click', actGoogleDisconnect);

    $('#smtp-save').addEventListener('click', function () { actSaveSmtp(false); });
    $('#smtp-test').addEventListener('click', function () { actTestSmtp(false); });
    $('#smtp-test-send').addEventListener('click', function () { actTestSmtp(true); });
    $('#ap-save').addEventListener('click', actSavePilot);
    $('#ap-run').addEventListener('click', actRunPilot);

    $('#ai-modes').addEventListener('click', function (e) {
      var btn = e.target.closest('.chip[data-mode]');
      if (!btn) return;
      state.aiMode = btn.dataset.mode;
      $$('#ai-modes .chip').forEach(function (c) { c.classList.toggle('active', c === btn); });
    });
    $$('#view-ai .chip[data-q]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        $('#chat-input').value = chip.dataset.q;
        $('#chat-input').focus();
      });
    });
    $('#btn-ai-send').addEventListener('click', function () {
      if (state.aiStreaming) { abortAi(); toast('Запрос остановлен', 'warn'); return; }
      var q = clean($('#chat-input').value);
      if (!q) { toast('Напишите вопрос', 'warn'); return; }
      $('#chat-input').value = '';
      askStream(q);
    });
    $('#chat-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#btn-ai-send').click(); }
    });
    $('#btn-ai-clear').addEventListener('click', function () {
      abortAi();
      state.chat = [];
      Store.set(K.chat, []);
      renderAI();
      toast('Чат очищен');
    });
    $('#btn-ai-settings').addEventListener('click', openAiSettingsModal);
    $('#btn-models-refresh').addEventListener('click', function () { refreshModels(false); });
    $('#ai-model').addEventListener('change', async function () {
      if (state.server) return;
      await Api.saveLlm({ model: this.value });
      renderAI();
      toast('Модель: ' + this.value);
    });

    $('#profile-form').addEventListener('submit', function (e) { e.preventDefault(); actSaveProfile(false); });
    ['#pf-name', '#pf-emails', '#pf-phones', '#pf-city', '#pf-birth', '#pf-address'].forEach(function (sel) {
      var el = $(sel);
      if (el) el.addEventListener('input', function () { actSaveProfile(true); });
    });
    $('#pf-lang').addEventListener('change', function () { actSaveProfile(true); });
    $('#btn-profile-clear').addEventListener('click', function () {
      ['#pf-name', '#pf-emails', '#pf-phones', '#pf-city', '#pf-birth', '#pf-address'].forEach(function (sel) { $(sel).value = ''; });
      actSaveProfile(true);
      toast('Форма очищена (профиль на сервере не тронут — нажмите «Сохранить»)');
    });
    $('#btn-export').addEventListener('click', function () { actExport(false); });
    $('#btn-backup').addEventListener('click', function () { actExport(true); });
    $('#btn-wipe').addEventListener('click', actWipe);

    window.addEventListener('resize', function () {
      if (state.view === 'dashboard') {
        clearTimeout(window.__dcResize);
        window.__dcResize = setTimeout(function () { renderDashboard(); }, 220);
      }
    });
  }

  /* ================================ ЗАПУСК ================================ */
  async function boot() {
    try {
      await Api.init();
    } catch (e) {
      if (e && e.authRequired) { showAccessModal(); return; }
      toast('Ошибка загрузки: ' + e.message, 'bad', 8000);
    }
    renderBadge();
    refreshModels(true);
    renderRequests();
    renderCatalog();
    renderAutopilot();
    renderProfile();
    renderAI();
    await renderDashboard();
    navigate(state.view || 'dashboard');
    if (!state.profile.full_name) {
      setTimeout(function () {
        toast('Заполните профиль — без ФИО и email оператор не сможет вас идентифицировать', 'warn', 7000);
      }, 900);
    }
    if (state.server && state.serverMeta && state.serverMeta.dry_run) {
      setTimeout(function () {
        toast('DRY_RUN=1: письма не уходят. Подключите SMTP в «Автопилоте», чтобы отправлять по-настоящему.', 'warn', 9000);
      }, 1800);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    try { bind(); } catch (e) { console.error('bind', e); }
    boot();
  });

})();
