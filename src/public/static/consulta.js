const scanCard = document.getElementById('scan-card');
const reader = document.getElementById('reader');
const scanButton = document.getElementById('scan-button');
const message = document.getElementById('scan-message');
const verdict = document.getElementById('verdict');
const ID_PATTERN = /^[0-9A-F]{12}$/;
let scanner = null;

function element(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = value;
  return item;
}

function displayNumber(value) {
  const parts = String(value).split('.');
  if (parts.length === 1) return parts[0];
  const decimals = parts[1].slice(0, 4).replace(/0+$/, '');
  return parts[0] + (decimals ? ',' + decimals : '');
}

function setMessage(value) {
  message.textContent = value;
}

function extractId(text) {
  const value = String(text).trim();
  const match = value.match(/\/c\/([0-9A-Fa-f]{12})(?:[/?#]|$)/) || value.match(/^([0-9A-Fa-f]{12})$/);
  return match ? match[1].toUpperCase() : null;
}

async function stopScanner() {
  if (!scanner) return;
  try { await scanner.stop(); } catch (error) {}
  scanner.clear();
  scanner = null;
  reader.hidden = true;
  scanButton.hidden = false;
}

async function startScanner() {
  if (typeof Html5Qrcode !== 'function') return setMessage('Leitor indisponível. Digite a identificação.');
  setMessage('');
  reader.hidden = false;
  scanButton.hidden = true;
  scanner = new Html5Qrcode('reader');
  try {
    await scanner.start({facingMode: 'environment'}, {fps: 10, qrbox: {width: 230, height: 230}}, async text => {
      const id = extractId(text);
      if (!id) return setMessage('Este QR Code não é de um certificado Calibra.');
      await stopScanner();
      load(id);
    });
  } catch (error) {
    await stopScanner();
    setMessage('Não foi possível abrir a câmera. Verifique a permissão ou digite a identificação.');
  }
}

async function load(id) {
  setMessage('Consultando…');
  try {
    const response = await fetch('/api/certificados/' + id);
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || 'Falha na consulta.');
    setMessage('');
    render(data);
    history.replaceState(null, '', '/c/' + id);
  } catch (error) {
    setMessage(error.message === 'Failed to fetch' ? 'Sem conexão com o servidor.' : error.message);
  }
}

function render(data) {
  const approved = data.parecer_final === 'APROVADO';
  scanCard.hidden = true;
  verdict.hidden = false;
  document.getElementById('verdict-banner').classList.toggle('rejected', !approved);
  document.getElementById('verdict-icon').textContent = approved ? '✓' : '✕';
  document.getElementById('verdict-status').textContent = data.parecer_final;
  document.getElementById('verdict-hint').textContent = approved
    ? 'Instrumento liberado para uso.'
    : 'Não utilizar. Encaminhe o instrumento para a engenharia.';
  const meta = document.getElementById('verdict-meta');
  meta.replaceChildren();
  for (const [label, value] of [
    ['Instrumento', data.instrumento],
    ['Identificação', data.id],
    ['Calibrado em', new Date(data.criado_em).toLocaleString('pt-BR')],
    ['Responsável', data.responsavel],
  ]) {
    const row = element('div');
    row.append(element('dt', '', label), element('dd', '', value));
    meta.append(row);
  }
  const list = document.getElementById('point-list');
  list.replaceChildren();
  for (const point of data.pontos) {
    const inside = point.classificacao === 'DENTRO_DA_TOLERANCIA';
    const unit = point.unidade ? ' ' + point.unidade : '';
    const item = element('li', inside ? '' : 'rejected');
    item.append(
      element('strong', '', point.ponto),
      element('span', '', 'Padrão ' + displayNumber(point.padrao) + unit + ' · Erro ' + displayNumber(point.erro_sistematico) + unit + ' · LEA ' + displayNumber(point.lea) + unit),
      element('span', 'pill' + (inside ? '' : ' rejected'), inside ? 'DENTRO' : 'FORA'),
    );
    list.append(item);
  }
  verdict.scrollIntoView({behavior: 'smooth'});
}

scanButton.addEventListener('click', startScanner);

document.getElementById('manual-form').addEventListener('submit', event => {
  event.preventDefault();
  const id = extractId(document.getElementById('manual-id').value);
  if (!id) return setMessage('A identificação tem 12 caracteres (0 a 9 e A a F).');
  load(id);
});

document.getElementById('again-button').addEventListener('click', () => {
  verdict.hidden = true;
  scanCard.hidden = false;
  history.replaceState(null, '', '/consulta');
  startScanner();
});

const initial = extractId(window.location.pathname);
if (initial && ID_PATTERN.test(initial)) load(initial);
