# MLC Bot

Telegram bot that asks for a name, sends `flystat.pdf`, then offers `marketing.pdf`. After the funnel is completed, it can answer free-form questions through OpenAI.

## Local run

1. Create `.env` рядом с `main.py`:

```env
BOT_TOKEN=your_new_telegram_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

2. Install dependencies:

```bash
pip3 install -r requirements.txt
```

3. Start the bot:

```bash
python3 main.py
```

## Railway

1. Push this project to GitHub.
2. Open Railway and create a new project from GitHub repo.
3. Select this repository.
4. Open the project settings and add variable:

```env
BOT_TOKEN=your_new_telegram_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

5. Railway should detect the `Procfile` automatically.
6. Deploy the project.
7. Open your bot in Telegram and send `/start`.

## Render

1. Push this project to GitHub.
2. Open Render.
3. Create `New` -> `Background Worker`.
4. Select this repository.
5. Set:

```text
Build Command: pip install -r requirements.txt
Start Command: python3 main.py
```

6. Add environment variable:

```env
BOT_TOKEN=your_new_telegram_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

7. Deploy the worker.
8. Open your bot in Telegram and send `/start`.

## Files

- `main.py` - bot logic
- `flystat.pdf` - first document
- `marketing.pdf` - second document
- `.env.example` - env template
- `render.yaml` - optional Render config
- `Procfile` - Railway process definition
