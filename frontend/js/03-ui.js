/* ==================================================================
   DataCleaner · 03-ui.js — рендеринг интерфейса 1.1
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
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 7l10 6 10-6"/></svg>',
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>',
    gavel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M14 10l-7.5 7.5a2.1 2.1 0 0 0 3 3L17 13"/><path d="M13 4l7 7"/><path d="M16.5 6.5l-3-3 3-3 3 3z" transform="rotate(45 15 4)"/></svg>',
    zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L4.5 13.5H11l-1 8.5L19.5 10H13l0-8z"/></svg>'
  };

  /* ----------------------------- уведомления ----------------------------- */
  function toast(msg, type, ms) {
    var wrap = $('#toasts');
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'ok');
    el.innerHTML = ((type === 'bad' || type === 'warn') ? ICONS.warn : ICONS.check) + '<div>' + esc(msg) + '</div>';
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
    document.body.classList.add('modal-open');
    if (onMount) onMount();
  }
  function closeModal() {
    $('#modal').classList.remove('open');
    document.body.classList.remove('modal-open');
  }

  function statusPill(status) {
    return '<span class="pill ' + (STATUS_CLASS[status] || 'neutral') + '">' + esc(STATUS_LABELS[status] || status) + '</span>';
  }

  var VIEWS = ['dashboard', 'requests', 'catalog', 'autopilot', 'ai', 'profile'];
  function navigate(view) {
    if (VIEWS.indexOf(view) === -1) view = 'dashboard';
    state.view = view;
    $$('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + view); });
    $$('#nav button, #bottom-nav button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.view === view);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (view === 'dashboard') renderDashboard();
    if (view === 'profile') renderProfile();
    if (view === 'catalog') renderCatalog();
    if (view === 'requests') renderRequests();
    if (view === 'autopilot') renderAutopilot();
    if (view === 'ai') renderAI();
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

  function ruNum(v) {
    return String(v == null ? '' : v).replace('.', ',');
  }

  function barRow(label, value, percent, cls, overridePercent) {
    var pct = overridePercent != null ? overridePercent : (percent == null ? 0 : percent);
    pct = Math.max(0, Math.min(100, pct));
    return '<div class="bar-row"><div class="bar-head"><span>' + esc(label) + '</span><b>' + esc(ruNum(value)) +
      (percent != null ? ' · ' + ruNum(percent) + '%' : '') + '</b></div>' +
      '<div class="track"><div class="fill ' + (cls || '') + '" style="width:' + pct + '%"></div></div></div>';
  }

  function sparkFor(activity, mode) {
    var values = (activity || []).map(function (a) { return a.count; });
    if (mode === 'cumulative') {
      var acc = 0;
      values = values.map(function (v) { acc += v; return acc; });
    }
    return sparkline(values, 74, 26);
  }

  function paintDashboard(stats) {
    var k = stats.kpi;
    var sentSeries = (stats.activity || []).map(function (a) { return a.count; });

    $('#kpi-sent').textContent = k.sent;
    $('#kpi-sent-hint').textContent = k.total ? 'из ' + k.total + ' ' + plural(k.total, 'запроса', 'запросов', 'запросов') : 'писем и обращений';
    $('#kpi-waiting').textContent = k.waiting;
    $('#kpi-waiting-hint').textContent = k.waiting ? 'в пределах срока' : 'нет активных ожиданий';
    $('#kpi-overdue').textContent = k.overdue;
    $('#kpi-overdue-hint').textContent = k.overdue ? ('макс. ' + k.oldest_overdue_days + ' ' + plural(k.oldest_overdue_days, 'день', 'дня', 'дней')) : 'сроки соблюдаются';
    $('#kpi-deleted').textContent = k.deleted;
    $('#kpi-deleted-hint').textContent = k.deleted ? 'подтверждено' : 'пока нет';

    $('#spark-sent').innerHTML = sparkFor(stats.activity, 'plain');
    $('#spark-wait').innerHTML = sparkFor(stats.activity, 'cumulative');
    $('#spark-over').innerHTML = sparkline(sentSeries.map(function (v, i) { return i % 3 === 0 ? v : 0; }), 74, 26);
    $('#spark-del').innerHTML = sparkFor(stats.activity, 'cumulative');

    $('#hero-stats').innerHTML = [
      ['Запросов', k.total], ['Удалено', k.deleted], ['Просрочено', k.overdue]
    ].map(function (p) {
      return '<div class="hero-stat"><b>' + p[1] + '</b><span>' + p[0] + '</span></div>';
    }).join('');

    var hvSent = $('#hv-sent');
    if (hvSent) {
      hvSent.textContent = k.sent + ' / ' + k.total;
      $('#hv-bar-sent').style.width = (k.total ? Math.round(k.sent / k.total * 100) : 0) + '%';
      $('#hv-deleted').textContent = k.deleted;
      $('#hv-bar-del').style.width = (k.total ? Math.round(k.deleted / k.total * 100) : 0) + '%';
      $('#hv-overdue').textContent = k.overdue;
      var smtpPill = $('#hv-smtp');
      var ready = state.settings && state.settings.resolved && state.settings.resolved.ready;
      smtpPill.textContent = ready ? 'готов' : 'не настроен';
      smtpPill.className = 'hv-pill ' + (ready ? 'ok' : 'wait');
      var pilot = state.settings && state.settings.autopilot;
      var on = pilot && (pilot.auto_send || pilot.followup_enabled);
      var hvPilot = $('#hv-pilot');
      if (hvPilot) {
        hvPilot.textContent = on ? 'включён' : 'выключен';
        hvPilot.className = 'hv-pill ' + (on ? 'ok' : 'bad');
      }
    }

    var rate = Number(k.deletion_rate) || 0;
    $('#ring').style.setProperty('--p', rate);
    $('#ring-num').textContent = (rate % 1 === 0 ? rate.toFixed(0) : rate.toFixed(1)) + '%';
    $('#lg-deleted').textContent = k.deleted;
    $('#lg-responded').textContent = k.responded;
    $('#lg-refused').textContent = k.refused;
    $('#lg-drafts').textContent = k.drafts;

    var avgEl = $('#avg-days');
    avgEl.textContent = k.avg_response_days == null ? '—' : String(k.avg_response_days).replace('.', ',');
    avgEl.style.background = k.avg_response_days == null ? 'none' : '';
    avgEl.style.color = k.avg_response_days == null ? 'var(--muted-2)' : '';
    $('#avg-note').textContent = k.avg_response_days == null
      ? 'Пока нет ответов — среднее появится после первой реакции оператора.'
      : 'Считается по ' + (k.responded + k.deleted) + ' ' + plural(k.responded + k.deleted, 'ответу', 'ответам', 'ответам') + ' операторов.';

    var base = Math.max(k.sent, 1);
    $('#rate-bars').innerHTML = [
      barRow('Удалено', k.deleted, Math.round(k.deleted / base * 100), 'f3'),
      barRow('Ответили, но не удалили', k.responded, Math.round(k.responded / base * 100), 'f4'),
      barRow('Отказ', k.refused, Math.round(k.refused / base * 100), 'f5'),
      barRow('Доля операторов, ответивших на запрос', k.response_rate + '%', null, 'f2', Number(k.response_rate) || 0)
    ].join('');

    $('#funnel').innerHTML = stats.funnel.map(function (f, i) {
      return barRow(f.label, f.count, f.percent, ['f5', 'f2', 'f4', 'f3'][i] || 'f2');
    }).join('');

    var maxDay = Math.max.apply(null, stats.activity.map(function (a) { return a.count; }).concat([1]));
    var chartEl = $('#chart');
    var maxBarPx = Math.max(60, (chartEl.clientHeight || 172) - 30);
    var narrow = window.innerWidth < 560;
    chartEl.innerHTML = stats.activity.map(function (a, idx) {
      var h = a.count ? Math.max(10, Math.round(a.count / maxDay * maxBarPx)) : 4;
      var d = parseDay(a.date);
      var label = (d && (!narrow || idx % 2 === 1))
        ? String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0') : '';
      return '<div class="col" title="' + esc(a.date) + ': ' + a.count + '">' +
        '<div class="bar ' + (a.count ? '' : 'zero') + '" style="height:' + h + 'px"><span>' + a.count + '</span></div>' +
        '<div class="cl">' + esc(label) + '</div></div>';
    }).join('');

    $('#categories').innerHTML = stats.by_category.length
      ? stats.by_category.map(function (c, i) { return barRow(c.label, c.count, c.percent, ['f2', 'f3', 'f4', 'f5'][i % 4]); }).join('')
      : '<div class="tiny">Пока нет отправленных запросов.</div>';

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
      : '<div class="tiny">Активных дедлайнов нет — отправьте первый запрос.</div>';

    $('#tips').innerHTML = stats.tips.map(function (t) {
      var warn = /Просрочено|Отказов/.test(t);
      return '<div class="tip' + (warn ? ' warn' : '') + '">' + (warn ? ICONS.warn : ICONS.info) + '<div>' + esc(t) + '</div></div>';
    }).join('');

    $('#privacy-note').textContent = stats.note || '';

    var banner = $('#demo-banner');
    if (stats.demo) {
      banner.innerHTML = '<div class="banner" style="margin-top:16px">' + ICONS.warn +
        '<div><b>Демо-режим.</b> Показаны синтетические данные — они не сохранены. ' +
        '<button class="btn sm" id="btn-demo-off" style="margin-left:8px">Вернуться к моим данным</button></div></div>';
      var off = $('#btn-demo-off');
      if (off) off.addEventListener('click', function () { state.demo = null; renderDashboard(); });
    } else {
      banner.innerHTML = '';
    }

    paintPilotStrip();
  }

  function paintPilotStrip() {
    var ap = (state.settings && state.settings.autopilot) || {};
    var on = !!(ap.auto_send || ap.followup_enabled);
    var ready = !!(state.settings && state.settings.resolved && state.settings.resolved.ready);
    var toggle = $('#pilot-toggle');
    if (!toggle) return;
    toggle.checked = !!ap.auto_send;
    $('#pilot-toggle-label').textContent = ap.auto_send ? 'Автоотправка включена' : 'Автоотправка выключена';
    $('#pilot-title').textContent = on ? 'Автопилот работает' : 'Автопилот выключен';
    $('#pilot-desc').textContent = on
      ? 'Черновики уходят сами, а операторам, которые молчат дольше ' + (ap.followup_days || 30) + ' дней, уходит повторное требование.'
      : 'Включите автопилот — DataCleaner сам отправит черновики и напомнит операторам, которые молчат дольше срока.';
    var smtpEl = $('#pilot-smtp');
    var tr = (state.settings && state.settings.transport) || {};
    var label = tr.kind === 'brevo' || tr.kind === 'resend'
      ? 'HTTPS-API'
      : (ready ? (state.settings.resolved.from_addr || 'настроена') : 'не настроена');
    smtpEl.textContent = label;
    smtpEl.style.color = ready ? 'var(--mint)' : 'var(--amber)';
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
    $('#profile-saved-at').textContent = state.profileUpdated ? 'сохранено ' + fmtDateTime(state.profileUpdated) : 'ещё не сохранено';
    $('#storage-note').textContent = state.server
      ? 'Серверный режим: профиль хранится в SQLite в зашифрованном виде (Fernet: AES-128-CBC + HMAC-SHA256), ключ — в DATA_KEY.'
      : (storageOK
        ? 'Браузерный режим: данные только в localStorage этого устройства. Автоотправка писем доступна в серверной версии.'
        : 'localStorage недоступен (приватный режим или песочница): данные живут только в памяти вкладки.');
    renderProfilePreview(p);

    var rows = state.server
      ? [
        ['Режим', 'серверный (FastAPI + SQLite)'],
        ['Шифрование ПД', 'Fernet, ключ из DATA_KEY'],
        ['Отправка писем', state.serverMeta.dry_run
          ? 'DRY_RUN=1 — письма не уходят'
          : 'реальная отправка: ' + (((state.settings || {}).transport || {}).label || 'SMTP')],
        ['SMTP', (state.settings.resolved && state.settings.resolved.ready) ? 'настроен' : 'не настроен'],
        ['AI', state.serverMeta.llm_configured ? 'подключён' : 'не настроен'],
        ['Запросов', String(state.requests.length)]
      ]
      : [
        ['Режим', 'браузерный (без сервера)'],
        ['Хранилище', storageOK ? 'localStorage этого устройства' : 'только память вкладки'],
        ['Шифрование', 'нет: данные не покидают устройство'],
        ['Отправка писем', 'вручную: копирование текста или mailto'],
        ['AI', (state.llm.base_url && state.llm.api_key) ? 'подключён из браузера' : 'не настроен'],
        ['Запросов', String(state.requests.length)]
      ];
    $('#storage-kv').innerHTML = rows.map(function (r) {
      return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>';
    }).join('');
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
      lines.push('(Блок пуст — заполните профиль, иначе оператор не сможет вас идентифицировать.)');
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
        '<div class="b-head"><div class="b-name">' + esc(b.name) + '</div>' +
        '<span class="badge lang">' + esc(b.language === 'en' ? 'EN' : 'RU') + '</span></div>' +
        '<div class="b-cat">' + esc(CATEGORY_LABELS[b.category] || b.category) + ' · ' + esc(METHOD_LABELS[b.method] || b.method) + '</div>' +
        '<div class="b-notes">' + esc(b.notes || '') + '</div>' +
        '<div class="b-meta">' +
        (b.verify ? '<span class="badge verify">' + ICONS.warn + 'проверить перед использованием</span>' : '') +
        (b.custom ? '<span class="badge custom">свой</span>' : '') +
        (b.email ? '<span class="pill neutral">' + esc(b.email) + '</span>' : '') +
        (b.deadline_days ? '<span class="pill neutral">' + b.deadline_days + ' дней</span>' : '') +
        '</div>' +
        '<div class="b-actions">' +
        (linked
          ? '<button class="btn sm" data-act="goto-request">' + ICONS.eye + 'Открыть запрос</button>'
          : '<button class="btn sm primary" data-act="create" data-broker="' + esc(b.id) + '">' + ICONS.mail + 'Создать запрос</button>') +
        (b.url ? '<a class="btn sm" href="' + esc(b.url) + '" target="_blank" rel="noopener noreferrer">' + ICONS.link + 'Сайт</a>' : '') +
        (b.custom ? '<button class="btn sm danger" data-act="del-broker" data-broker="' + esc(b.id) + '">' + ICONS.trash + '</button>' : '') +
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
      if (r.status === 'sent' || r.status === 'responded') {
        actions.push('<button class="btn sm ok" data-act="status" data-status="deleted" data-id="' + r.id + '">' + ICONS.check + 'Удалено</button>');
        actions.push('<button class="btn sm danger" data-act="status" data-status="refused" data-id="' + r.id + '">' + ICONS.x + 'Отказ</button>');
      }
      if (r.status === 'refused') actions.push('<button class="btn sm ok" data-act="status" data-status="deleted" data-id="' + r.id + '">' + ICONS.check + 'Всё же удалили</button>');
      if (r.status === 'sent') actions.push('<button class="btn sm warn" data-act="followup" data-id="' + r.id + '">' + ICONS.bell + 'Напомнить</button>');
      if (r.status !== 'draft') actions.push('<button class="btn sm" data-act="complaint" data-id="' + r.id + '">' + ICONS.gavel + 'Жалоба</button>');
      if (r.status !== 'draft') actions.push('<button class="btn sm" data-act="status" data-status="draft" data-id="' + r.id + '">' + ICONS.refresh + 'Повторить</button>');
      actions.push('<button class="btn sm" data-act="view" data-id="' + r.id + '">' + ICONS.eye + 'Письмо</button>');
      actions.push('<button class="btn sm ghost" data-act="note" data-id="' + r.id + '">Заметка</button>');
      actions.push('<button class="btn sm danger" data-act="del" data-id="' + r.id + '" title="Удалить запрос">' + ICONS.trash + '</button>');

      return '<article class="req">' +
        '<div class="req-head"><div class="req-name">' + esc(r.broker_name) + '</div>' + statusPill(r.status) + dlPill + '</div>' +
        '<div class="req-meta">' +
        '<span>' + esc(CATEGORY_LABELS[r.broker_category] || '—') + '</span>' +
        '<span>' + esc(METHOD_LABELS[r.method] || r.method) + '</span>' +
        (r.to_email ? '<span>' + esc(r.to_email) + '</span>' : '') +
        '<span>создан ' + esc(fmtDate(r.created_at)) + '</span>' +
        (r.sent_at ? '<span>отправлен ' + esc(fmtDate(r.sent_at)) + '</span>' : '') +
        (r.responded_at ? '<span>ответ ' + esc(fmtDate(r.responded_at)) + '</span>' : '') +
        '</div>' +
        (r.note ? '<div class="tiny">Заметка: ' + esc(r.note) + '</div>' : '') +
        (r.error ? '<div class="tiny" style="color:#fda4af">' + esc(r.error) + '</div>' : '') +
        '<div class="req-actions">' + actions.join('') + '</div></article>';
    }).join('');
  }

  /* ------------------------------ АВТОПИЛОТ ------------------------------ */
  function renderAutopilot() {
    var s = state.settings || {};
    var smtp = s.smtp || {};
    var ap = s.autopilot || {};
    var resolved = s.resolved || {};

    var preset = $('#smtp-preset');
    if (preset && !preset.options.length) {
      var presets = (s.presets || []).slice();
      preset.innerHTML = presets.map(function (p) {
        return '<option value="' + esc(p.id) + '">' + esc(p.label) + '</option>';
      }).join('') || '<option value="custom">Другой сервер</option>';
      preset.addEventListener('change', applySmtpPreset);
    }
    var hostNow = smtp.host || resolved.host || '';
    var presetNow = (s.presets || []).filter(function (x) { return x.host && x.host === hostNow; })[0];
    if (preset) preset.value = presetNow ? presetNow.id : (hostNow ? 'custom' : 'custom');
    $('#smtp-host').value = hostNow;
    $('#smtp-port').value = smtp.port || resolved.port || 587;
    $('#smtp-user').value = smtp.user || resolved.user || '';
    $('#smtp-from').value = smtp.from_addr || resolved.from_addr || '';
    $('#smtp-from-name').value = smtp.from_name || 'DataCleaner';
    $('#smtp-ssl').checked = !!smtp.use_ssl;
    $('#smtp-starttls').checked = !!smtp.use_starttls;
    $('#smtp-pass').value = '';
    $('#smtp-pass').placeholder = smtp.has_password ? 'пароль сохранён — оставьте пустым, чтобы не менять' : '••••••••';

    $('#ap-autosend').checked = !!ap.auto_send;
    $('#ap-followup').checked = !!ap.followup_enabled;
    $('#ap-days').value = ap.followup_days || 30;
    $('#ap-interval').value = ap.interval_minutes || 15;

    var on = !!(ap.auto_send || ap.followup_enabled);
    var chip = $('#pilot-state-chip');
    chip.className = 'status-chip ' + (on ? 'live' : '');
    chip.innerHTML = '<span class="dot"></span><span class="txt">' + (on ? 'включён' : 'выключен') + '</span>';

    renderQuickLogin();
    renderGoogleCard();
    renderMailStatus();
    renderDryRunTip();
    renderPilotLog();
  }

  /* Простой вход: адрес + пароль. Сервер определяется по домену. */
  function renderQuickLogin() {
    if (!$('#quick-card')) return;
    var s = state.settings || {};
    var smtp = s.smtp || {};
    var resolved = s.resolved || {};
    var email = smtp.user || resolved.user || (state.profile && listOf(state.profile.emails)[0]) || '';
    var emailEl = $('#quick-email');
    if (emailEl && !emailEl.value) emailEl.value = email;
    var stateEl = $('#quick-state');
    if (resolved.ready) {
      stateEl.className = 'pill ok';
      stateEl.textContent = 'вход выполнен';
    } else {
      stateEl.className = 'pill acc';
      stateEl.textContent = 'адрес + пароль';
    }
    updateQuickAutodetect();
    renderSendMode();
  }

  function updateQuickAutodetect() {
    var el = $('#quick-autodetect');
    if (!el) return;
    var email = clean($('#quick-email').value);
    if (email.indexOf('@') === -1) { el.textContent = ''; return; }
    var domain = email.split('@').pop().toLowerCase();
    var map = {
      'gmail.com': ['smtp.gmail.com', 587, 'STARTTLS', 'для Gmail нужен «пароль приложения» (Google не принимает обычный)'],
      'googlemail.com': ['smtp.gmail.com', 587, 'STARTTLS', 'для Gmail нужен «пароль приложения»'],
      'yandex.ru': ['smtp.yandex.ru', 465, 'SSL', 'Яндекс выдаёт «пароль приложения» в id.yandex.ru → Безопасность'],
      'ya.ru': ['smtp.yandex.ru', 465, 'SSL', 'Яндекс выдаёт «пароль приложения» в id.yandex.ru → Безопасность'],
      'mail.ru': ['smtp.mail.ru', 465, 'SSL', 'Mail.ru: Настройки → Безопасность → пароль для внешнего приложения'],
      'bk.ru': ['smtp.mail.ru', 465, 'SSL', 'Mail.ru: пароль для внешнего приложения'],
      'inbox.ru': ['smtp.mail.ru', 465, 'SSL', 'Mail.ru: пароль для внешнего приложения'],
      'list.ru': ['smtp.mail.ru', 465, 'SSL', 'Mail.ru: пароль для внешнего приложения'],
      'outlook.com': ['smtp-mail.outlook.com', 587, 'STARTTLS', 'нужен пароль приложения'],
      'hotmail.com': ['smtp-mail.outlook.com', 587, 'STARTTLS', 'нужен пароль приложения'],
      'icloud.com': ['smtp.mail.me.com', 587, 'STARTTLS', 'нужен пароль приложения Apple ID'],
      'yahoo.com': ['smtp.mail.yahoo.com', 465, 'SSL', 'нужен пароль приложения'],
      'rambler.ru': ['smtp.rambler.ru', 465, 'SSL', ''],
      'zoho.com': ['smtp.zoho.com', 465, 'SSL', '']
    };
    var info = map[domain];
    if (info) {
      el.innerHTML = 'Определено: <b>' + esc(info[0]) + ':' + info[1] + '</b> (' + esc(info[2]) + ')' +
        (info[3] ? ' · ' + esc(info[3]) : '');
    } else {
      el.innerHTML = 'Определено: <b>smtp.' + esc(domain) + ':587</b> (STARTTLS) — если не подойдёт, укажите сервер вручную ниже.';
    }
  }

  function renderSendMode() {
    if (!$('#send-mode-card')) return;
    var s = state.settings || {};
    var dry = s.dry_run;
    var toggle = $('#send-mode-toggle');
    var chip = $('#send-mode-state');
    var label = $('#send-mode-label');
    if (dry == null) dry = !!(state.serverMeta && state.serverMeta.dry_run);
    toggle.checked = !dry;
    chip.className = 'pill ' + (dry ? 'warn' : 'ok');
    chip.textContent = dry ? 'выключена (DRY_RUN)' : 'включена';
    label.textContent = dry
      ? 'Отправлять письма по-настоящему'
      : 'Письма уходят операторам — выключить';
  }

  /* Вход через Google: подключено / можно подключить / сервер не настроен */
  function renderGoogleCard() {
    if (!$('#google-card')) return;
    var s = state.settings || {};
    var g = s.google || {};
    var kind = (s.transport || {}).kind || 'none';
    var stateEl = $('#google-state');
    var accEl = $('#google-account');
    var hintEl = $('#google-hint');
    var noteEl = $('#google-note');
    var connectBtn = $('#google-connect');
    var disconnectBtn = $('#google-disconnect');

    if (g.connected) {
      stateEl.className = 'pill ok';
      stateEl.textContent = kind === 'google' ? 'письма идут через Google' : 'подключено';
      accEl.textContent = g.email || 'аккаунт Google подключён';
      hintEl.textContent = g.connected_at ? 'подключён ' + fmtDateTime(g.connected_at) : 'подключён';
      connectBtn.textContent = 'Переподключить';
      connectBtn.classList.remove('primary');
      disconnectBtn.style.display = '';
      noteEl.innerHTML = 'Письма отправляются с этого ящика. Отключить доступ можно здесь или в ' +
        '<a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">настройках аккаунта Google</a>.';
    } else if (g.configured) {
      stateEl.className = 'pill warn';
      stateEl.textContent = 'не подключено';
      accEl.textContent = 'Аккаунт Google не подключён';
      hintEl.textContent = 'вход в один клик';
      connectBtn.textContent = 'Войти через Google';
      connectBtn.classList.add('primary');
      disconnectBtn.style.display = 'none';
      noteEl.innerHTML = 'Нажмите кнопку и введите свой обычный пароль Google на странице Google — ' +
        'приложение его не видит и не хранит, сохраняется только токен доступа (зашифрованный).';
    } else {
      stateEl.className = 'pill neutral';
      stateEl.textContent = 'нужна настройка';
      accEl.textContent = 'Google не подключён: нужна настройка сервера';
      hintEl.textContent = 'смотреть README §5a';
      connectBtn.textContent = 'Как включить';
      connectBtn.classList.add('primary');
      disconnectBtn.style.display = 'none';
      noteEl.innerHTML = 'Владельцу сервиса нужно один раз создать OAuth-клиент в Google Cloud ' +
        '(Gmail API + redirect URI <span class="code">' + esc(g.redirect_uri || '/api/mail/google/callback') +
        '</span>) и добавить в переменные окружения <span class="code">GOOGLE_CLIENT_ID</span> и ' +
        '<span class="code">GOOGLE_CLIENT_SECRET</span>.';
    }
  }

  /* Статус транспорта: SMTP или HTTPS-API провайдера (для хостингов, где SMTP закрыт) */
  function renderMailStatus() {
    var s = state.settings || {};
    var resolved = s.resolved || {};
    var tr = s.transport || {};
    var kind = tr.kind || (resolved.ready ? 'smtp' : 'none');
    var lines = [];

    if (kind === 'smtp') {
      lines.push('<span style="color:var(--mint)">SMTP готов:</span> ' + esc(resolved.from_addr || '') +
        ' через ' + esc(resolved.host || '') + ':' + esc(String(resolved.port || '')));
      var port = Number(resolved.port || 0);
      if (port === 25 || port === 465 || port === 587) {
        lines.push('<span style="color:var(--amber)">Важно про хостинг:</span> бесплатный Render блокирует исходящий ' +
          'SMTP на портах 25/465/587 — письма там не уйдут. Варианты: порт <b>2525</b> у провайдера ' +
          '(Brevo/SendGrid) или HTTPS-API (переменные <span class="code">BREVO_API_KEY</span> / ' +
          '<span class="code">RESEND_API_KEY</span> + <span class="code">EMAIL_FROM</span>). На своём ПК/VPS порт ' +
          esc(String(port)) + ' работает как обычно.');
      }
    } else if (kind === 'google') {
      lines.push('<span style="color:var(--mint)">Отправка через Gmail API:</span> ' + esc(tr.from_addr || 'аккаунт Google') +
        '. SMTP и пароли приложений не нужны — используется вход через Google (OAuth 2.0), HTTPS-порт 443.');
    } else if (kind === 'brevo' || kind === 'resend') {
      lines.push('<span style="color:var(--mint)">Отправка через HTTPS-API:</span> ' + esc(tr.label || kind) +
        '. SMTP не нужен, ключ задан в переменных окружения, адрес отправителя — ' + esc(tr.from_addr || 'EMAIL_FROM') + '.');
    } else {
      lines.push('<span style="color:var(--amber)">Почта не подключена.</span> Быстрее всего — «Войти через Google» ' +
        'выше (без паролей приложений). Альтернативы: SMTP с паролем приложения ниже, либо ' +
        '<span class="code">BREVO_API_KEY</span> / <span class="code">RESEND_API_KEY</span> и ' +
        '<span class="code">EMAIL_FROM</span> в переменных окружения хостинга.');
    }
    (tr.notes || []).forEach(function (n) {
      if (kind === 'none' && /^Почта не подключена/.test(n)) return; /* уже сказано выше */
      lines.push('<span class="muted">' + esc(n) + '</span>');
    });
    $('#smtp-status').innerHTML = lines.join('<br>');
  }

  /* Подсказка про DRY_RUN: меняется в зависимости от окружения */
  function renderDryRunTip() {
    var el = $('#dry-run-tip');
    if (!el) return;
    if (!state.server) {
      el.innerHTML = 'В браузерном режиме письма не отправляются автоматически: текст копируется в ваш ' +
        'почтовый клиент. Реальная автоотправка — в серверной версии (FastAPI) с подключённой почтой.';
      return;
    }
    var dry = !!(state.serverMeta && state.serverMeta.dry_run);
    el.innerHTML = dry
      ? 'Сейчас <span class="code">DRY_RUN=1</span>: автопилот собирает письма, но не отправляет. ' +
        'Чтобы письма реально уходили: подключите почту выше и поставьте <span class="code">DRY_RUN=0</span> ' +
        'в переменных окружения хостинга (Render → Environment), затем перезапустите сервис.'
      : 'Сейчас <span class="code">DRY_RUN=0</span>: письма уходят по-настоящему. Автопилот отправит новые ' +
        'черновики и одно напоминание по каждому молчащему оператору.';
  }

  function applySmtpPreset() {
    var id = $('#smtp-preset').value;
    var presets = (state.settings && state.settings.presets) || [];
    var p = presets.filter(function (x) { return x.id === id; })[0];
    if (!p) return;
    if (p.host) {
      $('#smtp-host').value = p.host;
      $('#smtp-port').value = p.port;
      $('#smtp-ssl').checked = !!p.ssl;
      $('#smtp-starttls').checked = !!p.starttls;
    }
    if (p.hint) $('#smtp-hint').textContent = p.hint;
  }

  function renderPilotLog() {
    var root = $('#pilot-log');
    if (!root) return;
    if (!state.pilotLog.length) {
      root.innerHTML = '<div class="tiny">Пока пусто. Нажмите «Прогон сейчас», чтобы увидеть, что сделает автопилот.</div>';
      return;
    }
    root.innerHTML = state.pilotLog.slice(0, 6).map(function (rep) {
      var sent = (rep.sent || []).length, fups = (rep.followups || []).length, errs = (rep.errors || []).length;
      var cls = errs ? 'bad' : (sent || fups ? 'ok' : 'neutral');
      var manual = (rep.manual || []).length;
      var what = (sent || fups)
        ? 'отправлено ' + sent + ', напоминаний ' + fups
        : (manual ? 'автоматически отправлять нечего' : 'нечего отправлять — новых черновиков и просроченных запросов нет');
      if (manual) what += ' · через форму: ' + manual;
      if (rep.skipped) what += ' · ' + rep.skipped;
      return '<div class="dl"><span class="pill ' + cls + '">' + (errs ? 'ошибки: ' + errs : 'выполнено') + '</span>' +
        '<span class="nm">' + esc(what) + '</span>' +
        '<span class="dt">' + esc(fmtDateTime(rep.finished_at || rep.started_at)) + '</span></div>';
    }).join('');
  }

  /* ---------------------------------- AI ---------------------------------- */
  function renderAI() {
    var configured = state.server
      ? !!(state.llmServer && state.llmServer.configured)
      : !!(state.llm.base_url && state.llm.api_key && state.llm.model);
    var text;
    if (state.server) {
      text = configured
        ? 'Серверный режим: модель ' + esc(state.llmServer.model || '—') + ' через ' + esc(state.llmServer.base_url_host || '—') + '. Ключ на сервере, в браузер не попадает. Ответы идут потоком.'
        : 'AI на сервере не настроен. Задайте LLM_API_KEY, LLM_BASE_URL, LLM_MODEL в Environment и перезапустите сервис. Всё остальное работает без AI.';
    } else {
      text = configured
        ? 'Браузерный режим: запрос идёт напрямую на ' + esc(state.llm.base_url) + ' (модель ' + esc(state.llm.model) + '). Ключ только в этом браузере.'
        : 'AI не настроен. Нажмите «Настройки» и укажите Base URL, ключ и модель OpenAI-совместимого провайдера.';
    }
    $('#ai-status-text').innerHTML = text;

    var select = $('#ai-model');
    if (select) {
      var models = state.models.length ? state.models : [state.llm.model, state.llmServer && state.llmServer.model].filter(Boolean);
      var current = state.llm.model || (state.llmServer && state.llmServer.model) || '';
      select.innerHTML = models.map(function (m) {
        return '<option value="' + esc(m) + '"' + (m === current ? ' selected' : '') + '>' + esc(m) + '</option>';
      }).join('') || '<option value="">модель не выбрана</option>';
      select.disabled = state.server; /* на сервере модель задаётся в Environment */
      select.title = state.server ? 'В серверном режиме модель задаётся переменной LLM_MODEL' : 'Модель для браузерных запросов';
    }

    $$('#ai-modes .chip').forEach(function (c) { c.classList.toggle('active', c.dataset.mode === state.aiMode); });

    var chat = $('#chat');
    if (!state.chat.length) {
      chat.innerHTML = '<div class="msg bot"><div class="av">AI</div><div class="bubble">Здравствуйте! Помогу с удалением данных: 152-ФЗ, GDPR, CCPA, жалобы регуляторам, тактика против отказов. Я не спрашиваю персональные данные — ФИО и контакты подставляются в письма локально.</div></div>';
    } else {
      chat.innerHTML = state.chat.map(function (m) {
        var cls = m.role === 'user' ? 'user' : (m.role === 'system' ? 'sys' : 'bot');
        var av = m.role === 'user' ? 'Вы' : (m.role === 'system' ? '!' : 'AI');
        var typing = m.streaming ? ' typing' : '';
        return '<div class="msg ' + cls + '"><div class="av">' + av + '</div><div class="bubble' + typing + '">' + esc(m.content) + '</div></div>';
      }).join('');
      chat.scrollTop = chat.scrollHeight;
    }

    var know = $('#know-list');
    if (know) {
      know.innerHTML = (state.facts || []).slice(0, 8).map(function (f) {
        return '<div class="know-item"><b>' + esc(f.topic || '') + '</b>' + esc(f.text || '') + '</div>';
      }).join('');
    }
  }
