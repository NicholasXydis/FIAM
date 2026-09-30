# The trader: how far to move toward the target book each month, and at what gross, learned.

import gymnasium as gym
import numpy as np
import pandas as pd
import torch

from fiam import benchmarks as B
from fiam import book as P
from fiam import paths

# One thread and deterministic kernels, so every machine computes the same policy.
torch.use_deterministic_algorithms(True)
torch.set_num_threads(1)

# One investor's taste for risk: utility is mean return minus half this times its variance.
RISK_AVERSION = 5.0
# The action range: trade 20% to 100% of the way, at 120% up to the book's full gross.
RATE, GROSS = (0.2, 1.0), (1.2, P.LIMITS["gross"])
FIXED_RATES = (0.25, 0.5, 0.75, 1.0)
EPISODE, BATCH = 12, 64
# A full fit the first month, then a few steps each month from the last month's policy.
STEPS, MONTHLY_STEPS = (20, 5) if paths.SMOKE else (300, 25)
PPO_STEPS = 480 if paths.SMOKE else 24_000
SEED = 42

# Costs per unit traded: the book's commission and impact, plus its scaled half-spread.
LINEAR = (P.COSTS["commission_bps"] + P.COSTS["impact_bps"]) / 1e4
HALF_SPREAD = P.COSTS["spread_scale"] / 2
BORROW = P.COSTS["borrow_gc_bps"] / 1e4 / 12, P.COSTS["borrow_htb_bps"] / 1e4 / 12
FEATURES = ["aim_churn", "book_volatility", "market_volatility", "book_momentum"]


# The target path as dense arrays over every name: weights, returns, spreads, borrow and listing.
def arrays(steps: list) -> dict:
    names = sorted({p for _, w, *_ in steps for p in w.index})
    column = {p: i for i, p in enumerate(names)}
    shape = (len(steps), len(names))
    out = {k: np.zeros(shape) for k in ("aim", "ret", "spread", "htb", "listed")}
    rates = B.benchmarks().set_index("month")["rf"]
    out["rf"], out["months"] = np.zeros(len(steps)), []
    for i, (month, weights, _, cross, *_) in enumerate(steps):
        out["aim"][i, [column[p] for p in weights.index]] = weights.to_numpy()
        listed = cross.set_index("permno")
        listed = listed[listed.index.isin(column)]
        at = [column[p] for p in listed.index]
        out["ret"][i, at] = listed["ret_exc_lead1m"].fillna(0.0).to_numpy()
        out["spread"][i, at] = listed["bidaskhl_21d"].fillna(0.0).to_numpy()
        out["htb"][i, at] = listed["htb"].astype(float).to_numpy()
        out["listed"][i, at] = 1.0
        out["rf"][i] = rates.get((month + pd.offsets.MonthBegin(1)).normalize(), 0.0)
        out["months"].append(pd.Timestamp(month))
    return out


# What is known at each decision: how much the target moved, and how calm the book and market were.
def features(path: dict, nets: pd.Series) -> np.ndarray:
    churn = np.r_[1.0, np.abs(np.diff(path["aim"], axis=0)).sum(axis=1) / 2]
    past = nets.shift(1)
    vol = past.rolling(12, min_periods=6).std().fillna(past.std()).to_numpy()
    mom = past.rolling(12, min_periods=6).mean().fillna(0.0).to_numpy()
    close = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    daily = close.set_index("observation_date")["SP500"].pct_change().rolling(21).std()
    market = daily.reindex(pd.DatetimeIndex(path["months"]), method="ffill")
    return np.c_[churn, vol, market.fillna(market.mean()).to_numpy(), mom]


# One simulated month in PyTorch: trade part of the way, rebalance to gross, pay costs, drift.
def step_torch(held, t: dict, now, rate, gross, scale):
    mixed = (1 - rate) * held * t["listed"][now] + rate * t["aim"][now] * (gross / GROSS[1])
    longs, shorts = mixed.clamp(min=0), mixed.clamp(max=0)
    half = gross / 2
    mixed = longs * half / longs.sum(-1, keepdim=True) - shorts * half / shorts.sum(
        -1, keepdim=True
    )
    traded = (mixed - held).abs() * (LINEAR + t["spread"][now] * HALF_SPREAD)
    shorts = mixed.clamp(max=0).abs()
    borrow = shorts * (BORROW[0] + t["htb"][now] * BORROW[1])
    net = (mixed * t["ret"][now]).sum(-1) - traded.sum(-1) * scale - borrow.sum(-1)
    rf = t["rf"][now].unsqueeze(-1)
    return net, mixed * (1 + rf + t["ret"][now]) / (1 + rf + net.unsqueeze(-1))


# The same month in NumPy, for the PPO environment and for replaying real months.
def step_numpy(held, t: dict, now: int, rate: float, gross: float, scale: float):
    mixed = (1 - rate) * held * t["listed"][now] + rate * t["aim"][now] * (gross / GROSS[1])
    longs, shorts = mixed.clip(min=0), mixed.clip(max=0)
    mixed = longs * (gross / 2) / longs.sum() - shorts * (gross / 2) / shorts.sum()
    traded = np.abs(mixed - held) * (LINEAR + t["spread"][now] * HALF_SPREAD)
    borrow = np.abs(mixed.clip(max=0)) * (BORROW[0] + t["htb"][now] * BORROW[1])
    net = float((mixed * t["ret"][now]).sum() - traded.sum() * scale - borrow.sum())
    rf = t["rf"][now]
    return net, mixed * (1 + rf + t["ret"][now]) / (1 + rf + net)


