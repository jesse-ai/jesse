from abc import ABC, abstractmethod
from time import sleep
from typing import List

import numpy as np
import pydash

import jesse.helpers as jh
import jesse.services.logger as logger
import jesse.services.selectors as selectors
from jesse import exceptions
from jesse.enums import sides, trade_types, order_roles
from jesse.models import CompletedTrade, Order, Route, FuturesExchange, SpotExchange, Position
from jesse.models.utils import store_completed_trade_into_db, store_order_into_db
from jesse.services import metrics
from jesse.services.broker import Broker
from jesse.store import store
from jesse.services.cache import cached


class Strategy(ABC):
    """The parent strategy class which every strategy must extend"""

    def __init__(self) -> None:
        self.id = jh.generate_unique_id()
        self.name = None
        self.symbol = None
        self.exchange = None
        self.timeframe = None
        self.hp = None

        self.index = 0
        self.vars = {}

        self.increased_count = 0
        self.reduced_count = 0

        self.buy = None
        self._buy = None
        self.sell = None
        self._sell = None
        self.stop_loss = None
        self._stop_loss = None
        self.take_profit = None
        self._take_profit = None
        self._log_take_profit = None
        self._log_stop_loss = None

        self._open_position_orders = []
        self._stop_loss_orders = []
        self._take_profit_orders = []

        self.trade: CompletedTrade = None
        self.trades_count = 0

        self._is_executing = False
        self._is_initiated = False

        self.position: Position = None
        self.broker = None

        self._cached_methods = {}
        self._cached_metrics = {}

    def _init_objects(self) -> None:
        """
        This method gets called after right creating the Strategy object. It
        is just a workaround as a part of not being able to set them inside
        self.__init__() for the purpose of removing __init__() methods from strategies.
        """
        self.position = selectors.get_position(self.exchange, self.symbol)
        self.broker = Broker(self.position, self.exchange, self.symbol, self.timeframe)

        if self.hp is None:
            if len(self.hyperparameters()) > 0:
                self.hp = {}
                for dna in self.hyperparameters():
                    self.hp[dna['name']] = dna['default']

    @property
    def _price_precision(self):
        """
        used when live trading because few exchanges require numbers to have a specific precision
        """
        return selectors.get_exchange(self.exchange).vars['precisions'][self.symbol]['price_precision']

    @property
    def _qty_precision(self):
        """
        used when live trading because few exchanges require numbers to have a specific precision
        """
        return selectors.get_exchange(self.exchange).vars['precisions'][self.symbol]['qty_precision']

    def _broadcast(self, msg: str) -> None:
        """Broadcasts the event to all OTHER strategies

        Arguments:
            msg {str} -- [the message to broadcast]
        """
        from jesse.routes import router

        for r in router.routes:
            # skip self
            if r.strategy.id == self.id:
                continue

            if msg == 'route-open-position':
                r.strategy.on_route_open_position(self)
            elif msg == 'route-stop-loss':
                r.strategy.on_route_stop_loss(self)
            elif msg == 'route-take-profit':
                r.strategy.on_route_take_profit(self)
            elif msg == 'route-increased-position':
                r.strategy.on_route_increased_position(self)
            elif msg == 'route-reduced-position':
                r.strategy.on_route_reduced_position(self)
            elif msg == 'route-canceled':
                r.strategy.on_route_canceled(self)

            r.strategy._detect_and_handle_entry_and_exit_modifications()

    def _on_updated_position(self, order: Order) -> None:
        """
        Handles the after-effect of the executed order

        Note that it assumes that the position has already been affected
        by the executed order.

        Arguments:
            order {Order} -- the executed order object
        """
        role = order.role

        if role == order_roles.OPEN_POSITION and abs(self.position.qty) != abs(order.qty):
            order.role = order_roles.INCREASE_POSITION
            role = order_roles.INCREASE_POSITION

        if role == order_roles.CLOSE_POSITION and self.position.is_open:
            order.role = order_roles.REDUCE_POSITION
            role = order_roles.REDUCE_POSITION

        self._log_position_update(order, role)

        if role == order_roles.OPEN_POSITION:
            self._on_open_position(order)
        elif role == order_roles.CLOSE_POSITION and order in self._take_profit_orders:
            self._on_take_profit(order)
        elif role == order_roles.CLOSE_POSITION and order in self._stop_loss_orders:
            self._on_stop_loss(order)
        elif role == order_roles.INCREASE_POSITION:
            self._on_increased_position(order)
        elif role == order_roles.REDUCE_POSITION:
            self._on_reduced_position(order)

    def filters(self) -> list:
        return []

    def hyperparameters(self) -> list:
        return []

    def _execute_long(self) -> None:
        self.go_long()

        # validation
        if self.buy is None:
            raise exceptions.InvalidStrategy('You forgot to set self.buy. example [qty, price]')
        elif type(self.buy) not in [tuple, list]:
            raise exceptions.InvalidStrategy('self.buy must be either a list or a tuple. example: [qty, price]')

        self._prepare_buy()

        if self.take_profit is not None:
            # validate
            self._validate_take_profit()

            self._prepare_take_profit()

        if self.stop_loss is not None:
            # validate
            self._validate_stop_loss()

            self._prepare_stop_loss()

        # filters
        passed = self._execute_filters()
        if not passed:
            return

        for o in self._buy:
            # STOP order
            if o[1] > self.price:
                self._open_position_orders.append(
                    self.broker.start_profit_at(sides.BUY, o[0], o[1], order_roles.OPEN_POSITION)
                )
            # LIMIT order
            elif o[1] < self.price:
                self._open_position_orders.append(
                    self.broker.buy_at(o[0], o[1], order_roles.OPEN_POSITION)
                )
            # MARKET order
            elif o[1] == self.price:
                self._open_position_orders.append(
                    self.broker.buy_at_market(o[0], order_roles.OPEN_POSITION)
                )

    def _prepare_buy(self, make_copies: bool = True) -> None:
        if type(self.buy) is np.ndarray:
            return

        # create a copy in the placeholders variables so we can detect future modifications
        # also, make it list of orders even if there's only one, to make it easier to loop
        if type(self.buy[0]) not in [list, tuple]:
            self.buy = [self.buy]
        self.buy = self._convert_to_numpy_array(self.buy, 'self.buy')

        if make_copies:
            self._buy = self.buy.copy()

    def _prepare_sell(self, make_copies: bool = True) -> None:
        if type(self.sell) is np.ndarray:
            return

        # create a copy in the placeholders variables so we can detect future modifications
        # also, make it list of orders even if there's only one, to make it easier to loop
        if type(self.sell[0]) not in [list, tuple]:
            self.sell = [self.sell]
        self.sell = self._convert_to_numpy_array(self.sell, 'self.sell')

        if make_copies:
            self._sell = self.sell.copy()

    def _prepare_stop_loss(self, make_copies: bool = True) -> None:
        # if it's numpy, then it has already been prepared
        if type(self.stop_loss) is np.ndarray:
            return

        if type(self.stop_loss[0]) not in [list, tuple, np.ndarray]:
            self.stop_loss = [self.stop_loss]
        self.stop_loss = self._convert_to_numpy_array(self.stop_loss, 'self.stop_loss')

        if make_copies:
            self._stop_loss = self.stop_loss.copy()
            self._log_stop_loss = self._stop_loss.copy()

    def _prepare_take_profit(self, make_copies: bool = True) -> None:
        # if it's numpy, then it has already been prepared
        if type(self.take_profit) is np.ndarray:
            return

        if type(self.take_profit[0]) not in [list, tuple, np.ndarray]:
            self.take_profit = [self.take_profit]
        self.take_profit = self._convert_to_numpy_array(self.take_profit, 'self.take_profit')

        if make_copies:
            self._take_profit = self.take_profit.copy()
            self._log_take_profit = self._take_profit.copy()

    def _convert_to_numpy_array(self, arr, name) -> np.ndarray:
        if type(arr) is np.ndarray:
            return arr

        try:
            # create numpy array from list
            arr = np.array(arr, dtype=float)

            if jh.is_live():
                # in livetrade mode, we'll need them rounded
                current_exchange = selectors.get_exchange(self.exchange)

                # skip rounding if the exchange doesn't have values for 'precisions'
                if 'precisions' not in current_exchange.vars:
                    return arr

                price_precision = current_exchange.vars['precisions'][self.symbol]['price_precision']
                qty_precision = current_exchange.vars['precisions'][self.symbol]['qty_precision']

                prices = jh.round_price_for_live_mode(arr[:, 1], price_precision)
                qtys = jh.round_qty_for_live_mode(arr[:, 0], qty_precision)

                arr[:, 0] = qtys
                arr[:, 1] = prices

            return arr
        except ValueError:
            raise exceptions.InvalidShape(
                f'The format of {name} is invalid. \n'
                f'It must be (qty, price) or [(qty, price), (qty, price)] for multiple points; but {arr} was given'
            )

    def _validate_stop_loss(self) -> None:
        if self.stop_loss is None:
            raise exceptions.InvalidStrategy('You forgot to set self.stop_loss. example [qty, price]')
        elif type(self.stop_loss) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy('self.stop_loss must be either a list or a tuple. example: [qty, price]')

    def _validate_take_profit(self) -> None:
        if self.take_profit is None:
            raise exceptions.InvalidStrategy('You forgot to set self.take_profit. example [qty, price]')
        elif type(self.take_profit) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy('self.take_profit must be either a list or a tuple. example: [qty, price]')

    def _execute_short(self) -> None:
        self.go_short()

        # validation
        if self.sell is None:
            raise exceptions.InvalidStrategy('You forgot to set self.sell. example [qty, price]')
        elif type(self.sell) not in [tuple, list]:
            raise exceptions.InvalidStrategy('self.sell must be either a list or a tuple. example: [qty, price]')

        self._prepare_sell()

        if self.take_profit is not None:
            self._validate_take_profit()
            self._prepare_take_profit()

        if self.stop_loss is not None:
            self._validate_stop_loss()
            self._prepare_stop_loss()

        # filters
        passed = self._execute_filters()
        if not passed:
            return

        for o in self._sell:
            # STOP order
            if o[1] < self.price:
                self._open_position_orders.append(
                    self.broker.start_profit_at(sides.SELL, o[0], o[1], order_roles.OPEN_POSITION)
                )
            # LIMIT order
            elif o[1] > self.price:
                self._open_position_orders.append(
                    self.broker.sell_at(o[0], o[1], order_roles.OPEN_POSITION)
                )
            # MARKET order
            elif o[1] == self.price:
                self._open_position_orders.append(
                    self.broker.sell_at_market(o[0], order_roles.OPEN_POSITION)
                )

    def _execute_filters(self) -> bool:
        for f in self.filters():
            try:
                passed = f()
            except TypeError:
                raise exceptions.InvalidStrategy(
                    "Invalid filter format. You need to pass filter methods WITHOUT calling them "
                    "(no parentheses must be present at the end)"
                    "\n\n"
                    u"\u274C " + "Incorrect Example:\n"
                                 "return [\n"
                                 "    self.filter_1()\n"
                                 "]\n\n"
                                 u"\u2705 " + "Correct Example:\n"
                                              "return [\n"
                                              "    self.filter_1\n"
                                              "]\n"
                )

            if passed == False:
                logger.info(f.__name__)
                self._reset()
                return False

        return True

    @abstractmethod
    def go_long(self):
        pass

    @abstractmethod
    def go_short(self):
        pass

    def _execute_cancel(self) -> None:
        """
        cancels everything so that the strategy can keep looking for new trades.
        """
        # validation
        if self.position.is_open:
            raise Exception('cannot cancel orders when position is still open. there must be a bug somewhere.')

        logger.info('cancel all remaining orders to prepare for a fresh start...')

        self.broker.cancel_all_orders()

        self._reset()

        self._broadcast('route-canceled')

        self.on_cancel()

        if not jh.is_unit_testing() and not jh.is_live():
            store.orders.storage[f'{self.exchange}-{self.symbol}'].clear()

    def _reset(self) -> None:
        self.buy = None
        self._buy = None
        self.sell = None
        self._sell = None
        self.stop_loss = None
        self._stop_loss = None
        self.take_profit = None
        self._take_profit = None
        self._log_take_profit = None
        self._log_stop_loss = None

        self._open_position_orders = []
        self._stop_loss_orders = []
        self._take_profit_orders = []

        self.increased_count = 0
        self.reduced_count = 0

    def on_cancel(self):
        """
        what should happen after all active orders have been cancelled
        """
        pass

    @abstractmethod
    def should_long(self) -> bool:
        """are all filters good to execute buy"""
        pass

    @abstractmethod
    def should_short(self) -> bool:
        """are all filters good to execute sell"""
        pass

    @abstractmethod
    def should_cancel(self) -> bool:
        pass

    def before(self):
        """
        Get's executed BEFORE executing the strategy's logic
        """
        pass

    def after(self):
        """
        Get's executed AFTER executing the strategy's logic
        """
        pass

    def _update_position(self) -> None:
        self.update_position()

        self._detect_and_handle_entry_and_exit_modifications()

    def _detect_and_handle_entry_and_exit_modifications(self) -> None:
        if self.position.is_close:
            return

        try:
            if self.is_long:
                # prepare format
                self._prepare_buy(make_copies=False)

                # if entry has been modified
                if not np.array_equal(self.buy, self._buy):
                    self._buy = self.buy.copy()

                    # cancel orders
                    for o in self._open_position_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    # clean orders array but leave executed ones
                    self._open_position_orders = [o for o in self._open_position_orders if o.is_executed]
                    for o in self._buy:
                        # STOP order
                        if o[1] > self.price:
                            self._open_position_orders.append(
                                self.broker.start_profit_at(sides.BUY, o[0], o[1], order_roles.OPEN_POSITION)
                            )
                        # LIMIT order
                        elif o[1] < self.price:
                            self._open_position_orders.append(
                                self.broker.buy_at(o[0], o[1], order_roles.OPEN_POSITION)
                            )
                        # MARKET order
                        elif o[1] == self.price:
                            self._open_position_orders.append(
                                self.broker.buy_at_market(o[0], order_roles.OPEN_POSITION)
                            )

            elif self.is_short:
                # prepare format
                self._prepare_sell(make_copies=False)

                # if entry has been modified
                if not np.array_equal(self.sell, self._sell):
                    self._sell = self.sell.copy()

                    # cancel orders
                    for o in self._open_position_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    # clean orders array but leave executed ones
                    self._open_position_orders = [o for o in self._open_position_orders if o.is_executed]

                    for o in self._sell:
                        # STOP order
                        if o[1] < self.price:
                            self._open_position_orders.append(
                                self.broker.start_profit_at(sides.SELL, o[0], o[1], order_roles.OPEN_POSITION)
                            )
                        # LIMIT order
                        elif o[1] > self.price:
                            self._open_position_orders.append(
                                self.broker.sell_at(o[0], o[1], order_roles.OPEN_POSITION)
                            )
                        # MARKET order
                        elif o[1] == self.price:
                            self._open_position_orders.append(
                                self.broker.sell_at_market(o[0], order_roles.OPEN_POSITION)
                            )

            if self.position.is_open and self.take_profit is not None:
                self._validate_take_profit()
                self._prepare_take_profit(False)

                # if _take_profit has been modified
                if not np.array_equal(self.take_profit, self._take_profit):
                    self._take_profit = self.take_profit.copy()

                    # cancel orders
                    for o in self._take_profit_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    # clean orders array but leave executed ones
                    self._take_profit_orders = [o for o in self._take_profit_orders if o.is_executed]
                    self._log_take_profit = []
                    for s in self._take_profit_orders:
                        self._log_take_profit.append(
                            (abs(s.qty), s.price)
                        )
                    for o in self._take_profit:
                        self._log_take_profit.append(o)

                        self._take_profit_orders.append(
                            self.broker.reduce_position_at(
                                o[0],
                                o[1],
                                order_roles.CLOSE_POSITION
                            )
                        )

            if self.position.is_open and self.stop_loss is not None:
                self._validate_stop_loss()
                self._prepare_stop_loss(False)

                # if stop_loss has been modified
                if not np.array_equal(self.stop_loss, self._stop_loss):
                    # prepare format
                    self._stop_loss = self.stop_loss.copy()

                    # cancel orders
                    for o in self._stop_loss_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    # clean orders array but leave executed ones
                    self._stop_loss_orders = [o for o in self._stop_loss_orders if o.is_executed]
                    self._log_stop_loss = []
                    for s in self._stop_loss_orders:
                        self._log_stop_loss.append(
                            (abs(s.qty), s.price)
                        )
                    for o in self._stop_loss:
                        self._log_stop_loss.append(o)

                        self._stop_loss_orders.append(
                            self.broker.reduce_position_at(
                                o[0],
                                o[1],
                                order_roles.CLOSE_POSITION
                            )
                        )
        except TypeError:
            raise exceptions.InvalidStrategy(
                'Something odd is going on with your strategy. '
                'Try running it with "--debug" to see what was going on near the end, and fix it.'
            )
        except:
            raise

        # validations: stop-loss and take-profit should not be the same
        if self.position.is_open:
            if (self.stop_loss is not None and self.take_profit is not None) and np.array_equal(self.stop_loss,
                                                                                                self.take_profit):
                raise exceptions.InvalidStrategy(
                    'stop-loss and take-profit should not be exactly the same. Just use either one of them and it will do.')

    def update_position(self):
        pass

    def _check(self) -> None:
        """Based on the newly updated info, check if we should take action or not"""
        if not self._is_initiated:
            self._is_initiated = True

        if jh.is_live() and jh.is_debugging():
            logger.info(f'Executing  {self.name}-{self.exchange}-{self.symbol}-{self.timeframe}')

        # for caution to make sure testing on livetrade won't bleed your account
        if jh.is_test_driving() and store.completed_trades.count >= 2:
            logger.info('Maximum allowed trades in test-drive mode is reached')
            return

        if self._open_position_orders != [] and self.is_close and self.should_cancel():
            self._execute_cancel()

            # make sure order cancellation response is received via WS
            if jh.is_live():
                # sleep a little until cancel is received via WS
                sleep(0.1)
                # just in case, sleep some more if necessary
                for _ in range(20):
                    if store.orders.count_active_orders(self.exchange, self.symbol) == 0:
                        break

                    logger.info('sleeping 0.2 more seconds...')
                    sleep(0.2)

                # If it's still not cancelled, something is wrong. Handle cancellation failure
                if store.orders.count_active_orders(self.exchange, self.symbol) != 0:
                    raise exceptions.ExchangeNotResponding(
                        'The exchange did not respond as expected'
                    )

        if self.position.is_open:
            self._update_position()

        if jh.is_backtesting() or jh.is_unit_testing():
            store.orders.execute_pending_market_orders()

        if self.position.is_close and self._open_position_orders == []:
            should_short = self.should_short()
            should_long = self.should_long()
            # validation
            if should_short and should_long:
                raise exceptions.ConflictingRules(
                    'should_short and should_long should not be true at the same time.'
                )
            if should_long:
                self._execute_long()
            elif should_short:
                self._execute_short()

    def _on_open_position(self, order: Order) -> None:
        self.increased_count = 1

        self._broadcast('route-open-position')

        if self.take_profit is not None:
            for o in self._take_profit:
                # validation: make sure take-profit will exit with profit
                if self.is_long:
                    if o[1] <= self.position.entry_price:
                        raise exceptions.InvalidStrategy(
                            f'take-profit({o[1]}) must be above entry-price({self.position.entry_price}) in a long position'
                        )
                elif self.is_short:
                    if o[1] >= self.position.entry_price:
                        raise exceptions.InvalidStrategy(
                            f'take-profit({o[1]}) must be below entry-price({self.position.entry_price}) in a short position'
                        )

                # submit take-profit
                self._take_profit_orders.append(
                    self.broker.reduce_position_at(
                        o[0],
                        o[1],
                        order_roles.CLOSE_POSITION
                    )
                )

        if self.stop_loss is not None:
            for o in self._stop_loss:
                # validation
                if self.is_long:
                    if o[1] >= self.position.entry_price:
                        raise exceptions.InvalidStrategy(
                            f'stop-loss({o[1]}) must be below entry-price({self.position.entry_price}) in a long position'
                        )
                elif self.is_short:
                    if o[1] <= self.position.entry_price:
                        raise exceptions.InvalidStrategy(
                            f'stop-loss({o[1]}) must be above entry-price({self.position.entry_price}) in a short position'
                        )

                # submit stop-loss
                self._stop_loss_orders.append(
                    self.broker.stop_loss_at(
                        o[0],
                        o[1],
                        order_roles.CLOSE_POSITION
                    )
                )

        self._open_position_orders = []
        self.on_open_position(order)
        self._detect_and_handle_entry_and_exit_modifications()

    def on_open_position(self, order: Order):
        """
        What should happen after the open position order has been executed
        """
        pass

    def _on_stop_loss(self, order: Order) -> None:
        if not jh.should_execute_silently() or jh.is_debugging():
            logger.info('Stop-loss has been executed.')

        self._broadcast('route-stop-loss')
        self._execute_cancel()
        self.on_stop_loss(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_stop_loss(self, order: Order):
        """
        What should happen after the stop-loss order has been executed
        """
        pass

    def _on_take_profit(self, order: Order) -> None:
        if not jh.should_execute_silently() or jh.is_debugging():
            logger.info("Take-profit order has been executed.")

        self._broadcast('route-take-profit')
        self._execute_cancel()
        self.on_take_profit(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_take_profit(self, order: Order):
        """
        What should happen after the take-profit order is executed.
        """
        pass

    def _on_increased_position(self, order: Order) -> None:
        self.increased_count += 1

        self._open_position_orders = []

        self._broadcast('route-increased-position')

        self.on_increased_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_increased_position(self, order: Order):
        """
        What should happen after the order (if any) increasing the
        size of the position is executed. Overwrite it if needed.
        And leave it be if your strategy doesn't require it
        """
        pass

    def _on_reduced_position(self, order: Order) -> None:
        """
        prepares for on_reduced_position() is implemented by user
        """
        self.reduced_count += 1

        self._open_position_orders = []

        self._broadcast('route-reduced-position')

        self.on_reduced_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_reduced_position(self, order: Order):
        """
        What should happen after the order (if any) reducing the size of the position is executed.
        """
        pass

    def on_route_open_position(self, strategy):
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_stop_loss(self, strategy):
        """used when trading multiple routes that related
        """
        pass

    def on_route_take_profit(self, strategy):
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_increased_position(self, strategy):
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_reduced_position(self, strategy):
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_canceled(self, strategy):
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def _execute(self) -> None:
        """
        Handles the execution permission for the strategy.
        """
        # make sure we don't execute this strategy more than once at the same time.
        if self._is_executing is True:
            return

        self._is_executing = True

        self.before()
        self._check()
        self.after()
        self._clear_cached_methods()

        self._is_executing = False
        self.index += 1

    def _terminate(self) -> None:
        """
        Optional for executing code after completion of a backTest.
        This block will not execute in live use as a live
        Jesse is never ending.
        """
        if not jh.should_execute_silently() or jh.is_debugging():
            logger.info("Terminating strategy...")

        self.terminate()

        self._detect_and_handle_entry_and_exit_modifications()

        # fake execution of market orders in backtest simulation
        if not jh.is_live():
            store.orders.execute_pending_market_orders()

        if jh.is_live():
            return

        if self.position.is_open:
            store.app.total_open_trades += 1
            store.app.total_open_pl += self.position.pnl
            logger.info(
                f"Closed open {self.exchange}-{self.symbol} position at {self.position.current_price} with PNL: {round(self.position.pnl, 4)}({round(self.position.pnl_percentage, 2)}%) because we reached the end of the backtest session."
            )
            # fake a closing (market) order so that the calculations would be correct
            self.broker.reduce_position_at(self.position.qty, self.position.current_price, order_roles.CLOSE_POSITION)
            return

        if self._open_position_orders:
            self._execute_cancel()
            logger.info('Canceled open-position orders because we reached the end of the backtest session.')

    def terminate(self):
        pass

    def watch_list(self) -> list:
        """
        returns an array containing an array of key-value items that should
        be logged when backTested, and monitored while liveTraded

        Returns:
            [array[{"key": v, "value": v}]] -- an array of dictionary objects
        """
        return []

    def _clear_cached_methods(self) -> None:
        for m in self._cached_methods.values():
            m.cache_clear()

    @property
    def current_candle(self) -> np.ndarray:
        """
        Returns current trading candle

        :return: np.ndarray
        """
        return store.candles.get_current_candle(self.exchange, self.symbol, self.timeframe).copy()

    @property
    def open(self) -> float:
        """
        Returns the closing price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's OPEN price
        """
        return self.current_candle[1]

    @property
    def close(self) -> float:
        """
        Returns the closing price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's CLOSE price
        """
        return self.current_candle[2]

    @property
    def price(self) -> float:
        """
        Same as self.close, except in livetrde, this is rounded as the exchanges require it.

        Returns:
            [float] -- the current trading candle's current(close) price
        """
        return self.position.current_price

    @property
    def high(self) -> float:
        """
        Returns the closing price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's HIGH price
        """
        return self.current_candle[3]

    @property
    def low(self) -> float:
        """
        Returns the closing price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's LOW price
        """
        return self.current_candle[4]

    @property
    def candles(self) -> np.ndarray:
        """
        Returns candles for current trading route

        :return: np.ndarray
        """
        return store.candles.get_candles(self.exchange, self.symbol, self.timeframe)

    def get_candles(self, exchange: str, symbol: str, timeframe: str) -> np.ndarray:
        """
        Get candles by passing exchange, symbol, and timeframe

        :param exchange: str
        :param symbol: str
        :param timeframe: str

        :return: np.ndarray
        """
        return store.candles.get_candles(exchange, symbol, timeframe)

    @property
    def orders(self) -> List[Order]:
        """
        Returns all the orders submitted by for this strategy. Just as a helper
        to use when writing super simple strategies.

        Returns:
            [List[Order]] -- orders submitted by strategy
        """
        return store.orders.get_orders(self.exchange, self.symbol)

    @property
    def trades(self) -> List[CompletedTrade]:
        """
        Returns all the completed trades for this strategy.

        Returns:
         [List[CompletedTrade]] -- completed trades by strategy
        """
        return store.completed_trades.trades

    @property
    def metrics(self) -> dict:
        """
        Returns all the metrics of the strategy.
        """
        if self.trades_count in self._cached_metrics:
            return self._cached_metrics[self.trades_count]
        else:
            self._cached_metrics[self.trades_count] = metrics.trades(
                store.completed_trades.trades, store.app.daily_balance
            )
            return self._cached_metrics[self.trades_count]

    @property
    def time(self) -> int:
        """returns the current time"""
        return store.app.time

    @property
    def balance(self) -> float:
        """alias for self.capital"""
        return self.capital

    @property
    def capital(self) -> float:
        """the current capital in the trading exchange"""
        return self.position.exchange.wallet_balance(self.symbol)

    @property
    def available_margin(self) -> float:
        """Current available margin considering leverage"""
        return self.position.exchange.available_margin(self.symbol)

    @property
    def fee_rate(self) -> float:
        return selectors.get_exchange(self.exchange).fee_rate

    def _log_position_update(self, order: Order, role: str) -> None:
        """
        A log can be either about opening, adding, reducing, or closing the position.

        Arguments:
            order {order} -- the order object
        """
        # set the trade_id for the order if we're in the middle of a trade. Otherwise, it
        # is done at order_roles.OPEN_POSITION
        if self.trade:
            order.trade_id = self.trade.id

        if role == order_roles.OPEN_POSITION:
            self.trade = CompletedTrade()
            self.trade.leverage = self.leverage
            self.trade.orders = [order]
            self.trade.timeframe = self.timeframe
            self.trade.id = jh.generate_unique_id()
            order.trade_id = self.trade.id
            self.trade.strategy_name = self.name
            self.trade.exchange = order.exchange
            self.trade.symbol = order.symbol
            self.trade.type = trade_types.LONG if order.side == sides.BUY else trade_types.SHORT
            self.trade.qty = order.qty
            self.trade.opened_at = jh.now_to_timestamp()
            self.trade.entry_candle_timestamp = self.current_candle[0]
        elif role == order_roles.INCREASE_POSITION:
            self.trade.orders.append(order)
            self.trade.qty += order.qty
        elif role == order_roles.REDUCE_POSITION:
            self.trade.orders.append(order)
            self.trade.qty += order.qty
        elif role == order_roles.CLOSE_POSITION:
            self.trade.exit_candle_timestamp = self.current_candle[0]
            self.trade.orders.append(order)

            # calculate average stop-loss price
            sum_price = 0
            sum_qty = 0
            if self._log_stop_loss is not None:
                for l in self._log_stop_loss:
                    sum_qty += abs(l[0])
                    sum_price += abs(l[0]) * l[1]
                self.trade.stop_loss_at = sum_price / sum_qty
            else:
                self.trade.stop_loss_at = np.nan

            # calculate average take-profit price
            sum_price = 0
            sum_qty = 0
            if self._log_take_profit is not None:
                for l in self._log_take_profit:
                    sum_qty += abs(l[0])
                    sum_price += abs(l[0]) * l[1]
                self.trade.take_profit_at = sum_price / sum_qty
            else:
                self.trade.take_profit_at = np.nan

            # calculate average entry_price price
            sum_price = 0
            sum_qty = 0
            for l in self.trade.orders:
                if not l.is_executed:
                    continue

                if jh.side_to_type(l.side) != self.trade.type:
                    continue

                sum_qty += abs(l.qty)
                sum_price += abs(l.qty) * l.price
            self.trade.entry_price = sum_price / sum_qty

            # calculate average exit_price
            sum_price = 0
            sum_qty = 0
            for l in self.trade.orders:
                if not l.is_executed:
                    continue

                if jh.side_to_type(l.side) == self.trade.type:
                    continue

                sum_qty += abs(l.qty)
                sum_price += abs(l.qty) * l.price
            self.trade.exit_price = sum_price / sum_qty

            self.trade.closed_at = jh.now_to_timestamp()
            self.trade.qty = pydash.sum_by(
                filter(lambda o: o.side == jh.type_to_side(self.trade.type), self.trade.orders),
                lambda o: abs(o.qty)
            )

            store.completed_trades.add_trade(self.trade)
            if jh.is_livetrading():
                store_completed_trade_into_db(self.trade)
            self.trade = None
            self.trades_count += 1

        if jh.is_livetrading():
            store_order_into_db(order)

    @property
    def is_long(self) -> bool:
        return self.position.type == 'long'

    @property
    def is_short(self) -> bool:
        return self.position.type == 'short'

    @property
    def is_open(self) -> bool:
        return self.position.is_open

    @property
    def is_close(self) -> bool:
        return self.position.is_close

    @property
    def average_stop_loss(self) -> float:
        if self._stop_loss is None:
            raise exceptions.InvalidStrategy('You cannot access self.average_stop_loss before setting self.stop_loss')

        arr = self._stop_loss
        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    @property
    def average_take_profit(self) -> float:
        if self._take_profit is None:
            raise exceptions.InvalidStrategy(
                'You cannot access self.average_take_profit before setting self.take_profit')

        arr = self._take_profit
        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    @property
    def average_entry_price(self) -> float:
        if self.is_long:
            arr = self._buy
        elif self.is_short:
            arr = self._sell
        elif self.should_long():
            arr = self._buy
        elif self.should_short():
            arr = self._sell
        else:
            return None

        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    def liquidate(self) -> None:
        """
        closes open position with a MARKET order
        """
        if self.position.is_close:
            return

        if self.position.pnl > 0:
            self.take_profit = self.position.qty, self.price
        else:
            self.stop_loss = self.position.qty, self.price

    @property
    def shared_vars(self) -> dict:
        return store.vars

    @property
    def routes(self) -> List[Route]:
        from jesse.routes import router
        return router.routes

    @property
    def has_active_entry_orders(self) -> bool:
        return len(self._open_position_orders) > 0

    @property
    def leverage(self) -> int:
        if type(self.position.exchange) is SpotExchange:
            return 1
        elif type(self.position.exchange) is FuturesExchange:
            return self.position.exchange.futures_leverage
        else:
            raise ValueError('exchange type not supported!')

    @property
    def mark_price(self):
        return self.position.mark_price

    @property
    def funding_rate(self):
        return self.position.funding_rate

    @property
    def next_funding_timestamp(self):
        return self.position.next_funding_timestamp

    @property
    def liquidation_price(self):
        return self.position.liquidation_price

    def log(self, msg, log_type='info'):
        msg = str(msg)

        if log_type == 'info':
            logger.info(msg)
        elif log_type == 'error':
            logger.error(msg)
        else:
            raise ValueError(f'log_type should be either "info" or "error". You passed {log_type}')
