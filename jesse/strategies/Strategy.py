from abc import ABC, abstractmethod
from time import sleep
from typing import List, Dict, Union

import numpy as np

import jesse.helpers as jh
import jesse.services.logger as logger
import jesse.services.selectors as selectors
from jesse import exceptions
from jesse.enums import sides, order_submitted_via, order_types
from jesse.models import ClosedTrade, Order, Route, FuturesExchange, SpotExchange, Position
from jesse.services import metrics
from jesse.services.broker import Broker
from jesse.store import store
from jesse.services.cache import cached
from jesse.services import notifier


class Strategy(ABC):
    """
    The parent strategy class which every strategy must extend. It is the heart of the framework!
    """

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

        # Variables used for accepting orders from user. Each variable also has a
        # similar one   starting with _ which is used as a temp placeholder to
        # later compare with the current one to detect if user has submitted
        # any new orders. If so, we cancel old ones and submit the new ones.
        self.buy = None
        self._buy = None
        self.sell = None
        self._sell = None
        self.stop_loss = None
        self._stop_loss = None
        self.take_profit = None
        self._take_profit = None

        self.trade: ClosedTrade = None
        self.trades_count = 0

        self._is_executing = False
        self._is_initiated = False
        self._is_handling_updated_order = False

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

        if self.hp is None and len(self.hyperparameters()) > 0:
            self.hp = {}
            for dna in self.hyperparameters():
                self.hp[dna['name']] = dna['default']

    @property
    def _price_precision(self) -> int:
        """
        used when live trading because few exchanges require numbers to have a specific precision
        """
        return selectors.get_exchange(self.exchange).vars['precisions'][self.symbol]['price_precision']

    @property
    def _qty_precision(self) -> int:
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
            elif msg == 'route-close-position':
                r.strategy.on_route_close_position(self)
            elif msg == 'route-increased-position':
                r.strategy.on_route_increased_position(self)
            elif msg == 'route-reduced-position':
                r.strategy.on_route_reduced_position(self)
            elif msg == 'route-canceled':
                r.strategy.on_route_canceled(self)

            r.strategy._detect_and_handle_entry_and_exit_modifications()

    def _on_updated_position(self, order: Order) -> None:
        """
        Handles the after-effect of the executed order to execute strategy
        events. Note that it assumes that the position has already
        been affected by the executed order.
        """
        # in live-mode, sometimes order-update effects and new execution has overlaps, so:
        self._is_handling_updated_order = True

        # this is the last executed order, and had its effect on
        # the position. We need to know what its effect was:
        before_qty = self.position.previous_qty
        after_qty = self.position.qty

        # if opening position
        if abs(before_qty) <= abs(self.position._min_qty) < abs(after_qty):
            effect = 'opening_position'
        # if closing position
        elif abs(before_qty) > abs(self.position._min_qty) >= abs(after_qty):
            effect = 'closing_position'
        # if increasing position size
        elif abs(after_qty) > abs(before_qty):
            effect = 'increased_position'
        # if reducing position size
        else: # abs(after_qty) < abs(before_qty):
            effect = 'reduced_position'

        # call the relevant strategy event handler:
        if effect == 'opening_position':
            txt = f"OPENED {self.position.type} position for {self.symbol}: qty: {after_qty}, entry_price: {self.position.entry_price}"
            if jh.is_debuggable('position_opened'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_open_position(order)
        elif effect == 'closing_position':
            txt = f"CLOSED Position for {self.symbol}"
            if jh.is_debuggable('position_closed'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_close_position(order)
        elif effect == 'increased_position':
            txt = f"INCREASED Position size to {after_qty}"
            if jh.is_debuggable('position_increased'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_increased_position(order)
        else: # if effect == 'reduced_position':
            txt = f"REDUCED Position size to {after_qty}"
            if jh.is_debuggable('position_reduced'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_reduced_position(order)

        self._is_handling_updated_order = False

    def filters(self) -> list:
        return []

    def hyperparameters(self) -> list:
        return []

    def dna(self) -> str:
        return ''

    def _execute_long(self) -> None:
        self.go_long()

        # validation
        if self.buy is None:
            raise exceptions.InvalidStrategy('You forgot to set self.buy. example (qty, price)')
        elif type(self.buy) not in [tuple, list]:
            raise exceptions.InvalidStrategy(
                f'self.buy must be either a list or a tuple. example: (qty, price). You set: {type(self.buy)}')

        self._prepare_buy()

        if self.take_profit is not None:
            if self.exchange_type == 'spot':
                raise exceptions.InvalidStrategy(
                    "Setting self.take_profit in the go_long() method is not supported for spot trading (it's only supported in futures trading). "
                    "Try setting it in self.on_open_position() instead."
                )

            # validate
            self._validate_take_profit()

            self._prepare_take_profit()

        if self.stop_loss is not None:
            if self.exchange_type == 'spot':
                raise exceptions.InvalidStrategy(
                    "Setting self.stop_loss in the go_long() method is not supported for spot trading (it's only supported in futures trading). "
                    "Try setting it in self.on_open_position() instead."
                )

            # validate
            self._validate_stop_loss()

            self._prepare_stop_loss()

        # filters
        if not self._execute_filters():
            return

        self._submit_buy_orders()

    def _submit_buy_orders(self) -> None:
        for o in self._buy:
            # MARKET order
            if abs(o[1] - self.price) < 0.0001:
                self.broker.buy_at_market(o[0])
            # STOP order
            elif o[1] > self.price:
                self.broker.start_profit_at(sides.BUY, o[0], o[1])
            # LIMIT order
            elif o[1] < self.price:
                self.broker.buy_at(o[0], o[1])
            else:
                raise ValueError(f'Invalid order price: o[1]:{o[1]}, self.price:{self.price}')

    def _submit_sell_orders(self) -> None:
        for o in self._sell:
            # MARKET order
            if abs(o[1] - self.price) < 0.0001:
                self.broker.sell_at_market(o[0])
            # STOP order
            elif o[1] < self.price:
                self.broker.start_profit_at(sides.SELL, o[0], o[1])
            # LIMIT order
            elif o[1] > self.price:
                self.broker.sell_at(o[0], o[1])
            else:
                raise ValueError(f'Invalid order price: o[1]:{o[1]}, self.price:{self.price}')

    def _execute_short(self) -> None:
        self.go_short()

        # validation
        if self.sell is None:
            raise exceptions.InvalidStrategy('You forgot to set self.sell. example (qty, price)')
        elif type(self.sell) not in [tuple, list]:
            raise exceptions.InvalidStrategy(
                f'self.sell must be either a list or a tuple. example: (qty, price). You set {type(self.sell)}'
            )

        self._prepare_sell()

        if self.take_profit is not None:
            self._validate_take_profit()
            self._prepare_take_profit()

        if self.stop_loss is not None:
            self._validate_stop_loss()
            self._prepare_stop_loss()

        # filters
        if not self._execute_filters():
            return

        self._submit_sell_orders()

    def _prepare_buy(self, make_copies: bool = True) -> None:
        try:
            self.buy = self._get_formatted_order(self.buy)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.buy is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.buy} was given'
            )

        if make_copies:
            self._buy = self.buy.copy()

    def _prepare_sell(self, make_copies: bool = True) -> None:
        try:
            self.sell = self._get_formatted_order(self.sell)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.sell is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.sell} was given'
            )

        if make_copies:
            self._sell = self.sell.copy()

    def _prepare_stop_loss(self, make_copies: bool = True) -> None:
        try:
            self.stop_loss = self._get_formatted_order(self.stop_loss)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.stop_loss is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.stop_loss} was given'
            )

        if make_copies:
            self._stop_loss = self.stop_loss.copy()

    def _prepare_take_profit(self, make_copies: bool = True) -> None:
        try:
            self.take_profit = self._get_formatted_order(self.take_profit)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.take_profit is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.take_profit} was given'
            )

        if make_copies:
            self._take_profit = self.take_profit.copy()

    def _validate_stop_loss(self) -> None:
        if self.stop_loss is None:
            raise exceptions.InvalidStrategy('You forgot to set self.stop_loss. example (qty, price)')
        elif type(self.stop_loss) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy(
                f'self.stop_loss must be either a list or a tuple. example: (qty, price). You set {type(self.stop_loss)}')

    def _validate_take_profit(self) -> None:
        if self.take_profit is None:
            raise exceptions.InvalidStrategy('You forgot to set self.take_profit. example (qty, price)')
        elif type(self.take_profit) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy(
                f'self.take_profit must be either a list or a tuple. example: (qty, price). You set {type(self.take_profit)}')

    def _execute_filters(self) -> bool:
        for f in self.filters():
            try:
                passed = f()
            except TypeError:
                raise exceptions.InvalidStrategy(
                    "Invalid filter format. You need to pass filter methods WITHOUT calling them "
                    "(no parentheses must be present at the end)"
                    "\n\n"
                    "\u274C " + "Incorrect Example:\n"
                                "return [\n"
                                "    self.filter_1()\n"
                                "]\n\n"
                                "\u2705 " + "Correct Example:\n"
                                            "return [\n"
                                            "    self.filter_1\n"
                                            "]\n"
                )

            if not passed:
                logger.info(f.__name__)
                self._reset()
                return False

        return True

    @abstractmethod
    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
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

        store.orders.reset_trade_orders(self.exchange, self.symbol)

        self.increased_count = 0
        self.reduced_count = 0

    def on_cancel(self) -> None:
        """
        what should happen after all active orders have been cancelled
        """
        pass

    @abstractmethod
    def should_long(self) -> bool:
        pass

    def should_short(self) -> bool:
        return False

    @abstractmethod
    def should_cancel_entry(self) -> bool:
        pass

    def before(self) -> None:
        """
        Get's executed BEFORE executing the strategy's logic
        """
        pass

    def after(self) -> None:
        """
        Get's executed AFTER executing the strategy's logic
        """
        pass

    def _update_position(self) -> None:
        self._wait_until_executing_orders_are_fully_handled()

        # after _wait_until_executing_orders_are_fully_handled, the position might have closed, so:
        if self.position.is_close:
            return

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
                    for o in self.entry_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    self._submit_buy_orders()

            elif self.is_short:
                # prepare format
                self._prepare_sell(make_copies=False)

                # if entry has been modified
                if not np.array_equal(self.sell, self._sell):
                    self._sell = self.sell.copy()

                    # cancel orders
                    for o in self.entry_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    self._submit_sell_orders()

            if self.position.is_open and self.take_profit is not None:
                self._validate_take_profit()
                self._prepare_take_profit(False)

                # if _take_profit has been modified
                if not np.array_equal(self.take_profit, self._take_profit):
                    self._take_profit = self.take_profit.copy()

                    # cancel orders
                    for o in self.exit_orders:
                        if o.is_take_profit and (o.is_active or o.is_queued):
                            self.broker.cancel_order(o.id)
                    for o in self._take_profit:
                        submitted_order: Order = self.broker.reduce_position_at(o[0], o[1])
                        if submitted_order:
                            submitted_order.submitted_via = order_submitted_via.TAKE_PROFIT

            if self.position.is_open and self.stop_loss is not None:
                self._validate_stop_loss()
                self._prepare_stop_loss(False)

                # if stop_loss has been modified
                if not np.array_equal(self.stop_loss, self._stop_loss):
                    # prepare format
                    self._stop_loss = self.stop_loss.copy()

                    # cancel orders
                    for o in self.exit_orders:
                        if o.is_stop_loss and (o.is_active or o.is_queued):
                            self.broker.cancel_order(o.id)
                    # remove canceled orders to optimize the loop
                    for o in self._stop_loss:
                        submitted_order: Order = self.broker.reduce_position_at(o[0], o[1])
                        if submitted_order:
                            submitted_order.submitted_via = order_submitted_via.STOP_LOSS
        except TypeError:
            raise exceptions.InvalidStrategy(
                'Something odd is going on within your strategy causing a TypeError exception. '
                'Try running it with "--debug" in a backtest to see what was going on near the end, and fix it.'
            )
        except:
            raise

        # validations: stop-loss and take-profit should not be the same
        if (
                self.position.is_open
                and (self.stop_loss is not None and self.take_profit is not None)
                and np.array_equal(self.stop_loss, self.take_profit)
        ):
            raise exceptions.InvalidStrategy(
                'stop-loss and take-profit should not be exactly the same. Just use either one of them and it will do.')

    def update_position(self) -> None:
        pass

    def _wait_until_executing_orders_are_fully_handled(self):
        if self._is_handling_updated_order:
            logger.info(
                "Stopped strategy execution at this time because we're still handling the result "
                "of an executed order. Trying again in 3 seconds..."
            )
            sleep(3)

    def _check(self) -> None:
        """
        Based on the newly updated info, check if we should take action or not
        """
        if not self._is_initiated:
            self._is_initiated = True

        self._wait_until_executing_orders_are_fully_handled()

        if jh.is_live() and jh.is_debugging():
            logger.info(f'Executing  {self.name}-{self.exchange}-{self.symbol}-{self.timeframe}')

        # should cancel entry?
        if len(self.entry_orders) and self.is_close and self.should_cancel_entry():
            self._execute_cancel()

            # make sure order cancellation response is received via WS
            if jh.is_live():
                # sleep a little until cancel is received via WS
                sleep(0.1)
                # just in case, sleep some more if necessary
                for _ in range(20):
                    if store.orders.count_active_orders(self.exchange, self.symbol) == 0:
                        break

                    logger.info('sleeping 0.2 more seconds until cancellation is over...')
                    sleep(0.2)

                # If it's still not cancelled, something is wrong. Handle cancellation failure
                if store.orders.count_active_orders(self.exchange, self.symbol) != 0:
                    raise exceptions.ExchangeNotResponding(
                        'The exchange did not respond as expected for order cancellation'
                    )

        # update position
        if self.position.is_open:
            self._update_position()

            # sleep for 1 second if a MARKET order has been submitted but not executed yet (live trading only)
            if jh.is_livetrading():
                waiting_counter = 0
                waiting_seconds = 1
                while self._have_any_pending_market_exit_orders():
                    if jh.is_debugging():
                        logger.info(f'Waiting {waiting_seconds} second for pending market exit orders to be handled...')
                    waiting_counter += 1
                    sleep(1)
                    if waiting_counter > 10:
                        raise exceptions.ExchangeNotResponding(
                            'The exchange did not respond as expected for order execution'
                        )

        self._simulate_market_order_execution()

        # should_long and should_short
        if self.position.is_close and self.entry_orders == []:
            self._reset()

            should_short = self.should_short()
            # validate that should_short is not True if the exchange_type is spot
            if self.exchange_type == 'spot' and should_short is True:
                raise exceptions.InvalidStrategy(
                    'should_short cannot be True if the exchange type is "spot".'
                )

            should_long = self.should_long()

            # should_short and should_long cannot be True at the same time
            if should_short and should_long:
                raise exceptions.ConflictingRules(
                    'should_short and should_long should not be true at the same time.'
                )

            if should_long:
                self._execute_long()
            elif should_short:
                self._execute_short()

    def _have_any_pending_market_exit_orders(self) -> bool:
        return any(o.is_active and o.type == order_types.MARKET for o in self.exit_orders)

    @staticmethod
    def _simulate_market_order_execution() -> None:
        """
        Simulate market order execution in backtest mode
        """
        if jh.is_backtesting() or jh.is_unit_testing() or jh.is_paper_trading():
            store.orders.execute_pending_market_orders()

    def _on_open_position(self, order: Order) -> None:
        self.increased_count = 1

        self._broadcast('route-open-position')

        if self.take_profit is not None:
            for o in self._take_profit:
                # validation: make sure take-profit will exit with profit, if not, close the position
                if self.is_long and o[1] <= self.position.entry_price:
                    submitted_order: Order = self.broker.sell_at_market(o[0])
                    logger.info(
                        'The take-profit is below entry-price for long position, so it will be replaced with a market order instead')
                elif self.is_short and o[1] >= self.position.entry_price:
                    submitted_order: Order = self.broker.buy_at_market(o[0])
                    logger.info(
                        'The take-profit is above entry-price for a short position, so it will be replaced with a market order instead')
                else:
                    submitted_order: Order = self.broker.reduce_position_at(o[0], o[1])

                if submitted_order:
                    submitted_order.submitted_via = order_submitted_via.TAKE_PROFIT

        if self.stop_loss is not None:
            for o in self._stop_loss:
                # validation: make sure stop-loss will exit with profit, if not, close the position
                if self.is_long and o[1] >= self.position.entry_price:
                    submitted_order: Order = self.broker.sell_at_market(o[0])
                    logger.info(
                        'The stop-loss is above entry-price for long position, so it will be replaced with a market order instead')
                elif self.is_short and o[1] <= self.position.entry_price:
                    submitted_order: Order = self.broker.buy_at_market(o[0])
                    logger.info(
                        'The stop-loss is below entry-price for a short position, so it will be replaced with a market order instead')
                else:
                    submitted_order: Order = self.broker.reduce_position_at(o[0], o[1])

                if submitted_order:
                    submitted_order.submitted_via = order_submitted_via.STOP_LOSS

        self.on_open_position(order)
        self._detect_and_handle_entry_and_exit_modifications()

    def on_open_position(self, order) -> None:
        """
        What should happen after the open position order has been executed
        """
        pass

    def on_close_position(self, order) -> None:
        """
        What should happen after the open position order has been executed
        """
        pass

    def _on_close_position(self, order: Order):
        self._broadcast('route-close-position')
        self._execute_cancel()
        self.on_close_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def _on_increased_position(self, order: Order) -> None:
        self.increased_count += 1

        self._broadcast('route-increased-position')

        self.on_increased_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_increased_position(self, order) -> None:
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

        self._broadcast('route-reduced-position')

        self.on_reduced_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_reduced_position(self, order) -> None:
        """
        What should happen after the order (if any) reducing the size of the position is executed.
        """
        pass

    def on_route_open_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_close_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_increased_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_reduced_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_canceled(self, strategy) -> None:
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
            logger.info(f"Terminating {self.symbol}...")

        self.before_terminate()

        self._detect_and_handle_entry_and_exit_modifications()

        # fake execution of market orders in backtest simulation
        if not jh.is_live():
            store.orders.execute_pending_market_orders()

        if jh.is_live():
            self.terminate()
            return

        if self.position.is_open:
            store.app.total_open_trades += 1
            store.app.total_open_pl += self.position.pnl
            logger.info(
                f"Closed open {self.exchange}-{self.symbol} position at {self.position.current_price} with PNL: {round(self.position.pnl, 4)}({round(self.position.pnl_percentage, 2)}%) because we reached the end of the backtest session."
            )
            # first cancel all active orders so the balances would go back to the original state
            if self.exchange_type == 'spot':
                self.broker.cancel_all_orders()
            # fake a closing (market) order so that the calculations would be correct
            self.broker.reduce_position_at(self.position.qty, self.position.current_price)
            self.terminate()
            return

        if len(self.entry_orders):
            self._execute_cancel()
            logger.info('Canceled open-position orders because we reached the end of the backtest session.')

        self.terminate()

    def before_terminate(self):
        pass

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
        Same as self.close, except in livetrade, this is rounded as the exchanges require it.

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
    def metrics(self) -> dict:
        """
        Returns all the metrics of the strategy.
        """
        if self.trades_count not in self._cached_metrics:
            self._cached_metrics[self.trades_count] = metrics.trades(
                store.completed_trades.trades, store.app.daily_balance, final=False
            )
        return self._cached_metrics[self.trades_count]

    @property
    def time(self) -> int:
        """returns the current time"""
        return store.app.time

    @property
    def balance(self) -> float:
        """the current capital in the trading exchange"""
        return self.position.exchange.wallet_balance

    @property
    def capital(self) -> float:
        raise NotImplementedError('The alias "self.capital" has been removed. Please use "self.balance" instead.')

    @property
    def available_margin(self) -> float:
        """Current available margin considering leverage"""
        return self.position.exchange.available_margin

    @property
    def fee_rate(self) -> float:
        return selectors.get_exchange(self.exchange).fee_rate

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

    def _get_formatted_order(self, var, round_for_live_mode=True) -> Union[list, np.ndarray]:
        if type(var) is np.ndarray:
            return var

        # just to make sure we also support None
        if var is None or var == []:
            return []

        # create a copy in the placeholders variables so we can detect future modifications
        # also, make it list of orders even if there's only one, to make it easier to loop
        if type(var[0]) not in [list, tuple]:
            var = [var]

        # create numpy array from list
        arr = np.array(var, dtype=float)

        # validate that the price (second column) is not less or equal to zero
        if arr[:, 1].min() <= 0:
            raise exceptions.InvalidStrategy(f'Order price must be greater than zero: \n{var}')

        if jh.is_livetrading() and round_for_live_mode:
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

    @property
    def average_entry_price(self) -> float:
        if self.is_long:
            arr = self._buy
        elif self.is_short:
            arr = self._sell
        elif self.has_long_entry_orders:
            arr = self._get_formatted_order(self.buy)
        elif self.has_short_entry_orders:
            arr = self._get_formatted_order(self.sell)
        else:
            return None

        # if type of arr is not np.ndarray, then it's not ready yet. Return None
        if type(arr) is not np.ndarray:
            arr = None

        if arr is None and self.position.is_open:
            return self.position.entry_price
        elif arr is None:
            return None

        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    @property
    def has_long_entry_orders(self) -> bool:
        # if no order has been submitted yet, but self.buy is not None, then we are calling
        # this property inside a filter.
        if self.entry_orders == [] and self.buy is not None:
            return True

        return self.entry_orders != [] and self.entry_orders[0].side == 'buy'

    @property
    def has_short_entry_orders(self) -> bool:
        # if no order has been submitted yet, but self.sell is not None, then we are calling
        # this property inside a filter.
        if self.entry_orders == [] and self.sell is not None:
            return True
        return self.entry_orders != [] and self.entry_orders[0].side == 'sell'

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
    def leverage(self) -> int:
        if type(self.position.exchange) is SpotExchange:
            return 1
        elif type(self.position.exchange) is FuturesExchange:
            return self.position.exchange.futures_leverage
        else:
            raise ValueError('exchange type not supported!')

    @property
    def mark_price(self) -> float:
        return self.position.mark_price

    @property
    def funding_rate(self) -> float:
        return self.position.funding_rate

    @property
    def next_funding_timestamp(self) -> int:
        return self.position.next_funding_timestamp

    @property
    def liquidation_price(self) -> float:
        return self.position.liquidation_price

    @staticmethod
    def log(msg: str, log_type: str = 'info', send_notification: bool = False) -> None:
        msg = str(msg)

        if log_type == 'info':
            logger.info(msg, send_notification=jh.is_live() and send_notification)
        elif log_type == 'error':
            logger.error(msg, send_notification=jh.is_live() and send_notification)
        else:
            raise ValueError(f'log_type should be either "info" or "error". You passed {log_type}')

    @property
    def all_positions(self) -> Dict[str, Position]:
        positions_dict = {}
        for r in self.routes:
            positions_dict[r.symbol] = r.strategy.position
        return positions_dict

    @property
    def portfolio_value(self) -> float:
        total_position_values = 0

        # in spot mode, self.balance does not include open order's value, so:
        if self.is_spot_trading:
            for o in self.entry_orders:
                if o.is_active:
                    total_position_values += o.value

            for key, p in self.all_positions.items():
                total_position_values += p.value

        # in futures mode, it's simpler:
        elif self.is_futures_trading:
            for key, p in self.all_positions.items():
                total_position_values += p.pnl

        return (total_position_values + self.balance) * self.leverage

    @property
    def trades(self) -> List[ClosedTrade]:
        """
        Returns all the completed trades for this strategy.
        """
        return store.completed_trades.trades

    @property
    def orders(self) -> List[Order]:
        """
        Returns all the orders submitted by for this strategy.
        """
        return store.orders.get_orders(self.exchange, self.symbol)

    @property
    def entry_orders(self):
        """
        Returns all the entry orders for this position.
        """
        return store.orders.get_entry_orders(self.exchange, self.symbol)

    @property
    def exit_orders(self):
        """
        Returns all the exit orders for this position.
        """
        return store.orders.get_exit_orders(self.exchange, self.symbol)

    @property
    def exchange_type(self):
        return selectors.get_exchange(self.exchange).type

    @property
    def is_spot_trading(self) -> bool:
        return self.exchange_type == 'spot'

    @property
    def is_futures_trading(self) -> bool:
        return self.exchange_type == 'futures'

    @property
    def daily_balances(self):
        return store.app.daily_balance
