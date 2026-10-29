# Calibra: plataforma de certificados de calibração

Projeto Aplicado III · Empresa parceira: Schulz S.A. · AV4 (consolidação final)

Repositório público: https://github.com/Danielpk17/projeto-aplicado-iii-calibracao

Plataforma publicada: https://7swe75rdj4bpp5lqvvzpc3ida40ieyrw.lambda-url.sa-east-1.on.aws/

Roteiro do vídeo de evidência: [docs/ROTEIRO-VIDEO-AV4.md](docs/ROTEIRO-VIDEO-AV4.md)

A AV3 entregou o motor transacional: recebe uma planilha Excel, calcula os indicadores metrológicos por ponto de ensaio e emite o parecer. A AV4 integra esse motor em dois canais publicados na AWS dentro da camada gratuita:

- **Plataforma Web Gestora** (`/`): o engenheiro envia a planilha, consulta o histórico, imprime o certificado e gera a etiqueta com QR Code do instrumento.
- **Consulta no chão de fábrica** (`/consulta`): página mobile que abre a câmera do celular, lê o QR Code da etiqueta e mostra na hora se o instrumento está APROVADO ou REPROVADO. O QR aponta para `/c/{id}`, então qualquer leitor de QR do celular também abre o resultado direto.

## Arquitetura na nuvem

```
Celular / navegador ──HTTPS──▶ Lambda Function URL ──▶ AWS Lambda (Python 3.13, arm64)
                                                         │  serve as páginas e a API
                                                         ▼
                                                   Amazon DynamoDB (certificados)
CloudWatch Logs (7 dias)  ·  AWS Budgets (alerta acima de US$ 0,01)
```

| Serviço | Uso no Calibra | Camada gratuita usada |
|---|---|---|
| AWS Lambda + Function URL | Páginas, API e cálculos | 1 milhão de requisições e 400 mil GB-s por mês, sempre gratuito. A Function URL não tem cobrança própria |
| Amazon DynamoDB | Persistência dos certificados | 25 GB e 25 RCU/WCU provisionadas, sempre gratuito. A tabela usa 1 RCU/1 WCU e o índice mais 1/1 |
| CloudWatch Logs | Logs da função | 5 GB por mês; retenção de 7 dias |
| AWS Budgets | Alerta de custo | 2 orçamentos gratuitos por conta |

A Function URL substitui o API Gateway de propósito: o API Gateway só é gratuito nos 12 primeiros meses, enquanto a Function URL não gera custo além do próprio Lambda. O mesmo Lambda entrega o HTML, então não é preciso um bucket S3 para o frontend. O único uso de S3 é o bucket de artefatos que o SAM cria no deploy, com alguns KB.

O mesmo código roda localmente com SQLite (`server.py`) e na nuvem com DynamoDB (`src/lambda_function.py`). As rotas ficam em `src/web.py`, compartilhadas pelos dois.

## Estrutura

```
src/calibration.py      motor de cálculo (AV3)
src/web.py              rotas HTTP compartilhadas
src/storage.py          SQLite (local) e DynamoDB (nuvem)
src/lambda_function.py  adaptador AWS Lambda
src/public/             plataforma web, consulta mobile e bibliotecas de QR
server.py               servidor local
template.yaml           infraestrutura como código (AWS SAM)
deploy/                 scripts de deploy e remoção
tests/                  testes automatizados
```

## Execução local

Requer Python 3.10 ou superior, sem dependências externas.

```powershell
python server.py
```

Abra `http://127.0.0.1:8000`. Para testar a câmera pelo celular na mesma rede, use `python server.py --host 0.0.0.0`; o navegador só libera a câmera em HTTPS, então a leitura pela câmera funciona de verdade na versão publicada na AWS.

## Deploy na AWS

1. Instale as ferramentas: `winget install Amazon.AWSCLI` e `winget install Amazon.SAM-CLI`.
2. Crie um usuário IAM para o deploy e configure: `aws configure` (região `sa-east-1`).
3. Rode o script, informando o e-mail do alerta de custo e a chave de acesso dos engenheiros (mínimo de 8 caracteres):

```powershell
.\deploy\deploy.ps1 -EmailAlerta seu@email.com -ChaveAcesso "uma-chave-forte"
```

O script confere as credenciais, roda os testes, valida o template, faz o build e o deploy, e imprime `UrlPlataforma` e `UrlConsulta`. No Linux ou macOS use `deploy/deploy.sh`.

4. Confirme a assinatura do e-mail que a AWS Budgets envia.

Para remover tudo: `.\deploy\destroy.ps1`. A tabela DynamoDB é retida para não perder certificados.

## Segurança

O envio de planilhas exige a chave de acesso (`X-Chave`), comparada em tempo constante. A consulta é pública por desenho: o operador lê o QR sem login, e a identificação tem 12 caracteres hexadecimais aleatórios. A chave fica em variável de ambiente do Lambda; numa versão de produção ela iria para o Secrets Manager e o login seria por Cognito.

## Formato da planilha

Baixe o modelo em **Baixar planilha modelo** ou em `/modelo.xlsx`. Na primeira aba, a primeira linha deve conter:

| Ponto | Valor Padrão | LEA | Leitura 1 | Leitura 2 | Leitura 3 | Unidade |
|---|---:|---:|---:|---:|---:|---|
| P1 | 0 | 0,5 | 0,1 | 0,2 | 0 | bar |

`Ponto`, `Valor Padrão` e `LEA` são obrigatórios, assim como ao menos uma coluna `Leitura N` e uma leitura por linha. Aceitam-se até 20 colunas de leitura, 1000 pontos e arquivos de até 4 MB (limite de payload da Function URL). Fórmulas são rejeitadas.

## Regras de negócio

- Média por ponto: soma das leituras dividida pelo número de leituras.
- Erro sistemático: média menos valor padrão.
- Dentro da tolerância: |erro| ≤ LEA.
- Parecer `APROVADO` somente com todos os pontos dentro da tolerância.
- Os cálculos usam `Decimal` e a classificação compara `|soma − padrão × n|` com `LEA × n`, sem arredondar a média.

## API

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/processar` | Processa a planilha (corpo binário; cabeçalhos `X-Filename`, `X-Instrumento`, `X-Responsavel`, `X-Chave`) |
| GET | `/api/certificados` | 50 certificados mais recentes |
| GET | `/api/certificados/{id}` | Certificado completo |
| GET | `/api/saude` | Estado do serviço e se a chave é exigida |
| GET | `/c/{id}` | Página mobile do certificado (destino do QR Code) |

## Testes

```powershell
python -m unittest discover -s tests -v
```

São 14 testes: as regras de cálculo da AV3, o fluxo HTTP local com SQLite e o handler do Lambda com uma tabela DynamoDB simulada (upload, consulta, listagem, link do QR, download binário do modelo e chave de acesso).

O MVP não substitui procedimentos formais de rastreabilidade metrológica, incerteza de medição ou assinatura de laboratório.
