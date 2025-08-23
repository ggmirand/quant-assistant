import os
from dotenv import load_dotenv
load_dotenv()
MOCK_MODE = os.getenv("MOCK_MODE","1") == "1"
ALPHA_KEY   = os.getenv("ALPHAVANTAGE_API_KEY","")
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY","")
POLYGON_KEY = os.getenv("POLYGON_API_KEY","")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN","")
SNAPTRADE_CLIENT_ID = os.getenv("SNAPTRADE_CLIENT_ID","")
SNAPTRADE_CLIENT_SECRET = os.getenv("SNAPTRADE_CLIENT_SECRET","")
SNAPTRADE_REDIRECT_URI = os.getenv("SNAPTRADE_REDIRECT_URI","")
RHC_API_BASE = os.getenv("RHC_API_BASE","")
RHC_API_KEY_ID = os.getenv("RHC_API_KEY_ID","")
RHC_API_SECRET = os.getenv("RHC_API_SECRET","")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS","120"))
