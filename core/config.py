DEFAULT_TICKERS    = ["SPMO", "QQQ", "SPY"]
START              = "2020-01-01"
LEVERAGE           = 2.0
MARGIN_RATE        = 0.048       # Futu HK annual USD borrow rate
INITIAL_CAPITAL    = 10_000
MAINTENANCE_MARGIN = 0.30        # Futu HK margin call threshold
FEE_PER_SHARE      = 0.0049 + 0.005   # commission + platform fee
FEE_MIN_PER_ORDER  = 0.99 + 1.00      # minimums per order

# Hard constraints for optimization
MAX_DRAWDOWN_LIMIT = -0.50
MAX_MARGIN_CALLS   = 0
