<div align="center">
<img src="site/docs/banner.jpg" alt="QUARCC Purple" width="100%">

### A market-neutral fund that stays level when AI moves the market

McGill-FIAM Asset Management Hackathon 2026 · Finals

<br>

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/python/python-original.svg" alt="Python" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/pytorch/pytorch-original.svg" alt="PyTorch" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/scikitlearn/scikitlearn-original.svg" alt="scikit-learn" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/pandas/pandas-original.svg" alt="pandas" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/typescript/typescript-original.svg" alt="TypeScript" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/react/react-original.svg" alt="React" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/vitejs/vitejs-original.svg" alt="Vite" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/tailwindcss/tailwindcss-original.svg" alt="Tailwind CSS" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/cloudflare/cloudflare-original.svg" alt="Cloudflare" width="44" height="44">
  &nbsp;&nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons/githubactions/githubactions-original.svg" alt="GitHub Actions" width="44" height="44">
</p>

<p align="center">
  <strong>16.0% a year after costs</strong> &nbsp;|&nbsp; <strong>Information ratio 0.99</strong> &nbsp;|&nbsp; <strong>Sharpe 1.49</strong> &nbsp;|&nbsp; <strong>Beta 0.06</strong>
</p>

<a href="https://quarccpurple.ca"><img src="site/docs/site-btn.svg" alt="Visit quarccpurple.ca" width="560"></a>

</div>

## About

AI drives more of the stock market every year, and when the machines think alike, markets panic
together. QUARCC Purple is a fund built to stay level when that happens. Every month it buys the
strongest US companies and bets against the weakest, with the same money on both sides, so the
market's swings cancel out. LightGBM machine learning keeps that balance tight and the risk steady,
seven AI agents on our own computers check every step, and sixty AI investors we built show us
which trades the crowd piles into.

## Results

Our finals book, January 2021 to August 2026.

| Measure | Finals book |
|---|---|
| Return a year after costs | **16.0%** |
| Information ratio | **0.99** |
| Sharpe ratio | **1.49** |
| Alpha a year | **11.3%** |
| Beta to the S&P 500 | **+0.06** |
| Volatility a year | **8.0%** |
| Worst drawdown | **−6.2%** |
| Months the S&P 500 fell that we still gained | **17 of 25** |
| Breaks even at | **4.1× our trading costs** |
| Scales to | **$5 billion**, still above its hurdle |

## How it works

1. **Score.** Every month we rank about 3,500 US stocks on twelve published signals, such as value,
   quality and momentum, each stock judged against its own sector.
2. **Pick.** We buy the strongest and short the weakest, about 240 stocks in all.
3. **Stay neutral.** The same money long as short, every sector within 1%, and beta held at zero
   by a LightGBM model that learns each stock's beta from its daily returns.
4. **Predict risk.** A second LightGBM model forecasts each stock's volatility. A factor risk model
   turns that into the book's risk, and the book is sized for 10% a year, with a brake after losses.
5. **Pay.** Every trade pays the costs a real broker would charge.
6. **Check.** Seven AI agents, open Gemma and Qwen models on our own machines, each have one job.
   One reads the rules, one sorts filings, one judges stocks with the names hidden, one attacks the
   book, one writes the memo, one explains each holding, and an AI crowd of sixty investors shows
   where the trades pile up.

## Run it

```bash
pip install uv
uv run MAIN.py
```

On its own it checks our submitted book against every rule in seconds. With the organizer's data
beside it, it rebuilds the whole book.

## Made with

| Part | Built with |
|---|---|
| Research | Python, PyTorch, scikit-learn, LightGBM, pandas, NumPy, SciPy, uv |
| AI agents | Gemma 4 26B-A4B, Qwen3.8-27B |
| Website | TypeScript, React 19, Vite, Tailwind CSS, three.js, WebGL, GSAP |
| Film | Made in code with three.js, voiced by Kokoro, an AI voice that runs locally |
| Hosting | Cloudflare Workers and R2, GitHub Actions |

## What is where

| Folder | What it holds |
|---|---|
| `fiam/` | The book, its costs, the models, the AI agents and the audit |
| `submission/` | Our official results |
| `site/` | The website, the 3D tour and the film |
| `docs/` | The finals day guide and every protocol we wrote before running it |

<br>

Nicholas Xydis · Yohannah Ilieva · Andrew Koumoudjian · Nicolas Romero · Nokto Lapointe
