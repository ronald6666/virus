#!/usr/bin/env bash
set -u
cd "$(dirname "$(realpath "$0")")"

mkdir -p logs
while true; do
  printf '%s bot iniciado\n' "$(date -Is)" >> logs/supervisor.log
  python3 -u 'onix_host esse (2).py' >> logs/bot.log 2>&1
  status=$?
  printf '%s bot encerrou com código %s; reiniciando em 5s\n' "$(date -Is)" "$status" >> logs/supervisor.log
  sleep 5
done
