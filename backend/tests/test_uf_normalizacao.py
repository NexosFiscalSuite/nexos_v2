"""UF é campo controlado, não texto livre — em TODAS as matrizes.

Linha gravada com a UF fora do padrão ("Minas Gerais", "mg ", "XX") é linha que
o motor NUNCA encontra: ele compara com a sigla de 2 letras que vem do XML. A
regra fica no banco e o cálculo sai errado do mesmo jeito — por isso a entrada é
generosa (aceita o que o humano digita) e a gravação é sempre canônica.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.fiscal.api.matrizes_schemas import (
    MatrizAliquotaCreate,
    MatrizEnquadramentoCreate,
    MatrizFcpCreate,
    MatrizMvaCreate,
    MatrizProtocoloCreate,
    ufs_disponiveis,
)

_VIGENCIA = {"data_inicio_vigencia": date(2026, 1, 1)}


def _mva(**kw) -> MatrizMvaCreate:
    return MatrizMvaCreate(
        **{"ncm": "40111000", "cest": "0100500", "uf_destino": "MG",
           "mva_original": "42.00", **_VIGENCIA, **kw}
    )


def _enquadramento(**kw) -> MatrizEnquadramentoCreate:
    return MatrizEnquadramentoCreate(
        **{"ncm": "40111000", "cest": "0100500", "uf_destino": "MG",
           "regime": "ST", **_VIGENCIA, **kw}
    )


def _fcp(**kw) -> MatrizFcpCreate:
    return MatrizFcpCreate(**{"uf_destino": "MG", "aliq_fcp_st": "2.00", **_VIGENCIA, **kw})


def _aliquota(**kw) -> MatrizAliquotaCreate:
    return MatrizAliquotaCreate(**{"uf_destino": "MG", "aliq_modal": "18.00", **_VIGENCIA, **kw})


def _protocolo(**kw) -> MatrizProtocoloCreate:
    return MatrizProtocoloCreate(
        **{"uf_origem": "SP", "uf_destino": "MG",
           "numero_acordo": "Protocolo ICMS 41/2008", **_VIGENCIA, **kw}
    )


# Todas as fábricas de matriz — o validador tem de valer para as CINCO.
_FABRICAS = [_mva, _enquadramento, _fcp, _aliquota, _protocolo]


@pytest.mark.parametrize("fabrica", _FABRICAS)
@pytest.mark.parametrize("digitado", ["mg", "MG", " MG ", "Minas Gerais", "minas gerais",
                                      "MINAS GERAIS", "Minas gerais"])
def test_uf_destino_aceita_como_o_humano_digita_e_grava_a_sigla(fabrica, digitado):
    assert fabrica(uf_destino=digitado).normalizado()["uf_destino"] == "MG"


@pytest.mark.parametrize("fabrica", _FABRICAS)
@pytest.mark.parametrize("lixo", ["XX", "Minas", "", "   ", "MGG", "Estado de Minas"])
def test_uf_destino_recusa_o_que_nao_da_para_reconhecer(fabrica, lixo):
    """Fail-closed: sem certeza do estado, erro — nunca aproximação."""
    with pytest.raises(ValidationError) as exc:
        fabrica(uf_destino=lixo)
    assert "uf_destino" in str(exc.value)


def test_mensagem_de_erro_e_para_leigo():
    with pytest.raises(ValidationError) as exc:
        _mva(uf_destino="XX")
    assert "UF inválida: use a sigla do estado (ex.: MG)" in str(exc.value)


def test_acento_do_nome_por_extenso_nao_atrapalha():
    assert _mva(uf_destino="São Paulo").normalizado()["uf_destino"] == "SP"
    assert _mva(uf_destino="sao paulo").normalizado()["uf_destino"] == "SP"
    assert _mva(uf_destino="Espírito Santo").normalizado()["uf_destino"] == "ES"
    assert _mva(uf_destino="goias").normalizado()["uf_destino"] == "GO"


# ── UF de origem da MVA ──────────────────────────────────────────────────────
def test_mva_sem_uf_origem_vale_para_qualquer_origem():
    """Cadastro antigo (só destino) continua funcionando como regra geral."""
    assert _mva().normalizado()["uf_origem"] == "*"


def test_mva_aceita_curinga_e_sigla_na_origem():
    assert _mva(uf_origem="*").normalizado()["uf_origem"] == "*"
    assert _mva(uf_origem="sp").normalizado()["uf_origem"] == "SP"
    assert _mva(uf_origem="São Paulo").normalizado()["uf_origem"] == "SP"


@pytest.mark.parametrize("lixo", ["XX", "", "qualquer", "**"])
def test_mva_recusa_origem_invalida(lixo):
    with pytest.raises(ValidationError) as exc:
        _mva(uf_origem=lixo)
    assert "uf_origem" in str(exc.value)


def test_curinga_nao_serve_para_uf_de_destino():
    """A nota SEMPRE tem um destino concreto — '*' ali é regra inalcançável."""
    with pytest.raises(ValidationError):
        _mva(uf_destino="*")
    with pytest.raises(ValidationError):
        _aliquota(uf_destino="*")


def test_protocolo_nao_aceita_curinga_na_origem():
    """O acordo é de um PAR de estados e a busca compara a origem por
    igualdade: um '*' aqui nunca casaria com nota nenhuma."""
    with pytest.raises(ValidationError) as exc:
        _protocolo(uf_origem="*")
    assert "uf_origem" in str(exc.value)

    # Mas o par escrito de qualquer jeito é normalizado.
    d = _protocolo(uf_origem="são paulo", uf_destino="mg").normalizado()
    assert (d["uf_origem"], d["uf_destino"]) == ("SP", "MG")


# ── Lista de UFs que alimenta os dropdowns ───────────────────────────────────
def test_lista_de_ufs_tem_as_27_em_ordem_alfabetica():
    ufs = ufs_disponiveis()
    assert len(ufs) == 27                                  # 26 estados + DF
    siglas = [u.sigla for u in ufs]
    assert siglas == sorted(siglas)
    assert siglas[0] == "AC" and siglas[-1] == "TO"
    assert "DF" in siglas
    assert ufs[siglas.index("MG")].nome == "Minas Gerais"


def test_lista_de_ufs_nao_oferece_o_curinga():
    """'*' é opção do campo de ORIGEM da MVA, não uma UF do dropdown."""
    assert all(u.sigla != "*" for u in ufs_disponiveis())


def test_toda_sigla_da_lista_passa_na_validacao():
    """Prova o contrato com o front: o que o dropdown oferece, a API aceita."""
    for uf in ufs_disponiveis():
        assert _mva(uf_destino=uf.sigla).normalizado()["uf_destino"] == uf.sigla
        assert _mva(uf_destino=uf.nome).normalizado()["uf_destino"] == uf.sigla


# ── Contrato de rota com o front ─────────────────────────────────────────────
async def test_endpoint_de_ufs_devolve_sigla_e_nome():
    """GET /matrizes/ufs — o front monta os dropdowns a partir DESTA lista."""
    from app.modules.fiscal.api.matrizes_routers import listar_ufs

    ufs = await listar_ufs(claims=None)
    assert [u.model_dump() for u in ufs][:2] == [
        {"sigla": "AC", "nome": "Acre"}, {"sigla": "AL", "nome": "Alagoas"},
    ]


def test_rota_de_ufs_registrada_no_caminho_combinado():
    from app.modules.fiscal.api.matrizes_routers import router

    caminhos = {r.path for r in router.routes}
    assert "/matrizes/ufs" in caminhos


def test_listagem_de_matriz_aceita_filtro_por_uf_de_origem():
    """Sem o filtro, a tela não consegue separar a regra geral do par curado."""
    from app.modules.fiscal.api.matrizes_routers import router

    listar_mva = next(r for r in router.routes if r.path == "/matrizes/mva"
                      and "GET" in r.methods)
    params = {p.name for p in listar_mva.dependant.query_params}
    assert {"uf", "uf_origem", "ncm", "cest"} <= params


def test_filtro_de_uf_aceita_nome_por_extenso():
    from app.modules.fiscal.api.matrizes_routers import _sigla_do_filtro

    assert _sigla_do_filtro("Minas Gerais") == "MG"
    assert _sigla_do_filtro(" mg ") == "MG"
    assert _sigla_do_filtro("*") == "*"
    # Busca sem sentido não estoura: vira comparação que não casa com nada.
    assert _sigla_do_filtro("zzz") == "ZZZ"


# ── Leitura: linha legada gravada torta precisa APARECER na tela ─────────────
def test_resposta_nao_revalida_uf_para_o_curador_poder_corrigir():
    """Se o schema de leitura rejeitasse a UF fora do padrão, a linha legada
    sumiria da tela e ninguém conseguiria consertá-la."""
    from app.modules.fiscal.api.matrizes_schemas import MatrizMvaResponse

    legada = MatrizMvaResponse(
        id=1, ncm="40111000", cest="0100500", uf_origem="*",
        uf_destino="Minas Gerais", mva_original="42.00", **_VIGENCIA,
    )
    assert legada.uf_destino == "Minas Gerais"
