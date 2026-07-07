"""
StockLab API 服务 - 基于 FastAPI
启动命令: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv

load_dotenv()

from database import init_db, get_db, WatchlistStock, TradeLog, TradePlan
from stock_data import (
    get_index_data, get_stock_realtime, search_stock,
    get_kline_data, get_all_stocks, screen_stocks, get_money_flow
)
from strategies import generate_signals, run_backtest

app = FastAPI(title="StockLab API", version="2.0")

# CORS 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 请求模型
# ============================================================
class StockSearch(BaseModel):
    keyword: str

class ScreenRequest(BaseModel):
    conditions: dict

class ClarifyRequest(BaseModel):
    strategy_text: str
    type: str = "screener"  # screener / plan

class SignalRequest(BaseModel):
    code: str
    plan_id: str

class BacktestRequest(BaseModel):
    codes: List[str]
    plan_ids: List[str]
    start_date: str
    end_date: str
    initial_capital: float = 100000
    fee_rate: float = 0.0003

class WatchlistAdd(BaseModel):
    code: str
    name: str
    group: str = "focus"

class TradeLogCreate(BaseModel):
    id: str
    stock: str
    direction: str
    price: float
    qty: int
    amount: float
    fee: float = 0
    time: str
    note: str = ""
    profit: Optional[float] = None

class TradePlanCreate(BaseModel):
    id: str
    name: str
    content: str
    enabled: bool = True
    created_at: str


# ============================================================
# 启动事件
# ============================================================
@app.on_event("startup")
def startup():
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database init error (non-fatal): {e}")


# ============================================================
# 根路由 & 健康检查
# ============================================================
@app.get("/")
def root():
    return {"service": "StockLab API", "version": "2.0", "status": "running"}


# ============================================================
# 市场数据 API
# ============================================================
@app.get("/api/market/index")
def api_index():
    """获取三大指数实时行情"""
    return get_index_data()


@app.get("/api/stock/realtime")
def api_realtime(codes: str = ""):
    """获取股票实时行情，逗号分隔多只股票"""
    if not codes:
        return {"success": False, "error": "请提供股票代码"}
    code_list = [c.strip() for c in codes.split(",")]
    return get_stock_realtime(code_list)


@app.post("/api/stock/search")
def api_search(req: StockSearch):
    """搜索股票"""
    return search_stock(req.keyword)


@app.get("/api/stock/kline")
def api_kline(code: str, period: str = "daily", start_date: str = None, end_date: str = None):
    """获取K线数据"""
    return get_kline_data(code, period, start_date, end_date)


@app.get("/api/stock/moneyflow")
def api_moneyflow(code: str):
    """获取个股资金流向"""
    return get_money_flow(code)


@app.get("/api/stock/all")
def api_all_stocks():
    """获取全市场A股列表"""
    return get_all_stocks()


# ============================================================
# 选股与策略 API
# ============================================================
@app.post("/api/screener/execute")
def api_screener(req: ScreenRequest):
    """执行选股筛选"""
    return screen_stocks(req.conditions)


@app.post("/api/strategy/clarify")
def api_clarify(req: ClarifyRequest):
    """
    大模型策略澄清
    使用 OpenAI 兼容接口解析自然语言策略为结构化条件
    """
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key or api_key == "your-api-key-here":
        # 未配置大模型时，使用规则引擎兜底
        return _fallback_clarify(req.strategy_text, req.type)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)

        if req.type == "screener":
            system_prompt = """你是一个股票选股策略解析器。用户会用自然语言描述选股策略，你需要将其解析为结构化的筛选条件。
返回格式必须是 JSON 数组，每个元素包含：
- condition: 条件描述（中文）
- field: 对应字段（pe/market_cap/turnover/change_pct/volume）
- operator: 运算符（lt/gt/eq）
- value: 数值
- feasible: 是否可执行（true/false）
- fallback: 如果不可执行，替代建议

可选字段说明：
- pe: 市盈率
- market_cap: 总市值（单位：亿）
- turnover: 换手率
- change_pct: 涨跌幅
- volume: 成交量

只返回 JSON 数组，不要其他文字。"""
        else:
            system_prompt = """你是一个股票买卖策略解析器。用户会用自然语言描述买卖纪律，你需要将其解析为结构化的交易规则。
