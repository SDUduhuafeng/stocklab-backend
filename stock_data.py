"""
StockLab 股票数据模块 - 基于 akshare 获取 A 股数据
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import requests
import json
import time

# 懒加载 akshare（避免启动时导入耗时过长导致 Railway 超时）
_ak = None

def _get_ak():
    """延迟导入 akshare，只有真正调用数据接口时才加载"""
    global _ak
    if _ak is None:
        import akshare as ak
        _ak = ak
    return _ak

# 通用请求会话（带重试和超时）
_session = None

def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
    return _session

def _fetch_with_retry(url, params=None, max_retries=2, timeout=15):
    """带重试的 HTTP GET 请求"""
    session = _get_session()
    last_error = None
    for i in range(max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_error = e
            if i < max_retries:
                time.sleep(1)
    raise last_error


def get_index_data():
    """获取三大指数实时行情（直接HTTP请求，避免akshare过重）"""
    try:
        # 使用东方财富指数行情API（轻量级，适合海外访问）
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        codes = "1.000001,0.399001,0.399006"
        params = {
            "fltt": 2,
            "secids": codes,
            "fields": "f2,f3,f4,f12,f14",
            "cb": "jQuery"
        }
        resp = _fetch_with_retry(url, params=params, timeout=10)
        # 解析 JSONP 格式
        text = resp.text
        json_str = text[text.index("(")+1:text.rindex(")")]
        data = json.loads(json_str)

        index_map = {"1.000001": "上证指数", "0.399001": "深证成指", "0.399006": "创业板指"}
        code_map = {"1.000001": "000001", "0.399001": "399001", "0.399006": "399006"}
        indices = {}

        if data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                secid = item.get("f12", "")
                name = index_map.get(secid, secid)
                indices[name] = {
                    "code": code_map.get(secid, secid),
                    "name": name,
                    "price": float(item.get("f2", 0)),
                    "change": float(item.get("f4", 0)),
                    "change_pct": float(item.get("f3", 0)),
                }

        if indices:
            return {"success": True, "data": indices}
        else:
            return {"success": False, "error": "未获取到指数数据"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_stock_realtime(codes: list):
    """获取股票实时行情（批量）"""
    try:
        df = _get_ak().stock_zh_a_spot_em()
        result = []
        for code in codes:
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                result.append({
                    "code": code,
                    "name": str(r["名称"]),
                    "price": float(r["最新价"]),
                    "change_pct": float(r["涨跌幅"]),
                    "change": float(r["涨跌额"]),
                    "volume": str(r["成交量"]),
                    "amount": float(r["成交额"]),
                    "turnover": float(r["换手率"]),
                    "high": float(r["最高"]),
                    "low": float(r["低"]),
                    "open": float(r["今开"]),
                    "pre_close": float(r["昨收"]),
                    "pe": float(r["市盈率-动态"]) if pd.notna(r["市盈率-动态"]) else None,
                })
            else:
                result.append({"code": code, "name": "未知", "error": "未找到该股票"})
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_stock(keyword: str):
    """搜索股票（模糊匹配）"""
    try:
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
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        if code.startswith("6"):
            symbol = f"{code}.SH"
        else:
            symbol = f"{code}.SZ"

        df = _get_ak().stock_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust="qfq")
        if df is None or df.empty:
            return {"success": False, "error": "未获取到K线数据"}

        kline_data = []
        for _, row in df.iterrows():
            kline_data.append({
                "date": str(row["日期"])[:10],
                "open": float(row["开盘"]),
                "close": float(row["收盘"]),
                "high": float(row["最高"]),
                "low": float(row["最低"]),
                "volume": float(row["成交量"]),
                "amount": float(row["成交额"]),
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
    """
    根据条件筛选股票
    conditions 示例: {"pe_max": 15, "roe_min": 15, "market_cap_min": 100}
    """
    try:
        df = _get_ak().stock_zh_a_spot_em()
        mask = pd.Series([True] * len(df))

        if "pe_max" in conditions:
            mask &= df["市盈率-动态"].apply(lambda x: pd.notna(x) and float(x) > 0 and float(x) <= conditions["pe_max"])
        if "pe_min" in conditions:
            mask &= df["市盈率-动态"].apply(lambda x: pd.notna(x) and float(x) >= conditions["pe_min"])
        if "market_cap_min" in conditions:
            # 市值单位是亿，转换为元
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