import os
from dataclasses import dataclass

from django.conf import settings


class PaymentGatewayError(Exception):
    pass


@dataclass
class PaymentGatewayConfig:
    provider: str
    enabled: bool
    merchant_id: str = ""
    password: str = ""
    store_id: str = ""
    signature: str = ""
    sandbox: bool = True


class BasePaymentGateway:
    provider_name = "base"

    def __init__(self, config):
        self.config = config

    @property
    def available(self):
        return bool(self.config.enabled and self.config.merchant_id)

    def create_payment(self, order, amount, **kwargs):
        if not self.available:
            raise PaymentGatewayError(f"{self.provider_name.title()} is not configured.")
        return {
            "provider": self.provider_name,
            "order_number": getattr(order, "number", ""),
            "amount": amount,
            "sandbox": self.config.sandbox,
            "status": "pending",
        }


class JazzCashGateway(BasePaymentGateway):
    provider_name = "jazzcash"


class EasypaisaGateway(BasePaymentGateway):
    provider_name = "easypaisa"


class CardGateway(BasePaymentGateway):
    provider_name = "card"


def get_payment_gateway(provider_name):
    name = (provider_name or "").lower()
    providers = getattr(settings, "MARKX", {}).get("PAYMENT_PROVIDERS", {})
    config_values = providers.get(name, {})
    if not config_values:
        return None
    config = PaymentGatewayConfig(
        provider=name,
        enabled=bool(config_values.get("enabled", False)),
        merchant_id=str(config_values.get("merchant_id", "")),
        password=str(config_values.get("password", "")),
        store_id=str(config_values.get("store_id", "")),
        signature=str(config_values.get("signature", "")),
        sandbox=bool(config_values.get("sandbox", True)),
    )
    if name == "jazzcash":
        return JazzCashGateway(config)
    if name == "easypaisa":
        return EasypaisaGateway(config)
    if name == "card":
        return CardGateway(config)
    return None
