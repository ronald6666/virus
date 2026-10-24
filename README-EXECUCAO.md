# Execução contínua

1. Revogue o token antigo no `@BotFather` e gere um novo. O token antigo estava gravado no código e deve ser considerado comprometido.
2. Instale as dependências:

```bash
python3 -m pip install -r requirements.txt
```

3. Configure o token somente no ambiente:

```bash
export BOT_TOKEN='SEU_TOKEN_NOVO'
```

4. Inicie pelo supervisor:

```bash
./run_bot.sh
```

O supervisor reinicia o bot se o processo Python terminar. O próprio bot também reinicia o polling quando a conexão com o Telegram falha. Em Termux, mantenha o aplicativo sem restrição de bateria e use `termux-wake-lock` (o script tenta ativá-lo automaticamente quando disponível).

Para execução realmente 24/7 independente do celular/sessão, use um servidor persistente com um gerenciador de serviços (systemd, Docker com restart=always ou equivalente). O sandbox temporário não garante disponibilidade contínua.

Os logs ficam em `logs/bot.log` e `logs/supervisor.log`.
