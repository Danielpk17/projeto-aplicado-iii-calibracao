const form = document.getElementById('upload-form');
const fileInput = document.getElementById('arquivo');
const fileLabel = document.getElementById('file-label');
const dropzone = document.getElementById('dropzone');
const message = document.getElementById('message');
const processButton = document.getElementById('process-button');
const keyField = document.getElementById('key-field');
const keyInput = document.getElementById('chave');
const KEY_STORAGE = 'calibra-chave';

try { keyInput.value = localStorage.getItem(KEY_STORAGE) || ''; } catch (error) {}

function element(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = value;
  return item;
}

function displayNumber(value) {
  const normalized = String(value);
  const parts = normalized.split('.');
  if (parts.length === 1) return normalized;
  const decimals = parts[1].slice(0, 10).replace(/0+$/, '');
  return parts[0] + (decimals ? ',' + decimals : '');
}

function setMessage(value, success = false) {
  message.textContent = value;
  message.classList.toggle('success', success);
}

function setFile(file) {
  fileLabel.textContent = file ? file.name : 'Selecione a planilha Excel';
}

fileInput.addEventListener('change', () => setFile(fileInput.files[0]));
['dragenter', 'dragover'].forEach(type => dropzone.addEventListener(type, event => {
  event.preventDefault();
  dropzone.classList.add('dragover');
}));
['dragleave', 'drop'].forEach(type => dropzone.addEventListener(type, event => {
  event.preventDefault();
  dropzone.classList.remove('dragover');
}));
dropzone.addEventListener('drop', event => {
  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    setFile(fileInput.files[0]);
  }
});

async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.erro || 'Falha na comunicação com o servidor.');
  return body;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return setMessage('Selecione uma planilha .xlsx.');
  if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 4_000_000) return setMessage('Use um arquivo .xlsx de até 4 MB.');
  if (!keyField.hidden && !keyInput.value) return setMessage('Informe a chave de acesso.');
  processButton.disabled = true;
  processButton.textContent = 'Processando…';
  setMessage('');
  try {
    const result = await api('/api/processar', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Filename': encodeURIComponent(file.name),
        'X-Instrumento': encodeURIComponent(document.getElementById('instrumento').value),
        'X-Responsavel': encodeURIComponent(document.getElementById('responsavel').value || 'Não informado'),
        'X-Chave': encodeURIComponent(keyInput.value)
      },
      body: file
    });
    try { localStorage.setItem(KEY_STORAGE, keyInput.value); } catch (error) {}
    renderResult(result);
    history.replaceState(null, '', '?certificado=' + result.id);
    await loadHistory();
    setMessage('Planilha processada e resultado registrado.', true);
    document.getElementById('result-section').scrollIntoView({behavior:'smooth'});
  } catch (error) {
    setMessage(error.message);
  } finally {
    processButton.disabled = false;
    processButton.innerHTML = 'Processar calibração <span aria-hidden="true">→</span>';
  }
});

function renderResult(data) {
  document.getElementById('result-section').hidden = false;
  const status = document.getElementById('final-status');
  status.textContent = data.parecer_final;
  status.classList.toggle('rejected', data.parecer_final === 'REPROVADO');
  document.getElementById('cert-id').textContent = data.id;
  const meta = document.getElementById('result-meta');
  meta.replaceChildren();
  const created = new Date(data.criado_em).toLocaleString('pt-BR');
  for (const [label, value] of [
    ['Instrumento', data.instrumento], ['Responsável', data.responsavel],
    ['Data', created], ['Arquivo', data.arquivo], ['Pontos', String(data.quantidade_pontos)]
  ]) {
    const item = element('span');
    item.append(element('strong', '', label + ': '), document.createTextNode(value));
    meta.append(item);
  }
  const tbody = document.getElementById('result-rows');
  tbody.replaceChildren();
  for (const point of data.pontos) {
    const row = element('tr');
    const unit = point.unidade ? ' ' + point.unidade : '';
    for (const value of [
      point.ponto, displayNumber(point.padrao) + unit,
      point.leituras.map(displayNumber).join(' · '), displayNumber(point.media) + unit,
      displayNumber(point.erro_sistematico) + unit, displayNumber(point.lea) + unit
    ]) row.append(element('td', '', value));
    const classification = element('td');
    const badge = element('span', 'pill' + (point.classificacao === 'FORA_DA_TOLERANCIA' ? ' rejected' : ''),
      point.classificacao === 'DENTRO_DA_TOLERANCIA' ? 'DENTRO' : 'FORA');
    badge.title = point.classificacao;
    classification.append(badge);
    row.append(classification);
    tbody.append(row);
  }
  renderQr(data.id);
}

function renderQr(id) {
  const url = window.location.origin + '/c/' + id;
  const link = document.getElementById('qr-link');
  link.href = url;
  link.textContent = url;
  const target = document.getElementById('qr-code');
  target.replaceChildren();
  if (typeof qrcode !== 'function') return;
  const code = qrcode(0, 'M');
  code.addData(url);
  code.make();
  target.innerHTML = code.createSvgTag({cellSize: 5, margin: 2, scalable: true});
}

async function loadHistory() {
  const entries = await api('/api/certificados');
  document.getElementById('history-count').textContent = entries.length + (entries.length === 1 ? ' registro' : ' registros');
  const list = document.getElementById('history');
  list.replaceChildren();
  if (!entries.length) {
    list.append(element('p', 'empty-state', 'Nenhuma análise registrada ainda.'));
    return;
  }
  for (const entry of entries) {
    const row = element('div', 'history-row');
    row.append(element('span', 'history-id', '#' + entry.id));
    row.append(element('span', 'history-detail', entry.instrumento));
    row.append(element('span', 'history-detail', entry.quantidade_pontos + ' pontos'));
    row.append(element('span', 'history-status' + (entry.parecer === 'REPROVADO' ? ' rejected' : ''), entry.parecer));
    const button = element('button', '', 'Ver resultado →');
    button.type = 'button';
    button.addEventListener('click', async () => {
      try {
        renderResult(await api('/api/certificados/' + entry.id));
        history.replaceState(null, '', '?certificado=' + entry.id);
        document.getElementById('result-section').scrollIntoView({behavior:'smooth'});
      } catch (error) { setMessage(error.message); }
    });
    row.append(button);
    list.append(row);
  }
}

document.getElementById('print-button').addEventListener('click', () => window.print());
api('/api/saude').then(info => { keyField.hidden = !info.requer_chave; }).catch(() => {});
loadHistory().catch(() => setMessage('Não foi possível carregar o histórico.'));
const selectedCertificate = new URLSearchParams(window.location.search).get('certificado');
if (selectedCertificate && /^[A-F0-9]{12}$/.test(selectedCertificate)) {
  api('/api/certificados/' + selectedCertificate)
    .then(renderResult)
    .catch(() => setMessage('Não foi possível abrir o certificado solicitado.'));
}
