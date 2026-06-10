# -*- coding: utf-8 -*-

from decimal import Decimal
from ..out_record import TransactionOutRecord
from ..dataparser import DataParser, ParserType
from ...bt_types import TrType

WALLET = "Luno"

# TODO understand Handler parser vs Handlers2 _parser
def parse_luno(data_rows, _parser, **_kwargs):
    '''
    Luno requires you to separately download transactions for each "wallet".
    So each asset will be its own file. Could result in duplicates.

    Bought 0.0007 BTC/GBP @ 18,005.59
    Sold 0.01 BTC/GBP @ 18,666.56
    Trading fee
    Received Bitcoin into address1
    Sent Bitcoin to bc1qhe9qu6y7xt7g5dxsac9kuexlnu4rrtnnla5kum
    Trading fee
    Transferred from BTC Savings wallet
    '''

    prev_txn = None
    for data_row in data_rows:
        row_dict = data_row.row_dict
        print(row_dict)
        # 5446115377427084498,10680,2021-05-01 23:04:40,"Sold 0.0007 BTC/GBP @ 41,966.92",XBT,-0.00070000,0.00000000,0.00388333,0.00268333,,,GBP,29.37

        data_row.timestamp = DataParser.parse_timestamp(row_dict['Timestamp (UTC)'])

        # Crypto received
        if row_dict['Description'].startswith('Received '):
            data_row.t_record = TransactionOutRecord(
                TrType.DEPOSIT,
                data_row.timestamp,
                buy_quantity=abs(Decimal(row_dict['Balance delta'])),
                buy_asset='BTC' if row_dict['Currency'] == 'XBT' else row_dict['Currency'],
                wallet=WALLET,
                note='Description = {}'.format(row_dict['Description'])
            )
            continue

        # Crypto sent
        if row_dict['Description'].startswith('Sent '):
            data_row.t_record = prev_txn = TransactionOutRecord(
                TrType.WITHDRAWAL,
                data_row.timestamp,
                sell_quantity=abs(Decimal(row_dict['Balance delta'])),
                sell_asset='BTC' if row_dict['Currency'] == 'XBT' else row_dict['Currency'],
                wallet=WALLET,
                note='Description = {}'.format(row_dict['Description'])
            )
            continue

        # Fiat received
        if row_dict['Description'] == 'Deposit received':
            data_row.t_record = TransactionOutRecord(
                TrType.DEPOSIT,
                data_row.timestamp,
                buy_quantity=abs(Decimal(row_dict['Balance delta'])),
                buy_asset=row_dict['Currency'],
                wallet=WALLET,
                note='Description = {}'.format(row_dict['Description'])
            )
            continue

        # Fiat sent
        if row_dict['Description'].startswith('Payment sent to'):
            data_row.t_record = TransactionOutRecord(
                TrType.WITHDRAWAL,
                data_row.timestamp,
                sell_quantity=abs(Decimal(row_dict['Balance delta'])),
                sell_asset=row_dict['Currency'],
                wallet=WALLET,
                note='Description = {}'.format(row_dict['Description'])
            )
            continue

        if not (row_dict['Description'].startswith(('Bought', 'Sold', 'Trading fee'))
                or row_dict['Description'].endswith(' send fee')):
            continue;

        # A Trading fee or crypto send fee is on the subsequent row to the trade/send, hence the need to use all_handler.
        if row_dict['Description'] == 'Trading fee' or row_dict['Description'].endswith(' send fee'):
            if prev_txn.timestamp != data_row.timestamp:
                # I have seen a 1s difference before
                print('Warning: trade fee timestamp different to previous transaction {} != {}', data_row.timestamp, prev_txn.timestamp)

            prev_txn.fee_quantity = abs(Decimal(row_dict['Balance delta']))
            prev_txn.fee_asset = 'BTC' if row_dict['Currency'] == 'XBT' else row_dict['Currency']

            # > If the Fee Asset is the same as Sell Asset, then the Sell Quantity must be the net amount (after fee deduction), not gross amount.
            # > If the Fee Asset is the same as Buy Asset, then the Buy Quantity must be the gross amount (before fee deduction), not net amount.
            # > It is important that any withdrawal fee paid is specified, the withdrawal quantity should be the net amount (after fee deduction).
            if prev_txn.fee_asset == prev_txn.sell_asset:
                prev_txn.sell_quantity -= prev_txn.fee_quantity

            continue;

        # Instant trades have different description:
        #   Bought BTCÂ 0.00272219 for GBPÂ 101.00
        # or
        #   Sold BTCÂ 0.003 for Â£234.83

        # Eugh. A different syntax.
        # TODO fix properly not ignore
        # 
        # TODO instant trades have an inbuilt fee 1.5% vs fiat, 2% vs crypto, not a separate line item.
        # Can I break out a separate fee?
        if ' for ' in row_dict['Description']:
            continue


        # "Bought 0.001 BTC/GBP @ 25,000.01"
        #  0      1     2       3 4
        desc = row_dict['Description'].split()
        assets = desc[2].split('/')
        [base_asset, quote_asset] = assets

        '''
        Trading fees are charged in the base currency.
        Therefore - ignore the trade listed in the quote currency's wallet.
          Eg BTCGBP trade will be listed in _both_ the downloads of the BTC wallet and GBP wallet.
          But the trade fee will only appear in the BTC wallet.
        '''
        if quote_asset == row_dict['Currency']:
            continue

        [buy_asset, sell_asset] = assets if row_dict['Description'].startswith('Bought') else reversed(assets)
        base_quantity = Decimal(desc[1])
        quote_price = Decimal(desc[4].replace(',', ''))
        quote_quantity = base_quantity * quote_price
        quantities = [base_quantity, quote_quantity]
        [buy_quantity, sell_quantity] = quantities if row_dict['Description'].startswith('Bought') else reversed(quantities)

         # prev_row = {
         #        'date': row[2],
         #        'pair': desc[2].replace('/', ''),
         #        'side': 'Buy' if desc[0] == 'Bought' else 'Sell',
         #        'amount': desc[1],
         #        'total': float(desc[1]) * float(desc[4].replace(',', '')),
         #        'fee': '',
         #        'fee_ccy': ''
        
        # TODO
        # If GBP is one of the assets we know the values
        # if 'GBP' in assets:
        #    buy_value
        #    sell_value
        #    fee_value
        data_row.t_record = prev_txn = TransactionOutRecord(
            TrType.TRADE,
            data_row.timestamp,
            buy_quantity=buy_quantity,
            buy_asset=buy_asset,
            sell_quantity=sell_quantity,
            sell_asset=sell_asset,
            # fee_quantity=fee_quantity, << maybe set on next row
            # fee_asset=fee_asset, << maybe set on next row
            # buy_value=buy_value,
            # sell_value=sell_value,
            # fee_value=fee_value,
            wallet=WALLET,
            note='Description = {}'.format(row_dict['Description'])
        )

    # TODO promo

# TODO might need to split into a V1 and V2 to support different columns
DataParser(ParserType.EXCHANGE,
           WALLET,
           [
           'Wallet ID',
           'Row',
           'Timestamp (UTC)',
           'Description',
           'Currency',
           'Balance delta',
           'Available balance delta',
           'Balance',
           'Available balance',
           'Cryptocurrency transaction ID',
           'Cryptocurrency address',
           # There are three formats:
           # Oldest has single "Value" column.
           # At some point that was split into two for currency amount
           # Later, the Reference column was added.
           'Value currency',
           'Value amount',
           'Reference'
           ],
           worksheet_name=WALLET,
           all_handler=parse_luno)
