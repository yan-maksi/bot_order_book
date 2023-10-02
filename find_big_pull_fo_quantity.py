async def find_quantity(ask_bid_quantity, lowest_quantity):
    """
    input: list of bid or asks -> []

    function to find big quantity in order book
    :param ask_bid_quantity: list of bids/asks
    :param lowest_quantity: medium lowest quantity where there can be no resistance
    :return:
        if quantity more than 0.999 -> 1
        if quantity between 1 - 1.6 -> (2, {"index_in_list": "quantity"}) *tuple
        if quantity is bigger than 1.6 -> (3, {"index_in_list": "quantity"}) *tuple
    """
    # create a dict with indices and quantities where quantity is greater than 1.6
    large_positions = {i: quantity for i, quantity in enumerate(ask_bid_quantity[1:], start=1) if quantity > 1.6}
    # create a dict with indices and quantities where quantity is between 1 and 1.6 and greater than lowest_quantity
    average_positions = {i: quantity for i, quantity in enumerate(ask_bid_quantity[1:], start=1) if
                         lowest_quantity < quantity <= 1.6}
    # if there are quantities between 1 and 1.6, return "average" and the corresponding positions
    if large_positions:
        return 3, large_positions

    if average_positions:
        return 2, average_positions

    # if no relevant quantities are found, return 1
    return 1, {99: 99}