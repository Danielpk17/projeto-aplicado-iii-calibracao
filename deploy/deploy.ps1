param(
    [Parameter(Mandatory = $true)][string]$EmailAlerta,
    [Parameter(Mandatory = $true)][string]$ChaveAcesso
)

Set-Location (Split-Path $PSScriptRoot -Parent)

foreach ($tool in "aws", "sam", "python") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Ferramenta ausente: $tool. Veja o README." }
}

function Run([string]$mensagem, [scriptblock]$comando) {
    $ErrorActionPreference = "Continue"
    & $comando 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw $mensagem }
}

Run "Credenciais da AWS ausentes. Rode 'aws configure'." { aws sts get-caller-identity --output table }
Run "Testes falharam. Deploy cancelado." { python -m unittest discover -s tests }
Run "Template invalido." { sam validate --lint }
Run "Falha no build." { sam build }
Run "Falha no deploy." { sam deploy --parameter-overrides "EmailAlerta=$EmailAlerta" "ChaveAcesso=$ChaveAcesso" }
Run "Falha ao ler as saidas." { aws cloudformation describe-stacks --stack-name calibra --region sa-east-1 --query "Stacks[0].Outputs" --output table }
