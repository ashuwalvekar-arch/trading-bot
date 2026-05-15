import MetaTrader5 as mt5

print("Starting MT5 test...")

if not mt5.initialize():

    print("MT5 initialize failed")

    print(mt5.last_error())

else:

    print("MT5 Connected Successfully")

    account = mt5.account_info()

    print(account)

    mt5.shutdown()