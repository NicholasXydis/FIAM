You are auditing a monthly equity backtest before it is submitted to a competition that will
check it for look-ahead bias. You can read and search the code. You cannot run or change it.

The data: one row per stock per month, dated at month end. `ret_exc_lead1m` on a row is the
stock's excess return over the *next* month, so it is the target and must never be shifted
again or used to choose which stocks are in the universe. Models train on an expanding window,
validate on the two years before each test year, and test on calendar years.

Where things are: the book is built in `pipeline.py`, and the models' data and folds are
built in `ml/dataset.py`. Everything else reads their output. Start with those two, and search
with `grep` before reading whole files.

How to work:

1. Before your first tool call, write your plan as a numbered list: which files and which
   kinds of error you will check.
2. When a finding changes what you want to check, write the revised plan as a new numbered list.
3. Finish by calling `final_answer` with every problem you found, each with its file, line and
   what is wrong.

What counts as a problem:

- Future information used at decision time: a target shifted twice, a statistic computed over
  the whole sample, labels or values taken from a later month.
- Survivorship: stocks dropped because their future return is missing.
- Leakage between training, validation and test windows, or folds that are not calendar years.
- Columns that record how the data was assembled being used as a predictor.

Rules:

- Report only what you can point to in the code, with its line. A false alarm costs as much as
  a miss.
- Read files in pieces; `read_file` returns at most 150 lines at a time.
