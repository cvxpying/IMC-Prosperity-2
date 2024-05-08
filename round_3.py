import math
import statistics
from typing import List, Dict, Tuple, Any
from collections import deque, OrderedDict

import jsonpickle

from datamodel import *


class Strategy:
    """
    Base Class for Strategy Objects
    """
    def __init__(self, state: TradingState, product_config: dict):
        # product configuration
        self.symbol: Symbol = product_config['SYMBOL']
        self.product: Product = product_config['PRODUCT']
        self.position_limit: Position = product_config['POSITION_LIMIT']

        # extract information from TradingState
        self.timestamp = state.timestamp
        self.position = state.position.get(self.product, 0)

        # prevent reshuffling of order depth
        self.bids = OrderedDict(state.order_depths[self.symbol].buy_orders)
        self.asks = OrderedDict(state.order_depths[self.symbol].sell_orders)

        # build order book features
        self.best_bid = max(self.bids.keys())
        self.best_ask = min(self.asks.keys())
        self.worst_bid = min(self.bids.keys())
        self.worst_ask = max(self.asks.keys())
        self.bid_volume = sum(self.bids.values())  # sum of all quantities of bids
        self.ask_volume = sum(self.asks.values())
        self.bid_sweep = sum(p * q for p, q in self.bids.items())  # amount needed to sweep all bids
        self.ask_sweep = sum(p * q for p, q in self.asks.items())
        self.bid_vwap = self.bid_sweep / self.bid_volume  # volume weighted average price (vwap) of bids
        self.ask_vwap = self.ask_sweep / self.ask_volume
        self.mid_vwap = (self.bid_vwap + self.ask_vwap) / 2  # de-noised mid-price

        # initialize variables for orders
        self.orders: List[Order] = []  # append orders for this product here
        self.expected_position = self.position  # expected position after market taking
        self.sum_buy_qty = 0  # check whether if buy order exceeds limit
        self.sum_sell_qty = 0


class MarketMaking(Strategy):
    """
    Market making strategy with fair value.\n
    Sub-Strategy 1: Scratch by market taking for under / par valued orders\n
    Sub-Strategy 2: Stop loss if inventory piles over certain level\n
    Sub-Strategy 3: Market make around fair value with inventory management
    """
    def __init__(self, state: TradingState, product_config: dict, strategy_config: dict):
        super().__init__(state, product_config)

        # strategy configuration
        self.fair_value: float = strategy_config['FAIR_VALUE']  # initial or fixed fair value for market making
        self.sl_inventory: Position = strategy_config['SL_INVENTORY']  # acceptable inventory range
        self.sl_spread: int = strategy_config['SL_SPREAD']  # acceptable spread to take for stop loss
        self.mm_spread: int = strategy_config['MM_SPREAD']  # spread for market making
        self.order_skew: float = strategy_config['ORDER_SKEW']  # extra skewing order quantity when market making

    def scratch_under_valued(self, mid_vwap=False):
        """
        Scratch any under-valued or par-valued orders by aggressing against bots
        """
        reserve_price = self.mid_vwap if mid_vwap else self.fair_value
        if -self.sl_inventory <= self.position <= self.sl_inventory:
            # use this strategy only when position is within stop loss inventory level
            if self.best_bid >= reserve_price and len(self.bids) >= 2:
                # trade (sell) against bots trying to buy too expensive but not against worst bid
                order_quantity = min(max(-self.bids[self.best_bid],
                                         -self.position_limit - min(self.position, 0)), 0)
                self.orders.append(Order(self.symbol, self.best_bid, order_quantity))
                self.expected_position += order_quantity
                self.sum_sell_qty += order_quantity
                print(f"Scratch Sell {order_quantity} X @ {self.best_bid}")

            elif self.best_ask <= reserve_price and len(self.asks) >= 2:
                # trade (buy) against bots trying to sell to cheap but not against worst ask
                order_quantity = max(min(-self.asks[self.best_ask],
                                         self.position_limit - max(self.position, 0)), 0)
                self.orders.append(Order(self.symbol, self.best_ask, order_quantity))
                self.expected_position += order_quantity
                self.sum_buy_qty += order_quantity
                print(f"Scratch Buy {order_quantity} X @ {self.best_ask}")

    def stop_loss(self, ignore_worst=True):
        """
        Stop loss when inventory over acceptable level
        """
        if self.position > self.sl_inventory and self.best_bid >= self.fair_value - self.sl_spread:
            # stop loss sell not too cheap when in long position over acceptable inventory
            if len(self.bids) >= int(ignore_worst) + 1:
                # do not take worst bid which is also best bid if ignore worst
                order_quantity = max(-self.bids[self.best_bid], -self.position + self.sl_inventory)
                self.orders.append(Order(self.symbol, self.best_bid, order_quantity))
                self.expected_position += order_quantity
                self.sum_sell_qty += order_quantity
                print(f"Stop Loss Sell {order_quantity} X @ {self.best_bid}")

        elif self.position < -self.sl_inventory and self.best_ask <= self.fair_value + self.sl_spread:
            # stop loss buy not too expensive when in short position over acceptable inventory
            if len(self.asks) >= int(ignore_worst) + 1:
                # do not take worst ask which is also best ask if ignore worst
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

    def aggregate_orders(self, ignore_worst_sl=True) -> List[Order]:
        """
        Aggregate all orders from all sub strategies under market making

        :rtype: List[Order]
        :return: List of orders generated for product
        """
        print(f"{self.symbol} Position {self.position}")
        self.scratch_under_valued()
        self.stop_loss(ignore_worst_sl)
        self.market_make()
        return self.orders


