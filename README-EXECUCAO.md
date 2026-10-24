# Execução contínua

1. Revogue o token antigo no `@BotFather` e gere um novo.
2. Abra `onix_host esse (2).py` e localize:

```python
TOKEN = 'COLE_SEU_TOKEN_NOVO_AQUI'
```

Substitua o texto pelo token novo, mantendo as aspas:

```python
TOKEN = '1234567890:AASeuTokenNovo'
```

3. Instale as dependências:

```bash
python3 -m pip install -r requirements.txt
```

4. Inicie pelo supervisor:

```bash
./run_bot.sh
```

O supervisor reinicia o bot se o processo Python terminar. O próprio bot também reinicia o polling quando a conexão com o Telegram falha. Em Termux, mantenha o aplicativo sem restrição de bateria e use `termux-wake-lock` (o script tenta ativá-lo automaticamente quando disponível).

O token também pode ser informado por `BOT_TOKEN`, que tem prioridade sobre o valor colocado no arquivo.

Os logs ficam em `logs/bot.log` e `logs/supervisor.log`.