返回格式必须是 JSON 数组，每个元素包含：
- condition: 条件描述（中文）
- signal: 信号类型（buy/sell）
- rule_type: 规则类型（ma_cross/ma_break/volume/macd/rsi）
- params: 参数对象
- feasible: 是否可执行（true/false）

只返回 JSON 数组，不要其他文字。"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.strategy_text}
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        import json
        result = json.loads(response.choices[0].message.content)
        return {"success": True, "data": result, "source": "llm"}
    except Exception as e:
        print(f"LLM error: {e}")
        return _fallback_clarify(req.strategy_text, req.type)


def _fallback_clarify(text: str, stype: str):
    """规则引擎兜底：解析策略文本"""
    conditions = []
    text_lower = text.lower()

    if stype == "screener":
        if "市盈率" in text or "pe" in text_lower:
            import re
            nums = re.findall(r'(\d+)', text)
            if nums:
                conditions.append({"condition": f"市盈率 < {nums[0]}", "field": "pe", "operator": "lt", "value": int(nums[0]), "feasible": True})
        if "市值" in text or "market" in text_lower:
            import re
            nums = re.findall(r'(\d+)亿', text)
            if nums:
                conditions.append({"condition": f"市值 > {nums[0]}亿", "field": "market_cap", "operator": "gt", "value": int(nums[0]), "feasible": True})
        if "换手" in text or "turnover" in text_lower:
            import re
            nums = re.findall(r'(\d+)', text)
            if nums:
                conditions.append({"condition": f"换手率 > {nums[0]}%", "field": "turnover", "operator": "gt", "value": float(nums[0]), "feasible": True})
        if not conditions:
            conditions.append({"condition": text, "field": "pe", "operator": "lt", "value": 20, "feasible": True, "note": "未识别到具体条件，使用默认PE<20"})
    else:
        if "均线" in text or "ma" in text_lower:
            conditions.append({"condition": "均线突破策略", "signal": "buy", "rule_type": "ma_break", "params": {"period": 20}, "feasible": True})
        if "macd" in text_lower:
            conditions.append({"condition": "MACD金叉买入", "signal": "buy", "rule_type": "macd", "params": {}, "feasible": True})
        if "成交量" in text or "放量" in text:
            conditions.append({"condition": "放量买入", "signal": "buy", "rule_type": "volume", "params": {"multiplier": 1.5}, "feasible": True})
        if not conditions:
            conditions.append({"condition": "默认均线策略", "signal": "buy", "rule_type": "ma_break", "params": {"period": 20}, "feasible": True})

    return {"success": True, "data": conditions, "source": "rule_engine"}


@app.post("/api/strategy/signal")
def api_signal(req: SignalRequest, db: Session = Depends(get_db)):
    """生成买卖信号"""
    # 获取K线数据
    kline_result = get_kline_data(req.code, "daily")
    if not kline_result["success"]:
        return {"success": False, "error": "无法获取K线数据"}

    # 获取方案内容
    plan = db.query(TradePlan).filter(TradePlan.id == req.plan_id).first()
    if not plan:
        return {"success": False, "error": "方案不存在"}

    signal = generate_signals(kline_result["data"], plan.content)
    return {"success": True, "signal": signal, "plan_name": plan.name}


@app.post("/api/strategy/backtest")
def api_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """执行策略回测"""
    results = []
    for code in req.codes:
        kline_result = get_kline_data(code, "daily", req.start_date.replace("-", ""), req.end_date.replace("-", ""))
        if not kline_result["success"]:
            results.append({"code": code, "success": False, "error": kline_result.get("error", "无数据")})
            continue

        for plan_id in req.plan_ids:
            plan = db.query(TradePlan).filter(TradePlan.id == plan_id).first()
            if not plan:
                continue
            bt_result = run_backtest(kline_result["data"], plan.content, req.initial_capital, req.fee_rate / 100)
            bt_result["code"] = code
            bt_result["plan_name"] = plan.name
            results.append(bt_result)

    return {"success": True, "data": results}


# ============================================================
# 自选股 API
# ============================================================
@app.get("/api/watchlist")
def api_watchlist(db: Session = Depends(get_db)):
    """获取自选股列表"""
    stocks = db.query(WatchlistStock).all()
    return {"success": True, "data": [{"code": s.code, "name": s.name, "group": s.group, "added_at": s.added_at} for s in stocks]}


