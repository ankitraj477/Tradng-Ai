import sys
sys.path.insert(0, ".")
from app.data.yfinance_provider import YFinanceProvider
from app.fno.index_chain import IndexChainManager

provider = YFinanceProvider()
chain = IndexChainManager(provider)
print("BANKNIFTY spot:", chain.get_spot_price("BANKNIFTY"))
print("NIFTY spot:", chain.get_spot_price("NIFTY"))
