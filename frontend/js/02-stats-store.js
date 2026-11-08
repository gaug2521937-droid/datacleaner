/* ==================================================================
   DataCleaner · 02-stats-store.js — статистика, хранилище, слой API.
   ================================================================== */

  /* --------------------------- статистика --------------------------- */
  function computeStats(requests, opts) {
    opts = opts || {};
    var today = opts.today || todayDate();
    var historyDays = opts.historyDays || 14;
    var rows = Array.isArray(requests) ? requests.slice() : [];
    var counts = { draft: 0, sent: 0, responded: 0, deleted: 0, refused: 0 };
    var sentCount = 0, waiting = [], overdue = [], deadlines = [], responseTimes = [];
    var perDay = {}, perCategory = {};

    rows.forEach(function (r) {
      var st = r.status || 'draft';
      if (counts[st] == null) counts[st] = 0;
      counts[st] += 1;
      var cat = r.broker_category || 'custom';
      if (st !== 'draft') perCategory[cat] = (perCategory[cat] || 0) + 1;

      var sentAt = r.sent_at ? new Date(r.sent_at) : null;
      var respondedAt = r.responded_at ? new Date(r.responded_at) : null;
      var deletedAt = r.deleted_at ? new Date(r.deleted_at) : null;
      var deadline = parseDay(r.deadline_at) ||
        (sentAt && !isNaN(sentAt.getTime()) ? addDays(parseDay(isoDay(sentAt)), Number(r.deadline_days || 30)) : null);

      if (sentAt && !isNaN(sentAt.getTime())) {
        sentCount += 1;
        perDay[isoDay(sentAt)] = (perDay[isoDay(sentAt)] || 0) + 1;
      }
      if (sentAt && respondedAt && !isNaN(respondedAt.getTime())) {
        responseTimes.push(+(((respondedAt - sentAt) / 86400000)).toFixed(1));
      } else if (sentAt && deletedAt && st === 'deleted' && !isNaN(deletedAt.getTime())) {
        responseTimes.push(+(((deletedAt - sentAt) / 86400000)).toFixed(1));
      }

      if (deadline && (st === 'sent' || st === 'responded' || st === 'refused')) {
        var dl = { id: r.id, broker: r.broker_name, category: cat, status: st, deadline: isoDay(deadline), days_left: daysBetween(today, deadline) };
        deadlines.push(dl);
        if (st === 'sent') { (dl.days_left < 0 ? overdue : waiting).push(dl); }
      }
    });

    deadlines.sort(function (a, b) { return a.days_left - b.days_left; });

    var activity = [];
    for (var i = historyDays - 1; i >= 0; i--) {
      var d = isoDay(addDays(today, -i));
      activity.push({ date: d, count: perDay[d] || 0 });
    }

    var nonDraft = rows.filter(function (r) { return (r.status || 'draft') !== 'draft'; }).length;
    var deleted = counts.deleted || 0;
    var deletionRate = nonDraft ? +((deleted / nonDraft) * 100).toFixed(1) : 0;
    var answered = deleted + (counts.responded || 0) + (counts.refused || 0);
    var responseRate = sentCount ? +((answered / sentCount) * 100).toFixed(1) : 0;
    var total = rows.length;

    var funnel = ['draft', 'sent', 'responded', 'deleted'].map(function (st) {
      return {
        stage: st, label: STATUS_LABELS[st], count: counts[st] || 0,
        percent: total ? +(((counts[st] || 0) / total) * 100).toFixed(1) : 0
      };
    });

    var byCategory = Object.keys(perCategory).map(function (c) {
      return {
        category: c, label: CATEGORY_LABELS[c] || c, count: perCategory[c],
        percent: nonDraft ? +((perCategory[c] / nonDraft) * 100).toFixed(1) : 0
      };
    }).sort(function (a, b) { return b.count - a.count; });

    var tips = [];
    var T = {
      overdue: function (n) { return 'Просрочено ' + n + ': оператор не ответил в срок. Напишите повторно («Повторить» в карточке запроса) и через 5–10 рабочих дней жалуйтесь: в РФ — в Роскомнадзор, в ЕС — в надзорный орган вашей страны, в США (Калифорния) — в CPPA/Attorney General.'; },
      waiting: function (n) { return 'Ждут ответа ' + n + '. Ответ на запрос по 152-ФЗ — 10 рабочих дней (ст. 20, продлевается не более чем на 5), уничтожение данных — до 30 дней (ст. 21). В GDPR срок ответа — один месяц (Art. 12(3)). Сохраняйте подтверждение отправки: скриншот формы или заголовки письма.'; },
      forms: function (n) { return 'Есть ' + n + ' запрос(ов) через формы и ручное удаление. По ним не будет письма-подтверждения — после отправки формы фиксируйте номер обращения в заметке к запросу.'; },
      refused: function (n) { return 'Отказов: ' + n + '. Требуйте письменное обоснование со ссылкой на норму. Если основание «общедоступные данные» — ссылайтесь на ст. 21 152-ФЗ или Art. 17 GDPR.'; },
      drafts: function (n) { return 'Черновиков: ' + n + '. Проверьте текст и отправьте: пока запрос в черновике, срок 30 дней не идёт.'; },
      deleted: function (n) { return 'Удалено ' + n + '. Через 30–45 дней проверьте снова — часть брокеров возвращает данные из резервных копий.'; },
      noprofile: function () { return 'Профиль не заполнен: в письмах не будет ФИО и контактов. Заполните раздел «Профиль» — данные остаются у вас.'; }
    };
    if (opts.profileFilled === false) tips.push(T.noprofile());
    if (overdue.length) tips.push(T.overdue(overdue.length));
    if (waiting.length) tips.push(T.waiting(waiting.length));
    var forms = rows.filter(function (r) {
      return (r.method === 'form' || r.method === 'manual') && (r.status || 'draft') !== 'draft';
    }).length;
    if (forms) tips.push(T.forms(forms));
    if (counts.refused) tips.push(T.refused(counts.refused));
    if (counts.draft) tips.push(T.drafts(counts.draft));
    if (deleted) tips.push(T.deleted(deleted));
    if (!tips.length) tips.push('Добавьте первые запросы: выберите сервис в каталоге и сгенерируйте письмо.');

    var avg = responseTimes.length
      ? +(responseTimes.reduce(function (a, b) { return a + b; }, 0) / responseTimes.length).toFixed(1)
      : null;
    var oldestOverdue = overdue.reduce(function (m, d) { return Math.max(m, Math.abs(d.days_left)); }, 0);

    return {
      demo: !!opts.demo,
      generated_at: new Date().toISOString(),
      kpi: {
        total: total, sent: sentCount, waiting: waiting.length, overdue: overdue.length,
        deleted: deleted, refused: counts.refused || 0, drafts: counts.draft || 0,
        responded: counts.responded || 0,
        deletion_rate: deletionRate, response_rate: responseRate,
        avg_response_days: avg, oldest_overdue_days: oldestOverdue
      },
      funnel: funnel, activity: activity, by_category: byCategory,
      deadlines: deadlines, waiting: waiting, overdue: overdue, tips: tips,
      note: '«Прочитано» не отслеживается: сервис не использует трекинг-пиксели и внешние картинки в письмах. Учитываются только ответы сервисов и подтверждения удаления.'
    };
  }

  /* ------------------- локальные напоминание и жалоба ------------------- */
  function buildFollowup(profile, broker, language, today, original) {
    today = today || todayDate();
    var name = clean((profile || {}).full_name);
    var emails = listOf((profile || {}).emails);
    var reply = emails[0] || '';
    var service = clean(broker.name) || 'сервис';
    var orig = clean(original).slice(0, 10);
    var L = [];
    if (language === 'en') {
      L.push('To: ' + service);
      L.push('From: ' + (name || 'a data subject') + (reply ? ' <' + reply + '>' : ''));
      L.push('Date: ' + enDate(today));
      L.push('');
      L.push('Dear Sir or Madam,');
      L.push('');
      L.push('On ' + (orig || '[date]') + ' I submitted a request for erasure of my personal data under Articles 15, 17 and 21 GDPR.');
      L.push('The one-month period of Article 12(3) GDPR has expired without a substantive reply.');
      L.push('');
      L.push('I repeat the request: erase my personal data, including copies and data shared with third parties, and confirm in writing.');
      L.push('Otherwise I will complain to the supervisory authority (Art. 77 GDPR) and seek a judicial remedy (Art. 79, 82 GDPR).');
      L.push('');
      L.push('Sincerely,');
      L.push(name || 'A data subject');
      if (reply) L.push(reply);
      return { language: 'en', kind: 'followup', subject: 'Second request — erasure (GDPR Art. 17) — ' + service, body: L.join('\n') };
    }
    L.push('Кому: ' + service);
    L.push('От: ' + (name || 'субъекта персональных данных') + (reply ? ', ' + reply : ''));
    L.push('Дата: ' + ruDate(today));
    L.push('');
    L.push('Здравствуйте!');
    L.push('');
    L.push('Направляю повторное требование. Ранее, ' + (orig || '[дата]') + ', я требовал(а) удалить мои персональные данные на основании статей 14 и 21 152-ФЗ.');
    L.push('Срок, установленный статьёй 21 152-ФЗ (30 дней), истёк, ответ в порядке статьи 20 152-ФЗ не получен, данные не уничтожены.');
    L.push('');
    L.push('Повторно требую прекратить обработку и уничтожить мои персональные данные, включая копии и резервные копии, а также направить письменное подтверждение.');
    L.push('В случае отсутствия ответа в течение 14 дней обращусь с жалобой в Роскомнадзор и в суд.');
    L.push('');
    L.push('С уважением,');
    L.push(name || 'субъект персональных данных');
    if (reply) L.push(reply);
    return { language: 'ru', kind: 'followup', subject: 'Повторное требование об удалении персональных данных — ' + service, body: L.join('\n') };
  }

  function buildLocalComplaint(profile, request) {
    var today = todayDate();
    var name = clean((profile || {}).full_name) || 'субъект персональных данных';
    var emails = listOf((profile || {}).emails);
    var reply = emails[0] || '';
    var service = request.broker_name || 'оператор';
    var sent = clean(request.sent_at).slice(0, 10) || '[дата]';
    var L = [];
    L.push('В Федеральную службу по надзору в сфере связи,');
    L.push('информационных технологий и массовых коммуникаций (Роскомнадзор)');
    L.push('');
    L.push('Заявитель: ' + name + (reply ? ', ' + reply : ''));
    L.push('Дата: ' + ruDate(today));
    L.push('');
    L.push('Жалоба на оператора: ' + service);
    L.push('');
    L.push(sent + ' я направил(а) оператору требование об удалении персональных данных на основании статей 14 и 21 152-ФЗ.');
    L.push('Ответ в порядке статьи 20 152-ФЗ не получен, данные в срок статьи 21 152-ФЗ (30 дней) не уничтожены.');
    L.push('');
    L.push('Прошу провести проверку, выдать предписание об устранении нарушения и привлечь оператора по статье 13.11 КоАП РФ.');
    L.push('');
    L.push('Приложения: копия требования, подтверждение отправки, переписка.');
    L.push('');
    L.push('С уважением,');
    L.push(name);
    if (reply) L.push(reply);
    return { language: 'ru', kind: 'complaint_rkn', subject: 'Жалоба на нарушение законодательства о персональных данных — ' + service, body: L.join('\n') };
  }

  /* ----------------------- демо-статистика ----------------------- */
  var DEMO_SPEC = [
    ['Spokeo', 'people_search', 'form', 'deleted', 41, 9],
    ['Whitepages', 'people_search', 'form', 'deleted', 35, 14],
    ['Radaris', 'people_search', 'form', 'responded', 12, 4],
    ['Intelius', 'people_search', 'form', 'refused', 28, 6],
    ['Acxiom', 'data_broker', 'form', 'sent', 38, null],
    ['LiveRamp', 'marketing', 'email', 'sent', 33, null],
    ['TruePeopleSearch', 'people_search', 'form', 'deleted', 21, 2],
    ['Яндекс (выдача)', 'search', 'form', 'sent', 9, null],
    ['Google (выдача)', 'search', 'form', 'sent', 6, null],
    ['Российский сервис (152-ФЗ)', 'data_broker', 'email', 'responded', 17, 11],
    ['Маркетинговая база', 'marketing', 'email', 'draft', null, null],
    ['Европейский сервис (GDPR)', 'data_broker', 'email', 'sent', 2, null]
  ];
  function buildDemoRequests(today) {
    today = today || todayDate();
    return DEMO_SPEC.map(function (spec, idx) {
      var name = spec[0], cat = spec[1], method = spec[2], status = spec[3], sentAgo = spec[4], respDays = spec[5];
      var sentAt = sentAgo == null ? null : addDays(today, -sentAgo);
      var deadline = sentAt ? addDays(sentAt, 30) : null;
      var responded = sentAt && respDays != null ? addDays(sentAt, respDays) : null;
      var deleted = status === 'deleted' ? addDays(sentAt, (respDays || 5) + 2) : null;
      return {
        id: 9000 + idx, broker_id: 'demo-' + idx, broker_name: name, broker_category: cat,
        method: method, status: status, language: 'ru', deadline_days: 30,
        sent_at: sentAt ? sentAt.toISOString() : null,
        responded_at: responded ? responded.toISOString() : null,
        deleted_at: deleted ? deleted.toISOString() : null,
        deadline_at: deadline ? isoDay(deadline) : null,
        created_at: (sentAt || new Date()).toISOString()
      };
    });
  }

  /* ==================== ХРАНИЛИЩЕ (localStorage) ==================== */
  var K = {
    profile: 'dc.v1.profile', requests: 'dc.v1.requests', brokers: 'dc.v1.brokers',
    llm: 'dc.v1.llm', seq: 'dc.v1.seq', chat: 'dc.v1.chat', token: 'dc.v1.token'
  };
  var mem = {};
  var storageOK = (function () {
    try { var k = '__dc_test__'; localStorage.setItem(k, '1'); localStorage.removeItem(k); return true; }
    catch (e) { return false; }
  })();

  var Store = {
    get: function (k, def) {
      try {
        var raw = storageOK ? localStorage.getItem(k) : (mem[k] == null ? null : mem[k]);
        return raw == null ? def : JSON.parse(raw);
      } catch (e) { return def; }
    },
    set: function (k, v) {
      try {
        var raw = JSON.stringify(v);
        if (storageOK) localStorage.setItem(k, raw); else mem[k] = raw;
        return true;
      } catch (e) {
        try { mem[k] = JSON.stringify(v); } catch (e2) { /* совсем нет места */ }
        return false;
      }
    },
    del: function (k) {
      try { if (storageOK) localStorage.removeItem(k); } catch (e) { /* ignore */ }
      delete mem[k];
    }
  };

  /* ============================ СОСТОЯНИЕ ============================ */
  var state = {
    server: false,
    serverMeta: {},
    view: 'dashboard',
    profile: {},
    profileUpdated: null,
    brokers: [],
    customBrokers: [],
    requests: [],
    llm: { base_url: 'https://tokenlavka.com/v1', api_key: '', model: 'gpt-6-luna' },
    llmServer: { configured: false, model: null, base_url_host: null, hint: null },
    chat: [],
    demo: null,
    filterCat: 'all',
    filterStatus: 'all',
    busy: false,
    aiMode: 'advice',
    aiStreaming: false,
    abort: null,
    models: [],
    settings: {
      smtp: { host: '', port: 587, user: '', from_addr: '', from_name: 'DataCleaner', use_ssl: false, use_starttls: true, has_password: false },
      autopilot: { auto_send: false, followup_enabled: false, followup_days: 30, interval_minutes: 15 },
      resolved: { ready: false, host: '', port: 587, from_addr: '', user: '' },
      presets: [],
      dry_run: true
    },
    facts: (typeof LOCAL_FACTS !== 'undefined' ? LOCAL_FACTS : []),
    pilotLog: []
  };

  /* --------------------------- HTTP-обёртка --------------------------- */
  function accessToken() {
    var t = Store.get(K.token, '');
    return typeof t === 'string' ? t : '';
  }

  async function http(method, path, body) {
    var opts = { method: method, headers: {}, cache: 'no-store' };
    var token = accessToken();
    if (token) opts.headers['X-Access-Token'] = token;
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    var resp = await fetch(path, opts);
    var text = await resp.text();
    var data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text }; }
    if (!resp.ok) {
      var msg = (data && (data.detail || data.message || data.warning)) || ('HTTP ' + resp.status);
      var err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      err.status = resp.status; err.data = data;
      err.authRequired = !!(data && data.auth_required);
      throw err;
    }
    return data;
  }

  async function detectServer() {
    if (!/^https?:$/.test(location.protocol)) return false;
    try {
      var ctrl = new AbortController();
      var t = setTimeout(function () { ctrl.abort(); }, 2500);
      var headers = {};
      var token = accessToken();
      if (token) headers['X-Access-Token'] = token;
      var r = await fetch('api/health', { cache: 'no-store', signal: ctrl.signal, headers: headers });
      clearTimeout(t);
      if (r.status === 401) return true; /* сервер есть, но нужен код доступа */
      if (!r.ok) return false;
      var j = await r.json();
      return !!(j && j.ok);
    } catch (e) { return false; }
  }

  function seqNext() {
    var n = Number(Store.get(K.seq, 0) || 0) + 1;
    Store.set(K.seq, n);
    return n;
  }
  function localRequests() { return Store.get(K.requests, []) || []; }
  function persistRequests(list) { Store.set(K.requests, list); }
  function localEvent(req, type, from, to, note) {
    req.events = req.events || [];
    req.events.push({ type: type, from_status: from || '', to_status: to || '', note: note || '', at: new Date().toISOString() });
  }

  /* ============================== СЛОЙ API ==============================
     Один интерфейс, две реализации: local (localStorage) и server (FastAPI).
     ==================================================================== */
  var Api = {
    init: async function () {
      state.server = await detectServer();
      if (state.server) {
        state.serverMeta = (await http('GET', 'api/health')) || {};
        var prof = await http('GET', 'api/profile');
        state.profile = (prof && prof.profile) || {};
        state.profileUpdated = (prof && prof.updated_at) || null;
        var br = await http('GET', 'api/brokers');
        var items = (br && br.items) || [];
        state.brokers = items;
        state.customBrokers = items.filter(function (b) { return b.custom; });
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        state.llmServer = (await http('GET', 'api/assistant/status')) || { configured: false };
        try {
          state.settings = await http('GET', 'api/settings');
          state.facts = ((await http('GET', 'api/knowledge')) || {}).facts || state.facts;
        } catch (e) { /* настройки недоступны — работаем на значениях по умолчанию */ }
      } else {
        state.profile = Store.get(K.profile, {}) || {};
        state.profileUpdated = Store.get(K.profile + '.at', null);
        var custom = Store.get(K.brokers, []) || [];
        state.customBrokers = custom;
        state.brokers = BUILTIN_BROKERS.concat(custom.map(function (b) {
          return Object.assign({}, b, { custom: true, verify: false });
        }));
        state.requests = localRequests();
        state.llm = Object.assign({}, state.llm, Store.get(K.llm, {}) || {});
        state.llmServer = { configured: !!(state.llm.base_url && state.llm.api_key && state.llm.model), local: true };
        var localSettings = Store.get('dc.v1.settings', null);
        if (localSettings) state.settings = Object.assign({}, state.settings, localSettings);
        state.settings.serverOnly = true;
      }
      state.chat = Store.get(K.chat, []) || [];
    },

    profileFilled: function () {
      return !!(clean(state.profile.full_name) && listOf(state.profile.emails).length);
    },

    saveProfile: async function (p) {
      if (state.server) {
        var res = await http('PUT', 'api/profile', p);
        state.profile = p;
        state.profileUpdated = new Date().toISOString();
        return res;
      }
      state.profile = p;
      state.profileUpdated = new Date().toISOString();
      Store.set(K.profile, p);
      Store.set(K.profile + '.at', state.profileUpdated);
      return { ok: true, detail: 'Профиль сохранён в localStorage этого устройства.' };
    },

    addBroker: async function (b) {
      if (state.server) {
        var res = await http('POST', 'api/brokers', b);
        var br = await http('GET', 'api/brokers');
        state.brokers = (br && br.items) || [];
        state.customBrokers = state.brokers.filter(function (x) { return x.custom; });
        return res;
      }
      var custom = Store.get(K.brokers, []) || [];
      if (state.brokers.some(function (x) { return x.id === b.id; })) throw new Error('Сервис с таким id уже есть');
      custom.push(b);
      Store.set(K.brokers, custom);
      state.customBrokers = custom;
      state.brokers = BUILTIN_BROKERS.concat(custom.map(function (x) {
        return Object.assign({}, x, { custom: true, verify: false });
      }));
      return { ok: true };
    },

    deleteBroker: async function (id) {
      if (state.server) {
        var res = await http('DELETE', 'api/brokers/' + encodeURIComponent(id));
        var br = await http('GET', 'api/brokers');
        state.brokers = (br && br.items) || [];
        state.customBrokers = state.brokers.filter(function (x) { return x.custom; });
        return res;
      }
      var custom = (Store.get(K.brokers, []) || []).filter(function (b) { return b.id !== id; });
      Store.set(K.brokers, custom);
      state.customBrokers = custom;
      state.brokers = BUILTIN_BROKERS.concat(custom.map(function (x) {
        return Object.assign({}, x, { custom: true, verify: false });
      }));
      return { ok: true };
    },

    createRequest: async function (brokerId, language) {
      var broker = state.brokers.filter(function (b) { return b.id === brokerId; })[0];
      if (!broker) throw new Error('Сервис не найден');
      if (state.server) {
        var res = await http('POST', 'api/requests', { broker_id: brokerId, language: language || null });
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        return res;
      }
      var letter = buildLetter(state.profile, broker, language);
      var req = {
        id: seqNext(), broker_id: broker.id, broker_name: broker.name,
        broker_category: broker.category || 'data_broker', method: broker.method || 'email',
        to_email: broker.email || '', language: letter.language,
        subject: letter.subject, body: letter.body, status: 'draft',
        deadline_days: letter.deadline_days, deadline_at: letter.deadline_date,
        created_at: new Date().toISOString(), sent_at: null, responded_at: null,
        deleted_at: null, note: '', error: '', events: []
      };
      localEvent(req, 'created', '', 'draft', 'Запрос создан');
      var list = localRequests(); list.push(req); persistRequests(list);
      state.requests = list;
      return { ok: true, request: req, letter: letter };
    },

    getRequestFull: async function (id) {
      if (state.server) return await http('GET', 'api/requests/' + id);
      var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) throw new Error('Запрос не найден');
      return {
        request: req,
        letter: { language: req.language, subject: req.subject, body: req.body },
        events: req.events || []
      };
    },

    send: async function (id) {
      if (state.server) {
        var res = await http('POST', 'api/requests/' + id + '/send', {});
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        return res;
      }
      var list = localRequests();
      var req = list.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) throw new Error('Запрос не найден');
      if (req.status !== 'draft') throw new Error('Отправить можно только черновик');
      req.status = 'sent';
      req.sent_at = new Date().toISOString();
      req.deadline_at = isoDay(addDays(todayDate(), Number(req.deadline_days || 30)));
      localEvent(req, 'send', 'draft', 'sent', req.method === 'email'
        ? 'Письмо подготовлено: скопировано в буфер или открыто в почтовом клиенте'
        : 'Отправлено вручную через форму сервиса');
      persistRequests(list);
      state.requests = list;
      return {
        ok: true, dry_run: true,
        detail: 'Запрос отмечен отправленным. Браузерная версия не отправляет письма сама — текст копируется, отправка идёт из вашего почтового клиента.',
        request: req
      };
    },

    setStatus: async function (id, status, note) {
      if (state.server) {
        var res = await http('PATCH', 'api/requests/' + id, { status: status, note: note == null ? null : note });
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        return res;
      }
      var list = localRequests();
      var req = list.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) throw new Error('Запрос не найден');
      if (note != null) {
        req.note = note;
        localEvent(req, 'note', req.status, req.status, 'Заметка обновлена');
      }
      if (status && status !== req.status) {
        if (!canTransition(req.status, status)) {
          throw new Error('Переход «' + STATUS_LABELS[req.status] + '» → «' + STATUS_LABELS[status] + '» недоступен');
        }
        var from = req.status, ts = new Date().toISOString();
        req.status = status;
        if (status === 'sent' && !req.sent_at) {
          req.sent_at = ts;
          req.deadline_at = isoDay(addDays(todayDate(), Number(req.deadline_days || 30)));
        }
        if (status === 'responded') req.responded_at = req.responded_at || ts;
        if (status === 'deleted') req.deleted_at = ts;
        if (status === 'draft') { req.sent_at = null; req.responded_at = null; req.deleted_at = null; }
        localEvent(req, status === 'draft' ? 'repeat' : 'status', from, status, note || '');
      }
      persistRequests(list);
      state.requests = list;
      return { ok: true, request: req };
    },

    deleteRequest: async function (id) {
      if (state.server) {
        var res = await http('DELETE', 'api/requests/' + id);
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        return res;
      }
      var list = localRequests().filter(function (r) { return String(r.id) !== String(id); });
      persistRequests(list);
      state.requests = list;
      return { ok: true };
    },

    stats: async function () {
      if (state.server) return await http('GET', 'api/stats');
      return computeStats(state.requests, { profileFilled: Api.profileFilled() });
    },

    demoStats: async function () {
      if (state.server) return await http('POST', 'api/stats/demo', {});
      return computeStats(buildDemoRequests(), { profileFilled: true, demo: true });
    },

    wipe: async function () {
      if (state.server) {
        var res = await http('POST', 'api/wipe', { confirm: 'DELETE' });
        state.requests = []; state.profile = {}; state.profileUpdated = null; state.chat = [];
        var br = await http('GET', 'api/brokers');
        state.brokers = (br && br.items) || [];
        state.customBrokers = [];
        return res;
      }
      Object.keys(K).forEach(function (k) { Store.del(K[k]); });
      state.requests = []; state.profile = {}; state.profileUpdated = null;
      state.chat = []; state.customBrokers = [];
      state.brokers = BUILTIN_BROKERS.slice();
      return { ok: true, detail: 'localStorage очищен: профиль, запросы, история, свои сервисы.' };
    },

    exportData: async function () {
      if (state.server) return await http('GET', 'api/export');
      return {
        exported_at: new Date().toISOString(),
        warning: 'В файле ВАШИ персональные данные в открытом виде. Храните его как конфиденциальный документ.',
        profile: state.profile,
        requests: state.requests
      };
    },

    saveLlm: async function (cfg) {
      state.llm = Object.assign({}, state.llm, cfg);
      Store.set(K.llm, state.llm);
      state.llmServer = { configured: !!(state.llm.base_url && state.llm.api_key && state.llm.model), local: true };
      return { ok: true };
    },

    /* ---- настройки: почта и автопилот ---- */
    getSettings: async function () {
      if (state.server) state.settings = await http('GET', 'api/settings');
      return state.settings;
    },

    saveSettings: async function (payload) {
      if (state.server) {
        state.settings = await http('PUT', 'api/settings', payload);
      } else {
        state.settings = Object.assign({}, state.settings, payload);
        Store.set('dc.v1.settings', state.settings);
      }
      return state.settings;
    },

    testSmtp: async function (opts) {
      if (!state.server) {
        return { ok: false, detail: 'Проверка и автоотправка работают только в серверной версии: браузер не может отправить письмо с вашего домена.' };
      }
      return await http('POST', 'api/settings/smtp/test', opts || {});
    },

    runAutopilot: async function () {
      if (!state.server) {
        return { ok: false, detail: 'Автопилот доступен в серверной версии (FastAPI). В локальном режиме письма отправляются вручную.' };
      }
      var res = await http('POST', 'api/autopilot/run', {});
      var rq = await http('GET', 'api/requests');
      state.requests = (rq && rq.items) || [];
      state.pilotLog.unshift(res.report);
      return res;
    },

    bulkSend: async function () {
      if (!state.server) {
        var sent = [];
        for (var i = 0; i < state.requests.length; i++) {
          if (state.requests[i].status === 'draft') sent.push(await Api.send(state.requests[i].id));
        }
        return { ok: true, detail: 'Локальный режим: черновики отмечены отправленными (письма копируются вручную).', sent: sent, failed: [] };
      }
      var res = await http('POST', 'api/requests/autosend', {});
      var rq2 = await http('GET', 'api/requests');
      state.requests = (rq2 && rq2.items) || [];
      return res;
    },

    followup: async function (id) {
      if (state.server) {
        var res = await http('POST', 'api/requests/' + id + '/followup', {});
        var rq = await http('GET', 'api/requests');
        state.requests = (rq && rq.items) || [];
        return res;
      }
      var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) throw new Error('Запрос не найден');
      var letter = buildFollowup(state.profile, { name: req.broker_name, language: req.language }, req.language, todayDate(), req.sent_at);
      localEvent(req, 'followup', req.status, req.status, 'Подготовлено повторное требование (отправьте вручную)');
      persistRequests(state.requests);
      return { ok: true, dry_run: true, detail: 'Напоминание сформировано — скопируйте и отправьте.', letter: letter };
    },

    complaint: async function (id) {
      if (state.server) return await http('POST', 'api/requests/' + id + '/complaint', {});
      var req = state.requests.filter(function (r) { return String(r.id) === String(id); })[0];
      if (!req) throw new Error('Запрос не найден');
      return { ok: true, letter: buildLocalComplaint(state.profile, req) };
    },

    knowledge: async function () {
      if (state.server) {
        try { state.facts = ((await http('GET', 'api/knowledge')) || {}).facts || state.facts; } catch (e) { /* ignore */ }
      }
      return state.facts;
    },

    models: async function () {
      if (state.server) {
        try {
          var res = await http('GET', 'api/models');
          state.models = (res && res.models) || [];
          return res;
        } catch (e) { return { ok: false, models: [] }; }
      }
      state.models = [state.llm.model].filter(Boolean);
      return { ok: false, models: state.models };
    },

    ask: async function (question, history) {
      var kinds = detectPII(question);
      if (kinds.length) return { ok: false, blocked: true, warning: piiWarning(kinds) };

      if (state.server) {
        try {
          return await http('POST', 'api/assistant', { question: question, history: history || [] });
        } catch (e) {
          return { ok: false, message: e.message };
        }
      }

      var cfg = state.llm || {};
      if (!clean(cfg.base_url) || !clean(cfg.api_key) || !clean(cfg.model)) {
        return {
          ok: false, notConfigured: true,
          hint: 'AI-помощник не настроен. Откройте «Настройки» в этом разделе и укажите Base URL, ключ и модель OpenAI-совместимого провайдера. Ключ хранится только в этом браузере.'
        };
      }
      var base = clean(cfg.base_url).replace(/\/+$/, '');
      var sys = 'Ты — консультант сервиса DataCleaner по удалению персональных данных из интернета: брокеры данных, people-search, маркетинговые базы, поисковая выдача. '
        + 'Помогай с правами по 152-ФЗ (ст. 14, 20, 21), GDPR (Art. 15, 17, 21, 12) и CCPA/CPRA (§1798.105, §1798.130), с составлением запросов и жалоб (Роскомнадзор, надзорный орган ЕС, CPPA/Attorney General). '
        + 'Никогда не проси у пользователя персональные данные: ФИО, email, телефон, адрес, номера документов — вместо этого объясни, что их нужно вписать самостоятельно в шаблон письма. '
        + 'Если пользователь сам прислал ПД — не повторяй их и попроси удалить. Отвечай по-русски, кратко и структурно (нумерованные шаги, сроки, нормы), максимум 250 слов. '
        + 'Не выдумывай точные URL и email сервисов: если не уверен, скажи, что адрес надо проверить в политике конфиденциальности сервиса. '
        + 'Ты не юрист: в конце одной строкой напомни, что это информационная справка, а не юридическое заключение.';

      var messages = [{ role: 'system', content: sys }];
      (history || []).slice(-6).forEach(function (m) {
        if (m && (m.role === 'user' || m.role === 'assistant') && clean(m.content) && !detectPII(m.content).length) {
          messages.push({ role: m.role, content: String(m.content).slice(0, 2000) });
        }
      });
      messages.push({ role: 'user', content: question });

      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, 70000);
      try {
        var resp = await fetch(base + '/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg.api_key },
          body: JSON.stringify({ model: cfg.model, messages: messages, temperature: 0.3, max_tokens: 800 }),
          signal: ctrl.signal
        });
        clearTimeout(timer);
        if (resp.status === 401) return { ok: false, message: 'Провайдер отклонил ключ (401). Проверьте ключ в настройках AI.' };
        if (resp.status === 402) return { ok: false, message: 'На балансе провайдера закончились средства (402).' };
        if (resp.status === 429) return { ok: false, message: 'Слишком много запросов (429). Подождите немного.' };
        if (!resp.ok) {
          var txt = '';
          try {
            var j = await resp.json();
            txt = (j.error && (j.error.message || j.error)) || '';
          } catch (e) { txt = ''; }
          return {
            ok: false,
            message: 'Провайдер вернул ошибку ' + resp.status + '. ' + (typeof txt === 'string' ? txt.slice(0, 200) : '')
          };
        }
        var data = await resp.json();
        var answer = data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
        if (!answer) return { ok: false, message: 'Пустой ответ модели. Переформулируйте вопрос или увеличьте max_tokens.' };
        return { ok: true, answer: String(answer).trim(), model: data.model || cfg.model, usage: data.usage || {} };
      } catch (err) {
        clearTimeout(timer);
        var cors = (err && err.name === 'TypeError') || /Failed to fetch|NetworkError|Load failed/i.test(String(err && err.message));
        return {
          ok: false, cors: cors,
          message: cors
            ? 'Браузер не смог обратиться к провайдеру (CORS или сеть). Провайдер должен разрешать запросы из браузера. Если он этого не делает — используйте серверную версию DataCleaner (app/main.py): там запрос идёт с сервера и CORS не мешает.'
            : 'Ошибка запроса: ' + (err && err.message ? err.message : 'неизвестная') + '. Проверьте Base URL и подключение к интернету.'
        };
      }
    }
  };
