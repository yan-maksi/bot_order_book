import os
import json
from datetime import datetime

import asyncio
import websockets

from asynchronous_logging import TableLogger
from find_big_pull_fo_quantity import find_quantity
from post_binance_orders import open_order, update_trailing_stop
from consts import MAX_DEPTH_OF_ORDER_BOOK, LOWEST_QUANTITY, ORDER_BOOK_DEPTH20_100MS_ENDPOINT, \
    TRAILING_STOP_GAP, FIRST_PRICE, LOW_VOLUME, DEPTH_TYPE, LARGE_POSITION_INDEX_IN_DEPTH, PRICE, \
    FIRST_LIMIT_PRICE_WITH_QUANTITY, MINIMUM_PRICE_CHANGE_TO_LONG, MINIMUM_PRICE_CHANGE_TO_SHORT, \
    SECOND_LIMIT_PRICE_WITH_QUANTITY

API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')


class SocketConn:
    def __init__(self, url):
        self.url = url
        self.websocket = None

    async def on_open(self):
        print(f"Websocket for {self.url} was opened")

    async def on_error(self, error):
        print(f"Error from {self.url}: {error}")

    async def on_close(self, close_status):
        print(f"Closing {self.url} and close_status is: {close_status}")

    async def connect_to_stream(self):
        try:
            while True:
                async with websockets.connect(self.url, ping_timeout=None) as websocket:
                    self.websocket = websocket
                    await self.on_open()
                    async for message in websocket:
                        dl = DataElaboration(websocket=websocket, message=message)
                        await dl.handle_depth_data()

        except Exception as e:
            await self.on_error(e)

    async def stop(self):
        self.websocket.close()


