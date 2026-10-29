# Roteiro do vídeo AV4 (4 a 6 minutos)

Gravar a tela com Win+Alt+R (Xbox Game Bar) ou OBS, com microfone ligado.
Postar no YouTube como "Não listado" e colar o link no relatório.

## Antes de gravar

- Abrir no Chrome: https://7swe75rdj4bpp5lqvvzpc3ida40ieyrw.lambda-url.sa-east-1.on.aws/
- Baixar as duas planilhas de exemplo:
  - Aprovada: https://github.com/Danielpk17/projeto-aplicado-iii-calibracao/raw/main/exemplos/calibracao_aprovada.xlsx
  - Reprovada: https://github.com/Danielpk17/projeto-aplicado-iii-calibracao/raw/main/exemplos/calibracao_reprovada.xlsx
- Chave do engenheiro: pedir ao Daniel por mensagem privada (não fica no repositório) e colar no campo "Chave de acesso do engenheiro"
- Não precisa clonar o projeto nem ter conta na AWS: a plataforma já está publicada
- No celular, deixar a câmera pronta para ler QR Code
- O console da AWS é da conta do Daniel. Para a cena 7, usar as capturas `evidencias/av4-06-cloudformation.jpg` e `evidencias/av4-07-custo.jpg` (ou o Daniel grava esse trecho e junta na edição)

## Cenas

**1. Abertura (30 s)**
"Este é o Calibra, projeto da AV4 de Projeto Aplicado III com a Schulz S.A. Ele automatiza a emissão de certificados de calibração e leva o resultado até o chão de fábrica por QR Code. Tudo roda na AWS, dentro da camada gratuita."
Mostrar a URL na barra do navegador: o endereço é lambda-url.sa-east-1.on.aws.

**2. Planilha modelo (20 s)**
Clicar em "Baixar planilha modelo". "O engenheiro baixa o modelo e preenche ponto, valor padrão, LEA e as leituras."

**3. Cenário aprovado (60 s)**
Preencher instrumento (ex.: Manômetro PT-201), responsável, colar a chave, selecionar `calibracao_aprovada.xlsx`, clicar em Processar.
"O Lambda valida o arquivo, calcula média e erro sistemático de cada ponto e compara com o LEA. Todos os pontos dentro: APROVADO."
Mostrar a tabela de pontos e a etiqueta com QR Code.

**4. Cenário reprovado (40 s)**
Repetir com `calibracao_reprovada.xlsx` (ex.: Manômetro PT-202).
"Aqui o ponto P3 tem erro de 1,07 bar, acima do LEA de 0,5. Basta um ponto fora para o certificado ser REPROVADO."

**5. Histórico e impressão (30 s)**
Descer até "Análises recentes", clicar em "Ver resultado" de um deles, clicar em "Imprimir / salvar PDF" e mostrar a prévia de impressão.
"Tudo fica gravado no DynamoDB."

**6. Chão de fábrica (60 s)** (filmar a tela do celular ou espelhar)
Apontar a câmera do celular para o QR Code na tela do computador. Abrir o link.
"O operador lê a etiqueta com o celular, sem login e sem instalar nada, e vê na hora se o instrumento está liberado."
Mostrar também a página /consulta com o botão "Ler QR Code com a câmera" lendo o QR do reprovado: aparece em vermelho.

**7. Nuvem e custo (40 s)**
Mostrar `evidencias/av4-06-cloudformation.jpg` (stack `calibra`, aba Recursos): "A infraestrutura é código, criada por um script com o AWS SAM: Lambda com Function URL, DynamoDB, logs e um orçamento com alerta de custo."
Mostrar `evidencias/av4-07-custo.jpg` (Nível gratuito): "A conta está no plano gratuito, sem cobrança, e nenhum serviço passou do limite."

**8. Encerramento (15 s)**
"O código está no GitHub em github.com/Danielpk17/projeto-aplicado-iii-calibracao, junto com o roteiro de deploy. Obrigado."

## Depois de gravar

1. YouTube: Criar, Enviar vídeo, visibilidade "Não listado".
2. Mandar o link para o Daniel, que coloca no relatório e entrega o PDF no AVA.
