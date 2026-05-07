# Deploy ASTROTRADE

Two services: **engine** (FastAPI + Python) on Render, **UI** (Next.js) on Vercel.

This guide assumes you have a GitHub account. Render and Vercel both deploy from a Git repository.

---

## 1. Push to GitHub

```bash
# from /Users/ajitovhal/Astrotrader
git remote add origin https://github.com/<your-username>/astrotrader.git
git push -u origin main
```

(`git init` + the first commit have already been done locally.)

---

## 2. Deploy the engine to Render

### 2a. Create the service

1. Open <https://dashboard.render.com>, click **New → Web Service**.
2. Connect the GitHub repo.
3. Render auto-detects [`render.yaml`](render.yaml). Confirm:
   - **Plan**: Free
   - **Branch**: `main`
   - **Dockerfile path**: `./Dockerfile`
   - **Health-check path**: `/health`
4. Click **Create Web Service**. First build takes ~5–8 minutes (the `de440s.bsp` ephemeris kernel is downloaded and baked into the image).

When the build finishes Render will assign a URL like `https://astrotrader-engine.onrender.com`. Copy it.

### 2b. Verify

```bash
curl https://astrotrader-engine.onrender.com/health
# {"status":"ok"}

curl -X POST https://astrotrader-engine.onrender.com/decide \
     -H "Content-Type: application/json" \
     -d '{"symbol":"SPY","horizon":5,"top_n":50}' | head -c 200
```

### 2c. Free-tier behavior to expect

- Service **sleeps after 15 min of inactivity**. The next request takes ~30 s to wake it.
- 512 MB RAM cap. We warm only `SPY` at startup — other symbols lazy-load on first request (~5–10 s).
- Ephemeris is baked into the Docker image so no per-request kernel download.

---

## 3. Deploy the UI to Vercel

### 3a. Create the project

1. Open <https://vercel.com/new>, import the same GitHub repo.
2. Vercel reads [`vercel.json`](vercel.json) and uses these settings:
   - Build command: `cd web && npm install && npm run build`
   - Output directory: `web/.next`
   - Framework preset: Next.js
3. Before clicking Deploy, expand **Environment Variables** and add:
   - `ASTROTRADE_API_URL` = `https://astrotrader-engine.onrender.com` *(your Render URL from step 2)*
4. Click **Deploy**. First build is ~2 min.

### 3b. Wire CORS back to Render

Vercel will assign a URL like `https://astrotrader-xxxx.vercel.app`. Copy it, then in the Render dashboard:

1. Go to your engine service → **Environment** tab.
2. Set `ASTROTRADE_CORS_ORIGINS` = `https://astrotrader-xxxx.vercel.app`
   (multiple origins comma-separated, no trailing slash)
3. Render redeploys automatically.

---

## 4. Verify end-to-end

Open the Vercel URL in a browser. Expected behavior:

- Header + Controls paint instantly.
- Skeleton briefly visible (~30 s if Render was sleeping, ~2 s if warm).
- Real data lands: SPY shows BULLISH/BEARISH/NEUTRAL, the Clock animates planets in.
- Switch the symbol to NIFTY: skeleton flashes again while engine builds the context (~10 s first time, instant after).

---

## 5. Per-symbol calibrators

The repo ships SPY's calibrator only (it's tiny, was committed for the demo). To fit calibrators for the other 12 symbols on the deployed engine, run locally and re-deploy:

```bash
.venv/bin/python -m astrotrader.cli calibrate-all --method platt --stride 2
git add data_cache/calibrator_*.joblib
git commit -m "fit calibrators for all symbols"
git push
```

Render rebuilds; calibrators are baked into the new image. Without them, the `/decide` endpoint still works — it just returns uncalibrated raw probabilities (Truth Panel shows `uncalibrated`).

---

## Custom domain (optional)

Both Render and Vercel support custom domains in their dashboards. Point your DNS at the provider, add the domain in the project settings, and update `ASTROTRADE_CORS_ORIGINS` to include it.

---

## Cost

| Service | Plan | Cost |
|---|---|---|
| Render (engine) | Free | $0/mo, sleeps after idle |
| Vercel (UI) | Hobby | $0/mo, 100 GB bandwidth |

If you outgrow free tiers:
- Render Starter ($7/mo) → no sleep, 512 MB → 1 GB RAM, persistent disk available
- Vercel Pro ($20/mo) → only needed at high traffic; the UI is just SSR forwarding to the engine