# Mean minus half the risk aversion times the variance, over every simulated month.
def utility(nets: torch.Tensor) -> torch.Tensor:
    return nets.mean() - RISK_AVERSION / 2 * nets.var()


# Maps a raw pair in (0, 1) to a trade rate and a gross.
def actions(z0, z1):
    return RATE[0] + (RATE[1] - RATE[0]) * z0, GROSS[0] + (GROSS[1] - GROSS[0]) * z1


# The deep-hedging policy: two sigmoids of the standardized features, for rate and gross.
class Policy(torch.nn.Module):
    # One linear layer to two outputs, started as the book trades today.
    def __init__(self, width: int):
        super().__init__()
        self.linear = torch.nn.Linear(width, 2, dtype=torch.float64)
        torch.nn.init.zeros_(self.linear.weight)
        # Starts as the book is today: trade all the way, at full gross.
        torch.nn.init.constant_(self.linear.bias, 3.0)

    # Features to a trade rate and a gross.
    def forward(self, f):
        z = torch.sigmoid(self.linear(f))
        return actions(z[..., 0], z[..., 1])


# Episodes from a window of months: random starts, and costs scaled 1-2x at random.
def simulate(t: dict, f, starts, scales, act) -> torch.Tensor:
    held, nets = t["aim"][starts], []
    for k in range(1, EPISODE):
        now = starts + k
        rate, gross = act(f[now])
        net, held = step_torch(held, t, now, rate.unsqueeze(-1), gross.unsqueeze(-1), scales)
        nets.append(net)
    return torch.stack(nets)


# Trains the deep-hedging policy by gradient through the simulator, warm from last month's.
def train_deep(t: dict, f, window: np.ndarray, policy: Policy | None = None) -> Policy:
    steps = STEPS if policy is None else MONTHLY_STEPS
    torch.manual_seed(SEED)
    policy = policy or Policy(f.shape[1])
    opt = torch.optim.Adam(policy.parameters(), lr=0.05)
    rng = np.random.default_rng([SEED, len(window)])
    for _ in range(steps):
        starts = torch.as_tensor(rng.integers(window.min(), window.max() - EPISODE + 1, BATCH))
        scales = torch.as_tensor(rng.uniform(1.0, 2.0, BATCH))
        loss = -utility(simulate(t, f, starts, scales, policy))
        opt.zero_grad()
        loss.backward()
        opt.step()
    return policy


# The fixed-rate rule with the best utility on the same window: the baseline every policy must beat.
def train_fixed(t: dict, f, window: np.ndarray) -> float:
    starts = torch.as_tensor(np.arange(window.min(), window.max() - EPISODE + 1))
    scales = torch.full((len(starts),), 1.5, dtype=torch.float64)

    # The utility of trading at one fixed rate over the window.
    def score(rate: float) -> float:
        # The same rate and full gross for every month.
        def act(ft):
            ones = torch.ones(ft.shape[:-1], dtype=torch.float64)
            return ones * rate, ones * GROSS[1]

        return float(utility(simulate(t, f, starts, scales, act)))

    return max(FIXED_RATES, key=score)


# The same simulator as an environment, so PPO learns from rewards alone, not from gradients.
class Market(gym.Env):
    # The target path, its features and the months episodes may start in.
    def __init__(self, t: dict, f: np.ndarray, window: np.ndarray):
        self.t, self.f, self.window = t, f, window
        self.observation_space = gym.spaces.Box(-10, 10, (f.shape[1],), np.float64)
        self.action_space = gym.spaces.Box(-1, 1, (2,), np.float32)

    # A random start in the window, holding the target, at a random cost scale.
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.now = int(self.np_random.integers(self.window.min(), self.window.max() - EPISODE + 1))
        self.held, self.left = self.t["aim"][self.now], EPISODE - 1
        self.scale = float(self.np_random.uniform(1.0, 2.0))
        return self.f[self.now + 1], {}

    # One month traded at the action, rewarded by mean-variance utility.
    def step(self, action):
        self.now += 1
        rate, gross = actions(*((np.clip(action, -1, 1) + 1) / 2))
        net, self.held = step_numpy(self.held, self.t, self.now, rate, gross, self.scale)
        self.left -= 1
        reward = net - RISK_AVERSION / 2 * net**2
        return self.f[min(self.now + 1, len(self.f) - 1)], reward, self.left == 0, False, {}


# PPO on the same months and rewards, with a fixed seed so the run repeats.
def train_ppo(t: dict, f: np.ndarray, window: np.ndarray):
    from stable_baselines3 import PPO

    model = PPO(
        "MlpPolicy", Market(t, f, window), n_steps=240, batch_size=60, seed=SEED, device="cpu"
    )
    return model.learn(total_timesteps=PPO_STEPS)


# A policy walked through real months of the target path: its net return each month.
def replay(t: dict, months, act) -> np.ndarray:
    held, nets = t["aim"][months[0] - 1], []
    for now in months:
        net, held = step_numpy(held, t, int(now), *act(int(now)), 1.0)
        nets.append(net)
    return np.array(nets)
