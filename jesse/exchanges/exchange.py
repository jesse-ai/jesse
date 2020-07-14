from abc import ABC, abstractmethod


class Exchange(ABC):
    """
    The interface that every Exchange driver has to implement
    """

    @abstractmethod
    def market_order(self, symbol, qty, current_price, side, role, flags):
        """

        :param symbol:
        :param qty:
        :param current_price:
        :param side:
        :param role:
        :param flags:
        """
        pass

    @abstractmethod
    def limit_order(self, symbol, qty, price, side, role, flags):
        """

        :param symbol:
        :param qty:
        :param price:
        :param side:
        :param role:
        :param flags:
        """
        pass

    @abstractmethod
    def stop_order(self, symbol, qty, price, side, role, flags):
        """

        :param symbol:
        :param qty:
        :param price:
        :param side:
        :param role:
        :param flags:
        """
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol):
        """

        :param symbol:
        """
        pass

    @abstractmethod
    def cancel_order(self, symbol, order_id):
        """

        :param symbol:
        :param order_id:
        """
        pass

    @abstractmethod
    def get_exec_inst(self, flags):
        """

        :param flags:
        """
        pass
