/* ==================================================================
   DataCleaner · 04-actions.js — действия, модальные сценарии,
   «Самопроверка», привязка событий и запуск приложения.
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

  function letterText(subject, body) {
    return 'Тема: ' + subject + '\n\n' + body;
  }

  /* ---------------------------- новый запрос ---------------------------- */
  function openNewRequestModal() {
    var options = state.brokers.map(function (b) {
      return '<option value="' + esc(b.id) + '">' + esc(b.name) + ' · ' +
        esc(CATEGORY_LABELS[b.category] || b.category) + (b.custom ? ' · свой' : '') + '</option>';
    }).join('');
    var html = '<div class="field"><label for="nr-broker">Сервис</label><select id="nr-broker">' + options + '</select></div>' +
      '<div class="field"><label for="nr-lang">Язык письма</label><select id="nr-lang">' +
      '<option value="">Автоматически (по языку сервиса)</option>' +
      '<option value="ru">Русский — ст. 14 и 21 152-ФЗ, срок 30 дней</option>' +
      '<option value="en">English — GDPR Art. 17 и CCPA</option></select></div>' +
      '<p class="tiny">Письмо собирается локально из вашего профиля. Пустые поля в текст не попадают.</p>';
    openModal('Новый запрос', html, [
      { label: 'Отмена', cls: 'ghost', onClick: closeModal },
      {
        label: 'Создать письмо', cls: 'primary', icon: 'mail', onClick: async function (btn) {
          btn.disabled = true;
          try {
            var brokerId = $('#nr-broker').value;
            var lang = $('#nr-lang').value || null;
            var res = await Api.createRequest(brokerId, lang);
            closeModal();
            await refreshAll();
            toast('Письмо создано и сохранено как черновик');
            var full = await Api.getRequestFull(res.request.id);
            openLetterModal(full.request, full.letter, full.events || []);
          } catch (e) {
            toast('Не удалось создать запрос: ' + e.message, 'bad', 6000);
          } finally { btn.disabled = false; }
        }
      }
    ]);
  }

  /* ------------------------------ письмо ------------------------------ */
  function openLetterModal(req, letter, events) {
    var broker = state.brokers.filter(function (b) { return b.id === req.broker_id; })[0] || {};
    var html = '<div class="inline" style="margin-bottom:12px">' + statusPill(req.status) +
      '<span class="pill neutral">' + esc(letter.language === 'en' ? 'English / GDPR' : 'Русский / 152-ФЗ') + '</span>' +
      (req.to_email ? '<span class="pill neutral">' + esc(req.to_email) + '</span>' : '') +
      (req.deadline_at ? '<span class="pill neutral">дедлайн ' + esc(fmtDate(req.deadline_at)) + '</span>' : '') +
      '</div>' +
      '<div class="field"><label>Тема письма</label><div class="letter" style="max-height:none">' + esc(letter.subject) + '</div></div>' +
      '<div class="field"><label>Текст письма</label><pre class="letter" id="letter-body">' + esc(letter.body) + '</pre></div>' +
      (broker.url ? '<p class="tiny">Ссылка сервиса: <a href="' + esc(broker.url) + '" target="_blank" rel="noopener noreferrer">' +
        esc(broker.url) + '</a> — проверьте актуальность перед отправкой.</p>' : '') +
      '<p class="tiny">Письмо отправляется как обычный текст: без трекинг-пикселей и внешних картинок. «Прочитано» не отслеживается.</p>' +
      ((events && events.length)
        ? '<div class="hr"></div><h3 style="font-size:13px;margin:0 0 6px">История изменений</h3><div class="timeline">' +
        events.map(function (e) {
          var cls = e.to_status === 'deleted' ? 'ok' : (e.to_status === 'refused' ? 'bad' : '');
          var label = e.type === 'created' ? 'Создан'
            : (e.type === 'send' ? 'Отправлен'
              : (e.type === 'send_failed' ? 'Ошибка отправки'
                : (e.type === 'repeat' ? 'Возвращён в черновик'
                  : (STATUS_LABELS[e.to_status] || e.type))));
          return '<div class="tl-item ' + cls + '">' + esc(label) +
            (e.note ? ' — ' + esc(e.note) : '') +
            '<span class="t-when">' + esc(fmtDateTime(e.at || e.created_at)) + '</span></div>';
        }).join('') + '</div>'
        : '');

    var buttons = [
      {
        label: 'Скопировать письмо', cls: 'primary', icon: 'copy', onClick: async function () {
          var ok = await copyText(letterText(letter.subject, letter.body));
          toast(ok ? 'Письмо скопировано в буфер' : 'Не удалось скопировать — выделите текст вручную', ok ? 'ok' : 'warn');
        }
      }
    ];
    if (req.method === 'email' && req.to_email) {
      buttons.push({
        label: 'Открыть в почте', cls: 'ghost', icon: 'mail', onClick: function () {
          location.href = 'mailto:' + encodeURIComponent(req.to_email) +
            '?subject=' + encodeURIComponent(letter.subject) +
            '&body=' + encodeURIComponent(letter.body);
        }
      });
    }
    if (broker.url) {
      buttons.push({
        label: 'Открыть форму', cls: 'ghost', icon: 'link', onClick: function () {
          window.open(broker.url, '_blank', 'noopener');
        }
      });
    }
    if (req.status === 'draft') {
      buttons.push({
        label: 'Отметить отправленным', cls: 'ok', icon: 'send', onClick: async function (btn) {
          btn.disabled = true;
          try {
            var res = await Api.send(req.id);
            closeModal();
            await refreshAll();
            toast(res.detail || 'Запрос отмечен отправленным', res.ok === false ? 'bad' : 'ok', 7000);
          } catch (e) {
            toast('Ошибка отправки: ' + e.message, 'bad', 7000);
          } finally { btn.disabled = false; }
        }
      });
    }
    openModal('Письмо · ' + req.broker_name, html, buttons);
  }

  /* ------------------------------ заметка ------------------------------ */
  function openNoteModal(req) {
    var html = '<div class="field"><label for="note-input">Заметка к запросу</label>' +
      '<textarea id="note-input" placeholder="Например: номер обращения с сайта, имя оператора, что ответили">' +
      esc(req.note || '') + '</textarea>' +
      '<div class="help">Заметки хранятся вместе с историей запроса.</div></div>';
    openModal('Заметка · ' + req.broker_name, html, [
      { label: 'Отмена', cls: 'ghost', onClick: closeModal },
      {
        label: 'Сохранить', cls: 'primary', icon: 'check', onClick: async function (btn) {
          btn.disabled = true;
          try {
            await Api.setStatus(req.id, null, $('#note-input').value);
            closeModal();
            await refreshAll();
            toast('Заметка сохранена');
          } catch (e) {
            toast('Ошибка: ' + e.message, 'bad');
          } finally { btn.disabled = false; }
        }
      }
    ]);
  }

  /* ---------------------------- свой сервис ---------------------------- */
  function openAddBrokerModal() {
    var html = '<div class="row"><div class="field"><label for="ab-name">Название сервиса</label>' +
      '<input id="ab-name" type="text" placeholder="Например: БКИ «Пример»"></div>' +
      '<div class="field"><label for="ab-cat">Категория</label><select id="ab-cat">' +
      ['people_search', 'data_broker', 'marketing', 'search', 'custom'].map(function (c) {
        return '<option value="' + c + '">' + esc(CATEGORY_LABELS[c]) + '</option>';
      }).join('') + '</select></div></div>' +
      '<div class="row"><div class="field"><label for="ab-method">Способ обращения</label><select id="ab-method">' +
      '<option value="email">email</option><option value="form">форма на сайте</option><option value="manual">вручную</option></select></div>' +
      '<div class="field"><label for="ab-lang">Язык письма</label><select id="ab-lang">' +
      '<option value="ru">Русский (152-ФЗ)</option><option value="en">English (GDPR/CCPA)</option></select></div></div>' +
      '<div class="row"><div class="field"><label for="ab-email">Email для запросов</label>' +
      '<input id="ab-email" type="text" placeholder="privacy@example.ru"></div>' +
      '<div class="field"><label for="ab-url">URL формы / сайта</label>' +
      '<input id="ab-url" type="text" placeholder="https://example.ru/privacy"></div></div>' +
      '<div class="field"><label for="ab-deadline">Срок ответа, дней</label>' +
      '<input id="ab-deadline" type="text" inputmode="numeric" value="30"></div>' +
      '<div class="field"><label for="ab-notes">Заметки</label>' +
      '<textarea id="ab-notes" placeholder="Где взял адрес, что нужно подтвердить"></textarea></div>';
    openModal('Свой сервис', html, [
      { label: 'Отмена', cls: 'ghost', onClick: closeModal },
      {
        label: 'Добавить', cls: 'primary', icon: 'check', onClick: async function (btn) {
          var name = clean($('#ab-name').value);
          if (!name) { toast('Укажите название', 'warn'); return; }
          var method = $('#ab-method').value;
          var email = clean($('#ab-email').value);
          var url = clean($('#ab-url').value);
          if (method === 'email' && !email) { toast('Для способа «email» нужен адрес', 'warn'); return; }
          if (method === 'form' && !url) { toast('Для способа «форма» нужен URL', 'warn'); return; }
          btn.disabled = true;
          try {
            await Api.addBroker({
              id: 'custom-' + Date.now(), name: name, category: $('#ab-cat').value, method: method,
              email: email, url: url, language: $('#ab-lang').value,
              notes: clean($('#ab-notes').value), deadline_days: Number($('#ab-deadline').value) || 30
            });
            closeModal();
            renderCatalog();
            toast('Сервис добавлен в каталог');
          } catch (e) {
            toast('Ошибка: ' + e.message, 'bad');
          } finally { btn.disabled = false; }
        }
      }
    ]);
  }

  /* --------------------------- настройки AI --------------------------- */
  function openAiSettingsModal() {
    if (state.server) {
      openModal('Настройки AI',
        '<p class="tiny">В серверном режиме ключ задаётся только переменными окружения на сервере — в браузер он не попадает.</p>' +
        '<div class="letter" style="max-height:none">LLM_API_KEY=&lt;ключ провайдера&gt;\nLLM_BASE_URL=' +
        esc(state.llmServer.base_url_host ? 'https://' + state.llmServer.base_url_host + '/v1' : 'https://tokenlavka.com/v1') +
        '\nLLM_MODEL=' + esc(state.llmServer.model || 'gpt-6-luna') + '</div>' +
        '<p class="tiny">После правки .env перезапустите uvicorn. Ключ из браузера не используется вообще.</p>',
        [{ label: 'Понятно', cls: 'primary', onClick: closeModal }]);
      return;
    }
    var cfg = state.llm || {};
    var html = '<div class="banner">' + ICONS.warn +
      '<div>Ключ хранится в localStorage этого браузера и уходит напрямую провайдеру. На чужом устройстве не сохраняйте ключ. Для продукта используйте серверный режим: там ключ не покидает сервер.</div></div>' +
      '<div class="field"><label for="llm-base">Base URL</label>' +
      '<input id="llm-base" type="text" placeholder="https://tokenlavka.com/v1" value="' + esc(cfg.base_url || '') + '">' +
      '<div class="help">OpenAI-совместимый адрес. Запрос уйдёт на {Base URL}/chat/completions.</div></div>' +
      '<div class="field"><label for="llm-key">API-ключ</label>' +
      '<input id="llm-key" type="password" placeholder="sk-..." value="' + esc(cfg.api_key || '') + '"></div>' +
      '<div class="field"><label for="llm-model">Модель</label>' +
      '<input id="llm-model" type="text" placeholder="gpt-6-luna" value="' + esc(cfg.model || '') + '">' +
      '<div class="help">Точный ID модели из документации провайдера.</div></div>';
    openModal('Настройки AI', html, [
      { label: 'Отмена', cls: 'ghost', onClick: closeModal },
      {
        label: 'Сохранить', cls: 'primary', icon: 'check', onClick: async function () {
          await Api.saveLlm({
            base_url: clean($('#llm-base').value),
            api_key: clean($('#llm-key').value),
            model: clean($('#llm-model').value)
          });
          closeModal();
          renderAI();
          toast('Настройки AI сохранены');
        }
      }
    ]);
  }

  /* ---------------------------- полная очистка ---------------------------- */
  function openWipeModal() {
    var html = '<div class="banner">' + ICONS.warn +
      '<div>Это необратимо: ' +
      (state.server
        ? 'будут удалены профиль, все запросы, история изменений и ваши сервисы в базе SQLite.'
        : 'будет очищен localStorage: профиль, запросы, история, свои сервисы и история чата.') +
      '</div></div>' +
      '<div class="field"><label for="wipe-confirm">Введите DELETE, чтобы подтвердить</label>' +
      '<input id="wipe-confirm" type="text" placeholder="DELETE" autocomplete="off"></div>';
    openModal('Удалить все данные?', html, [
      { label: 'Отмена', cls: 'ghost', onClick: closeModal },
      {
        label: 'Удалить всё', cls: 'danger', icon: 'trash', onClick: async function (btn) {
          if (clean($('#wipe-confirm').value).toUpperCase() !== 'DELETE') {
            toast('Введите DELETE для подтверждения', 'warn');
            return;
          }
          btn.disabled = true;
          try {
            var res = await Api.wipe();
            closeModal();
            await refreshAll();
            renderProfile();
            renderAI();
            toast(res.detail || 'Все данные удалены');
          } catch (e) {
            toast('Ошибка: ' + e.message, 'bad');
          } finally { btn.disabled = false; }
        }
      }
    ]);
  }

  /* ============================= САМОПРОВЕРКА ============================= */
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
      '<div class="self-test-result">' + results.map(function (r) {
        return '<div class="tr ' + (r.pass ? 'pass' : 'fail') + '"><span class="st">' + (r.pass ? 'OK' : 'FAIL') + '</span>' +
          '<div><div>' + esc(r.name) + '</div>' +
          (r.pass ? '' : '<div class="detail">' + esc(r.detail) + '</div>') + '</div></div>';
      }).join('') + '</div>' +
      '<p class="tiny" style="margin-top:12px">Проверяются тексты писем (152-ФЗ, GDPR, CCPA), пустые поля, PII-фильтр, KPI и воронка, дедлайн 30 дней, серия активности, переходы статусов, экранирование HTML и хранилище.</p>';
    openModal('Самопроверка логики', html, [{ label: 'Закрыть', cls: 'primary', onClick: closeModal }]);
    if (passed === results.length) toast('Самопроверка: все ' + results.length + ' проверок пройдены', 'ok');
    else toast('Самопроверка: ошибок — ' + (results.length - passed), 'bad', 6000);
  }

  /* ============================== ОБНОВЛЕНИЕ ============================== */
  async function refreshAll() {
    if (state.server) {
      var rq = await http('GET', 'api/requests');
      state.requests = (rq && rq.items) || [];
    } else {
      state.requests = localRequests();
    }
    if (state.view === 'dashboard') renderDashboard();
    if (state.view === 'requests') renderRequests();
    if (state.view === 'catalog') renderCatalog();
    if (state.view === 'data') renderData();
  }

  /* ================================ СОБЫТИЯ ================================ */
  function bind() {
    $('#nav').addEventListener('click', function (e) {
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
      } catch (e) {
        toast('Не удалось загрузить демо: ' + e.message, 'bad');
      }
    });

    $('#btn-new-request').addEventListener('click', openNewRequestModal);
    $('#btn-new-request-2').addEventListener('click', openNewRequestModal);
    $('#btn-add-broker').addEventListener('click', openAddBrokerModal);

    $('#profile-form').addEventListener('submit', async function (e) {
      e.preventDefault();
      var p = {
        full_name: clean($('#pf-name').value),
        emails: listOf($('#pf-emails').value),
        phones: listOf($('#pf-phones').value),
        city: clean($('#pf-city').value),
        birth_year: clean($('#pf-birth').value),
        address: clean($('#pf-address').value),
        language: $('#pf-lang').value
      };
      if (p.birth_year && !/^\d{4}$/.test(p.birth_year)) { toast('Год рождения — четыре цифры', 'warn'); return; }
      try {
        var res = await Api.saveProfile(p);
        renderProfile();
        toast(res.detail || 'Профиль сохранён');
      } catch (err) {
        toast('Ошибка сохранения: ' + err.message, 'bad', 6000);
      }
    });

    ['#pf-name', '#pf-emails', '#pf-phones', '#pf-city', '#pf-birth', '#pf-address'].forEach(function (sel) {
      var el = $(sel);
      if (el) el.addEventListener('input', function () {
        renderProfilePreview({
          full_name: $('#pf-name').value, emails: $('#pf-emails').value, phones: $('#pf-phones').value,
          city: $('#pf-city').value, birth_year: $('#pf-birth').value, address: $('#pf-address').value
        });
      });
    });

    $('#btn-profile-clear').addEventListener('click', function () {
      ['#pf-name', '#pf-emails', '#pf-phones', '#pf-city', '#pf-birth', '#pf-address'].forEach(function (s) { $(s).value = ''; });
      renderProfilePreview({});
      toast('Форма очищена — сохранённый профиль не изменился', 'warn', 5000);
    });

    $('#cat-filters').addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip) return;
      state.filterCat = chip.dataset.cat;
      $$('#cat-filters .chip').forEach(function (c) { c.classList.toggle('active', c === chip); });
      renderCatalog();
    });

    $('#status-filters').addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip) return;
      state.filterStatus = chip.dataset.status;
      $$('#status-filters .chip').forEach(function (c) { c.classList.toggle('active', c === chip); });
      renderRequests();
    });

    $('#broker-list').addEventListener('click', async function (e) {
      var btn = e.target.closest('button[data-act]');
      if (!btn) return;
      var act = btn.dataset.act;
      try {
        if (act === 'create') {
          btn.disabled = true;
          var res = await Api.createRequest(btn.dataset.broker, null);
          await refreshAll();
          toast('Черновик создан');
          var full = await Api.getRequestFull(res.request.id);
          openLetterModal(full.request, full.letter, full.events || []);
        }
        if (act === 'del-broker') {
          if (!confirm('Удалить этот сервис из каталога?')) return;
          await Api.deleteBroker(btn.dataset.broker);
          renderCatalog();
          toast('Сервис удалён');
        }
        if (act === 'goto-request') {
          state.filterStatus = 'all';
          $$('#status-filters .chip').forEach(function (c) { c.classList.toggle('active', c.dataset.status === 'all'); });
          navigate('requests');
        }
      } catch (err) {
        toast('Ошибка: ' + err.message, 'bad');
      } finally {
        btn.disabled = false;
      }
    });

    $('#request-list').addEventListener('click', async function (e) {
      var btn = e.target.closest('button[data-act]');
      if (!btn) return;
      var id = btn.dataset.id;
      var act = btn.dataset.act;
      var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) return;
      try {
        if (act === 'view') {
          var full = await Api.getRequestFull(id);
          openLetterModal(full.request, full.letter, full.events || []);
        }
        if (act === 'send') {
          btn.disabled = true;
          var res = await Api.send(id);
          await refreshAll();
          toast(res.detail || 'Готово', res.ok === false ? 'bad' : 'ok', 7000);
          if (res.ok !== false && req.method === 'email' && req.to_email) {
            var full2 = await Api.getRequestFull(id);
            openLetterModal(full2.request, full2.letter, full2.events || []);
          }
        }
        if (act === 'status') {
          var target = btn.dataset.status;
          if (target === 'draft' && !confirm('Вернуть запрос в черновик для повторной отправки?')) return;
          await Api.setStatus(id, target, null);
          await refreshAll();
          toast('Статус: ' + (STATUS_LABELS[target] || target));
        }
        if (act === 'note') openNoteModal(req);
        if (act === 'del') {
          if (!confirm('Удалить запрос и его историю?')) return;
          await Api.deleteRequest(id);
          await refreshAll();
          toast('Запрос удалён');
        }
      } catch (err) {
        toast('Ошибка: ' + err.message, 'bad', 6000);
      } finally {
        btn.disabled = false;
      }
    });

    $('#btn-ai-send').addEventListener('click', sendChat);
    $('#chat-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); }
    });
    $('#view-ai').addEventListener('click', function (e) {
      var chip = e.target.closest('.chip[data-q]');
      if (chip) { $('#chat-input').value = chip.dataset.q; sendChat(); }
    });
    $('#btn-ai-settings').addEventListener('click', openAiSettingsModal);
    $('#btn-ai-clear').addEventListener('click', function () {
      state.chat = [];
      Store.set(K.chat, []);
      renderAI();
      toast('История чата очищена');
    });

    $('#btn-export').addEventListener('click', async function () {
      try {
        var data = await Api.exportData();
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'datacleaner-export-' + isoDay(todayDate()) + '.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
        toast('Экспорт скачан. В файле ваши ПД — храните его аккуратно', 'warn', 7000);
      } catch (e) {
        toast('Ошибка экспорта: ' + e.message, 'bad');
      }
    });

    $('#btn-backup').addEventListener('click', async function () {
      try {
        var data = await Api.exportData();
        var ok = await copyText(JSON.stringify(data, null, 2));
        toast(ok ? 'JSON скопирован в буфер' : 'Не удалось скопировать (возможно, большой объём)', ok ? 'ok' : 'warn');
      } catch (e) {
        toast('Ошибка: ' + e.message, 'bad');
      }
    });

    $('#btn-wipe').addEventListener('click', openWipeModal);
  }

  /* ================================= ЗАПУСК ================================= */
  /* Код доступа: сервер вернул 401 с флагом auth_required */
  function askAccessToken(message) {
    var html = '<div class="banner">' + ICONS.warn +
      '<div>Этот сервер защищён кодом доступа: он закрывает API от посторонних.' +
      (message ? ' <br>' + esc(message) : '') + '</div></div>' +
      '<div class="field"><label for="access-code">Код доступа</label>' +
      '<input id="access-code" type="password" placeholder="ACCESS_TOKEN" autocomplete="off" autofocus>' +
      '<div class="help">Значение переменной окружения ACCESS_TOKEN на сервере. Хранится только в этом браузере.</div></div>';
    openModal('Нужен код доступа', html, [
      {
        label: 'Подключиться', cls: 'primary', icon: 'check', onClick: async function (btn) {
          var code = clean($('#access-code').value);
          if (!code) { toast('Введите код доступа', 'warn'); return; }
          Store.set(K.token, code);
          btn.disabled = true;
          closeModal();
          try {
            await Api.init();
            attachBadge();
            renderProfile(); renderAI(); renderCatalog(); renderRequests(); renderData();
            await renderDashboard();
            toast('Подключено к серверу');
          } catch (e) {
            if (e.authRequired) {
              Store.del(K.token);
              toast('Код не подошёл', 'bad');
              askAccessToken('Код не подошёл, попробуйте снова.');
            } else {
              toast('Ошибка: ' + e.message, 'bad', 8000);
            }
          } finally { btn.disabled = false; }
        }
      },
      {
        label: 'Работать локально', cls: 'ghost', onClick: function () {
          Store.del(K.token);
          state.server = false;
          state.brokers = BUILTIN_BROKERS.slice();
          state.requests = localRequests();
          state.profile = Store.get(K.profile, {}) || {};
          closeModal();
          attachBadge();
          renderProfile(); renderAI(); renderCatalog(); renderRequests(); renderData();
          renderDashboard();
          toast('Режим LOCAL: данные в этом браузере', 'warn', 6000);
        }
      }
    ]);
  }

  function attachBadge() {
    var badge = $('#mode-badge');
    badge.textContent = state.server ? 'server' : 'local';
    badge.classList.toggle('server', state.server);
    badge.title = state.server
      ? 'Подключено к FastAPI: данные в SQLite, зашифрованы Fernet'
      : 'Автономный режим: данные в localStorage вашего браузера';
  }

  async function boot() {
    bind();
    var needsToken = false;
    try {
      await Api.init();
    } catch (e) {
      if (e && e.authRequired) {
        needsToken = true;
      } else {
        console.error(e);
        toast('Ошибка инициализации: ' + e.message, 'bad', 8000);
      }
    }
    if (needsToken) {
      state.server = true;
      attachBadge();
      askAccessToken('');
      return;
    }
    attachBadge();

    if (!storageOK && !state.server) {
      toast('localStorage недоступен: данные будут потеряны после перезагрузки', 'warn', 9000);
    }
    try {
      renderProfile();
      renderAI();
      renderCatalog();
      renderRequests();
      renderData();
      await renderDashboard();
    } catch (e) {
      console.error(e);
      toast('Ошибка отрисовки: ' + e.message, 'bad', 8000);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

})();
