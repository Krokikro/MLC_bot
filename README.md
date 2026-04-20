# MLC Bot

Telegram bot for MLC and CGM Flystat. It remembers the user's name, routes product vs investor questions, sends `flystat.pdf` and `marketing.pdf` when relevant, and answers free-form questions through OpenAI.

## Current behavior

- Remembers the user's name across sessions and uses it on return
- Sends `flystat.pdf` for product / presentation requests
- Sends `marketing.pdf` not only for direct requests like `marketing plan`, but also for indirect investor phrases such as `commercialization`, `monetization`, `partner plan`, and similar Russian variants and typos
- Explains in English why the marketing plan is relevant for the investor side
- Ends the conversation cleanly when the user explicitly closes it, sends important links, and does not ask an open question in the closing flow
- Treats short replies like `no` or `no thanks` as conversation-ending only when the bot had actually asked a question or proposed a next step
- Uses OpenAI for free-form answers after the initial routing and file sharing flow

## Local run

1. Create `.env` next to `main.py`:

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
4. Open the project settings and add variables:

```env
BOT_TOKEN=your_new_telegram_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

5. Railway should detect the `Procfile` automatically.
6. Deploy the project.
7. Open your bot in Telegram and send `/start`.

## Before pushing to GitHub

1. Review local changes:

```bash
git status
git diff
```

2. Commit the updated bot logic and docs:

```bash
git add main.py knowledge.py data.json README.md .env.example
git commit -m "Improve investor routing, closing flow, and name memory"
```

3. Push to GitHub:

```bash
git push origin <your-branch>
```

4. In Railway, redeploy the latest commit from GitHub.

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
- `knowledge.py` - context selection, investor facts, resource detection, and sales guidance
- `flystat.pdf` - first document
- `marketing.pdf` - second document
- `.env.example` - env template
- `render.yaml` - optional Render config
- `Procfile` - Railway process definition
