#!/usr/bin/env sh
set -eu

if [ $# -ne 2 ]; then
  echo "Uso: deploy/deploy.sh <email-alerta> <chave-acesso>" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
aws sts get-caller-identity --output table
python -m unittest discover -s tests
sam validate --lint
sam build
sam deploy --parameter-overrides "EmailAlerta=$1" "ChaveAcesso=$2"
aws cloudformation describe-stacks --stack-name calibra --region sa-east-1 --query "Stacks[0].Outputs" --output table
