/* ==================================================================
   DataCleaner · 01-core.js — утилиты и чистая логика.
   Блок не обращается к DOM и к сети: его прогоняет «Самопроверка».
   ================================================================== */
(function () {
  'use strict';

  /* ============================ УТИЛИТЫ ============================ */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function clean(v) { return (v == null ? '' : String(v)).trim(); }
  function listOf(v) {
    if (v == null) return [];
    var parts = Array.isArray(v) ? v : String(v).replace(/;/g, ',').split(',');
    var out = [];
    parts.forEach(function (p) { p = clean(p); if (p && out.indexOf(p) === -1) out.push(p); });
    return out;
  }
  function isoDay(d) {
    var y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), dd = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + dd;
  }
  function todayDate() { var d = new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
  function parseDay(s) {
    if (!s) return null;
    var m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }
  function addDays(d, n) { var x = new Date(d.getTime()); x.setDate(x.getDate() + n); return x; }
  function daysBetween(a, b) { return Math.round((b.getTime() - a.getTime()) / 86400000); }
  function fmtDate(s) {
    var d = parseDay(s);
    if (!d) return '—';
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function fmtDateTime(s) {
    if (!s) return '—';
    var d = new Date(s);
    if (isNaN(d.getTime())) return fmtDate(s);
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  }

  /* ======================= СТАТУСЫ И КАТЕГОРИИ ======================= */
  var STATUS_LABELS = { draft: 'Черновик', sent: 'Отправлено', responded: 'Ответили', deleted: 'Удалено', refused: 'Отказ' };
  var STATUS_CLASS = { draft: 'neutral', sent: 'acc', responded: 'warn', deleted: 'ok', refused: 'bad' };
  var CATEGORY_LABELS = {
    people_search: 'People-search', data_broker: 'Брокеры данных',
    marketing: 'Маркетинг', search: 'Поисковики', custom: 'Свои сервисы'
  };
  var METHOD_LABELS = { email: 'письмо на email', form: 'форма на сайте', manual: 'вручную' };

  var TRANSITIONS = {
    draft: ['sent'],
    sent: ['responded', 'deleted', 'refused', 'draft'],
    responded: ['deleted', 'refused', 'draft'],
    refused: ['deleted', 'draft'],
    deleted: ['draft']
  };
  function canTransition(from, to) {
    if (to === from) return true;
    return (TRANSITIONS[from] || []).indexOf(to) !== -1;
  }

  /* ---- встроенный каталог (аналог app/brokers.json) ---- */
  var BUILTIN_BROKERS = [
    { id: 'spokeo', name: 'Spokeo', category: 'people_search', method: 'form', url: 'https://www.spokeo.com/optout', email: '', language: 'en', deadline_days: 30, verify: true, notes: 'Крупный people-search агрегатор (США). Удаление через форму opt-out: найти свою карточку по URL профиля.' },
    { id: 'whitepages', name: 'Whitepages', category: 'people_search', method: 'form', url: 'https://www.whitepages.com/suppression-requests', email: '', language: 'en', deadline_days: 30, verify: true, notes: 'Форма suppression request: подтверждение приходит на email или по телефону.' },
    { id: 'truepeoplesearch', name: 'TruePeopleSearch', category: 'people_search', method: 'form', url: 'https://www.truepeoplesearch.com/removal', email: '', language: 'en', deadline_days: 30, verify: true, notes: 'Бесплатный people-search. Форма удаления по URL записи, обычно удаляют за 72 часа.' },
    { id: 'radaris', name: 'Radaris', category: 'people_search', method: 'form', url: 'https://radaris.com/control/privacy', email: '', language: 'en', deadline_days: 30, verify: true, notes: 'Требует регистрации/подтверждения для opt-out.' },
    { id: 'intelius', name: 'Intelius', category: 'people_search', method: 'form', url: 'https://www.intelius.com/opt-out/', email: '', language: 'en', deadline_days: 45, verify: true, notes: 'Группа PeopleConnect: один opt-out может покрыть несколько брендов.' },
    { id: 'beenverified', name: 'BeenVerified', category: 'people_search', method: 'form', url: 'https://www.beenverified.com/app/optout/search', email: '', language: 'en', deadline_days: 45, verify: true, notes: 'PeopleConnect. Жителям Калифорнии дополнительно помогает CCPA/CPRA.' },
    { id: 'acxiom', name: 'Acxiom', category: 'data_broker', method: 'form', url: 'https://isapps.acxiom.com/optout/optout.aspx', email: '', language: 'en', deadline_days: 45, verify: true, notes: 'Крупный маркетинговый брокер. Opt-out ограничивает продажу/маркетинг, но не всегда значит полное удаление.' },
    { id: 'liveramp', name: 'LiveRamp', category: 'marketing', method: 'form', url: 'https://liveramp.com/opt_out/', email: 'privacy@liveramp.com', language: 'en', deadline_days: 45, verify: true, notes: 'Identity-граф для рекламы: форма opt-out + письмо по GDPR/CCPA.' },
    { id: 'google-search', name: 'Google (удаление из выдачи)', category: 'search', method: 'form', url: 'https://reportcontent.google.com/forms/rtbf', email: '', language: 'en', deadline_days: 30, verify: true, notes: 'Удаление конкретных URL из поиска. Это не удаление у первоисточника: сначала требуйте удаления у сайта.' },
    { id: 'yandex-search', name: 'Яндекс (удаление из выдачи)', category: 'search', method: 'form', url: 'https://yandex.ru/support/search/request/remove-personal-data.html', email: '', language: 'ru', deadline_days: 30, verify: true, notes: 'Заявление об удалении ссылок с ПД из результатов поиска (152-ФЗ). Адрес формы проверяйте: Яндекс его меняет.' },
    { id: 'ru-152-template', name: 'Российский сервис (шаблон 152-ФЗ)', category: 'data_broker', method: 'email', url: '', email: 'privacy@example.ru', language: 'ru', deadline_days: 30, verify: true, notes: 'ШАБЛОН: замените privacy@example.ru на адрес оператора из его политики обработки ПД и переименуйте сервис.' },
    { id: 'eu-gdpr-template', name: 'Европейский сервис (шаблон GDPR)', category: 'data_broker', method: 'email', url: '', email: 'dpo@example.eu', language: 'en', deadline_days: 30, verify: true, notes: 'ШАБЛОН: замените dpo@example.eu на адрес DPO/privacy из политики конфиденциальности сервиса.' },
    { id: 'ru-marketing-template', name: 'Российская маркетинговая база (шаблон)', category: 'marketing', method: 'email', url: '', email: 'privacy@example.ru', language: 'ru', deadline_days: 30, verify: true, notes: 'ШАБЛОН для рассылочных баз и колл-центров: отзыв согласия и требование прекратить обработку (ст. 9, 21 152-ФЗ).' }
  ];

  var LEGAL_RU = [
    'ст. 14 152-ФЗ — право субъекта на доступ к своим персональным данным',
    'ст. 21 152-ФЗ — обязанность оператора прекратить обработку и уничтожить данные',
    'ст. 9 152-ФЗ — отзыв согласия на обработку',
    'ст. 20 152-ФЗ — срок ответа на запрос субъекта'
  ];
  var LEGAL_EN = [
    'Art. 15 GDPR — right of access',
    'Art. 17 GDPR — right to erasure',
    'Art. 21 GDPR — right to object',
    'Art. 12(3) GDPR — ответ в течение одного месяца',
    'CCPA/CPRA §1798.105 — right to delete, §1798.130 — срок 45 дней'
  ];

  function piiRows(profile, lang) {
    profile = profile || {};
    var rows = [], name = clean(profile.full_name), emails = listOf(profile.emails),
        phones = listOf(profile.phones), city = clean(profile.city),
        year = clean(profile.birth_year), address = clean(profile.address);
    if (lang === 'ru') {
      if (name) rows.push('ФИО: ' + name);
      if (emails.length) rows.push('Адрес электронной почты: ' + emails.join(', '));
      if (phones.length) rows.push('Номер телефона: ' + phones.join(', '));
      if (year) rows.push('Год рождения: ' + year);
      if (city) rows.push('Город: ' + city);
      if (address) rows.push('Адрес: ' + address);
    } else {
      if (name) rows.push('Full name: ' + name);
      if (emails.length) rows.push('Email address(es): ' + emails.join(', '));
      if (phones.length) rows.push('Phone number(s): ' + phones.join(', '));
      if (year) rows.push('Year of birth: ' + year);
      if (city) rows.push('City: ' + city);
      if (address) rows.push('Postal address: ' + address);
    }
    return rows;
  }

  function ruDate(d) {
    var months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    return d.getDate() + ' ' + months[d.getMonth()] + ' ' + d.getFullYear() + ' г.';
  }
  function enDate(d) {
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return d.getDate() + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
  }

  /* ------------------------- русское письмо ------------------------- */
  function buildRuLetter(profile, broker, today) {
    profile = profile || {}; broker = broker || {};
    today = today || todayDate();
    var name = clean(profile.full_name), who = name || 'субъекта персональных данных';
    var rows = piiRows(profile, 'ru'), emails = listOf(profile.emails), phones = listOf(profile.phones);
    var reply = emails[0] || phones[0] || '';
    var service = clean(broker.name) || clean(broker.id) || 'сервис';
    var days = Number(broker.deadline_days || 30);
    var subject = 'Требование об удалении персональных данных — ' + who;
    var L = [];
    L.push('Кому: ' + service + (clean(broker.email) ? ' (' + clean(broker.email) + ')' : ''));
    L.push('От: ' + who + (reply ? ', ' + reply : ''));
    L.push('Дата: ' + ruDate(today));
    L.push('');
    L.push('Здравствуйте!');
    L.push('');
    L.push('Я являюсь субъектом персональных данных и обращаюсь к вам как к оператору, осуществляющему обработку персональных данных (сервис: ' + service + ').');
    L.push('');
    if (rows.length) {
      L.push('В вашем сервисе обрабатываются следующие мои персональные данные:');
      L.push('');
      rows.forEach(function (r) { L.push('  • ' + r); });
      L.push('');
    }
    L.push('На основании статьи 14 Федерального закона от 27.07.2006 № 152-ФЗ «О персональных данных» прошу предоставить мне сведения, предусмотренные частью 7 указанной статьи, в том числе:');
    L.push('  1) подтверждение факта обработки моих персональных данных;');
    L.push('  2) правовые основания и цели обработки;');
    L.push('  3) перечень обрабатываемых персональных данных и источники их получения;');
    L.push('  4) сроки обработки, а также порядок и условия их прекращения;');
    L.push('  5) сведения о лицах, которым могут быть переданы мои персональные данные.');
    L.push('');
    L.push('Одновременно, на основании статьи 21 152-ФЗ, требую:');
    L.push('  1) прекратить обработку моих персональных данных;');
    L.push('  2) уничтожить (удалить) мои персональные данные, включая их копии, резервные копии, а также данные, переданные третьим лицам и партнёрам;');
    L.push('  3) исключить мои данные из поисковой выдачи, профилей и открытых карточек;');
    L.push('  4) прекратить использование моих данных в целях рекламы и маркетинга и отозвать переданные ранее согласия (статья 9 152-ФЗ);');
    L.push('  5) направить мне письменное подтверждение уничтожения персональных данных.');
    L.push('');
    L.push('Согласно частям 1, 3 и 5 статьи 21 152-ФЗ обработка должна быть прекращена, а персональные данные уничтожены в срок, не превышающий 30 дней с даты получения настоящего требования. Ответ на запрос субъекта персональных данных предоставляется в порядке и сроки, установленные статьёй 20 152-ФЗ.');
    L.push('');
    L.push(reply
      ? 'Ответ прошу направить в письменной форме на адрес электронной почты: ' + reply + '.'
      : 'Ответ прошу направить в письменной форме по указанным выше контактным данным.');
    L.push('');
    L.push('В случае неисполнения требования я оставляю за собой право обратиться в Роскомнадзор с жалобой на нарушение законодательства о персональных данных, а также в суд.');
    L.push('');
    L.push('Прошу не использовать мои персональные данные для иных целей, кроме рассмотрения настоящего требования.');
    L.push('');
    L.push('С уважением,');
    L.push(name || 'субъект персональных данных');
    if (reply) L.push(reply);
    return {
      language: 'ru', subject: subject, body: L.join('\n').replace(/\n+$/, '\n'),
      legal: LEGAL_RU.slice(), deadline_days: days,
      deadline_date: isoDay(addDays(today, days))
    };
  }

  /* ------------------------ английское письмо ------------------------ */
  function buildEnLetter(profile, broker, today) {
    profile = profile || {}; broker = broker || {};
    today = today || todayDate();
    var name = clean(profile.full_name), who = name || 'a data subject';
    var rows = piiRows(profile, 'en'), emails = listOf(profile.emails), phones = listOf(profile.phones);
    var reply = emails[0] || phones[0] || '';
    var service = clean(broker.name) || clean(broker.id) || 'the service';
    var days = Number(broker.deadline_days || 30);
    var subject = 'Formal request for erasure of personal data (GDPR Art. 17 / CCPA §1798.105) — ' + who;
    var L = [];
    L.push('To: ' + service + (clean(broker.email) ? ' — ' + clean(broker.email) : ' — Privacy / DPO'));
    L.push('From: ' + who + (reply ? ' <' + reply + '>' : ''));
    L.push('Date: ' + enDate(today));
    L.push('');
    L.push('Dear Sir or Madam,');
    L.push('');
    L.push('I am writing to exercise my rights as a data subject under the EU General Data Protection Regulation (Regulation (EU) 2016/679) and, where applicable, the California Consumer Privacy Act as amended by the CPRA. The processing concerns the service ' + service + '.');
    L.push('');
    if (rows.length) {
      L.push('The personal data concerned:');
      L.push('');
      rows.forEach(function (r) { L.push('  • ' + r); });
      L.push('');
    }
    L.push('Under Article 15 GDPR I request confirmation of whether you process personal data concerning me, together with a copy of that data, the purposes of the processing, the categories of data, the recipients, the retention period and the source of the data.');
    L.push('');
    L.push('Under Article 17 GDPR I request the erasure of my personal data without undue delay, including any copies, backups, derived profiles, and data shared with third parties, affiliates and marketing partners. Under Article 21 GDPR I object to the processing of my personal data for direct marketing purposes.');
    L.push('');
    L.push('Where you are a business subject to the CCPA/CPRA, I request the deletion of my personal information pursuant to §1798.105 and confirmation that you have directed service providers and contractors to delete it as well. I do not wish my personal information to be sold or shared (§1798.120, §1798.121).');
    L.push('');
    L.push('Please confirm in writing, within one month as required by Article 12(3) GDPR (45 days under §1798.130 CCPA), that my personal data has been erased and that no further processing will take place.');
    L.push('');
    L.push(reply ? 'Please send your written confirmation to: ' + reply + '.' : 'Please send your written confirmation to the contact details above.');
    L.push('');
    L.push('I am ready to provide reasonable proof of identity if required, and I ask you not to request more personal data than is necessary to verify it.');
    L.push('');
    L.push('If you fail to act on this request, I reserve the right to lodge a complaint with the competent supervisory authority in my country, with the California Privacy Protection Agency or the California Attorney General, and to seek a judicial remedy.');
    L.push('');
    L.push('Sincerely,');
    L.push(name || 'A data subject');
    if (reply) L.push(reply);
    return {
      language: 'en', subject: subject, body: L.join('\n').replace(/\n+$/, '\n'),
      legal: LEGAL_EN.slice(), deadline_days: days,
      deadline_date: isoDay(addDays(today, days))
    };
  }

  function buildLetter(profile, broker, language, today) {
    var lang = clean(language) || clean((broker || {}).language) || clean((profile || {}).language) || 'ru';
    if (lang !== 'ru' && lang !== 'en') lang = 'ru';
    return lang === 'ru' ? buildRuLetter(profile, broker, today) : buildEnLetter(profile, broker, today);
  }

  /* ------------------------ PII-фильтр для AI ------------------------ */
  var PII_PATTERNS = [
    ['email', '[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}'],
    ['phone', '(?:\\+\\d{1,3}[\\s\\-().]*)?(?:\\(\\d{2,4}\\)[\\s\\-]*)?\\d[\\d\\s\\-().]{7,}\\d'],
    ['card', '(?:\\d[ \\-]?){13,19}'],
    ['snils', '\\d{3}[-\\s]?\\d{3}[-\\s]?\\d{3}[-\\s]?\\d{2}'],
    ['passport', '\\d{2}\\s?\\d{2}\\s?(?:№|N|no\\.?)?\\s?\\d{6}']
  ];
  function detectPII(text) {
    var src = text == null ? '' : String(text), found = [];
    PII_PATTERNS.forEach(function (p) {
      var re = new RegExp(p[1]);
      if (re.test(src) && found.indexOf(p[0]) === -1) found.push(p[0]);
    });
    return found;
  }
  function piiWarning(kinds) {
    return 'Похоже, в вопросе есть персональные данные (' + kinds.join(', ') + '). Запрос в AI-модель не отправлен: переписка с внешним провайдером не должна содержать ПД. Уберите email/телефон/номер документа — ФИО и контакты подставляются в письма локально, на вашем устройстве.';
  }
