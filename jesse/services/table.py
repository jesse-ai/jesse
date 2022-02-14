from tabulate import tabulate
from typing import Union

def key_value(data, title: str, alignments: Union[list, tuple] = None, uppercase_title: bool = True) -> None:
    table = [d for d in data]

    if alignments is None:
        print(tabulate(table, headers=[title.upper() if uppercase_title else title, ''], tablefmt="presto"))
    else:
        print(tabulate(table, headers=[title.upper() if uppercase_title else title, ''], tablefmt="presto",
                       colalign=alignments))


def multi_value(data, with_headers: bool = True, alignments: Union[list, tuple] = None) -> None:
    """

    :param data:
    :param with_headers:
    :param alignments:
    :return:
    """
    if data is None:
        return

    headers = data.pop(0) if with_headers else ()

    table = data

    if alignments is None:
        print(tabulate(table, headers=headers, tablefmt="presto"))
    else:
        print(tabulate(table, headers=headers, tablefmt="presto", colalign=alignments))
