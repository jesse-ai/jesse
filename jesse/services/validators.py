from jesse import exceptions


def validate_routes(router):
    if not router.routes:
        raise exceptions.RouteNotFound(
            'No routes found. Please add at least one route at: routes.py\nMore info: https://docs.jesse.trade/docs/routes.html#routing')
