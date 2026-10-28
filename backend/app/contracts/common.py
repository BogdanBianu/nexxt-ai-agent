"""Tipuri de bază reutilizate în toate contractele."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Bani: intern Decimal (NICIODATĂ float în calcule), în JSON număr cu 2 zecimale.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(Decimal(v).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    return_type=float, when_used="json"),
]


def money(value) -> Decimal:
    """Convertește orice (str/int/float/Decimal) într-un Decimal rotunjit la 2 zecimale."""
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


class Contract(BaseModel):
    """Baza tuturor contractelor: câmpuri necunoscute = eroare (prinde greșelile de integrare)."""
    model_config = ConfigDict(extra="forbid", use_enum_values=False)
