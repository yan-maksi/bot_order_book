import hmac
import time
import httpx
import hashlib
import requests

from consts import OPEN_ORDER_ENDPOINT
from main import API_KEY, API_SECRET, QUANTITY, COIN_SYMBOL


async def update_trailing_stop(potential_new_stop_loss, new_stop_order_id, current_coin_price, side):
    """
    update trailing stop price
    :return:
        new_stop_order_id: new id of stop loss order
        previous_price: previous coin price
    """
    new_stop_loss_price = round(potential_new_stop_loss, 4)

    await delete_previous_stop_loss(coin_symbol=COIN_SYMBOL, orderId=new_stop_order_id["orderId"])
    new_stop_order_id = await open_order(
        order_metadata={"side": side, "stop_loss_price": new_stop_loss_price},
        order_type="stop_loss_order")

    previous_price = current_coin_price
    print(f"current_coin_price: {current_coin_price}, new_stop_loss_price: {new_stop_loss_price}")
    return new_stop_order_id, previous_price


async def open_order(order_metadata: dict, order_type: str) -> dict:
    """
    :param order_metadata: metadata about open order
    :param order_type: BUY / SELL
    :return: metadata about order
    """

    order_query_string = None

    # post stop loss order
    if order_type == "stop_loss_order":
        order_query_string = f'symbol={COIN_SYMBOL}&side={order_metadata["side"]}&type=STOP_MARKET&quantity={QUANTITY}&' \
                             f'stopPrice={order_metadata["stop_loss_price"]}&timestamp={int(time.time() * 1000)}'
    # post new order
    elif order_type == "new_order":
        order_query_string = f'symbol={COIN_SYMBOL}&side={order_metadata["side"]}&type=LIMIT&timeInForce=GTC&' \
                             f'quantity={QUANTITY}&price={order_metadata["entry_price"]}&' \
                             f'newOrderRespType=FULL&postOnly=true&' \
                             f'timestamp={int(time.time() * 1000)}'

    # Sign the query string
    signature = hmac.new(API_SECRET.encode('utf-8'), order_query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    # Send the POST request
    async with httpx.AsyncClient() as client:
        response = await client.post(OPEN_ORDER_ENDPOINT,
                                     headers={'X-MBX-APIKEY': API_KEY},
                                     data=f'{order_query_string}&signature={signature}')
        return response.json()


async def delete_previous_stop_loss(coin_symbol, orderId):
    # remove stop loss query string
    delete_stop_loss_query = f'symbol={coin_symbol}&orderId={orderId}&timestamp={int(time.time() * 1000)}'
    # sign the query string
    signature = hmac.new(API_SECRET.encode('utf-8'), delete_stop_loss_query.encode('utf-8'), hashlib.sha256).hexdigest()

    response = requests.delete(OPEN_ORDER_ENDPOINT,
                               headers={'X-MBX-APIKEY': API_KEY},
                               params=f'{delete_stop_loss_query}&signature={signature}')