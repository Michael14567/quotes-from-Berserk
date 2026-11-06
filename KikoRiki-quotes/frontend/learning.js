(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const workspace = $('#workspace');
  let openedBy = null;
  let taskTimer = null;
  let mapTimer = null;

  function closePanel() {
    workspace.hidden = true;
    document.querySelectorAll('.work-panel').forEach(panel => { panel.hidden = true; });
    document.querySelectorAll('[data-panel]').forEach(button => button.setAttribute('aria-expanded', 'false'));
    $('.terminal').classList.remove('has-workspace');
    stopMap();
    clearInterval(taskTimer);
    openedBy?.focus();
  }

  document.querySelectorAll('[data-panel]').forEach(button => {
    button.addEventListener('click', () => {
      const panel = document.getElementById(button.dataset.panel);
      if (!panel.hidden) { closePanel(); return; }
      closePanel();
      openedBy = button;
      panel.hidden = false;
      workspace.hidden = false;
      $('.terminal').classList.add('has-workspace');
      button.setAttribute('aria-expanded', 'true');
      if (panel.id === 'map-panel') requestAnimationFrame(drawMap);
      if (panel.id === 'tasks-panel') {
        loadTasks();
        taskTimer = setInterval(() => { if (!document.hidden) loadTasks(true); }, 15000);
      }
      panel.scrollIntoView({ block: 'start', behavior: reducedMotion.matches ? 'instant' : 'smooth' });
      panel.querySelector('h1').setAttribute('tabindex', '-1');
      panel.querySelector('h1').focus({ preventScroll: true });
    });
  });
  document.querySelectorAll('[data-close-panel]').forEach(button => button.addEventListener('click', closePanel));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !workspace.hidden) closePanel();
  });

  // Вопросы и эталонные решения для самопроверки: никакого исполнения команд.
  const exercises = {
    sql: [
      { question: 'Выведи последние 5 цитат Бараша по убыванию id.', context: 'smeshariki_quotes(id, text, character)', hint: 'WHERE отбирает строки, ORDER BY задаёт порядок, LIMIT ограничивает результат.', code: "SELECT id, text\nFROM smeshariki_quotes\nWHERE character = 'Бараш'\nORDER BY id DESC\nLIMIT 5;", explanation: 'Сначала отбираем персонажа, затем сортируем. Без ORDER BY порядок строк не гарантирован.' },
      { question: 'Посчитай цитаты каждого персонажа. Покажи только тех, у кого больше 10 цитат.', context: 'smeshariki_quotes(id, text, character)', hint: 'После GROUP BY используй HAVING для фильтрации групп.', code: 'SELECT character, COUNT(*) AS total\nFROM smeshariki_quotes\nGROUP BY character\nHAVING COUNT(*) > 10\nORDER BY total DESC;', explanation: 'WHERE фильтрует отдельные строки до группировки; HAVING — результаты группировки.' },
      { question: 'Найди цитаты, в которых встречается «смысл», независимо от регистра.', context: 'smeshariki_quotes(id, text, character)\nИспользуем PostgreSQL.', hint: 'ILIKE — поиск без учёта регистра. % соответствует произвольной последовательности символов.', code: "SELECT text, character\nFROM smeshariki_quotes\nWHERE text ILIKE '%смысл%';", explanation: 'ILIKE удобен для подстроки. Для регулярных выражений в PostgreSQL можно использовать оператор ~*.' },
      { question: 'Покажи число задач каждого привязанного чата, включая чаты без задач.', context: 'telegram_sessions(session_hash, chat_id)\ndaily_tasks(id, chat_id, title, done)\nОдин чат может быть привязан к нескольким браузерам.', hint: 'Сначала получи уникальные chat_id. Затем LEFT JOIN и COUNT(t.id), а не COUNT(*).', code: 'SELECT s.chat_id, COUNT(t.id) AS total\nFROM (SELECT DISTINCT chat_id\n      FROM telegram_sessions\n      WHERE chat_id IS NOT NULL) AS s\nLEFT JOIN daily_tasks t ON t.chat_id = s.chat_id\nGROUP BY s.chat_id;', explanation: 'DISTINCT исключает удвоение задач из-за нескольких браузеров. LEFT JOIN сохраняет чаты без задач; COUNT(t.id) даёт для них ноль.' },
      { question: 'Пронумеруй цитаты каждого персонажа от новых к старым, сохранив все строки.', context: 'smeshariki_quotes(id, text, character)', hint: 'Оконная функция ROW_NUMBER() с PARTITION BY и ORDER BY.', code: 'SELECT id, character, text,\n       ROW_NUMBER() OVER (\n         PARTITION BY character ORDER BY id DESC\n       ) AS position\nFROM smeshariki_quotes;', explanation: 'Оконная функция сохраняет строки. GROUP BY собрал бы их в агрегированные группы.' },
      { question: 'Найди одинаковые цитаты, ошибочно записанные несколько раз у одного персонажа.', context: 'smeshariki_quotes(id, text, character)', hint: 'Сгруппируй по text и character и оставь группы с COUNT(*) > 1.', code: 'SELECT text, character, COUNT(*)\nFROM smeshariki_quotes\nGROUP BY text, character\nHAVING COUNT(*) > 1;', explanation: 'Это диагностический SELECT. Перед удалением дубликатов нужно определить, какую запись сохранять, и сделать резервную копию.' },
      { question: 'Как найти в PostgreSQL запросы, выполняющиеся дольше минуты?', context: 'Учебная диагностика. Видимость чужих запросов зависит от прав роли.', hint: 'Посмотри pg_stat_activity, state и query_start.', code: "SELECT pid, now() - query_start AS duration, query\nFROM pg_stat_activity\nWHERE state = 'active'\n  AND query_start < now() - interval '1 minute'\n  AND pid <> pg_backend_pid();", explanation: 'Долгий запрос может ждать блокировку. После этого проверяют wait_event_type и wait_event, а не сразу завершают процесс.' },
      { question: 'Зачем при замене подборки цитат использовать транзакцию? Напиши каркас.', context: 'Нужно заменить содержимое таблицы одной согласованной операцией.', hint: 'BEGIN → изменения → COMMIT. Если ошибка — ROLLBACK.', code: "BEGIN;\nDELETE FROM smeshariki_quotes;\nINSERT INTO smeshariki_quotes (text, character)\nVALUES ('Учебный пример', 'Бараш');\nCOMMIT;", explanation: 'Изменения фиксируются вместе. При ошибке до COMMIT их можно откатить. В psql для скриптов включают ON_ERROR_STOP, а перед работой делают backup.' },
    ],
    linux: [
      { question: 'Сайт отвечает 502. Как посмотреть последние логи Nginx и приложения в Docker Compose?', context: 'Ты в /opt/smeshariki/KikoRiki-quotes. Сервисы называются nginx и app.', hint: 'docker compose logs, опции --tail и --since.', code: 'docker compose ps\ndocker compose logs --tail 100 --since 10m nginx app', explanation: 'Проверь состояние контейнеров, ошибки upstream и доступность app. Для нашей полной схемы добавляют -f с нужными Compose overlay-файлами.' },
      { question: 'Как узнать, какой процесс слушает TCP-порт 443?', context: 'Linux-сервер. Для информации о чужих процессах нужны права.', hint: 'Утилита ss: listening, numeric, process, TCP.', code: "sudo ss -lntp 'sport = :443'", explanation: '-l — слушающие сокеты, -n — номера портов, -t — TCP, -p — процессы. Контейнеры также проверяют через docker compose ps.' },
      { question: 'На сервере закончилось место. С чего начать диагностику?', context: 'Нужно проверить место и inode, затем найти крупные каталоги.', hint: 'df -h, df -i и du. Не удаляй данные, пока не выяснишь, кому они принадлежат.', code: 'df -h\ndf -i\nsudo du -xhd1 /var | sort -h\ndocker system df', explanation: 'Место может закончиться из-за логов, образов или inode. docker system prune --volumes опасен для данных базы; сначала выясняют, что занимает место.' },
      { question: 'Как проверить память и увидеть самые прожорливые процессы?', context: 'Приложение стало медленно отвечать. Необходимо собрать факты.', hint: 'free -h и сортировка ps по использованию памяти.', code: 'free -h\nps aux --sort=-%mem | head -n 10\ndocker stats --no-stream', explanation: 'Смотри available, swap и потребление контейнеров. Использованный файловый кеш сам по себе не означает нехватку памяти.' },
      { question: 'Как посмотреть статус системной службы Docker и её логи за 10 минут?', context: 'На сервере используется systemd.', hint: 'systemctl status и journalctl -u.', code: "systemctl status docker --no-pager\nsudo journalctl -u docker --since '10 minutes ago' --no-pager", explanation: 'Статус показывает текущее состояние, журнал — события и причины сбоев. Сначала диагностика, затем обоснованный перезапуск.' },
      { question: 'Как проверить HTTPS и HTTP-код нашего API из терминала?', context: 'https://dnec4.ru/api/smeshariki-quotes', hint: 'curl с таймаутом. Не отключай проверку сертификата.', code: "curl -sS --max-time 10 -o /dev/null \\\n  -w '%{http_code}\\n' \\\n  https://dnec4.ru/api/smeshariki-quotes", explanation: '200 — успешный HTTP-ответ; 502 часто означает недоступный upstream; ошибки curl помогают отделить DNS, соединение и TLS. Затем проверяют содержимое ответа.' },
      { question: 'Найди строки с ошибками без учёта регистра в последних логах приложения.', context: 'Сервис Docker Compose называется app.', hint: 'Передай логи в grep -i.', code: "docker compose logs --tail 200 app 2>&1 | grep -i 'error'", explanation: 'Фильтрация помогает начать поиск, но соседние строки дают контекст. Не публикуй полные логи, пока не проверишь их на секреты.' },
      { question: 'Какие права задать приватному SSH-ключу и каталогу .ssh?', context: 'Ключ принадлежит текущему пользователю.', hint: 'Каталог доступен только владельцу; ключ читается и записывается только владельцем.', code: 'chmod 700 ~/.ssh\nchmod 600 ~/.ssh/id_ed25519', explanation: '700 у каталога даёт владельцу доступ к содержимому. 600 у файла разрешает только владельцу чтение и запись. Владельца проверяют командой ls -l.' },
    ],
  };
  let topic = 'sql';
  let exerciseIndex = 0;
  const understood = new Set();
  const drafts = new Map();
  const exerciseKey = () => `${topic}:${exerciseIndex}`;
  function saveDraft() { drafts.set(exerciseKey(), $('#practice-answer').value); }
  function renderExercise() {
    const exercise = exercises[topic][exerciseIndex];
    $('#practice-number').textContent = `${topic.toUpperCase()} · ${exerciseIndex + 1} / ${exercises[topic].length}`;
    $('#practice-question').textContent = exercise.question;
    $('#practice-context').textContent = exercise.context;
    $('#practice-answer').value = drafts.get(exerciseKey()) || '';
    $('#practice-code').textContent = exercise.code;
    $('#practice-explanation').textContent = exercise.explanation;
    $('#practice-hint-text').textContent = exercise.hint;
    $('#practice-hint-text').hidden = true;
    $('#practice-solution').hidden = true;
    $('#practice-understood').setAttribute('aria-pressed', String(understood.has(exerciseKey())));
    $('#practice-understood').textContent = understood.has(exerciseKey()) ? 'Уже разобрался ✓' : 'Разобрался ✓';
    $('#practice-progress').textContent = `Разобрано в этой сессии: ${understood.size} / ${exercises.sql.length + exercises.linux.length}`;
  }
  $('#practice-topic').addEventListener('change', event => {
    saveDraft(); topic = event.target.value; exerciseIndex = 0; renderExercise();
  });
  $('#practice-prev').addEventListener('click', () => {
    saveDraft(); exerciseIndex = (exerciseIndex - 1 + exercises[topic].length) % exercises[topic].length; renderExercise();
  });
  $('#practice-next').addEventListener('click', () => {
    saveDraft(); exerciseIndex = (exerciseIndex + 1) % exercises[topic].length; renderExercise();
  });
  $('#practice-hint').addEventListener('click', () => { $('#practice-hint-text').hidden = !$('#practice-hint-text').hidden; });
  $('#practice-reveal').addEventListener('click', () => { $('#practice-solution').hidden = !$('#practice-solution').hidden; });
  $('#practice-understood').addEventListener('click', () => {
    understood.add(exerciseKey()); saveDraft(); renderExercise(); $('#practice-solution').hidden = false;
  });
  renderExercise();

  const nodeInfo = {
    browser: ['Браузер', 'Получает список цитат из API, выбирает случайную и рисует её в терминале. После этого отдельным POST передаёт ID выбранной цитаты. Cookie связывает браузер с Telegram; задачи требуют этой привязки. Диагностика: вкладка Network и HTTP-коды.'],
    caddy: ['Caddy · вход на сервер', 'Принимает HTTPS на порту 443, автоматически получает и обновляет сертификат и направляет запросы в Nginx. HTTP перенаправляется на HTTPS. При проблемах проверяют DNS, порты, сертификат и логи caddy.'],
    nginx: ['Nginx · фронтенд и API', 'Отдаёт HTML, CSS, JavaScript и PNG. Запросы /api/* перенаправляет в FastAPI без префикса /api. При 502 проверяют доступность app, DNS Docker и upstream в конфигурации.'],
    api: ['FastAPI · основной сервис', 'Python API читает PostgreSQL, проверяет привязку браузера и владельца задач. Для уведомления берёт текст цитаты из базы и публикует событие в Kafka. Токена Telegram у него нет. Проверки: Swagger локального API, HTTP-ответы, тесты и логи app.'],
    db: ['PostgreSQL · данные', 'Хранит цитаты, хеши браузерных сессий, ID привязанных чатов, задачи и позицию обработчика бота. Задачи отделяются по chat_id; API получает владельца из cookie, а не из параметра клиента. Пароль подключается отдельным secret-файлом.'],
    kafka: ['Redpanda × 3 · Kafka API', 'Топик quote-clicks хранит события с цитатой и хешем сессии. Репликация — 3, producer использует acks=all, идемпотентность и транзакции. Consumer читает read_committed. Три брокера работают на одном сервере: это учебная репликация, а не защита от отказа всего сервера.'],
    tunnel: ['SSH-туннель · соединение с сервером', 'Инициируется с компьютера и даёт локальным контейнерам доступ к серверной базе и Kafka. Их порты на сервере открыты только на loopback. При обрыве SSH переподключается внутри контейнера, сохраняя его сетевую среду.'],
    consumer: ['Сервис уведомлений · consumer', 'Читает события Kafka, по хешу сессии находит chat_id в базе и отправляет текст цитаты в Telegram. Подтверждает позицию после обработки. При недоступном Telegram повторяет попытку; возможен дубль при сбое после доставки и до commit позиции.'],
    bot: ['Обработчик Telegram', 'На компьютере получает /start, /tasks, /add и нажатия кнопок через getUpdates. /start привязывает чат по одноразовому коду, /tasks показывает задачи. Привязки и задачи меняются в серверном PostgreSQL через туннель. На сервере этого процесса нет.'],
    telegram: ['Telegram API', 'Внешний сервис для получения команд и отправки сообщений. С ним общается компьютер. Сайт, база и Kafka расположены на Linux-сервере; сам сервер к Telegram обращаться не должен.'],
  };
  const routes = {
    quote: [
      ['browser', 'caddy', 'Браузер: GET /api/smeshariki-quotes по HTTPS.'],
      ['caddy', 'nginx', 'Caddy завершает TLS и передаёт HTTP-запрос Nginx.'],
      ['nginx', 'api', 'Nginx убирает /api и направляет запрос в app:8000.'],
      ['api', 'db', 'FastAPI выполняет SELECT id, text, character FROM smeshariki_quotes.'],
      ['db', 'api', 'PostgreSQL возвращает список цитат.'],
      ['api', 'nginx', 'FastAPI сериализует список в JSON.'],
      ['nginx', 'caddy', 'Nginx передаёт ответ обратно.'],
      ['caddy', 'browser', 'Браузер получает JSON, выбирает случайную цитату и печатает её.'],
    ],
    notification: [
      ['browser', 'caddy', 'После выбора цитаты: POST /api/quote-click с quote_id.'],
      ['caddy', 'nginx', 'HTTPS-запрос проходит через Caddy.'],
      ['nginx', 'api', 'Nginx направляет запрос к producer в FastAPI.'],
      ['api', 'db', 'Сервер берёт текст и персонажа по quote_id, не доверяя тексту от браузера.'],
      ['db', 'api', 'В событие добавляются цитата, event_id и хеш сессии из cookie.'],
      ['api', 'kafka', 'Producer записывает событие в quote-clicks и фиксирует транзакцию. HTTP-ответ браузеру: 202.'],
      ['kafka', 'tunnel', 'Локальный consumer получает подтверждённое событие через SSH-туннель.'],
      ['tunnel', 'consumer', 'Сервис уведомлений разбирает событие. Без сессии уведомление пропускается.'],
      ['consumer', 'tunnel', 'Consumer ищет получателя через соединение к базе.'],
      ['tunnel', 'db', 'SELECT chat_id по session_hash. Удалённая привязка означает пропуск.'],
      ['db', 'tunnel', 'База возвращает chat_id привязанного пользователя.'],
      ['tunnel', 'consumer', 'Получатель найден; текст уже содержится в событии.'],
      ['consumer', 'telegram', 'С компьютера отправляется sendMessage с цитатой и персонажем.'],
      ['telegram', 'consumer', 'Telegram подтверждает принятие сообщения.'],
      ['consumer', 'tunnel', 'После доставки consumer подтверждает обработку через SSH-туннель.'],
      ['tunnel', 'kafka', 'В Kafka сохраняется позиция consumer. При сбое после доставки и до этого шага возможен дубль.'],
    ],
    link: [
      ['browser', 'caddy', 'Пользователь нажал «Привязать Telegram»: POST /api/telegram/link.'],
      ['caddy', 'nginx', 'Защищённый запрос проходит Caddy.'],
      ['nginx', 'api', 'FastAPI создаёт сессию и одноразовый код.'],
      ['api', 'db', 'В базе сохраняются только хеши сессии и кода. Код действует пять минут.'],
      ['api', 'browser', 'Браузер получает HttpOnly Secure cookie, ссылку и QR-код. Ответ идёт через Nginx и Caddy.'],
      ['browser', 'telegram', 'Пользователь открывает бота и нажимает Start с одноразовым кодом.'],
      ['telegram', 'bot', 'Локальный обработчик получает /start через getUpdates.'],
      ['bot', 'tunnel', 'Обработчик ищет код в серверной базе через туннель.'],
      ['tunnel', 'db', 'В действующей сессии записывается chat_id. Одноразовый код очищается.'],
      ['browser', 'api', 'Сайт опрашивает /api/telegram/status и видит linked: true. Теперь доступны личные задачи.'],
    ],
    tasks: [
      ['browser', 'caddy', 'POST /api/tasks с названием задачи и cookie браузера.'],
      ['caddy', 'nginx', 'Caddy принимает HTTPS.'],
      ['nginx', 'api', 'FastAPI проверяет, что браузер привязан к Telegram.'],
      ['api', 'db', 'INSERT задачи с chat_id владельца и сегодняшней датой по Москве.'],
      ['db', 'api', 'Возвращается сохранённая задача. Чужие задачи отсекаются условиями SQL по chat_id.'],
      ['api', 'browser', 'Сайт обновляет список. При выполнении задачи запускает фейерверк. Ответ идёт через Nginx и Caddy.'],
      ['telegram', 'bot', 'Позже пользователь пишет /tasks в личном чате бота.'],
      ['bot', 'tunnel', 'Обработчик обращается к PostgreSQL через SSH.'],
      ['tunnel', 'db', 'SELECT задач за сегодня только для этого chat_id.'],
      ['db', 'bot', 'Список возвращается через туннель. Для задач Kafka не используется.'],
      ['bot', 'telegram', 'Бот показывает тот же список с кнопками «Готово». Изменения сохраняются в базе.'],
    ],
  };
  let routeIndex = -1;
  let activeEdge = null;
  const nodeButtons = [...document.querySelectorAll('[data-node]')];
  function selectNode(id) {
    nodeButtons.forEach(node => node.classList.toggle('is-selected', node.dataset.node === id));
    $('#map-node-title').textContent = nodeInfo[id][0];
    $('#map-node-description').textContent = nodeInfo[id][1];
  }
  nodeButtons.forEach(node => node.addEventListener('click', () => selectNode(node.dataset.node)));
  function drawMap() {
    if ($('#map-panel').hidden) return;
    const bounds = $('#architecture').getBoundingClientRect();
    const paths = $('#map-paths');
    paths.replaceChildren();
    const edges = new Set(routes[$('#map-scenario').value].map(([from, to]) => `${from}:${to}`));
    for (const edge of edges) {
      const [from, to] = edge.split(':');
      const a = $(`[data-node="${from}"]`).getBoundingClientRect();
      const b = $(`[data-node="${to}"]`).getBoundingClientRect();
      const vertical = Math.abs(a.x - b.x) < a.width / 2;
      const ax = (vertical ? a.x + a.width / 2 : (a.x < b.x ? a.right : a.left)) - bounds.x;
      const ay = (vertical ? (a.y < b.y ? a.bottom : a.top) : a.y + a.height / 2) - bounds.y;
      const bx = (vertical ? b.x + b.width / 2 : (a.x < b.x ? b.left : b.right)) - bounds.x;
      const by = (vertical ? (a.y < b.y ? b.top : b.bottom) : b.y + b.height / 2) - bounds.y;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', vertical ? `M${ax},${ay} C${ax},${(ay + by) / 2} ${bx},${(ay + by) / 2} ${bx},${by}` : `M${ax},${ay} C${(ax + bx) / 2},${ay} ${(ax + bx) / 2},${by} ${bx},${by}`);
      path.setAttribute('class', `flow-path${edge === activeEdge ? ' is-active' : ''}`);
      path.dataset.edge = edge;
      paths.append(path);
    }
  }
  const mapObserver = new ResizeObserver(drawMap);
  mapObserver.observe($('#architecture'));
  function stopMap() { clearInterval(mapTimer); mapTimer = null; $('#map-play').textContent = '▶ Запустить'; }
  function resetMap() {
    stopMap(); routeIndex = -1; activeEdge = null;
    $('#map-log').replaceChildren();
    nodeButtons.forEach(node => node.classList.remove('is-active'));
    $('#map-current').textContent = 'Нажми «Запустить» или «Шаг», чтобы проследить запрос.';
    drawMap();
  }
  function stepMap() {
    const route = routes[$('#map-scenario').value];
    if (routeIndex >= route.length - 1) { stopMap(); return; }
    const [from, to, text] = route[++routeIndex];
    activeEdge = `${from}:${to}`;
    nodeButtons.forEach(node => node.classList.toggle('is-active', [from, to].includes(node.dataset.node)));
    $('#map-current').textContent = `${routeIndex + 1} / ${route.length} · ${text}`;
    const line = document.createElement('li'); line.textContent = text; $('#map-log').append(line);
    if ($('#map-log').children.length > 5) $('#map-log').firstElementChild.remove();
    $('#map-log').start = Math.max(1, routeIndex - 3);
    selectNode(to); drawMap();
    if (routeIndex === route.length - 1) stopMap();
  }
  $('#map-scenario').addEventListener('change', resetMap);
  $('#map-reset').addEventListener('click', resetMap);
  $('#map-step').addEventListener('click', () => { stopMap(); stepMap(); });
  $('#map-play').addEventListener('click', () => {
    if (mapTimer) { stopMap(); return; }
    if (routeIndex >= routes[$('#map-scenario').value].length - 1) resetMap();
    stepMap();
    mapTimer = setInterval(stepMap, 1900);
    $('#map-play').textContent = 'Ⅱ Пауза';
  });

  let taskBusy = false;
  let taskLoadId = 0;
  async function taskRequest(path = '', options = {}) {
    const response = await fetch(`/api/tasks${path}`, {
      cache: 'no-store', ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error('Сначала привяжи Telegram кнопкой «Привязать Telegram» ниже. Затем нажми «Обновить».');
      if (response.status === 404) throw new Error('Задача уже удалена или больше не относится к сегодняшнему дню. Обнови список.');
      throw new Error('Не удалось сохранить или загрузить задачи. Попробуй ещё раз.');
    }
    return response.status === 204 ? null : response.json();
  }
  function renderTasks(payload) {
    const list = $('#task-list'); list.replaceChildren();
    $('#tasks-date').textContent = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'Europe/Moscow' }).format(new Date(`${payload.date}T12:00:00+03:00`)) + ' · Москва';
    const completed = payload.tasks.filter(task => task.done).length;
    $('#tasks-progress').textContent = payload.tasks.length ? `Готово ${completed} из ${payload.tasks.length}` : 'Список пока пуст. Самое время выбрать одну небольшую задачу.';
    for (const task of payload.tasks) {
      const row = document.createElement('li'); row.className = `task-row${task.done ? ' is-done' : ''}`;
      const label = document.createElement('label');
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = task.done;
      const title = document.createElement('span'); title.className = 'task-text'; title.textContent = task.title;
      label.append(checkbox, title);
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Удалить'; remove.setAttribute('aria-label', `Удалить задачу: ${task.title}`);
      checkbox.addEventListener('change', () => mutateTask(async () => {
        const done = checkbox.checked;
        const point = checkbox.getBoundingClientRect();
        await taskRequest(`/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done }) });
        if (done) firework(point.x + point.width / 2, point.y);
        $('#tasks-message').textContent = done ? 'Сделано! Ещё одна маленькая победа.' : 'Задача возвращена в работу.';
      }, checkbox));
      remove.addEventListener('click', () => mutateTask(async () => {
        await taskRequest(`/${task.id}`, { method: 'DELETE' }); $('#tasks-message').textContent = 'Задача удалена.';
      }));
      row.append(label, remove); list.append(row);
    }
  }
  async function loadTasks(silent = false) {
    if (taskBusy) return;
    const id = ++taskLoadId;
    try {
      const payload = await taskRequest();
      if (id !== taskLoadId || taskBusy) return;
      renderTasks(payload);
      if (!silent) $('#tasks-message').textContent = '';
      $('#task-title').disabled = false; $('#task-add').disabled = false;
    } catch (error) {
      if (id !== taskLoadId) return;
      $('#tasks-message').textContent = error.message;
      // Не оставляем на экране чужой список после смены привязки браузера.
      $('#task-list').replaceChildren(); $('#tasks-progress').textContent = '';
      $('#task-title').disabled = true; $('#task-add').disabled = true;
    }
  }
  async function mutateTask(action, checkbox) {
    if (taskBusy) { if (checkbox) checkbox.checked = !checkbox.checked; return; }
    taskBusy = true; ++taskLoadId;
    $('#tasks-panel').querySelectorAll('input, button[type="submit"], .task-row button').forEach(input => { input.disabled = true; });
    try {
      await action();
    } catch (error) {
      $('#tasks-message').textContent = error.message;
    } finally {
      taskBusy = false;
      await loadTasks(true);
    }
  }
  $('#task-form').addEventListener('submit', event => {
    event.preventDefault();
    const title = $('#task-title').value.trim();
    if (!title) return;
    mutateTask(async () => {
      await taskRequest('', { method: 'POST', body: JSON.stringify({ title }) });
      $('#task-title').value = ''; $('#tasks-message').textContent = 'Задача добавлена. Она уже доступна по /tasks в Telegram.';
    });
  });
  $('#tasks-refresh').addEventListener('click', () => loadTasks());
  window.addEventListener('focus', () => { if (!$('#tasks-panel').hidden) loadTasks(true); });

  // Лёгкий фейерверк на canvas: сначала взлёт, потом разлёт и затухание частиц.
  const canvas = $('#fireworks');
  const ctx = canvas.getContext('2d');
  let celebrations = [];
  let animation = null;
  function firework(x, y) {
    if (reducedMotion.matches || !ctx) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * ratio; canvas.height = window.innerHeight * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const target = { x: Math.min(Math.max(x + 80, 100), Math.max(100, window.innerWidth - 100)), y: Math.max(100, Math.min(y - 150, window.innerHeight * .5)) };
    const colors = ['#b9f4b6', '#ffc4dc', '#ffe6a1', '#a7d8ff', '#c8b3ff'];
    const particles = Array.from({ length: 65 }, (_, i) => {
      const angle = (Math.PI * 2 * i) / 65;
      const speed = 45 + Math.random() * 115;
      return { vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, color: colors[i % colors.length] };
    });
    celebrations.push({ start: performance.now(), x, target, particles });
    celebrations = celebrations.slice(-3); canvas.hidden = false;
    if (animation === null) animation = requestAnimationFrame(drawFireworks);
  }
  function drawFireworks(now) {
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    celebrations = celebrations.filter(item => now - item.start < 2200);
    for (const item of celebrations) {
      const age = (now - item.start) / 1000;
      if (age < .55) {
        const t = age / .55;
        const x = item.x + (item.target.x - item.x) * t;
        const y = window.innerHeight - (window.innerHeight - item.target.y) * t;
        ctx.globalAlpha = 1; ctx.strokeStyle = '#ffd9a0'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(x - 3, y + 24); ctx.lineTo(x, y); ctx.stroke();
      } else {
        const t = age - .55;
        ctx.globalAlpha = Math.max(0, 1 - t / 1.65);
        for (const particle of item.particles) {
          ctx.fillStyle = particle.color; ctx.beginPath();
          ctx.arc(item.target.x + particle.vx * t, item.target.y + particle.vy * t + 45 * t * t, 2.3, 0, Math.PI * 2); ctx.fill();
        }
      }
    }
    ctx.globalAlpha = 1;
    if (celebrations.length) animation = requestAnimationFrame(drawFireworks);
    else { animation = null; canvas.hidden = true; }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stopMap(); celebrations = []; }
  });
})();
