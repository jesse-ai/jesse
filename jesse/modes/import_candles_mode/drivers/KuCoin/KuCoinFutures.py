from .KuCoinMain import KuCoinMain
from jesse.enums import exchanges
import jesse.helpers as jh


class KuCoinFutures(KuCoinMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_FUTURES,
            rest_endpoint='https://api-futures.kucoin.com',
            backup_exchange_class=None
        )

    def get_available_symbols(self) -> list:
        response = self._make_request(self.endpoint + '/api/v1/contracts/active')

        self.validate_response(response)

        data = response.json()

        if not data.get('data'):
            return []

        return [jh.dashy_symbol(s['symbol']) for s in data['data']]
