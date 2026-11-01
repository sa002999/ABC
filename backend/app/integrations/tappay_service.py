import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

TAPPAY_ENDPOINT = os.getenv(
    "TAPPAY_ENDPOINT", "https://sandbox.tappaysdk.com/tpc/payment/pay-by-prime"
)


class TapPayConfigurationError(RuntimeError):
    pass


class TapPayRequestError(RuntimeError):
    pass


def pay_by_prime(
    prime: str,
    order_number: str,
    amount: int,
    cardholder: dict[str, str],
) -> dict[str, Any]:
    partner_key = os.getenv("TAPPAY_PARTNER_KEY")
    merchant_id = os.getenv("TAPPAY_MERCHANT_ID")
    if not partner_key or not merchant_id:
        raise TapPayConfigurationError("TapPay 設定不完整")

    payload = {
        "prime": prime,
        "partner_key": partner_key,
        "merchant_id": merchant_id,
        "details": f"Taipei Day Trip {order_number}",
        "amount": amount,
        "cardholder": cardholder,
        "remember": False,
        "order_number": order_number,
    }
    request = Request(
        TAPPAY_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": partner_key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            result = json.loads(body)
        except json.JSONDecodeError:
            result = {"status": error.code, "msg": "TapPay 回應格式錯誤"}
        return (
            result
            if isinstance(result, dict)
            else {"status": error.code, "msg": "TapPay 付款失敗"}
        )
    except (URLError, TimeoutError) as error:
        raise TapPayRequestError("無法連線至 TapPay") from error

    try:
        result = json.loads(body)
    except json.JSONDecodeError as error:
        raise TapPayRequestError("TapPay 回應格式錯誤") from error

    if not isinstance(result, dict):
        raise TapPayRequestError("TapPay 回應格式錯誤")
    return result
