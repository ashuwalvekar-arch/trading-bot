import MetaTrader5 as mt5

SYMBOL = "GOLD.i#"

def connect_mt5():

    if not mt5.initialize():

        print("MT5 FAILED")

        return False

    print("MT5 Connected")

    return True


def execute_trade(signal):

    symbol = SYMBOL

    tick = mt5.symbol_info_tick(symbol)

    if tick is None:

        return "NO TICK DATA"

    order_type = mt5.ORDER_TYPE_BUY
    price = tick.ask

    if signal["signal"] == "SELL":

        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    request = {

        "action": mt5.TRADE_ACTION_DEAL,

        "symbol": symbol,

        "volume": 0.01,

        "type": order_type,

        "price": price,

        "sl": signal["sl"],

        "tp": signal["tp"],

        "deviation": 20,

        "magic": 100,

        "comment": "AI GOLD TRADE",

        "type_time": mt5.ORDER_TIME_GTC,

        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    return str(result)