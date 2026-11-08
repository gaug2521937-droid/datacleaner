/* ==================================================================
   DataCleaner · 03-ui.js — рендеринг интерфейса.
   ================================================================== */

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var ICONS = {
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    reply: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17l-5-5 5-5"/><path d="M4 12h9a7 7 0 0 1 7 7v2"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.6L2.5 17a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 7l10 6 10-6"/></svg>'
  };

  /* ----------------------------- уведомления ----------------------------- */
  function toast(msg, type, ms) {
    var wrap = $('#toasts');
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'ok');
    var icon = (type === 'bad' || type === 'warn') ? ICONS.warn : ICONS.check;
    el.innerHTML = icon + '<div>' + esc(msg) + '</div>';
    wrap.appendChild(el);
    setTimeout(function () {
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 280);
    }, ms || 4200);
  }

  /* ------------------------------- модалки ------------------------------- */
  function openModal(title, bodyHTML, buttons, onMount) {
    $('#modal-title').textContent = title;
    $('#modal-body').innerHTML = bodyHTML;
    var foot = $('#modal-foot');
    foot.innerHTML = '';
    (buttons || []).forEach(function (b) {
      var el = document.createElement('button');
      el.className = 'btn ' + (b.cls || 'ghost');
      el.innerHTML = (b.icon ? ICONS[b.icon] : '') + '<span>' + esc(b.label) + '</span>';
      el.addEventListener('click', function () { if (b.onClick) b.onClick(el); });
      foot.appendChild(el);
    });
    $('#modal').classList.add('open');
    if (onMount) onMount();
  }
  function closeModal() {
    $('#modal').classList.remove('open');
  }

  function statusPill(status) {
    return '<span class="pill ' + (STATUS_CLASS[status] || 'neutral') + '">' + esc(STATUS_LABELS[status] || status) + '</span>';
  }

  function navigate(view) {
    state.view = view;
    $$('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + view); });
    $$('#nav button').forEach(function (b) { b.classList.toggle('active', b.dataset.view === view); });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (view === 'dashboard') renderDashboard();
    if (view === 'profile') renderProfile();
    if (view === 'catalog') renderCatalog();
    if (view === 'requests') renderRequests();
    if (view === 'ai') renderAI();
    if (view === 'data') renderData();
  }

  /* -------------------------------- ОБЗОР -------------------------------- */
  async function renderDashboard() {
    var stats = state.demo;
    if (!stats) {
      try { stats = await Api.stats(); }
      catch (e) { toast('Не удалось получить статистику: ' + e.message, 'bad'); return; }
    }
    paintDashboard(stats);
  }

  function barRow(label, value, percent, cls, overridePercent) {
    var pct = overridePercent != null ? overridePercent : (percent == null ? 0 : percent);
    pct = Math.max(0, Math.min(100, pct));
    return '<div class="bar-row"><div class="bar-head"><span>' + esc(label) + '</span><b>' + esc(String(value)) +
      (percent != null ? ' · ' + percent + '%' : '') + '</b></div>' +
      '<div class="bar-track"><div class="bar-fill ' + (cls || '') + '" style="width:' + pct + '%"></div></div></div>';
  }

  function paintDashboard(stats) {
    var k = stats.kpi;

    $('#kpi-sent').textContent = k.sent;
    $('#kpi-sent-hint').textContent = k.total
      ? 'из ' + k.total + ' ' + plural(k.total, 'запроса', 'запросов', 'запросов') + ' создано'
      : 'писем и обращений';
    $('#kpi-waiting').textContent = k.waiting;
    $('#kpi-waiting-hint').textContent = k.waiting ? 'в пределах 30 дней' : 'нет активных ожиданий';
    $('#kpi-overdue').textContent = k.overdue;
    $('#kpi-overdue-hint').textContent = k.overdue
      ? ('макс. просрочка ' + k.oldest_overdue_days + ' ' + plural(k.oldest_overdue_days, 'день', 'дня', 'дней'))
      : 'сроки соблюдаются';
    $('#kpi-deleted').textContent = k.deleted;
    $('#kpi-deleted-hint').textContent = k.deleted ? 'подтверждено сервисами' : 'пока нет подтверждений';

    var rate = Number(k.deletion_rate) || 0;
    $('#ring').style.setProperty('--p', rate);
    $('#ring-num').textContent = (rate % 1 === 0 ? rate.toFixed(0) : rate.toFixed(1)) + '%';
    $('#lg-deleted').textContent = k.deleted;
    $('#lg-responded').textContent = k.responded;
    $('#lg-refused').textContent = k.refused;
    $('#lg-drafts').textContent = k.drafts;

    $('#avg-days').textContent = k.avg_response_days == null ? '—' : String(k.avg_response_days).replace('.', ',');
    $('#avg-note').textContent = k.avg_response_days == null
      ? 'Пока нет ответов от сервисов — среднее появится после первого ответа.'
      : 'Считается по ' + (k.responded + k.deleted) + ' ' + plural(k.responded + k.deleted, 'ответу', 'ответам', 'ответам') + ' сервисов.';

    var base = Math.max(k.sent, 1);
    $('#rate-bars').innerHTML = [
      barRow('Удалено', k.deleted, Math.round(k.deleted / base * 100), 'c3'),
      barRow('Ответили, но не удалили', k.responded, Math.round(k.responded / base * 100), 'c4'),
      barRow('Отказ', k.refused, Math.round(k.refused / base * 100), 'c5'),
      barRow('Доля сервисов, ответивших на запрос', k.response_rate + '%', null, 'c2', Number(k.response_rate) || 0)
    ].join('');

    $('#funnel').innerHTML = stats.funnel.map(function (f, i) {
      var cls = ['c5', 'c2', 'c4', 'c3'][i] || 'c2';
      return barRow(f.label, f.count, f.percent, cls);
    }).join('');

    var maxDay = Math.max.apply(null, stats.activity.map(function (a) { return a.count; }).concat([1]));
    /* высота столбца считается от реальной высоты области графика (телефон/ПК) */
    var chartEl = $('#chart');
    var maxBarPx = Math.max(60, (chartEl.clientHeight || 168) - 30);
    var narrow = window.innerWidth < 560;
    chartEl.innerHTML = stats.activity.map(function (a, idx) {
      var h = a.count ? Math.max(10, Math.round(a.count / maxDay * maxBarPx)) : 4;
      var d = parseDay(a.date);
      var label = (d && (!narrow || idx % 2 === 1))
        ? String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0')
        : '';
      return '<div class="col" title="' + esc(a.date) + ': ' + a.count + '">' +
        '<div class="bar ' + (a.count ? '' : 'zero') + '" style="height:' + h + 'px"><span>' + a.count + '</span></div>' +
        '<div class="cl">' + esc(label) + '</div></div>';
    }).join('');

    $('#categories').innerHTML = stats.by_category.length
      ? stats.by_category.map(function (c, i) {
        return barRow(c.label, c.count, c.percent, ['c2', 'c3', 'c4', 'c5'][i % 4]);
      }).join('')
      : '<div class="tiny">Пока нет отправленных запросов — разбивка появится после первой отправки.</div>';

    $('#deadlines').innerHTML = stats.deadlines.length
      ? stats.deadlines.map(function (d) {
        var cls = d.days_left < 0 ? 'bad' : (d.days_left <= 7 ? 'warn' : 'ok');
        var label = d.days_left < 0
          ? ('просрочено на ' + Math.abs(d.days_left) + ' ' + plural(Math.abs(d.days_left), 'день', 'дня', 'дней'))
          : ('осталось ' + d.days_left + ' ' + plural(d.days_left, 'день', 'дня', 'дней'));
        return '<div class="dl"><span class="nm">' + esc(d.broker) + '</span>' +
          '<span class="pill ' + cls + '">' + esc(label) + '</span>' +
          '<span class="dt">до ' + esc(fmtDate(d.deadline)) + '</span></div>';
      }).join('')
      : '<div class="tiny">Активных дедлайнов нет: отправьте первый запрос, и здесь появится таймер 30 дней.</div>';

    $('#tips').innerHTML = stats.tips.map(function (t) {
      var warn = /Просрочено|Отказов/.test(t);
      return '<div class="tip' + (warn ? ' warn' : '') + '">' + (warn ? ICONS.warn : ICONS.info) +
        '<div>' + esc(t) + '</div></div>';
    }).join('');

    $('#privacy-note').textContent = stats.note || '';

    var banner = $('#demo-banner');
    if (stats.demo) {
      banner.innerHTML = '<div class="banner">' + ICONS.warn +
        '<div><b>Демо-режим.</b> Показаны синтетические данные для проверки интерфейса — они не сохранены. ' +
        '<button class="btn sm" id="btn-demo-off" style="margin-left:8px">Вернуться к моим данным</button></div></div>';
      var off = $('#btn-demo-off');
      if (off) off.addEventListener('click', function () { state.demo = null; renderDashboard(); });
    } else {
      banner.innerHTML = '';
    }
  }

  /* ------------------------------- ПРОФИЛЬ ------------------------------- */
  function renderProfile() {
    var p = state.profile || {};
    $('#pf-name').value = p.full_name || '';
    $('#pf-emails').value = listOf(p.emails).join(', ');
    $('#pf-phones').value = listOf(p.phones).join(', ');
    $('#pf-city').value = p.city || '';
    $('#pf-birth').value = p.birth_year || '';
    $('#pf-address').value = p.address || '';
    $('#pf-lang').value = p.language || 'ru';
    $('#profile-saved-at').textContent = state.profileUpdated
      ? 'сохранено ' + fmtDateTime(state.profileUpdated)
      : 'ещё не сохранено';
    $('#storage-note').textContent = state.server
      ? 'Серверный режим: профиль хранится в SQLite в зашифрованном виде (Fernet: AES-128-CBC + HMAC-SHA256), ключ — в переменной окружения DATA_KEY.'
      : (storageOK
        ? 'Браузерный режим: данные лежат только в localStorage этого устройства и никуда не передаются. Полей, которые не заполнены, в письме просто не будет.'
        : 'Внимание: localStorage недоступен (приватный режим или песочница iframe). Данные живут только в памяти вкладки и исчезнут после перезагрузки.');
    renderProfilePreview(p);
  }

  function renderProfilePreview(p) {
    p = p || {};
    var rows = piiRows(p, 'ru');
    var emails = listOf(p.emails);
    var lines = [];
    lines.push('Кому: <Название сервиса>');
    lines.push('От: ' + (clean(p.full_name) || 'субъекта персональных данных') + (emails[0] ? ', ' + emails[0] : ''));
    lines.push('Дата: ' + ruDate(todayDate()));
    lines.push('');
    if (rows.length) {
      lines.push('В вашем сервисе обрабатываются следующие мои персональные данные:');
      lines.push('');
      rows.forEach(function (r) { lines.push('  • ' + r); });
    } else {
      lines.push('(Блок с персональными данными пуст — заполните профиль, иначе оператор не сможет вас идентифицировать.)');
    }
    $('#profile-preview').textContent = lines.join('\n');
  }

  /* ------------------------------- КАТАЛОГ ------------------------------- */
  function renderCatalog() {
    var list = state.brokers.filter(function (b) {
      if (state.filterCat === 'all') return true;
      if (state.filterCat === 'custom') return !!b.custom;
      return b.category === state.filterCat;
    });
    var root = $('#broker-list');
    if (!list.length) {
      root.innerHTML = '<div class="empty"><strong>В этой категории пусто</strong>Добавьте свой сервис кнопкой «Свой сервис».</div>';
      return;
    }
    root.innerHTML = list.map(function (b) {
      var linked = state.requests.filter(function (r) { return r.broker_id === b.id; })[0];
      return '<article class="broker">' +
        '<div class="b-top"><div class="b-name">' + esc(b.name) + '</div>' +
        '<span class="pill neutral">' + esc(b.language === 'en' ? 'EN' : 'RU') + '</span></div>' +
        '<div class="b-cat">' + esc(CATEGORY_LABELS[b.category] || b.category) + ' · ' +
        esc(METHOD_LABELS[b.method] || b.method) + (b.custom ? ' · свой' : '') + '</div>' +
        '<div class="b-notes">' + esc(b.notes || '') + '</div>' +
        '<div class="b-meta">' +
        (b.verify ? '<span class="verify">' + ICONS.warn + 'проверить перед использованием</span>' : '') +
        (b.email ? '<span class="pill neutral">' + esc(b.email) + '</span>' : '') +
        (b.deadline_days ? '<span class="pill neutral">' + b.deadline_days + ' дней</span>' : '') +
        '</div>' +
        '<div class="b-actions">' +
        (linked
          ? '<button class="btn sm" data-act="goto-request" data-req="' + linked.id + '">' + ICONS.eye + 'Открыть запрос</button>'
          : '<button class="btn sm primary" data-act="create" data-broker="' + esc(b.id) + '">' + ICONS.mail + 'Создать запрос</button>') +
        (b.url ? '<a class="btn sm" href="' + esc(b.url) + '" target="_blank" rel="noopener noreferrer">' + ICONS.link + 'Открыть сайт</a>' : '') +
        (b.custom ? '<button class="btn sm danger" data-act="del-broker" data-broker="' + esc(b.id) + '">' + ICONS.trash + 'Удалить</button>' : '') +
        '</div></article>';
    }).join('');
  }

  /* ------------------------------- ЗАПРОСЫ ------------------------------- */
  function renderRequests() {
    var list = state.requests.filter(function (r) {
      return state.filterStatus === 'all' || r.status === state.filterStatus;
    });
    var root = $('#request-list');
    if (!list.length) {
      root.innerHTML = '<div class="empty"><strong>Запросов пока нет</strong>Выберите сервис в «Каталоге» — письмо соберётся автоматически с вашими данными.</div>';
      return;
    }
    root.innerHTML = list.map(function (r) {
      var dl = parseDay(r.deadline_at);
      var daysLeft = dl ? daysBetween(todayDate(), dl) : null;
      var dlPill = (r.status === 'sent' && daysLeft != null)
        ? '<span class="pill ' + (daysLeft < 0 ? 'bad' : (daysLeft <= 7 ? 'warn' : 'ok')) + '">' +
        (daysLeft < 0 ? 'просрочено на ' + Math.abs(daysLeft) + ' дн.' : 'осталось ' + daysLeft + ' дн.') + '</span>'
        : '';

      var actions = [];
      if (r.status === 'draft') actions.push('<button class="btn sm primary" data-act="send" data-id="' + r.id + '">' + ICONS.send + 'Отправить</button>');
      if (r.status === 'sent') actions.push('<button class="btn sm" data-act="status" data-status="responded" data-id="' + r.id + '">' + ICONS.reply + 'Ответили</button>');
      if (r.status === 'sent' || r.status === 'responded') actions.push('<button class="btn sm ok" data-act="status" data-status="deleted" data-id="' + r.id + '">' + ICONS.check + 'Удалено</button>');
      if (r.status === 'sent' || r.status === 'responded') actions.push('<button class="btn sm danger" data-act="status" data-status="refused" data-id="' + r.id + '">' + ICONS.x + 'Отказ</button>');
      if (r.status === 'refused') actions.push('<button class="btn sm ok" data-act="status" data-status="deleted" data-id="' + r.id + '">' + ICONS.check + 'Всё же удалили</button>');
      if (r.status !== 'draft') actions.push('<button class="btn sm" data-act="status" data-status="draft" data-id="' + r.id + '">' + ICONS.refresh + 'Повторить</button>');
      actions.push('<button class="btn sm" data-act="view" data-id="' + r.id + '">' + ICONS.eye + 'Письмо</button>');
      actions.push('<button class="btn sm ghost" data-act="note" data-id="' + r.id + '">Заметка</button>');
      actions.push('<button class="btn sm danger" data-act="del" data-id="' + r.id + '" title="Удалить запрос">' + ICONS.trash + '</button>');

      return '<article class="req">' +
        '<div class="req-head"><div class="req-name">' + esc(r.broker_name) + '</div>' +
        statusPill(r.status) + dlPill + '</div>' +
        '<div class="req-meta">' +
        '<span>' + esc(CATEGORY_LABELS[r.broker_category] || '—') + '</span>' +
        '<span>' + esc(METHOD_LABELS[r.method] || r.method) + '</span>' +
        (r.to_email ? '<span>' + esc(r.to_email) + '</span>' : '') +
        '<span>создан ' + esc(fmtDate(r.created_at)) + '</span>' +
        (r.sent_at ? '<span>отправлен ' + esc(fmtDate(r.sent_at)) + '</span>' : '') +
        (r.responded_at ? '<span>ответ ' + esc(fmtDate(r.responded_at)) + '</span>' : '') +
        '<span>' + esc(r.language === 'en' ? 'English' : 'Русский') + '</span>' +
        '</div>' +
        (r.note ? '<div class="tiny">Заметка: ' + esc(r.note) + '</div>' : '') +
        (r.error ? '<div class="tiny" style="color:#fda4af">' + esc(r.error) + '</div>' : '') +
        '<div class="req-actions">' + actions.join('') + '</div>' +
        '</article>';
    }).join('');
  }

  /* --------------------------------- AI --------------------------------- */
  function renderAI() {
    var configured = state.server
      ? !!(state.llmServer && state.llmServer.configured)
      : !!(state.llm.base_url && state.llm.api_key && state.llm.model);
    var text;
    if (state.server) {
      text = configured
        ? 'Серверный режим: AI подключён через сервер (модель ' + esc(state.llmServer.model || '—') +
        ', провайдер ' + esc(state.llmServer.base_url_host || '—') + '). Ключ хранится в переменной окружения LLM_API_KEY и в браузер не попадает.'
        : 'AI на сервере не настроен. Задайте LLM_API_KEY, LLM_BASE_URL, LLM_MODEL в .env и перезапустите сервер. Всё остальное работает и без AI.';
    } else {
      text = configured
        ? 'Браузерный режим: запрос идёт напрямую из браузера на ' + esc(state.llm.base_url) +
        ' (модель ' + esc(state.llm.model) + '). Ключ хранится только в localStorage этого устройства.'
        : 'AI-помощник не настроен. Нажмите «Настройки» и укажите Base URL, ключ и модель OpenAI-совместимого провайдера. Без AI всё остальное работает.';
    }
    $('#ai-status-text').innerHTML = text;

    var chat = $('#chat');
    if (!state.chat.length) {
      chat.innerHTML = '<div class="msg bot"><div class="av">AI</div><div class="bubble">Здравствуйте! Помогу разобраться с удалением данных: 152-ФЗ, GDPR, CCPA, жалобы регуляторам, тексты запросов. Я не спрашиваю и не сохраняю ваши персональные данные — ФИО, email и телефоны подставляются в письма локально, в разделе «Запросы».</div></div>';
    } else {
      chat.innerHTML = state.chat.map(function (m) {
        var cls = m.role === 'user' ? 'user' : (m.role === 'system' ? 'sys' : 'bot');
        var av = m.role === 'user' ? 'Вы' : (m.role === 'system' ? '!' : 'AI');
        return '<div class="msg ' + cls + '"><div class="av">' + av + '</div><div class="bubble">' + esc(m.content) + '</div></div>';
      }).join('');
      chat.scrollTop = chat.scrollHeight;
    }
  }

  async function sendChat() {
    var input = $('#chat-input');
    var q = clean(input.value);
    if (!q || state.busy) return;
    var kinds = detectPII(q);
    if (kinds.length) {
      state.chat.push({ role: 'user', content: q });
      state.chat.push({ role: 'system', content: piiWarning(kinds) });
      Store.set(K.chat, state.chat);
      input.value = '';
      renderAI();
      toast('Запрос заблокирован: в вопросе есть персональные данные', 'warn', 6000);
      return;
    }
    state.chat.push({ role: 'user', content: q });
    input.value = '';
    renderAI();
    state.busy = true;
    var btn = $('#btn-ai-send');
    btn.disabled = true;
    var span = btn.querySelector('span');
    if (span) span.textContent = 'Думаю…';
    try {
      var history = state.chat.filter(function (m) { return m.role !== 'system'; }).slice(0, -1);
      var res = await Api.ask(q, history);
      if (res.blocked) state.chat.push({ role: 'system', content: res.warning });
      else if (res.notConfigured) state.chat.push({ role: 'system', content: res.hint });
      else if (!res.ok) state.chat.push({ role: 'system', content: (res.cors ? 'CORS: ' : 'Ошибка: ') + (res.message || res.detail || 'не удалось получить ответ') });
      else state.chat.push({ role: 'assistant', content: res.answer });
    } catch (e) {
      state.chat.push({ role: 'system', content: 'Ошибка: ' + e.message });
    } finally {
      state.busy = false;
      btn.disabled = false;
      if (span) span.textContent = 'Спросить';
      Store.set(K.chat, state.chat);
      renderAI();
    }
  }

  /* -------------------------------- ДАННЫЕ -------------------------------- */
  function renderData() {
    var rows = state.server
      ? [
        ['Режим', 'серверный (FastAPI + SQLite)'],
        ['Шифрование ПД', 'Fernet, ключ из DATA_KEY'],
        ['Отправка писем', state.serverMeta.dry_run ? 'DRY_RUN=1 (письма не уходят)' : 'реальная отправка через SMTP'],
        ['SMTP', state.serverMeta.smtp_configured ? 'настроен' : 'не настроен'],
        ['AI', state.serverMeta.llm_configured ? 'подключён' : 'не настроен'],
        ['Запросов в базе', String(state.requests.length)]
      ]
      : [
        ['Режим', 'браузерный (без сервера)'],
        ['Хранилище', storageOK ? 'localStorage этого устройства' : 'только память вкладки (localStorage недоступен)'],
        ['Шифрование', 'нет: данные лежат локально и не передаются по сети'],
        ['Отправка писем', 'вручную: копирование текста или mailto'],
        ['AI', (state.llm.base_url && state.llm.api_key) ? 'подключён из браузера' : 'не настроен'],
        ['Запросов', String(state.requests.length)]
      ];
    $('#storage-kv').innerHTML = rows.map(function (r) {
      return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>';
    }).join('');
    $('#wipe-note').textContent = state.server
      ? 'Будут удалены таблицы profile, requests, events, custom_brokers в SQLite. Отменить нельзя.'
      : 'Будет очищен localStorage этого домена: профиль, запросы, история, свои сервисы и история AI-чата. Отменить нельзя.';
  }
