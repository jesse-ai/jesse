from tabulate import tabulate


def key_value(data, title, alignments=None, uppercase_title=True):
    """

    :param data:
    :param title:
    :param alignments:
    :param uppercase_title:
    """
    table = []

    for d in data:
        table.append(d)

    if alignments is None:
        print(tabulate(table, headers=[title.upper() if uppercase_title else title, ''], tablefmt="presto"))
    else:
        print(tabulate(table, headers=[title.upper() if uppercase_title else title, ''], tablefmt="presto",
                       colalign=alignments))


def multi_value(data, with_headers=True, alignments=None):
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
