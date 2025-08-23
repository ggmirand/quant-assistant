from __future__ import annotations
import datetime as dt, random, pandas as pd
def sector_performance():
    now = dt.datetime.utcnow().isoformat()
    return {"Meta Data":{"Last Refreshed":now},
            "Rank A: Real-Time Performance":{"Information Technology":"1.23%","Health Care":"0.88%","Financials":"0.65%","Energy":"-0.12%"}}
def top_gainers_losers():
    return {"top_gainers":[{"ticker":"MOCK","price":"100.0","change_amount":"+5.0","change_percentage":"+5.26%"}],
            "top_losers":[{"ticker":"FAKE","price":"50.0","change_amount":"-3.0","change_percentage":"-5.66%"}],
            "most_actively_traded":[{"ticker":"TEST","price":"25.0","change_amount":"+0.5","change_percentage":"+2.04%"}]}
def daily_series(symbol: str):
    n=160; dates = pd.bdate_range(end=dt.date.today(), periods=n); price=100.0; closes=[]; vols=[]
    for _ in range(n):
        price *= (1+random.uniform(-0.02,0.02)); closes.append(price); vols.append(random.randint(5e5,5e6))
    return pd.DataFrame({"date":dates, "adj_close":closes, "volume":vols})