@app.post("/api/watchlist/add")
def api_watchlist_add(req: WatchlistAdd, db: Session = Depends(get_db)):
    """添加自选股"""
    existing = db.query(WatchlistStock).filter(WatchlistStock.code == req.code).first()
    if existing:
        return {"success": False, "error": "已在自选股中"}
    stock = WatchlistStock(code=req.code, name=req.name, group=req.group)
    db.add(stock)
    db.commit()
    return {"success": True}


@app.delete("/api/watchlist/{code}")
def api_watchlist_delete(code: str, db: Session = Depends(get_db)):
    """删除自选股"""
    db.query(WatchlistStock).filter(WatchlistStock.code == code).delete()
    db.commit()
    return {"success": True}


# ============================================================
# 交易日志 API
# ============================================================
@app.get("/api/tradelogs")
def api_tradelogs(db: Session = Depends(get_db)):
    """获取所有交易记录"""
    logs = db.query(TradeLog).order_by(TradeLog.time.desc()).all()
    return {"success": True, "data": [{
        "id": l.id, "stock": l.stock, "direction": l.direction,
        "price": l.price, "qty": l.qty, "amount": l.amount,
        "fee": l.fee, "time": l.time, "note": l.note, "profit": l.profit
    } for l in logs]}


@app.post("/api/tradelogs")
def api_tradelogs_create(req: TradeLogCreate, db: Session = Depends(get_db)):
    """新增交易记录"""
    log = TradeLog(**req.dict())
    db.add(log)
    db.commit()
    return {"success": True}


@app.put("/api/tradelogs/{log_id}")
def api_tradelogs_update(log_id: str, req: TradeLogCreate, db: Session = Depends(get_db)):
    """更新交易记录"""
    log = db.query(TradeLog).filter(TradeLog.id == log_id).first()
    if not log:
        return {"success": False, "error": "记录不存在"}
    for key, value in req.dict().items():
        setattr(log, key, value)
    db.commit()
    return {"success": True}


@app.delete("/api/tradelogs/{log_id}")
def api_tradelogs_delete(log_id: str, db: Session = Depends(get_db)):
    """删除交易记录"""
    db.query(TradeLog).filter(TradeLog.id == log_id).delete()
    db.commit()
    return {"success": True}


# ============================================================
# 交易方案 API
# ============================================================
@app.get("/api/plans")
def api_plans(db: Session = Depends(get_db)):
    """获取所有方案"""
    plans = db.query(TradePlan).all()
    return {"success": True, "data": [{
        "id": p.id, "name": p.name, "content": p.content,
        "enabled": p.enabled, "created_at": p.created_at
    } for p in plans]}


@app.post("/api/plans")
def api_plans_create(req: TradePlanCreate, db: Session = Depends(get_db)):
    """新增方案"""
    plan = TradePlan(**req.dict())
    db.add(plan)
    db.commit()
    return {"success": True}


@app.put("/api/plans/{plan_id}")
def api_plans_update(plan_id: str, req: TradePlanCreate, db: Session = Depends(get_db)):
    """更新方案"""
    plan = db.query(TradePlan).filter(TradePlan.id == plan_id).first()
    if not plan:
        return {"success": False, "error": "方案不存在"}
    for key, value in req.dict().items():
        setattr(plan, key, value)
    db.commit()
    return {"success": True}


@app.delete("/api/plans/{plan_id}")
def api_plans_delete(plan_id: str, db: Session = Depends(get_db)):
    """删除方案"""
    db.query(TradePlan).filter(TradePlan.id == plan_id).delete()
    db.commit()
    return {"success": True}


@app.put("/api/plans/{plan_id}/toggle")
def api_plans_toggle(plan_id: str, db: Session = Depends(get_db)):
    """切换方案启用状态"""
    plan = db.query(TradePlan).filter(TradePlan.id == plan_id).first()
    if not plan:
        return {"success": False, "error": "方案不存在"}
    plan.enabled = not plan.enabled
    db.commit()
    return {"success": True, "enabled": plan.enabled}


# ============================================================
# 健康检查
# ============================================================
@app.get("/api/health")
def api_health():
    return {"status": "ok", "version": "2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))