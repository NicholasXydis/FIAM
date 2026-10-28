# QUARCC Purple at the McGill-FIAM 2026 finals

This is our whole project in plain English. The detailed rules and the list of what is left live in PLAN.md.

## The team

Nicholas Xydis is Team Leader and leads AI and Research. Nicolas Romero covers Data and Finance. Nokto Lapointe covers Machine Learning. Andrew Koumoudjian covers Portfolio Construction. Yohannah Ilieva covers Risk.

## The challenge

The organisers asked each team to run a $1 billion US stock fund that stays neutral to the market from January 2021 to August 2026. The fund must beat T bills plus 4 percent a year after every cost. The judges' headline number is the information ratio against that hurdle. No single stock may be more than 5 percent of the fund and the longs plus the shorts may not pass 200 percent. The short book must always hold at least $500 million. Every number must trace to a file and the judges study each fund on a platform called Arcana. We get ten minutes to pitch.

## The idea

Markets are slow with public facts that take work to read. Filings and insider buys and short positions all carry news that prices absorb over weeks rather than seconds. We hold the gap between a fact going public and the price catching up. The core is ten published signals from 2012 so nobody can say we picked them by looking at the test years. The edge fades when ideas get crowded or markets panic.

We tested eight new ideas against a bar written before any test. None passed. Short interest came closest and the final fund uses it as one input to the model.

## The data and one clock

We use every file the organisers gave us plus our WRDS data and filings rebuilt straight from the SEC. The organisers' filing file mostly kept companies that survived so we rebuilt it with the dead ones included. Every row gets the moment the public could first see it and the first market close after that. We join data only on that close and trade on it one close later. Companies that later died stay in. Numbers changed after the fact are replaced by the numbers first filed.

## The model

We forecast only the part of each stock's return that the market and its sector and known styles cannot explain. A win then has to come from the stock itself which is what a neutral fund is paid for. Three models vote together. They are LightGBM and an elastic net and a small neural network. Each refit learns only from the past and the final fund refits every quarter. The choice between yearly and quarterly refits and between tight and loose limits was made on 2017 to 2020 alone.

## Building the portfolio

An optimiser turns forecasts into positions. It maximises the edge minus the risk minus the trading costs minus the borrow cost. The book stays neutral to the market and close to neutral on sectors and styles. We open positions in companies worth at least $600 million and hold them while they stay above $500 million. We rebalance monthly because the signals move slowly. Every trade pays fees and spread and market impact and every short pays borrow. Together they cost about 2.2 percent of the fund a year.

## The AI team

AI touches every stage but never picks a stock or sets a size. Eight agents read the rules and sort filings and argue as devil's advocate and write memos and explain positions and play an AI crowd. One of them is the AI risk desk. It can only ever make a position smaller. Plain code checks every rule after any agent speaks. Every AI answer is logged with its inputs so the whole run replays exactly.

We tested the desk fairly against a simple fixed rule and against 100 random desks at the same risk. It did not help so the fund runs without it and we say so. We also measured our AI itself. Sixty AI investors voted like about four independent people, which shows how AI could crowd a market. When we hid company names our model still recognised 21 of 84 companies, so we measure that memory instead of ignoring it.

## Carbon Arc

For the Carbon Arc prize we treat alternative data as evidence. We screened all 77 of its datasets with the organisers' four questions. Only two could even be backtested and we traded none. Carbon Arc's data is today's version of the past so it never enters our forecasts. In our last step we use its free AI connection to ask whether a fund that is neutral to the market is also neutral to shoppers. We compare the spending trends of our longs and our shorts and show how a sudden drop in sales could alert the risk desk if the fund ran live.

## How we kept it honest

The code refused every 2021 to 2026 return until we froze and fingerprinted everything. The first real run lost money with an information ratio of minus 1.39. The team leader then chose one revision after seeing that result. It rebuilt the earnings surprise table and set the hurdle exactly as the rules define it. It traded to the target each month, added short interest and refit from 2017. That revision is our final fund and the team leader tells the judges about it in person. Every other variant we tried on 2021 to 2026 is shown only as an example of how easy it is to overfit and never as our result. A later check found a few earnings surprise values that later filings corrected, which moves some forecasts slightly. We recorded it rather than hide it.

Andrew built another version that looked stronger, but it breaks the 5 percent limit per stock on 317 days so it cannot be our fund.

## The results

From January 2021 to August 2026 the fund grew from $1 billion to $1.054 billion after every cost. Cash plus 4 percent would have reached $1.509 billion, so we missed the hurdle. The information ratio after costs is minus 0.82 and minus 0.54 before costs. The fund made 0.93 percent a year with volatility of 7.45 percent and its worst fall was 10.3 percent. It broke no rule on any day. It barely moved with the market. Its beta is close to zero.

The fund stayed calm when markets fell. Across 17 crises replayed on today's book the market lost 12.1 percent on average and our book lost 0.73 percent. In 2022 the S&P 500 lost 19.4 percent and bonds lost 13.0 percent and a 60 40 portfolio lost 15.8 percent while our fund made 0.9 percent. That is why a neutral fund belongs next to a 60 40 portfolio.

## What Arcana taught us

Arcana splits our return into stock picking and factor bets before costs. Our stock picks earned 11.5 percent over the period. Our unintended factor tilts lost 10.5 percent and took it all back. Positions older than a year held more than half the fund but earned almost nothing. The days around earnings lost money. Three fixes follow. Neutralise the factor tilts. Recycle stale positions. Step aside around earnings.

## The website and the film

The website takes visitors through the fund in short interactive scenes and works on phones and laptops. The 62 second film tells the story in three shapes for wide screens and phones held upright or sideways. Both show only honest numbers from our files.

## The deck

The deck has 16 slides and a short appendix. Nicholas opens and presents the AI and closes with what Arcana taught us and where the product goes next. Nicolas presents the idea and the data and Carbon Arc. Nokto presents the model and the ideas that failed. Andrew presents how forecasts become a portfolio and what everything costs. Yohannah presents risk and the crises and where the fund fits next to a 60 40 portfolio and the standard table the rules require.

## Reproducing everything

Anyone can check our work in four ways. MAIN.py on its own checks every rule and recomputes our headline and confirms the code matches our fingerprints. With the organisers' own price file it also recomputes our returns from their prices. Our own copy of the code plus the USB stick proves every file matches our fingerprints in about a minute. The same copy can rebuild the whole fund from scratch in about three hours.

The Mac rebuilds it exactly. The Windows PC rounds numbers very slightly differently when it retrains so we report its tiny gap instead of calling it identical. The USB stick carries the data and results and films and offline installers for Mac and Windows. Without the AI model files it is about 57 GB. The PC is reached through Tailscale and if that link fails everything except the live AI demo still runs on the Mac.

## Words you will hear

Market neutral means the shorts balance the longs so the market's direction mostly cancels out. Gross is the size of all longs plus all shorts compared with the fund. Beta is how much we move with the whole market. The information ratio is our return above T bills plus 4 percent divided by how much it swings. The Sharpe ratio is the same idea above T bills alone. Out of sample means years the model never saw. Overfitting means tuning a strategy until it fits the past by luck.

## What is left

Tonight we finish MAIN.py and test all four ways on the Mac and the PC and save a lean kit to the USB. Tomorrow morning we review the results and the deck and record the clips. Last come Carbon Arc and the study guide and Arcana and then we launch the website.
