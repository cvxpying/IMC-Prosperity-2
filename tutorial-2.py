from datamodel import OrderDepth, TradingState, Position, Order, Product
from typing import List, Dict


class StrategyAmethysts:
    """
    Market making strategy for Amethysts with fixed fair value.
    Sub-Strategy 1: Scratch by market taking for free lunch
    Sub-Strategy 2: Stop loss if inventory piles over certain level
    Sub-Strategy 3: Market Make
    """

    SYMBOL = "AMETHYSTS"
    PRODUCT = "AMETHYSTS"
    FAIR_VALUE = 10000
    POSITION_LIMIT = 20
    SL_INVENTORY = 0  # acceptable inventory range
    SL_SPREAD = 2  # stop loss within this spread
    MM_SPREAD = 4  # market make with spread no smaller than this

    def __init__(self, state: TradingState):
        self.order_depth = state.order_depths[self.SYMBOL] if self.SYMBOL in state.order_depths else {}
        self.bids = self.order_depth.buy_orders if self.order_depth else {}
        self.asks = self.order_depth.sell_orders if self.order_depth else {}
        self.position = state.position[self.PRODUCT] if self.PRODUCT in state.position else 0
        self.best_bid = max(self.bids.keys())
        self.best_ask = min(self.asks.keys())
        self.expected_position = self.position  # expected position if all orders are filled
        self.orders: List[Order] = []

    def scratch_under_valued(self):
        """
        Scratch any under-valued or par-valued orders by aggressing against bots
        """
        # this opportunity only occurs for best bid and best ask
        if self.position <= self.SL_INVENTORY and self.best_bid >= self.FAIR_VALUE:
            # trade (sell) against bots trying to buy too expensive
            order_quantity = min(max(-self.bids[self.best_bid], -self.POSITION_LIMIT - self.expected_position), 0)
            self.orders.append(Order(self.SYMBOL, self.best_bid, order_quantity))
            self.expected_position += order_quantity
            print(f"Scratch Sell {order_quantity} X @ {self.best_bid}")
        elif self.position >= -self.SL_INVENTORY and self.best_ask <= self.FAIR_VALUE:
            # trade (buy) against bots trying to sell to cheap
            order_quantity = max(min(-self.asks[self.best_ask], self.POSITION_LIMIT - self.expected_position), 0)
            self.orders.append(Order(self.SYMBOL, self.best_ask, order_quantity))
            self.expected_position += order_quantity
            print(f"Scratch Buy {order_quantity} X @ {self.best_ask}")
        else:
            pass

    def stop_loss(self):
        """
        Stop loss when inventory over acceptable level
        """
        if self.position > self.SL_INVENTORY and self.best_bid >= self.FAIR_VALUE - self.SL_SPREAD:
            # stop loss sell not too cheap when in long position over acceptable inventory
            for price, quantity in enumerate(self.bids):
                if price >= self.FAIR_VALUE - self.SL_SPREAD and self.expected_position < -self.POSITION_LIMIT:
                    order_quantity = min(max(-quantity, -self.POSITION_LIMIT - self.expected_position), 0)
                    self.orders.append(Order(self.SYMBOL, price, order_quantity))
                    self.expected_position += order_quantity
                    print(f"Stop Loss Sell {order_quantity} X @ {price}")
        elif self.position < -self.SL_INVENTORY and self.best_ask <= self.FAIR_VALUE + self.SL_SPREAD:
            # stop loss buy not too expensive when in short position over acceptable inventory
            for price, quantity in enumerate(self.asks):
                if price <= self.FAIR_VALUE + self.SL_SPREAD and self.expected_position > -self.POSITION_LIMIT:
                    order_quantity = max(min(-quantity, self.POSITION_LIMIT - self.expected_position), 0)
                    self.orders.append(Order(self.SYMBOL, price, order_quantity))
                    self.expected_position += order_quantity
                    print(f"Stop Loss Buy {order_quantity} X @ {price}")

    def market_make(self):
        """
        Market make with fixed spread around fair value
        """
        bid_quantity = max(min(self.POSITION_LIMIT, self.POSITION_LIMIT - self.expected_position), 0)
        ask_quantity = min(max(-self.POSITION_LIMIT, -self.POSITION_LIMIT - self.expected_position), 0)
        bid_price = self.FAIR_VALUE - self.MM_SPREAD
        ask_price = self.FAIR_VALUE + self.MM_SPREAD
        self.orders.append(Order(self.SYMBOL, bid_price, bid_quantity))
        self.orders.append(Order(self.SYMBOL, ask_price, ask_quantity))
        print(f"Market Make Bid {bid_quantity} X @ {bid_price} Ask {ask_quantity} X @ {ask_quantity}")

    def aggregate_orders(self) -> List[Order]:
        """
        Aggregate all orders from various strategies

        :rtype: List[Order]
        :return: List of orders generated for product Amethysts
        """
        self.scratch_under_valued()
        self.stop_loss()
        self.market_make()
        return self.orders


class Trader:
    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData = "SAMPLE"

        # Symbol 1: AMETHYSTS (Fixed Fair Value Market Making)
        strategy_amethysts = StrategyAmethysts(state)
        result["AMETHYSTS"] = strategy_amethysts.aggregate_orders()

        return result, conversions, traderData
