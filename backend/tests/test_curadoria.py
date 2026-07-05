"""Regra pura de curadoria das matrizes (quem pode escrever a regra global)."""
from app.modules.fiscal.api.curadoria import curador_autorizado


def test_lista_vazia_mantem_comportamento_historico():
    """Sem NEXOS_MATRIZ_CURADORES configurado, qualquer ADMIN escreve."""
    assert curador_autorizado("qualquer@escritorio.com", []) is True
    assert curador_autorizado(None, []) is True


def test_lista_configurada_restringe_aos_curadores():
    permitidos = ["curador@sol.com.br"]
    assert curador_autorizado("curador@sol.com.br", permitidos) is True
    assert curador_autorizado("  CURADOR@sol.com.br ", permitidos) is True   # normaliza
    assert curador_autorizado("outro.admin@sol.com.br", permitidos) is False
    assert curador_autorizado(None, permitidos) is False
