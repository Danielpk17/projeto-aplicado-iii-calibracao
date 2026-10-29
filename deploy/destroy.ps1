$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

sam delete --stack-name calibra --region sa-east-1
Write-Host "A tabela DynamoDB fica retida para não perder certificados. Para apagar, remova-a no console do DynamoDB."
