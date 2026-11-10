"""Sandbox only; provider payloads must never be logged or persisted."""
import json
import os
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from app.modules.bookings.rules import utcnow

BASE = 'https://sandbox.tappaysdk.com/tpc/'
class TapPayConfigurationError(RuntimeError): pass
class TapPayRequestError(RuntimeError): pass

def configured():
    return bool(os.getenv('TAPPAY_PARTNER_KEY') and os.getenv('TAPPAY_MERCHANT_ID')) and os.getenv('TAPPAY_ENDPOINT', BASE+'payment/pay-by-prime') == BASE+'payment/pay-by-prime'

def request(path, payload):
    if not configured(): raise TapPayConfigurationError('TapPay Sandbox 設定不完整或端點不符')
    key = os.environ['TAPPAY_PARTNER_KEY']
    req = Request(BASE+path, data=json.dumps({'partner_key': key, **payload}).encode(), headers={'Content-Type':'application/json','x-api-key':key}, method='POST')
    try:
        with urlopen(req, timeout=30) as response: result=json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise TapPayRequestError('TapPay 結果待查核') from None
    if not isinstance(result, dict): raise TapPayRequestError('TapPay 結果待查核')
    return result

def pay_by_prime(prime, order_number, amount, cardholder, bank_transaction_id):
    return request('payment/pay-by-prime', {'prime':prime,'merchant_id':os.environ['TAPPAY_MERCHANT_ID'],
        'order_number':order_number,'bank_transaction_id':bank_transaction_id,'details':'KINU TABI '+order_number,
        'amount':amount,'currency':'TWD','cardholder':cardholder,'remember':False,'three_domain_secure':False})

def records(order):
    now=utcnow()
    return request('transaction/query', {'records_per_page':50,'page':0,'filters':{
        'time':{'start_time':int(max(order['created_at']-timedelta(days=1),now-timedelta(days=89)).timestamp()*1000),'end_time':int(now.timestamp()*1000)},
        'merchant_id':[order['merchant_id']],
        **({'rec_trade_id':order['rec_trade_id']} if order.get('rec_trade_id') else {'bank_transaction_id':order['bank_transaction_id']})}})
