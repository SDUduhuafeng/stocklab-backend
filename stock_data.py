"""
StockLab 股票数据模块 - 使用 yfinance 获取 A 股数据
yfinance 官方 Yahoo Finance API，全球节点稳定访问
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import yfinance as yf

# 懒加载 akshare 作为备份（选股、资金流向需要）
_ak = None

def _get_ak():
    """延迟导入 akshare，只有真正调用数据接口时才加载"""
    global _ak
    if _ak is None:
        import akshare as ak
        _ak = ak
    return _ak


def get_index_data():
    """获取三大指数实时行情（yfinance 全球稳定）"""
    try:
        # yfinance 指数 ticker
        indices_map = {
            "000001.SS": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
        }

        result = {}
        for ticker, name in indices_map.items():
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            # 获取最新价格和涨跌
            price = info.get("regularMarketPrice", info.get("currentPrice", 0))
            prev_close = info.get("regularMarketPreviousClose", 0)

            if price and prev_close:
                change = price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                # 用历史数据获取最新
                hist = ticker_obj.history(period="2d")
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    price = hist['Close'].iloc[-1]
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100
                else:
                    price = 0
                    change = 0
                    change_pct = 0

            code = ticker.split(".")[0]
            result[name] = {
                "code": code,
                "name": name,
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
            }

        if result:
            return {"success": True, "data": result}
        else:
            return {"success": False, "error": "yfinance 获取指数失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_stock_realtime(codes: list):
    """获取股票实时行情（批量）"""
    try:
        result = []
        for code in codes:
            # yfinance ticker 格式
            if code.startswith("6"):
                ticker = f"{code}.SS"
            else:
                ticker = f"{code}.SZ"

            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            price = info.get("regularMarketPrice", info.get("currentPrice", 0))
            prev_close = info.get("regularMarketPreviousClose", 0)
            volume = info.get("volume", 0)
            pe = info.get("trailingPE", None)
            market_cap = info.get("marketCap", None)

            if price and prev_close:
                change = price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = 0
                change_pct = 0

            result.append({
                "code": code,
                "name": info.get("shortName", "未知"),
                "price": float(price) if price else 0,
                "change_pct": float(change_pct) if change_pct else 0,
                "change": float(change) if change else 0,
                "volume": str(volume),
                "amount": 0,
                "turnover": 0,
                "high": 0,
                "low": 0,
                "open": 0,
                "pre_close": float(prev_close) if prev_close else 0,
                "pe": float(pe) if pe else None,
            })
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_stock(keyword: str):
    """搜索股票（模糊匹配）"""
    try:
        # yfinance 不支持搜索， fallback 到 akshare
        df = _get_ak().stock_zh_a_spot_em()
        mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(keyword, na=False)
        matched = df[mask].head(20)
        result = []
        for _, r in matched.iterrows():
            result.append({
                "code": str(r["代码"]),
                "name": str(r["名称"]),
                "price": float(r["最新价"]),
                "change_pct": float(r["涨跌幅"]),
            })
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_kline_data(code: str, period: str = "daily", start_date: str = None, end_date: str = None):
    """获取K线数据"""
    try:
        if code.startswith("6"):
            ticker = f"{code}.SS"
        else:
            ticker = f"{code}.SZ"

        # 转换日期格式
        if start_date:
            start = datetime.strptime(start_date, "%Y%m%d")
        else:
            start = datetime.now() - timedelta(days=365)

        if end_date:
            end = datetime.strptime(end_date, "%Y%m%d")
        else:
            end = datetime.now()

        # yfinance 获取历史数据
        interval = "1d"
        if period == "weekly":
            interval = "1wk"
        elif period == "monthly":
            interval = "1mo"

        df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
        if df.empty:
            return {"success": False, "error": "未获取到K线数据"}

        kline_data = []
        for date, row in df.iterrows():
            kline_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "close": float(row["Close"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "volume": float(row["Volume"]),
                "amount": 0,
            })

        return {"success": True, "data": kline_data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_all_stocks():
    """获取全市场A股列表（用于筛选）"""
    try:
        df = _get_ak().stock_zh_a_spot_em()
        stocks = []
        for _, r in df.iterrows():
            stocks.append({
                "code": str(r["代码"]),
                "name": str(r["名称"]),
                "price": float(r["最新价"]),
                "change_pct": float(r["涨跌幅"]),
                "pe": float(r["市盈率-动态"]) if pd.notna(r["市盈率-动态"]) else None,
                "market_cap": float(r["总市值"]) if pd.notna(r["总市值"]) else None,
                "volume": float(r["成交量"]),
                "turnover": float(r["换手率"]),
                "amount": float(r["成交额"]),
                "main_flow": float(r.get("主力净流入", 0)) if "主力净流入" in r else None,
            })
        return {"success": True, "data": stocks, "total": len(stocks)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def screen_stocks(conditions: dict):
    """根据条件筛选股票"""
    try:
        df = _get_ak().stock_zh_a_spot_em()
        mask = pd.Series([True] * len(df))

        if "pe_max" in conditions:
            mask &= df["市盈率-动态"].apply(lambda x: pd.notna(x) and float(x) > 0 and float(x) <= conditions["pe_max"])
        if "pe_min" in conditions:
            mask &= df["市盈率-动态"].apply(lambda x: pd.notna(x) and float(x) >= conditions["pe_min"])
        if "market_cap_min" in conditions:
            mask &= df["总市值"].apply(lambda x: pd.notna(x) and float(x) >= conditions["market_cap_min"] * 1e8)
        if "turnover_min" in conditions:
            mask &= df["换手率"].apply(lambda x: pd.notna(x) and float(x) >= conditions["turnover_min"])
        if "change_pct_min" in conditions:
            mask &= df["涨跌幅"].apply(lambda x: pd.notna(x) and float(x) >= conditions["change_pct_min"])
        if "change_pct_max" in conditions:
            mask &= df["涨跌幅"].apply(lambda x: pd.notna(x) and float(x) <= conditions["change_pct_max"])

        matched = df[mask].head(100)
        result = []
        for _, r in matched.iterrows():
            result.append({
                "code": str(r["代码"]),
                "name": str(r["名称"]),
                "price": float(r["最新价"]),
                "change_pct": float(r["涨跌幅"]),
                "pe": float(r["市盈率-动态"]) if pd.notna(r["市盈率-动态"]) else None,
                "market_cap": float(r["总市值"]) if pd.notna(r["总市值"]) else None,
                "turnover": float(r["换手率"]),
                "match_reason": _build_match_reason(conditions, r),
            })
        return {"success": True, "data": result, "total": len(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _build_match_reason(conditions, row):
    """构建匹配原因说明"""
    reasons = []
    if "pe_max" in conditions:
        reasons.append(f"PE≤{conditions['pe_max']}")
    if "pe_min" in conditions:
        reasons.append(f"PE≥{conditions['pe_min']}")
    if "market_cap_min" in conditions:
        reasons.append(f"市值≥{conditions['market_cap_min']}亿")
    return ", ".join(reasons) if reasons else "满足所有条件"


def get_money_flow(code: str):
    """获取个股资金流向"""
    try:
        df = _get_ak().stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
        if df is None or df.empty:
            return {"success": False, "error": "未获取到资金流向数据"}
        latest = df.iloc[-1]
        return {
            "success": True,
            "data": {
                "date": str(latest["日期"])[:10],
                "main_net_inflow": float(latest["主力净流入-净额"]) if "主力净流入-净额" in latest else 0,
                "main_net_inflow_pct": float(latest["主力净流入-净占比"]) if "主力净流入-净占比" in latest else 0,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
