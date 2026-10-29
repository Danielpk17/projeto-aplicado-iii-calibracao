param(
    [Parameter(Mandatory = $true)][string]$EmailAlerta,
    [Parameter(Mandatory = $true)][string]$ChaveAcesso
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

foreach ($tool in "aws", "sam", "python") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Ferramenta ausente: $tool. Veja o README." }
}

aws sts get-caller-identity --output table
if (-not $?) { throw "Credenciais da AWS ausentes. Rode 'aws configure'." }

python -m unittest discover -s tests
if (-not $?) { throw "Testes falharam. Deploy cancelado." }

sam validate --lint
if (-not $?) { throw "Template inválido." }

sam build
if (-not $?) { throw "Falha no build." }

sam deploy --parameter-overrides "EmailAlerta=$EmailAlerta" "ChaveAcesso=$ChaveAcesso"
if (-not $?) { throw "Falha no deploy." }

aws cloudformation describe-stacks --stack-name calibra --region sa-east-1 --query "Stacks[0].Outputs" --output table
