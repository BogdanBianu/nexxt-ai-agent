"""Contractul unui modul juridic + registrul de module. Proprietar: Om1.

Ca să adăugați un modul nou (ex. „sechestre”): creați app/modules/<nume>/module.py
cu o clasă care respectă `LegalModule` și înregistrați-o în `_build_registry()`.
"""
from typing import Protocol

from app.contracts import BankSnapshot, Case, DocType, ModuleInfo, ModuleStatus, ReviewAction
from app.core.events import EmitFn


class LegalModule(Protocol):
    info: ModuleInfo

    def process(self, case: Case, bank: BankSnapshot, emit: EmitFn,
                review: ReviewAction | None = None) -> Case:
        """Procesează dosarul și întoarce dosarul actualizat (decizie, excepții, outcome)."""
        ...


class RoadmapModule:
    """Modul declarat, dar neimplementat: arată viziunea de platformă la demo."""

    def __init__(self, info: ModuleInfo):
        self.info = info

    def process(self, case, bank, emit, review=None):
        raise NotImplementedError(self.info.module_id)


def _build_registry() -> dict[str, LegalModule]:
    from app.modules.autoritati.module import AutoritatiModule
    from app.modules.gdpr.module import GdprModule
    from app.modules.popriri.module import PopririModule
    modules: list[LegalModule] = [
        PopririModule(),
        AutoritatiModule(),
        RoadmapModule(ModuleInfo(
            module_id="sechestre", name="Sechestre asigurătorii",
            description="Sechestre dispuse în procese civile și penale.",
            status=ModuleStatus.ROADMAP)),
        RoadmapModule(ModuleInfo(
            module_id="insolventa", name="Insolvență și succesiuni",
            description="Notificări de deschidere a procedurii de insolvență, certificate de moștenitor.",
            status=ModuleStatus.ROADMAP)),
        GdprModule(),
    ]
    return {m.info.module_id: m for m in modules}


_REGISTRY: dict[str, LegalModule] | None = None


def registry() -> dict[str, LegalModule]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def module_for(doc_type: DocType) -> LegalModule | None:
    return next((m for m in registry().values() if doc_type in m.info.handled_doc_types), None)
