import math
import statistics
from typing import List, Dict
from collections import deque, OrderedDict

from datamodel import TradingState, Order, Symbol, Product, Position


class StrategyMarketMaking:
    """
    Market making strategy with fair value.
    Sub-Strategy 1: Scratch by market taking for under / par valued orders
    Sub-Strategy 2: Stop loss if inventory piles over certain level
    Sub-Strategy 3: Market make around fair value with inventory management
    """

    def __init__(self, state: TradingState,
                 symbol: Symbol, product: Product, position_limit: Position, fair_value: float,
                 sl_inventory: Position, sl_spread: int, mm_spread: int, order_skew: float):

        # product configuration
        self.symbol = symbol  # used as key of order_depths dictionary
        self.product = product  # used as key of position dictionary
        self.position_limit = position_limit  # max and min position limit
        self.fair_value = fair_value  # initial fair value given in the video

        # extract information from TradingState
        self.timestamp = state.timestamp
        self.bids = OrderedDict(state.order_depths[self.symbol].buy_orders)
        self.asks = OrderedDict(state.order_depths[self.symbol].sell_orders)
        self.position = state.position.get(self.product, 0)  # prevent KeyError if no position
        self.best_bid = max(self.bids.keys())
        self.best_ask = min(self.asks.keys())

        # strategy configuration
        self.sl_inventory = sl_inventory  # acceptable inventory range
        self.sl_spread = sl_spread  # acceptable spread to take for stop loss
        self.mm_spread = mm_spread  # spread for market making
        self.order_skew = order_skew  # extra skewing order quantity when market making

        # initialize variables for orders
        self.orders: List[Order] = []  # append orders for this product here
        self.expected_position = self.position  # expected position after market taking
        self.sum_buy_qty = 0  # check whether if buy order exceeds limit
        self.sum_sell_qty = 0  # check whether if buy order exceeds limit

    def scratch_under_valued(self):
        """
        Scratch any under-valued or par-valued orders by aggressing against bots
        """

        if -self.sl_inventory <= self.position <= self.sl_inventory:
            # use this strategy only when position is within stop loss inventory level
            if self.best_bid >= self.fair_value and len(self.bids) >= 2:
                # trade (sell) against bots trying to buy too expensive but not against worst bid
                order_quantity = min(max(-self.bids[self.best_bid],
                                         -self.position_limit - min(self.position, 0)), 0)
                self.orders.append(Order(self.symbol, self.best_bid, order_quantity))
                self.expected_position += order_quantity
                self.sum_sell_qty += order_quantity
                print(f"Scratch Sell {order_quantity} X @ {self.best_bid}")

            elif self.best_ask <= self.fair_value and len(self.asks) >= 2:
                # trade (buy) against bots trying to sell to cheap but not against worst ask
                order_quantity = max(min(-self.asks[self.best_ask],
                                         self.position_limit - max(self.position, 0)), 0)
                self.orders.append(Order(self.symbol, self.best_ask, order_quantity))
                self.expected_position += order_quantity
                self.sum_buy_qty += order_quantity
                print(f"Scratch Buy {order_quantity} X @ {self.best_ask}")

    def stop_loss(self):
        """
        Stop loss when inventory over acceptable level
        """
        if self.position > self.sl_inventory and self.best_bid >= self.fair_value - self.sl_spread:
            # stop loss sell not too cheap when in long position over acceptable inventory
            if len(self.bids) >= 2:
                # do not take worst bid which is also best bid
                order_quantity = max(-self.bids[self.best_bid], -self.position + self.sl_inventory)
                self.orders.append(Order(self.symbol, self.best_bid, order_quantity))
                self.expected_position += order_quantity
                self.sum_sell_qty += order_quantity
                print(f"Stop Loss Sell {order_quantity} X @ {self.best_bid}")

        elif self.position < -self.sl_inventory and self.best_ask <= self.fair_value + self.sl_spread:
            # stop loss buy not too expensive when in short position over acceptable inventory
            if len(self.asks) >= 2:
                # do not take worst ask which is also best ask
                order_quantity = min(-self.asks[self.best_ask], -self.position - self.sl_inventory)
                self.orders.append(Order(self.symbol, self.best_ask, order_quantity))
                self.expected_position += order_quantity
                self.sum_buy_qty += order_quantity
                print(f"Stop Loss Buy {order_quantity} X @ {self.best_ask}")

    def market_make(self):
        """
        Market make with fixed spread around fair value
        """
        # for limit consider position, expected position and single-sided aggregate
        bid_limit = max(min(self.position_limit,
                            self.position_limit - self.position,
                            self.position_limit - self.expected_position,
                            self.position_limit - self.sum_buy_qty - self.position), 0)
        ask_limit = min(max(-self.position_limit,
                            -self.position_limit - self.position,
                            -self.position_limit - self.expected_position,
                            -self.position_limit - self.sum_sell_qty - self.position), 0)

        # natural order skew due to limit + extra skewing to prevent further adverse selection
        bid_skew = math.ceil(self.order_skew * max(self.expected_position, 0))
        ask_skew = math.floor(self.order_skew * min(self.expected_position, 0))
        bid_quantity = min(max(bid_limit - bid_skew, 0), bid_limit)
        ask_quantity = max(min(ask_limit - ask_skew, 0), ask_limit)

        # determine price for market making using fair value as reserve price
        bid_price = math.ceil(self.fair_value - self.mm_spread)
        ask_price = math.floor(self.fair_value + self.mm_spread)
        self.orders.append(Order(self.symbol, bid_price, bid_quantity))
        self.orders.append(Order(self.symbol, ask_price, ask_quantity))
        print(f"Market Make Bid {bid_quantity} X @ {bid_price} Ask {ask_quantity} X @ {ask_price}")

    def aggregate_orders(self) -> List[Order]:
        """
        Aggregate all orders from all sub strategies under market making

        :rtype: List[Order]
        :return: List of orders generated for product Amethysts
        """

        print(f"{self.symbol} Position {self.position}")
        self.scratch_under_valued()
        self.stop_loss()
        self.market_make()
        return self.orders


