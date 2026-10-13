# Calibra — MVP de certificados de calibração

Projeto Aplicado III · AV3 · Empresa parceira: Schulz S.A.

Repositório público: https://github.com/Danielpk17/projeto-aplicado-iii-calibracao

Aplicação web transacional que recebe uma planilha Excel, calcula os indicadores metrológicos por ponto de ensaio, registra o processamento em SQLite e apresenta o parecer final em uma interface imprimível.

## Execução

Requer Python 3.10 ou superior. Não há dependências externas.

```powershell
python server.py
```

Abra `http://127.0.0.1:8000`. Para usar outra porta: `python server.py --port 8080`.

## Formato da planilha

Baixe o modelo em **Baixar planilha modelo** na aplicação ou acesse `/modelo.xlsx`.
Na primeira aba, a primeira linha deve conter:

| Ponto | Valor Padrão | LEA | Leitura 1 | Leitura 2 | Leitura 3 | Unidade |
|---|---:|---:|---:|---:|---:|---|
| P1 | 0 | 0,5 | 0,1 | 0,2 | 0 | bar |

`Ponto`, `Valor Padrão` e `LEA` são obrigatórios, assim como pelo menos uma coluna `Leitura N` e uma leitura em cada linha. `Unidade` é opcional. Aceitam-se até 20 colunas de leitura e 1000 pontos. A planilha precisa conter valores medidos, sem fórmulas. A aplicação aceita vírgula ou ponto decimal. O LEA deve ser não negativo e ter a mesma unidade do valor padrão e das leituras.

## Regras de negócio

- Média por ponto: soma das leituras dividida pelo número de leituras preenchidas.
- Erro sistemático: média menos valor padrão.
- Dentro da tolerância: valor absoluto do erro menor ou igual ao LEA.
- Parecer `APROVADO`: todos os pontos dentro da tolerância. Havendo qualquer ponto fora, `REPROVADO`.
- Os cálculos usam `Decimal`. Para evitar arredondamento em médias periódicas, a classificação compara `|soma das leituras − padrão × n|` com `LEA × n`, que é equivalente a `|erro| ≤ LEA`.

## Fluxo transacional

1. O navegador envia o arquivo `.xlsx` e os dados do instrumento ao endpoint `POST /api/processar`.
2. O servidor valida a estrutura da primeira aba, calcula os resultados e persiste um certificado identificado por ID em `data/calibracoes.sqlite3`.
3. A interface mostra o resultado e o histórico. `GET /api/certificados` retorna os 50 registros mais recentes; `GET /api/certificados/{id}` recupera um registro.
4. O botão **Imprimir / salvar PDF** usa a impressão do navegador para gerar uma cópia do certificado.

O serviço escuta apenas em `127.0.0.1` nesta versão acadêmica. O certificado exibido é um parecer gerado a partir dos dados importados; o MVP não substitui procedimentos formais de rastreabilidade, incerteza de medição ou assinatura de laboratório.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem aprovação, reprovação, limite exato do LEA, erro negativo, arquivo inválido, fórmula proibida e fluxo HTTP com persistência e recuperação do resultado.