class LinearRegressionMM(MarketMaking):
    """
    Market making based on prediction of price with simple linear regression of price over time
    """
    def __init__(self, state: TradingState,
                 product_config: dict, strategy_config: dict):
        super().__init__(state, product_config, strategy_config)

        # strategy configuration
        self.min_window_size = strategy_config['MIN_WINDOW_SIZE']
        self.max_window_size = strategy_config['MAX_WINDOW_SIZE']
        self.predict_shift = strategy_config['PREDICT_SHIFT']

    def predict_price(self, price_history: deque):
        """
        Predict price value after n timestamp shift with linear regression and update fair value

        :param price_history: (deque) Array of historical prices
        """
        n = len(price_history)
        if n >= self.min_window_size:
            t = int(self.timestamp / 100)
            xs = [100 * i for i in range(t - n + 1, t + 1)]
            ys = list(price_history)
            slope, intercept = statistics.linear_regression(xs, ys)
            y_hat = slope * (self.timestamp + 100 * self.predict_shift) + intercept
            self.fair_value = y_hat
        else:
            self.fair_value = self.mid_vwap


class OTCArbitrage(Strategy):
    """
    Arbitrage Between OTC and Exchange comparing with estimated fair value
    Sub-Strategy 1: Take orders from exchange which provide arbitrage opportunity
    Sub-Strategy 2: Market make so that we secure margin over arbitrage free pricing
    Sub-Strategy 3: Convert remaining position to exit arbitrage position
    """
    def __init__(self, state: TradingState,
                 product_config: dict, strategy_config: dict):
        super().__init__(state, product_config)
        self.unit_cost_storing = product_config['COST_STORING']

        # extract information from conversion observation
        self.observation = state.observations.conversionObservations[self.symbol]
        self.otc_bid = self.observation.bidPrice
        self.otc_ask = self.observation.askPrice
        self.cost_import = self.observation.transportFees + self.observation.importTariff
        self.cost_export = self.observation.transportFees + self.observation.exportTariff
        self.sunlight = self.observation.sunlight
        self.humidity = self.observation.humidity

        # initialize variables for conversions
        self.conversions = 0  # reset every timestamp

        # strategy configuration
        self.expected_storage_time = strategy_config['EXP_STORAGE_TIME']
        self.effective_cost_export = self.cost_export + self.expected_storage_time * self.unit_cost_storing
        self.min_edge = strategy_config['MIN_EDGE']  # only try market taking arbitrage over this edge
        self.mm_edge = strategy_config['MM_EDGE']  # edge added to arbitrage free pricing for market making

    def arbitrage_exchange_enter(self):
        """
        Long Arbitrage: take exchange good ask (buy) then take next otc bid (sell)\n
        Short Arbitrage: take exchange good bid (sell) then take next otc ask (buy)\n
        Note you pay export storing cost for long arb but only import cost for short arb
        """
        # calculate effective import and export cost then get arbitrage edge of each side
        long_arb_edge = self.otc_bid - self.best_ask - self.effective_cost_export
        short_arb_edge = self.best_bid - self.otc_ask - self.cost_import

        edges = {"Long": long_arb_edge, "Short": short_arb_edge}
        max_key = max(edges, key=lambda k: edges[k])  # choose best side
        if max_key == "Long" and edges[max_key] >= self.min_edge:
            for price, quantity in self.asks.items():
                if self.otc_bid - price - self.effective_cost_export >= self.min_edge:
                    order_quantity = max(min(-quantity,
                                             self.position_limit - max(self.expected_position, 0)), 0)
                    self.orders.append(Order(self.symbol, price, order_quantity))
                    print(f"{max_key} Arbitrage {order_quantity} X @ {self.best_ask}")
                    self.expected_position += order_quantity
                    self.sum_buy_qty += order_quantity
                else:
                    break
        elif max_key == "Short" and edges[max_key] >= self.min_edge:
            for price, quantity in self.bids.items():
                if price - self.otc_ask - self.cost_import >= self.min_edge:
                    order_quantity = min(max(-self.bids[self.best_bid],
                                             -self.position_limit - min(self.expected_position, 0)), 0)
                    self.orders.append(Order(self.symbol, self.best_bid, order_quantity))
                    print(f"{max_key} Arbitrage Enter {order_quantity} X @ {self.best_bid}")
                    self.expected_position += order_quantity
                    self.sum_sell_qty += order_quantity
                else:
                    break

    def market_make(self):
        """
        Make bid low enough to take bid (sell) arbitrage-freely in otc considering cost\n
        Make ask high enough to take ask (buy) arbitrage-freely in otc considering cost
        """
        # for limit consider position, expected position and single-sided aggregate
        bid_quantity = max(min(self.position_limit,
                               self.position_limit - self.position,
                               self.position_limit - self.expected_position,
                               self.position_limit - self.sum_buy_qty - self.position), 0)
        ask_quantity = min(max(-self.position_limit,
                               -self.position_limit - self.position,
                               -self.position_limit - self.expected_position,
                               -self.position_limit - self.sum_sell_qty - self.position), 0)

        # determine price for market making by adding edge to arbitrage free price
        bid_arb_free = self.otc_bid - self.effective_cost_export
        ask_arb_free = self.otc_ask + self.cost_import
        bid_price = math.floor(bid_arb_free - self.mm_edge)
        ask_price = math.ceil(ask_arb_free + self.mm_edge)
        self.orders.append(Order(self.symbol, bid_price, bid_quantity))
        self.orders.append(Order(self.symbol, ask_price, ask_quantity))
        print(f"Market Make Bid {bid_quantity} X @ {bid_price} Ask {ask_quantity} X @ {ask_price}")

    def arbitrage_otc_exit(self):
        """
        Exit position from arbitrage strategy by converting position in otc
        """
        self.conversions = -self.position
        if self.conversions > 0:
            print(f"Short Arbitrage Exit {self.conversions} X @ {self.otc_ask}")
        elif self.conversions < 0:
            print(f"Long Arbitrage Exit {self.conversions} X @ {self.otc_bid}")

    def aggregate_orders_conversions(self) -> Tuple[List[Order], int]:
        """
        Aggregate all orders from all sub strategies under OTC Arbitrage

        :rtype: List[Order]
        :return: List of orders generated for product
        """
        print(f"{self.symbol} Position {self.position}")
        self.arbitrage_exchange_enter()
        self.market_make()
        self.arbitrage_otc_exit()
        return self.orders, self.conversions


