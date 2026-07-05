"""
StockLab 策略引擎 - 买卖信号生成 + 策略回测
"""
import pandas as pd
import numpy as np
from typing import List, Dict


def generate_signals(kline_data: List[Dict], plan_content: str) -> str:
    """
    根据K线数据和方案内容生成买卖信号
    返回: "buy" / "sell" / "hold"
    """
    if not kline_data or len(kline_data) < 20:
        return "hold"

    df = pd.DataFrame(kline_data)
    closes = df["close"].values
    volumes = df["volume"].values
    latest_close = closes[-1]
    latest_volume = volumes[-1]

    # 计算均线
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    avg_volume_20 = np.mean(volumes[-20:])

    # 计算 MACD
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12 - ema26
    dea = _ema(np.array([dif]), 9)[-1] if len(closes) >= 35 else dif
    macd = 2 * (dif - dea)

    # 计算 RSI
    rsi = _calc_rsi(closes, 14)

    # 解析方案内容中的关键词，决定信号策略
    content_lower = plan_content.lower()

    buy_signals = 0
    sell_signals = 0

    # 均线策略
    if "均线" in content_lower or "ma" in content_lower:
        if "金叉" in content_lower:
            if ma5 > ma10 and ma5 > ma20:
                buy_signals += 1
        if "死叉" in content_lower:
            if ma5 < ma10 and ma5 < ma20:
                sell_signals += 1
        if "突破" in content_lower and "20" in content_lower:
            if latest_close > ma20:
                buy_signals += 1
        if "跌破" in content_lower and "20" in content_lower:
            if latest_close < ma20:
                sell_signals += 1

    # MACD 策略
    if "macd" in content_lower:
        if "金叉" in content_lower:
            if dif > dea and macd > 0:
                buy_signals += 1
        if "死叉" in content_lower:
            if dif < dea and macd < 0:
                sell_signals += 1

    # RSI 策略
    if "rsi" in content_lower:
        if "超卖" in content_lower or "70" in content_lower:
            if rsi < 30:
                buy_signals += 1
            if rsi > 70:
                sell_signals += 1

    # 成交量策略
    if "成交量" in content_lower or "放量" in content_lower:
        if "放大" in content_lower:
            if latest_volume > avg_volume_20 * 1.5:
                buy_signals += 1
        if "缩量" in content_lower:
            if latest_volume < avg_volume_20 * 0.5:
                sell_signals += 1

    # 默认：如果没有匹配任何策略，用均线判断
    if buy_signals == 0 and sell_signals == 0:
        if latest_close > ma20 and ma5 > ma10:
            return "buy"
        elif latest_close < ma20 and ma5 < ma10:
            return "sell"
        else:
            return "hold"

    if buy_signals > sell_signals:
        return "buy"
    elif sell_signals > buy_signals:
        return "sell"
    else:
        return "hold"