class StrategyAmethysts(StrategyMarketMaking):
    """
    Use fixed fair value for market making strategy of Amethysts
    """
    # product configuration
    SYMBOL = "AMETHYSTS"
    PRODUCT = "AMETHYSTS"
    FAIR_VALUE = 10000.0
    POSITION_LIMIT = 20

    # strategy configuration
    SL_INVENTORY = 20
    SL_SPREAD = 1
    MM_SPREAD = 2
    ORDER_SKEW = 1.0

    def __init__(self, state: TradingState):
        # Overload all instance variable from StrategyMarketMaking
        super().__init__(state,
                         self.SYMBOL, self.PRODUCT, self.POSITION_LIMIT, self.FAIR_VALUE,
                         self.SL_INVENTORY, self.SL_SPREAD, self.MM_SPREAD, self.ORDER_SKEW)


class StrategyStarfruit(StrategyMarketMaking):
    """
    Use linear regression as fair value for market making strategy of Starfruit
    """
    # product configuration
    SYMBOL = "STARFRUIT"
    PRODUCT = "STARFRUIT"
    FAIR_VALUE = 5000.0
    POSITION_LIMIT = 20

    # strategy configuration
    SL_INVENTORY = 10
    SL_SPREAD = 1
    MM_SPREAD = 2
    ORDER_SKEW = 1.0

    # regression configuration
    MIN_WINDOW_SIZE = 5  # min rolling window for regression
    MAX_WINDOW_SIZE = 10  # min rolling window for regression
    PREDICT_SHIFT = 1  # predict target timestamp shift

    def __init__(self, state: TradingState):
        # Overload all instance variable from StrategyMarketMaking
        super().__init__(state,
                         self.SYMBOL, self.PRODUCT, self.POSITION_LIMIT, self.FAIR_VALUE,
                         self.SL_INVENTORY, self.SL_SPREAD, self.MM_SPREAD, self.ORDER_SKEW)

        # volume weighted average price (vwap) for bid, ask, and mid for de-noising
        self.bid_vwap = sum(p * q for p, q in self.bids.items()) / sum(self.bids.values())
        self.ask_vwap = sum(p * q for p, q in self.asks.items()) / sum(self.asks.values())
        self.mid_vwap = (self.bid_vwap + self.ask_vwap) / 2

    def predict_price(self, price_history: deque):
        """
        Predict price value after n timestamp shift with linear regression and update fair value

        :param price_history: (deque) Array of historical prices
        """
        n = len(price_history)
        if n >= self.MIN_WINDOW_SIZE:
            t = int(self.timestamp / 100)
            xs = [100 * i for i in range(t - n + 1, t + 1)]
            ys = list(price_history)
            slope, intercept = statistics.linear_regression(xs, ys)
            y_hat = slope * (self.timestamp + 100 * self.PREDICT_SHIFT) + intercept
            self.fair_value = y_hat
        else:
            self.fair_value = self.mid_vwap


class Trader:
    data = {'STARFRUIT': deque()}

    def data_starfruit(self, strategy_state: StrategyStarfruit):
        """
        Store new mid vwap data for Starfruit to class variable as queue

        :param strategy_state: (StrategyStarfruit) Strategy class for Starfruit
        """
        mid_vwap = strategy_state.mid_vwap
        while len(self.data[strategy_state.SYMBOL]) >= strategy_state.MAX_WINDOW_SIZE:
            self.data[strategy_state.SYMBOL].popleft()
        self.data[strategy_state.SYMBOL].append(mid_vwap)

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData = "SAMPLE"

        # Round 1: AMETHYSTS and STARFRUIT (Market Making)
        # Symbol 1: AMETHYSTS (Fixed Fair Value Market Making)
        strategy_amethysts = StrategyAmethysts(state)
        result["AMETHYSTS"] = strategy_amethysts.aggregate_orders()

        # Symbol 2: STARFRUIT (Linear Regression Market Making)
        strategy_starfruit = StrategyStarfruit(state)
        self.data_starfruit(strategy_starfruit)  # update data
        strategy_starfruit.predict_price(self.data['STARFRUIT'])  # update fair value
        result["STARFRUIT"] = strategy_starfruit.aggregate_orders()

        return result, conversions, traderData