class BasketTrading:
    """
    Basket trading based on pricing with NAV of constituents\n
    Basket is traded alone in market making style but with pricing from constituent NAV\n
    Sub-Strategy 1: Calculate fair value considering spread between basket and NAV\n
    Sub-Strategy 2: Market make around fair value\n
    Sub-Strategy 3: Follow trends with constituents which provide smaller spread to take
    """
    def __init__(self, state: TradingState,
                 basket_config: dict, constituent_config: Dict[Symbol, dict], strategy_config: dict):
        # initialize basket and each constituent as Strategy Object
        self.basket = MarketMaking(state, basket_config, strategy_config)
        self.constituent = {symbol: Strategy(state, config) for symbol, config in constituent_config.items()}

        # configure basket information
        self.c_symbols = list(self.constituent.keys())
        self.c_ratios = {symbol: config['PER_BASKET'] for symbol, config in constituent_config.items()}
        self.c_limits = {symbol: strategy.position_limit for symbol, strategy in self.constituent.items()}
        self.c_mid_vwap = {symbol: strategy.mid_vwap for symbol, strategy in self.constituent.items()}
        self.c_w_bid = {symbol: strategy.worst_bid for symbol, strategy in self.constituent.items()}
        self.c_w_ask = {symbol: strategy.worst_ask for symbol, strategy in self.constituent.items()}
        self.c_positions = {symbol: strategy.position for symbol, strategy in self.constituent.items()}
        self.basket_limit = math.floor(min(self.c_limits[symbol] / self.c_ratios[symbol] for symbol in self.c_symbols))
        self.basket_limit = min(self.basket_limit, self.basket.position_limit)  # max basket constituent pairs

        # strategy configuration
        self.premium_mean = strategy_config['PREMIUM_MEAN']  # long-term mean premium of basket over constituents
        self.premium_std = strategy_config['PREMIUM_STD']  # long-term standard deviation of premium
        self.alpha = strategy_config['LINEAR_SENSITIVITY']  # sensitivity for linear term of z-score
        self.beta = strategy_config['QUADRATIC_SENSITIVITY']  # sensitivity for quadratic term of z-score
        self.sl_target = strategy_config['SL_TARGET']  # stop loss up to sl target position level
        self.carry = strategy_config['CARRY']  # amount of delta to carry for trend following
        self.basket.fair_value = self.basket.mid_vwap  # initialize
        self.basket.position_limit = self.basket_limit  # change to maximum possible

        # build basket features
        self.basket_nav = sum(self.c_ratios[symbol] * self.c_mid_vwap[symbol] for symbol in self.c_symbols)
        self.premium = self.basket.mid_vwap - self.basket_nav  # basket - constituent net asset value
        self.z_score = (self.premium - self.premium_mean) / self.premium_std  # z-score of premium

    def calculate_fair_value(self):
        """
        Calculate fair value of basket using the basket premium value and its z-score
        """
        demeaned_premium = self.premium - self.premium_mean  # center the variable with long term mean
        scaling_coefficient = self.alpha * abs(self.z_score) + self.beta * self.z_score ** 2
        pricing_shift = -demeaned_premium * scaling_coefficient  # premium is mean-reverting
        self.basket.fair_value = self.basket.fair_value + pricing_shift

    def aggressive_stop_loss(self):
        """
        Take aggressive stop loss to control inventory with stop loss trigger and target inventory level
        """
        if self.basket.position > self.basket.sl_inventory:
            # stop loss sell when too much positive inventory, sl up to sl target, max volume worst price
            order_quantity = max(-self.basket.bid_volume, self.sl_target - self.basket.position)
            order_price = self.basket.worst_bid
            self.basket.orders.append(Order(self.basket.symbol, order_price, order_quantity))
            self.basket.expected_position += order_quantity
            self.basket.sum_sell_qty += order_quantity
            print(f"Stop Loss Sell {order_quantity} X @ {order_price}")

        elif self.basket.position < -self.basket.sl_inventory:
            # stop buy sell when too much negative inventory, sl up to sl target, max volume worst price
            order_quantity = min(-self.basket.ask_volume, -self.sl_target - self.basket.position)
            order_price = self.basket.worst_ask
            self.basket.orders.append(Order(self.basket.symbol, order_price, order_quantity))
            self.basket.expected_position += order_quantity
            self.basket.sum_buy_qty += order_quantity
            print(f"Stop Loss Buy {order_quantity} X @ {order_price}")

    def aggregate_basket_orders(self) -> List[Order]:
        """
        Aggregate all orders from market making basket product

        :rtype: List[Order]
        :return: List of orders generated for product
        """
        print(f"{self.basket.symbol} Position {self.basket.position}")
        self.calculate_fair_value()
        self.basket.scratch_under_valued(mid_vwap=True)
        self.aggressive_stop_loss()
        self.basket.market_make()
        return self.basket.orders


