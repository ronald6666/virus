#!/usr/bin/env bash
set -u
cd "$(dirname "$(realpath "$0")")"
# O token pode estar no arquivo Python; BOT_TOKEN é opcional e, quando definido, tem prioridade.

# Supervisor externo: se o Python morrer por erro, OOM ou falha transitória, reinicia.
# Ctrl+C encerra o supervisor e o bot de forma limpa.
trap 'exit 0' INT TERM
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
  trap 'termux-wake-unlock >/dev/null 2>&1 || true; exit 0' INT TERM EXIT
fi

mkdir -p logs
while true; do
  printf '%s bot iniciado\n' "$(date -Is)" >> logs/supervisor.log
  python3 -u 'onix_host esse (2).py' 2>&1 | tee -a logs/bot.log
  status=$?
  printf '%s bot encerrou com código %s; reiniciando em 5s\n' "$(date -Is)" "$status" >> logs/supervisor.log
  sleep 5
done