class DataElaboration:
    def __init__(self, websocket, message):
        self.ask_bid = None
        self.websocket = websocket
        self.depth_data = json.loads(message)

    async def handle_depth_data(self):
        # Implement your logic to determine weak sides and strong sides
        # Assuming you want to work with the latest N data points
        ask_quantity = [float(quantity) for price, quantity in self.depth_data['a']]
        bid_quantity = [float(quantity) for price, quantity in self.depth_data['b']]

        # Apply your logic to decide if buyers or sellers are stronger
        if sum(bid_quantity) / MAX_DEPTH_OF_ORDER_BOOK > sum(ask_quantity) / MAX_DEPTH_OF_ORDER_BOOK:
            self.ask_bid = 'a'
            await self.check_order_book_density(bid_ask_quantity=ask_quantity)

        elif sum(bid_quantity) / MAX_DEPTH_OF_ORDER_BOOK < sum(ask_quantity) / MAX_DEPTH_OF_ORDER_BOOK:
            self.ask_bid = 'b'
            await self.check_order_book_density(bid_ask_quantity=bid_quantity)

    async def check_order_book_density(self, bid_ask_quantity):
        # result -> (2, {"index_in_list": "quantity"}) *tuple
        result: tuple = await find_quantity(ask_bid_quantity=bid_ask_quantity, lowest_quantity=LOWEST_QUANTITY)
        # parse of all situations from result
        result_type: int = result[DEPTH_TYPE]
        result_dict: dict = result[LARGE_POSITION_INDEX_IN_DEPTH]
        # check if Average value is less than index 5 -> False else True
        average_value = result_dict is not None and not any(key < 6 for key in result_dict.keys())

        if result_type == 1:
            if bid_ask_quantity[FIRST_PRICE] <= LOW_VOLUME:
                await self.open_position()

        elif result_type == 2:
            if average_value is True and bid_ask_quantity[FIRST_PRICE] <= LOW_VOLUME:
                await self.open_position()

        elif result_type == 3:
            avr_value = not any(key < 8 for key in result_dict.keys())
            if avr_value is True and bid_ask_quantity[FIRST_PRICE] <= LOW_VOLUME:
                await self.open_position()

    async def open_position(self):
        # get second limit price, because we need to open position when buy up the main quantity
        entry_price = float(self.depth_data[self.ask_bid][FIRST_LIMIT_PRICE_WITH_QUANTITY][PRICE])
        print(entry_price)
        # logger.log_value("entry_price", entry_price)

        # open short / long order
        await open_order(order_metadata={"side": "SELL", "entry_price": entry_price}, order_type="new_order")

        stop_loss_price = float(self.depth_data["a" if self.ask_bid == "a" else "b"][SECOND_LIMIT_PRICE_WITH_QUANTITY][PRICE])
        stop_order_metadata = await open_order(order_metadata={"side": "BUY" if self.ask_bid == "b" else "SELL", "stop_loss_price": stop_loss_price},
                                               order_type="stop_loss_order")

        logger.log_value({"stop_loss_price": stop_loss_price, "opening_side": "short",
                          "open_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})
        print(f'open_position_to: short, entry_price: {entry_price}, stop_loss_price: {stop_loss_price}')
        manager = TrailingStopLossManager(websocket=self.websocket,
                                          stop_loss_side="a" if self.ask_bid == "a" else "b",
                                          entry_price=entry_price)
        await manager.set_trailing_stop_loss(stop_loss_price=stop_loss_price, stop_order_metadata=stop_order_metadata)


class TrailingStopLossManager:
    def __init__(self, websocket, stop_loss_side, entry_price):
        self.websocket = websocket
        self.stop_loss_side = stop_loss_side
        self.entry_price = entry_price

    async def set_trailing_stop_loss(self, stop_loss_price, stop_order_metadata):
        price_data = []
        stop_loss_price_data = []
        previous_price = self.entry_price
        current_stop_loss_price = stop_loss_price

        async def should_update_trailing_stop(current_price, previous_price):
            price_change = current_price - previous_price
            threshold = TRAILING_STOP_GAP + (MINIMUM_PRICE_CHANGE_TO_LONG if self.stop_loss_side == "b" else MINIMUM_PRICE_CHANGE_TO_SHORT)
            return price_change >= threshold

        async def should_close_position(current_price):
            return self.entry_price == current_stop_loss_price or (current_price <= current_stop_loss_price if self.stop_loss_side == "b" else current_price >= current_stop_loss_price)

        while True:
            market_depth_data = await self.websocket.recv()
            current_coin_price = float(json.loads(market_depth_data)[self.stop_loss_side][FIRST_LIMIT_PRICE_WITH_QUANTITY][PRICE])
            price_data.append(current_coin_price)

            if await should_update_trailing_stop(current_coin_price, previous_price):
                new_stop_price = current_coin_price - TRAILING_STOP_GAP if self.stop_loss_side == "b" else current_coin_price + TRAILING_STOP_GAP
                stop_order_metadata, previous_price = await update_trailing_stop(new_stop_price,
                                                                                 stop_order_metadata,
                                                                                 current_coin_price,
                                                                                 "SELL" if self.stop_loss_side == "b" else "BUY")
                stop_loss_price_data.append(current_stop_loss_price)

            elif await should_close_position(current_coin_price):
                print(f'CLOSE_POSITION_AT: {current_coin_price}')
                logger.log_value({"stop_loss_price_data": stop_loss_price_data,
                                  "price_data": price_data,
                                  "current_coin_price_before_close_position": current_coin_price,
                                  "close_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")})
                break


if __name__ == "__main__":
    COIN_SYMBOL, QUANTITY = 'BTCUSDT', '0.005'
    logger_columns = ['entry_price', 'stop_loss_price', 'stop_loss_price_data', 'current_coin_price_before_close_position',
                      'opening_side', 'price_data', 'open_time', 'close_time']
    logger = TableLogger(filename='async.log', columns=logger_columns)
    conn = SocketConn(ORDER_BOOK_DEPTH20_100MS_ENDPOINT)
    asyncio.get_event_loop().run_until_complete(conn.connect_to_stream())
