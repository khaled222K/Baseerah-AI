# Deploy: website on Vercel, backend on your own computer

How the two halves connect:

```
visitor ──► https://baseerah-ai-sigma.vercel.app             (Vercel: the pages in frontend/)
                │  questions (fetch)
                ▼
          https://<your-name>.ngrok-free.app                  (ngrok: a fixed public address)
                │
                ▼
          your Fedora PC: uvicorn api:app :8000  +  Ollama aya-expanse:8b
```

**Why not run everything on Vercel?** A Vercel function cannot hold the backend:
- torch alone is 769 MB;
- the databases are 126 MB;
- the backend needs about 1.7 GB of memory;
- Ollama cannot run there at all.

`vercel.json` therefore deploys only `frontend/`.

**The trade-off:** the site answers questions only while your PC, the API and ngrok are running.

## One-time setup on your PC

1. Create a free account at https://ngrok.com and sign in.

2. Install ngrok on Fedora:
   ```bash
   curl -sSLo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
   sudo tar xzf /tmp/ngrok.tgz -C /usr/local/bin
   ```

3. Connect ngrok to your account:
   - In the ngrok dashboard, open **Your Authtoken** and copy it. It is a secret: don't paste it anywhere else.
   - Then run:
     ```bash
     ngrok config add-authtoken PASTE_YOUR_TOKEN_HERE
     ```

4. Get your fixed address: in the ngrok dashboard, open **Domains** and claim your free static domain, for example
   `calm-owl-123.ngrok-free.app`.

5. Let the Vercel site call your API. Add this line to `.env` in the project folder:
   ```
   BASEERAH_CORS_ORIGINS=https://baseerah-ai-sigma.vercel.app,https://baseerah-ai-sss-rank-team.vercel.app
   ```

6. Send the domain from step 4 (the domain only, never the token) to Claude, or set it yourself:
   - In Vercel, open the project, then **Settings → Environment Variables**.
   - Add `API_BASE_URL` = `https://calm-owl-123.ngrok-free.app`.
   - Redeploy.

## Every time you want the site to work

Open two terminals:

```bash
# terminal 1: the backend
sudo systemctl start ollama
cd ~/Baseerah-AI
uvicorn api:app --port 8000
```

```bash
# terminal 2: the public address
ngrok http --url=https://calm-owl-123.ngrok-free.app 8000
```

Then open https://baseerah-ai-sigma.vercel.app.

## Checks

- **ngrok is reaching your PC:** open `https://calm-owl-123.ngrok-free.app/health` in a browser. You should see ngrok's
  warning page with a "Visit Site" button, and then `{"status":"ok"}`. Baseerah's own requests skip that warning page.
- **Questions fail but /health works:** check `BASEERAH_CORS_ORIGINS` in `.env`, then restart uvicorn.
- **Answers are slow:** they take 30–90 s with aya-expanse:8b, and the first one after start-up takes a few minutes. The
  site waits up to 5 minutes (`REQUEST_TIMEOUT_MS=300000` on Vercel).

## Notes

- **Visitors share your PC:** anyone with the link can send questions to your computer. Every question uses your CPU, and
  several at once will queue.
- **To stop serving:** close terminal 2.
- **Without the AI model:** start the API with `BASEERAH_LLM=retrieval` for fast, texts-only answers.
- **aya-expanse:8b license:** non-commercial only (CC-BY-NC).
