import MetaTrader5 as mt5

mt5.initialize()

def get_gold_price():

    tick = mt5.symbol_info_tick("XAUUSD")

    if tick is None:
        return None

    return tick.bid

def place_buy_order():

    request = {

        "action": mt5.TRADE_ACTION_DEAL,

        "symbol": "XAUUSD",

        "volume": 0.01,

        "type": mt5.ORDER_TYPE_BUY,

        "price": mt5.symbol_info_tick("XAUUSD").ask,

        "deviation": 20,

        "magic": 100,

        "comment": "AI GOLD BUY",

        "type_time": mt5.ORDER_TIME_GTC,

        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    return result