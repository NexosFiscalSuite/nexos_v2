"""Regra de classificação do regime via consulta optante (função pura).

A parte com sessão/RLS é integração (Fase 3, testcontainers); aqui validamos a
decisão de negócio: quem fica resolvido e quem vira ponto de observação.
"""
from app.modules.contrapartes.application.service import classificar_optante


def _ok(regime: str) -> dict:
    return {"ok": True, "dados": {"regime": regime}}


def test_simples_resolvido_nao_pendente():
    regime, pendente = classificar_optante(_ok("Simples Nacional"))
    assert regime == "Simples Nacional"
    assert pendente is False


def test_mei_resolvido_nao_pendente():
    regime, pendente = classificar_optante(_ok("MEI"))
    assert regime == "MEI"
    assert pendente is False


def test_normal_vira_ponto_de_observacao():
    # Não-Simples: optante não distingue Presumido/Real -> pendente para revisão.
    regime, pendente = classificar_optante(_ok("Normal"))
    assert regime == "Normal"
    assert pendente is True


def test_regime_vazio_assume_normal_pendente():
    regime, pendente = classificar_optante({"ok": True, "dados": {"regime": ""}})
    assert regime == "Normal"
    assert pendente is True


def test_lookup_falhou_mantem_pendente_sem_regime():
    regime, pendente = classificar_optante({"ok": False, "error": "CNPJ não encontrado"})
    assert regime is None
    assert pendente is True