class Trader:
    """
    Class containing data and sending and receiving data with the trading server
    """
    symbols = ['AMETHYSTS', 'STARFRUIT',  # Round 1
               'ORCHIDS',  # Round 2
               'GIFT_BASKET', 'CHOCOLATE', 'STRAWBERRIES', 'ROSES'  # Round 3
               ]
    data = {"STARFRUIT": deque()}
    config = {'PRODUCT': {'AMETHYSTS': {'SYMBOL': 'AMETHYSTS',
                                        'PRODUCT': 'AMETHYSTS',
                                        'POSITION_LIMIT': 20},
                          'STARFRUIT': {'SYMBOL': 'STARFRUIT',
                                        'PRODUCT': 'STARFRUIT',
                                        'POSITION_LIMIT': 20},
                          'ORCHIDS': {'SYMBOL': 'ORCHIDS',
                                      'PRODUCT': 'ORCHIDS',
                                      'POSITION_LIMIT': 100,
                                      'COST_STORING': 0.1},
                          'GIFT_BASKET': {'SYMBOL': 'GIFT_BASKET',
                                          'PRODUCT': 'GIFT_BASKET',
                                          'POSITION_LIMIT': 60},
                          'CHOCOLATE': {'SYMBOL': 'CHOCOLATE',
                                        'PRODUCT': 'CHOCOLATE',
                                        'POSITION_LIMIT': 250,
                                        'PER_BASKET': 4},
                          'STRAWBERRIES': {'SYMBOL': 'STRAWBERRIES',
                                           'PRODUCT': 'STRAWBERRIES',
                                           'POSITION_LIMIT': 350,
                                           'PER_BASKET': 6},
                          'ROSES': {'SYMBOL': 'ROSES',
                                    'PRODUCT': 'ROSES',
                                    'POSITION_LIMIT': 60,
                                    'PER_BASKET': 1}},
              'STRATEGY': {'AMETHYSTS': {'FAIR_VALUE': 10000.0,
                                         'SL_INVENTORY': 20,
                                         'SL_SPREAD': 1,
                                         'MM_SPREAD': 2,
                                         'ORDER_SKEW': 1.0},
                           'STARFRUIT': {'FAIR_VALUE': 5000.0,
                                         'SL_INVENTORY': 10,
                                         'SL_SPREAD': 1,
                                         'MM_SPREAD': 2,
                                         'ORDER_SKEW': 1.0,
                                         'MIN_WINDOW_SIZE': 5,
                                         'MAX_WINDOW_SIZE': 10,
                                         'PREDICT_SHIFT': 1},
                           'ORCHIDS': {'EXP_STORAGE_TIME': 1,
                                       'MIN_EDGE': 1.0,
                                       'MM_EDGE': 1.5},
                           'GIFT_BASKET': {'PREMIUM_MEAN': 385.0,
                                           'PREMIUM_STD': 75.0,
                                           'FAIR_VALUE': 70000.0,
                                           'SL_INVENTORY': 57,
                                           'SL_SPREAD': 1,
                                           'MM_SPREAD': 2.0,
                                           'ORDER_SKEW': 1.0,
                                           'LINEAR_SENSITIVITY': 1.0,
                                           'QUADRATIC_SENSITIVITY': 0.0,
                                           'SL_TARGET': 0,
                                           'CARRY': 2.0}
                           }
              }

    def restore_data(self, timestamp, encoded_data):
        """
        Restore data by decoding traderData with jsonpickle if loss in data is found

        :param timestamp: (int) current timestamp
        :param encoded_data: (str) traderData from previous timestamp encoded with jsonpickle
        """
        data_loss = any([bool(v) for v in self.data.values()])
        # restore only if any empty data except 0 timestamp
        if timestamp >= 100 and data_loss:
            self.data = jsonpickle.decode(encoded_data, keys=True)

    def store_data(self, symbol: Symbol, value: Any, max_size: int = None):
        """
        Store new mid vwap data for Starfruit to class variable as queue
        :param symbol: (Symbol) Symbol of which data belongs to
        :param value: (Any) Value to be stored in data
        :param max_size: (int) Maximum size of the array, default None
        """
        if max_size:
            while len(self.data[symbol]) >= max_size:
                self.data[symbol].popleft()
        self.data[symbol].append(value)

    def run(self, state: TradingState):
        """
        Trading algorithm that will be iterated for every timestamp

        :param state: (TradingState) State of each timestamp
        :return: result, conversions, traderData: (Tuple[Tuple[Dict[Symbol, List[Order]], int, str])
        Results (dict of orders, conversion number, and data) of algorithms to send to the server
        """
        # restore data from traderData of last timestamp
        self.restore_data(state.timestamp, state.traderData)

        config_p = self.config['PRODUCT']
        config_s = self.config['STRATEGY']

        # aggregate orders in this result dictionary
        result: Dict[Symbol, List[Order]] = {}
        conversions: int = 0

        # Round 1: AMETHYSTS and STARFRUIT (Market Making)
        # Symbol 0: AMETHYSTS (Fixed Fair Value Market Making)
        symbol = self.symbols[0]
        fixed_mm = MarketMaking(state, config_p[symbol], config_s[symbol])
        result[symbol] = fixed_mm.aggregate_orders()

        # Symbol 1: STARFRUIT (Linear Regression Market Making)
        symbol = self.symbols[1]
        lr_mm = LinearRegressionMM(state, config_p[symbol], config_s[symbol])
        self.store_data(lr_mm.symbol, lr_mm.mid_vwap, lr_mm.max_window_size)  # update data
        lr_mm.predict_price(self.data[symbol])  # update fair value
        result[symbol] = lr_mm.aggregate_orders()

        # Round 2: OTC-Exchange Arbitrage
        # Symbol 2: ORCHIDS
        symbol = self.symbols[2]
        otc_arb = OTCArbitrage(state, config_p[symbol], config_s[symbol])
        result[symbol], conversions = otc_arb.aggregate_orders_conversions()

        # Round 3: Basket Trading
        # Symbol 3: GIFT_BASKET, 4 ~ 6: CHOCOLATE, STRAWBERRIES, ROSES
        symbol_basket = self.symbols[3]
        symbols_constituent = [self.symbols[i] for i in range(4, 7)]
        basket_trading = BasketTrading(state, config_p[symbol_basket],
                                       {s: config_p[s] for s in symbols_constituent}, config_s[symbol_basket])
        result[symbol_basket] = basket_trading.aggregate_basket_orders()

        # Save Data to traderData and pass to next timestamp
        traderData = jsonpickle.encode(self.data, keys=True)
        # logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
