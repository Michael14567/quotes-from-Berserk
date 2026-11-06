const button = document.querySelector('#next');
const output = document.querySelector('#quote');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const telegramButton = document.querySelector('#telegram');
const pairing = document.querySelector('#pairing');
const pairingStatus = document.querySelector('#pairing-status');
const admireButton = document.querySelector('#admire');
const clouds = document.querySelector('#clouds');
let linked = false;
let pairingTimer = null;
let lastId = null;

admireButton.addEventListener('click', () => {
  clouds.hidden = !clouds.hidden;
  admireButton.setAttribute('aria-pressed', String(!clouds.hidden));
  admireButton.textContent = clouds.hidden ? 'Любоваться облаками' : 'Остановить облака';
});

async function refreshTelegramStatus() {
  const response = await fetch('/api/telegram/status', { cache: 'no-store' });
  if (!response.ok) throw new Error('status unavailable');
  linked = (await response.json()).linked;
  telegramButton.textContent = linked ? 'Отвязать Telegram' : 'Привязать Telegram';
  if (linked) {
    clearInterval(pairingTimer);
    pairingTimer = null;
    pairing.hidden = true;
  }
  return linked;
}

refreshTelegramStatus().catch(() => {});

telegramButton.addEventListener('click', async () => {
  telegramButton.disabled = true;
  try {
    if (linked) {
      const response = await fetch('/api/telegram/link', { method: 'DELETE' });
      if (!response.ok) throw new Error('unlink failed');
      clearInterval(pairingTimer);
      pairingTimer = null;
      pairing.hidden = true;
      linked = false;
      telegramButton.textContent = 'Привязать Telegram';
      return;
    }
    const response = await fetch('/api/telegram/link', { method: 'POST' });
    if (!response.ok) throw new Error('link failed');
    const result = await response.json();
    document.querySelector('#qr').src = result.qr;
    document.querySelector('#bot-link').href = result.url;
    pairingStatus.textContent = 'Ожидаем подтверждение в Telegram…';
    pairing.hidden = false;
    clearInterval(pairingTimer);
    const expiresAt = Date.now() + result.expires_in * 1000;
    pairingTimer = setInterval(async () => {
      if (Date.now() >= expiresAt) {
        clearInterval(pairingTimer);
        pairingTimer = null;
        pairingStatus.textContent = 'Код устарел. Нажмите «Привязать Telegram» ещё раз.';
        document.querySelector('#qr').removeAttribute('src');
        document.querySelector('#bot-link').removeAttribute('href');
        return;
      }
      try { await refreshTelegramStatus(); } catch (_) { /* Следующая проверка повторит запрос. */ }
    }, 3000);
  } catch (_) {
    pairing.hidden = false;
    pairingStatus.textContent = 'Не удалось изменить привязку. Попробуйте ещё раз.';
  } finally {
    telegramButton.disabled = false;
  }
});

async function typeText(text) {
  if (reducedMotion.matches) {
    output.textContent = text;
    return;
  }
  for (const character of text) {
    output.textContent += character;
    await new Promise(resolve => setTimeout(resolve, 28));
  }
}

button.addEventListener('click', async () => {
  button.disabled = true;
  output.textContent = '';
  try {
    const response = await fetch('/api/smeshariki-quotes', { cache: 'no-store' });
    if (!response.ok) throw new Error('Сервис недоступен');
    const quotes = await response.json();
    if (!Array.isArray(quotes) || quotes.length === 0) throw new Error('Цитат пока нет');
    const choices = quotes.length > 1 ? quotes.filter(quote => quote.id !== lastId) : quotes;
    const quote = choices[Math.floor(Math.random() * choices.length)];
    lastId = quote.id;
    // Уведомление не должно мешать показу цитаты, если Kafka недоступна.
    fetch('/api/quote-click', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quote_id: quote.id }),
    }).catch(() => {});
    await typeText(`${quote.text}\n\n— ${quote.character}`);
  } catch (error) {
    output.textContent = 'Не удалось получить цитату. Попробуйте ещё раз.';
  } finally {
    button.disabled = false;
  }
});

document.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.repeat && !button.disabled && document.querySelector('#workspace').hidden && !document.activeElement.closest('button, a, input, textarea, select')) {
    event.preventDefault();
    button.click();
  }
});
