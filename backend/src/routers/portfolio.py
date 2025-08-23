from fastapi import APIRouter, Query
router = APIRouter()
@router.get("/connect-link")
def connect_link(user_id: str = Query(..., description="Your internal user id")):
    return {"mock": True, "url": "https://mock.connect/snaptrade/robinhood", "userId": user_id}
@router.get("/holdings")
def holdings(user_id: str):
    return {"mock": True, "holdings":[{"symbol":"AAPL","quantity":10},{"symbol":"NVDA","quantity":2}]}
