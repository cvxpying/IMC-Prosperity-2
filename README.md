# IMC-Prosperity-2024, Y-FoRM
[Link to Korean Version]()

## What is IMC Prosperity?
- Prosperity is 17-day long algorithmic & manual trading competition hosted by IMC Trading.
- The virtual market is an archipelago where currency is SeaShells and products are Strawberries, etc.
- For algorithmic trading, python file will be submitted to trade against bots on limit order book.
- This year's theme included market making, OTC trading, basket trading and options trading.
- For manual trading, puzzle on trading decision related to math and game theory is given.

## Major Reference Links
- [IMC Prosperity](https://prosperity.imc.com)
- [Prosperity Wiki](https://imc-prosperity.notion.site/Prosperity-2-Wiki-fe650c0292ae4cdb94714a3f5aa74c85)
- Special thanks to [jmerle](https://github.com/jmerle) for contributing open source tools: [Visualizer](https://jmerle.github.io/imc-prosperity-2-visualizer/) and [Backtester](https://github.com/jmerle/imc-prosperity-2-backtester/tree/master).
  
---

## Results
### Final Rank: 189th overall (top 2%), 5th in Korea.

| Rank    | Overall | Manual | Algorithmic | Country |
| ------- | ------- | ------ | ----------- | ------- |
| Round 1 | 1913    | 2263   | 674         | 12      |
| Round 2 | 290     | 1397   | 292         | 6       |
| Round 3 | 279     | 971    | 280         | 6       |
| Round 4 | 212     | 794    | 199         | 5       |
| Round 5 | 189     | 576    | 177         | 5       |

| PnL     | Manual  | Algorithmic | Overall | Cumulative |
| ------- | ------- | ----------- | ------- | ---------- |
| Round 1 | 68,531  | 22,124      | 90,655  | 90,655     |
| Round 2 | 113,938 | 219,146     | 333,085 | 423,740    |
| Round 3 | 75,107  | 49,707      | 124,814 | 548,555    |
| Round 4 | 52,212  | 282,865     | 335,077 | 883,632    |
| Round 5 | 69,785  | 108,109     | 177,895 | 1,061,527  |

---

## Team Y-FoRM
We are undergraduate students from Yonsei University, 2 industrial eng. major and 1 econ major.  
Also as the name of our team suggests, we are members of financial eng. and risk mgt. club [Y-FoRM](https://yform.co.kr/).

- Ji Seob Lim [LinkedIn](https://www.linkedin.com/in/jimmylim0823/)
- Seong Yun Cho [LinkedIn](https://www.linkedin.com/in/seongyun0727/)
- Sang Hyeon Park [LinkedIn](https://www.linkedin.com/in/sang-hyeon-park-84612a271/)

---

## Round Summaries
1. [Common Consideration](#Some-common-consideration-for-all-rounds)
1. [Tutorial Round: Market Making](#Tutorial-Round-Market-Making)
1. [Round 1: Market Making (Continued)](#Round-1-Market-Making-Continued)
1. [Round 2: OTC Trading (Exchange-OTC Arbitrage)](#Round-2-OTC-Trading-Exchange-OTC-Arbitrage)
1. [Round 3: Basket Trading (NAV Trading)](#Round-3-Basket-Trading-NAV-Trading)
1. [Round 4: Option Trading (Vega Trading)](#Round-4-Option-Trading-Vega-Trading)
1. [Round 5: De-anonymized Trade Data](#Round-5-De-Anonymized-Trade-Data)

### Some common consideration for all rounds
- Though we have an order book, it operates by turn (think of board games) rather than simultaneously.
- Orders are cancelled at every point in time, so re-processed to next timestamp.
- All products have distinct position limit, and with volume and notional value potential PnL is decided.
- If the order potentially hits the positon limit, order will be canceled, so we should cap our order sizes.
- Scripts will run on AWS, and last year many teamS with complex algorithm had Lambda issue.
- In AWS class variables may be lost, but we can pass serialized data across timestamps through `traderData`. 
- If Prosperity server goes down (happend twice), they might give additional 24 hours for the round.
- The products in previous rounds will stay in the market, but marke regime may change.

### Tutorial Round: Market Making
We spent most of our time in tutorial understanding the mechanics and structure of [trading code](https://imc-prosperity.notion.site/Writing-an-Algorithm-in-Python-658e233a26e24510bfccf0b1df647858). In the end, we decided to market make and take around the fair value with stop loss considering the position limit.

**Some Observations**
- For both products, the order book mainly had two agents:
    - one very-passive market maker: large and symmetric order +- 5 from mid-price (always worst)
    - one active trader (noise or informed): undercutting the +-5 orders with smaller and asymetric size
- Position limit does some work in inventory management against adverse selection
    - The maximum allowed order size of a side decreases as inventory piles up in such direction due to the trend.
    - We could further reduce the size of order in disadvantageous side to protect ourself from the trend.

**Market Making (MM) Logic**
1. Update the fair value (FV) of product
1. Scratch by market taking under or par valued orders (but not against worst bid/ask)
1. Stop loss if inventory piles over certain level (but not against worst bid/ask)
1. Market make around FV with max amount deducted by skew of order size determined by inventory

**Amethesis**
- The FV is clearly 10k and the mid-price is very stable (10k +- 2), so we used fixed FV of 10k.
- Apply the market making logic above directly as there is no need for update of FV.

**Starfruit**
- Prices have trends (strong drift) and the trend may invert during the day.
- We used rolling linear regression $P_t=\beta_0+\beta_1 t$ to predict the price of next timestamp $\hat{P_{t+1}}=\hat{\beta_0}+\hat{\beta_0}(t+1)$.
- Utilizing [SOBI](https://www.cis.upenn.edu/~mkearns/projects/sobi.html) (Static Order Book Imbalance), we stored mid-vwap of order book rather than mid-price into a queue for data to regress. This will denoise mid-price when there is bias due to small best bid/ask.
- We examined various rolling window size using heatmap to find optimal window for prediction.

### Round 1: Market Making (Continued)
- Round1 was extension of tutorial and we continued market making. We focused on optimizing the strategy with some data analytics. We also refactored our code in a more object-oriented way.
- We have `Strategy` class which is the base class for each product. Product configuration, order book features and variables related to our orders (submission, expected position, sum of buys and sells) are defined as instance variable of the class, and we will declare the object of type `Strategy` for each product.  
- `MarketMaking` class inherits from superclass `Strategy` with extra strategy configurations. We have `scratch_under_valued`, `stop_loss`, `market_make` implementing the MM logic above. Then `aggregate_orders` method calls all 3 order-generating methods and returns list of orders, which will be the input for `results[product]` in the `run` method of `Trader` class submitting the orders to the Prosperity system. Orders for `AMETHYSTS` is generated by `MarketMaking` class in the `run` method.
- `LinearRegressionMM` inherits from superclass `MarketMaking` with and extra rolling regression configurations. The only extra method is `predict_price` which performs a linear regrssion and prediction with data externally stored in class variable of `Trader` class, while the rolling part is implemented by queuing up to max rolling sizea. Orders for `STARFRUIT` is generaged by `LinearRegressionMM` class in the `run` method.
- Our equity curve had very high sharpe ratio PnL with almost 0 drawdown. The profit for both product was almost the same, and we managed to maintain profit per round for both product until end of the competition.

**Manual Trading Challege**  
Round 1 was on probability distribution and optimization, we misunderstood the problem missing the answer very badly. We had to bid to maximize our profit give the probability distribution of reserve price which basically is the willingness to sell at our bid. The size of potential from manual trading was way bigger than that of algorithmic trading, so we had a slow start and a long ladder to climb up.

<div align=center><img src = "https://raw.githubusercontent.com/jimmylim0823/IMC-Prosperity-2/master/img/R1_PnL.png?raw=True" width="50%" height="50%"> </div>

### Round 2: OTC Trading (Exchange-OTC Arbitrage)
- The largest challenge for us and the entire community was to comprehend the intentionally vague specification of the product `ORCHIDS` from [Prosperity Wiki](https://imc-prosperity.notion.site/Round-2-accf8ab79fdf4ce5a558e49ecf83b122) and [Prosperity TV](https://www.youtube.com/watch?v=k4mV5XZZM-I).
- Price of `ORCHIDS`, according to wiki and TV, is affected by sunlight and humidity. However, the provided data had low explanatory power with unknown units making it even harder to understand. We tried analytical (building a function) and statistical (linear regression with 2 predictor, linear regression on the residual, etc.) methods which all turned out to be unsuccessful.
- Instead, we turned our focus on arbitrage opportunity between our exchange and another OTC trading venue in the South. We could convert (close position) orchids that we got from our exchange (both long and short) to Seashells in the South. The OTC market have an independent bid and ask, while it is a quote-driven market and will receive conversion of any size, for price of paying transportation fee + import/export tariff. As this is some sort of a single-dealer platform, we had infinite liquidity to close our position immediately, so we would make or take from exchange and close at OTC. `OTCArbitrage` class includes following methods:
1. We could enter our arbitrage position with `arbitrage_exchange_enter` which takes orders from exchange that provide direct arbitrage opportunity. The opportunity is scarace, and the risk is change in price for 1 timestamp before converting to seashelss in OTC. Thus we would only enter with arbitrage edge over `self.min_edge`.
1. We also made market with arbitrage-free pricing using OTC price + transaction cost and added some `self.mm_edge` for magin.
1. Finally, exit all open position at OTC to lock in our margin using `arbitrage_otc_exit`.
- This was all possible due to strong negative import tariff (subsidy), and all of our trade were executed in short direction. Our infinite liquidity in OTC solved the issue with inventory stacking up in one direction, and we were able to make huge profit in Round 2. Unfortunately, this alpha disappeared from Round 3 as import subsidy dropped, and it was impossible to undercut other orders with arbitrage-free pricing. Our team and many other team only relying on arbitrage had huge negative impact on cumulative overall PnL since this point, and we failed to find alpha using humidity/sunlight until the end of competition.

**Manual Trading Challege**  
Round 2 was about triangular arbitrage given the transition rate matrix. We used brute-force algorithm considering small size of the matrix.

<div align=center><img src = "https://raw.githubusercontent.com/jimmylim0823/IMC-Prosperity-2/master/img/R2_PnL.png?raw=True" width="50%" height="50%"></div>

### Round 3: Basket Trading (NAV Trading)
- `GIFT_BASKET` is an index basket equivalent of: 4 `CHOCOLATE`, 6 `STRAWBERRIES` and a `ROSES`.
- The basket always traded premium over NAV and we calculated z-score of the basket-NAV spread.
- We tried stat arb between basket and constituent with z-score, but was not sucessful only market taking.
- Basket had big spread and constituents had small spreads, so we decided to only market make basket with pricing using constituents.
- We shifted are fair value from mid-vwap of basket by adding `pricindg_shift = -demeaned_premium * scaling coefficient` where are pricing bias scaling coefficient uses quadratic sensitivity to spread z-score: `scaling_coefficient = self.alpha * abs(self.z_score) + self.beta * self.z_score ** 2`. This dynamic scaling will make `pricing_shift` approach 0 when z-score is close to 0 and give spike to the signal when z-score deviates significantly from the mean 0, when we have low alpha and high enough beta.
- Mechanics of `aggregate_basket_orders` work similary to market making. `BasketTrading` class will generate orders for only `GIFT_BASKET`.
1. Type of `self.basket` will be `Strategy` and type of `self.constituent` will be `Dict[Symbol: Strategy]`.
1. `calculate_fair_value` calculates FV of basket using mid-vwap, demeaned premium and spread z-score.
1. Simmilar to Round 2, scratch, stop loss and market make basket. However, there are two difference:
   - `scratch_under_valued(mid_vwap=True)`: Scratch under/par-valued based on mid-vwap not fair value (as we already updated our fair value)
   - `aggresive_stop_loss`: Take max quantity from worst bid/ask for stop loss at stop loss inventory level
- We had acceptable and steady profit for basket throughout competition. Nevertheless, we should have tried trading some constituents, even if market making was impossible due to small (0 or 1) spread.

**Manual Trading Challege**  
Round 3 was about game theory, where we choose few grid from a map to search for treasure. Expedition, maximum of 3, have huge marginal cost, and we will share the pie of the treasure we found on the grid with other participants. We tried to avoid crowding in most attractive options, and took one good but not best, and two so so options.

<div align=center><img src = "https://raw.githubusercontent.com/jimmylim0823/IMC-Prosperity-2/master/img/R3_PnL.png?raw=True" width="50%" height="50%"> </div>

### Round 4: Option Trading (Vega Trading)
- `COCONUT` is an underlying asset and `COCONUT_COUPON` is an European call option with strike price of 10000 and time to maturity 250 days(rounds).
- Using our basic knowledge to option greeks, pricing of long-term options are mostly affected by change in volatility (besides the obvious change in underlying price).
- Considering limitation of computing power, we used analytic estimator from [Hallerbach (2004)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=567721) to calculate implied volatility. We found out that IV is highly mean-reverting intraday, so we decided to profit from vega trading based on rolling z-score of IV.
- We first tried a pyramid-style grid trading on IV mean reversion. We found out the mean-reverting signal is too weak for lower z-score, so we modified our trading style to trapezoid style where we cut off lower part of the pyramid below the threshold. Surprisingly, just all-in at lower z-score (near 1.5) signal was most profitable.
- We were delta hedging initially, and this led to constant loss. Our gamma was long and short for similar proportion of the time, but due to lower gamma of long-term option, all we had to pay was the spread and some loss by short gamma. We had to decide hedge, no-hedge, or flip the hedge. We decided to flip the hedge, which is trading underlying using IV level as a signal.
- During backtest, our algo profited moderately (30-40K) for the first two day and very lucratively (170-180K)for the third day (on par with Discord benchmark). This was due to high vol-of-vol of the third day. We hoped we would have high vol-of-of again, and thankfully we earned near 150K only trading the option. One issue was that our PnL for algo trading was missing in the first and thankfully moderators ran our algo again, resulting in near 300K profit which was our single-round best. Unfortunately, this alpha of vega trading from high vol-of-vol was weakened in the last round.

**Manual Trading Challege**  
Round 4 is similar to Round 1, but some game theory added. The probability distribution of willingness to buy is a function of average bids of all the participants. We took a conservative approach and didn't go too far away from the best answer.

<div align=center><img src = "https://raw.githubusercontent.com/jimmylim0823/IMC-Prosperity-2/master/img/R4_PnL.png?raw=True" width="50%" height="50%"> </div>

### Round 5: De-anonymized Trade Data
- No new product was introduced in Round 5, but now name of the trader (both buyer and seleer) for market trades and own trades are visible.
- We plotted the mid-price and labeled the timestamp where given trader bought and sold to gain some insights on each trader's characteristic.
- We found some patterns that involves with the first character of the trader: A, R, V.
  - Trader starting with A (stands for Amatuer?) was really bad, market taking, always trading the opposite way.
  - Trader starting with R (stands for Rookie?) was also bad, market taking, often trading the opposite way.
  - Trader starting with V (stands for Veteran?) was good, market making, mostly high frequency.
- We found relatinship between (signed) size of the trade and with future price movement.
- Linear regression of trade quantity to PnL had good P-value but bad R-squared values.
- We decided to aggregate the signal by multiplying the regression coefficient with R-squared value, so the signal for predicting return is scaled by model fit.
- Good P-values were only found for Round 1 products, while other products had poor model fit.
- Trader based signal was only applied to `AMETHYSTS` and `STARFRUIT`, but extra profit was small.

**Manual Trading Challege**  
Round 5 is news trading. Based on the most credible news source from north archipelago "Iceberg" (not Bloomberg), we have to allocate long and short position to tradable goods with gross position limit of 100%. We tried to take position on all products in order to reduce impact of few wrong answers. We got 5 correct 4 worng trades, but the profit from a single correct trade was able to offset all the losses from wrong trades.

<div align=center><img src = "https://raw.githubusercontent.com/jimmylim0823/IMC-Prosperity-2/master/img/R5_PnL.png?raw=True" width="50%" height="50%"> </div>

---

## In Closing

- Among many algorithmic trading competitions, IMC Prosperity stands out due to its engaging storyline and well-designed graphics. Despite its challenges, it was an enjoyable experience throughout.
- The unexpected server downtime extended the competition by 24 hours, causing inconvenience and disrupting schedules for many participants. Nevertheless, I would like to express my gratitude to IMC for hosting such a fascinating event.
- I am deeply thankful to Ji-seob for introducing me to this competition and encouraging participation. His initiative allowed us to explore market microstructures, CLOB, object-oriented programming, and algorithmic trading strategies extensively.
- My heartfelt thanks also go to Seong-yun, who did not give up despite the difficulties and took charge of manual trading and documenting our meetings, contributing significantly until the end.
- Despite overlapping with exam periods, the fact that we could conduct our Zoom meetings daily past midnight for over two hours without any complaints speaks volumes about the good team spirit and the enjoyable nature of the competition.
- If Prosperity3 is held, I definitely plan to participate again and hope that more people in Korea will also take interest and join the competition.