def run_backtest(kline_data: List[Dict], plan_content: str, initial_capital: float = 100000, fee_rate: float = 0.0003) -> Dict:
    """
    策略回测
    返回: 回测结果字典
    """
    if not kline_data or len(kline_data) < 20:
        return {"success": False, "error": "数据不足，无法回测"}

    df = pd.DataFrame(kline_data)
    closes = df["close"].values
    volumes = df["volume"].values
    highs = df["high"].values
    lows = df["low"].values

    capital = initial_capital
    position = 0  # 持仓数量
    trades = []
    equity_curve = [initial_capital]

    for i in range(20, len(closes)):
        # 生成当前时间点的信号
        window_closes = closes[:i+1]
        window_volumes = volumes[:i+1]

        ma5 = np.mean(window_closes[-5:])
        ma10 = np.mean(window_closes[-10:])
        ma20 = np.mean(window_closes[-20:])
        avg_vol = np.mean(window_volumes[-20:])

        signal = "hold"
        content_lower = plan_content.lower()

        # 均线策略
        if "均线" in content_lower or "ma" in content_lower:
            if "突破" in content_lower and "20" in content_lower:
                if window_closes[-1] > ma20 and window_closes[-2] <= ma20:
                    signal = "buy"
            if "跌破" in content_lower and "20" in content_lower:
                if window_closes[-1] < ma20 and window_closes[-2] >= ma20:
                    signal = "sell"

        # 成交量策略
        if "成交量" in content_lower or "放量" in content_lower:
            if window_volumes[-1] > avg_vol * 1.5 and window_closes[-1] > ma20:
                signal = "buy"

        # 执行交易
        if signal == "buy" and position == 0:
            position = int(capital * 0.95 / closes[i])
            cost = position * closes[i]
            fee = cost * fee_rate
            capital -= (cost + fee)
            trades.append({"date": str(df["date"].iloc[i])[:10], "action": "buy", "price": round(closes[i], 2), "qty": position, "amount": round(cost, 2), "fee": round(fee, 2)})
        elif signal == "sell" and position > 0:
            revenue = position * closes[i]
            fee = revenue * fee_rate
            capital += (revenue - fee)
            profit = revenue - fee - sum(t["amount"] + t["fee"] for t in trades if t["action"] == "buy")
            trades.append({"date": str(df["date"].iloc[i])[:10], "action": "sell", "price": round(closes[i], 2), "qty": position, "amount": round(revenue, 2), "fee": round(fee, 2), "profit": round(profit, 2)})
            position = 0

        equity = capital + (position * closes[i] if position > 0 else 0)
        equity_curve.append(equity)

    # 最终清仓
    if position > 0:
        revenue = position * closes[-1]
        fee = revenue * fee_rate
        capital += (revenue - fee)
        profit = revenue - fee - sum(t["amount"] + t["fee"] for t in trades if t["action"] == "buy")
        trades.append({"date": str(df["date"].iloc[-1])[:10], "action": "sell", "price": round(closes[-1], 2), "qty": position, "amount": round(revenue, 2), "fee": round(fee, 2), "profit": round(profit, 2)})
        position = 0
        equity_curve.append(capital)

    # 计算指标
    total_return = (capital - initial_capital) / initial_capital * 100
    win_trades = [t for t in trades if t["action"] == "sell" and t.get("profit", 0) > 0]
    all_sell_trades = [t for t in trades if t["action"] == "sell"]
    win_rate = len(win_trades) / len(all_sell_trades) * 100 if all_sell_trades else 0

    # 最大回撤
    peak = initial_capital
    max_drawdown = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_drawdown:
            max_drawdown = dd

    # 年化收益率
    days = len(closes) - 20
    annual_return = ((1 + total_return / 100) ** (252 / max(days, 1)) - 1) * 100

    # 夏普比率（简化）
    if len(equity_curve) > 1:
        returns = np.diff(equity_curve) / equity_curve[:-1]
        sharpe = (np.mean(returns) / max(np.std(returns), 0.0001)) * np.sqrt(252)
    else:
        sharpe = 0

    return {
        "success": True,
        "summary": {
            "initial_capital": initial_capital,
            "final_capital": round(capital, 2),
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": len(trades),
            "win_trades": len(win_trades),
        },
        "trades": trades,
        "equity_curve": [round(e, 2) for e in equity_curve[::max(1, len(equity_curve)//100)]],
    }


def _ema(data, period):
    """计算EMA"""
    if len(data) < period:
        return data[-1] if len(data) > 0 else 0
    alpha = 2 / (period + 1)
    ema = np.mean(data[:period])
    for x in data[period:]:
        ema = alpha * x + (1 - alpha) * ema
    return ema


def _calc_rsi(closes, period=14):
    """计算RSI"""
    if len(closes) < period + 1:
        return 50
    deltas = np.diff(closes[-period-1:])
    gains = np.sum(deltas[deltas > 0]) if len(deltas[deltas > 0]) > 0 else 0
    losses = -np.sum(deltas[deltas < 0]) if len(deltas[deltas < 0]) > 0 else 0
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))