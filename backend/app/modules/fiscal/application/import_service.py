"""Importação de XML: parse -> classifica fluxo -> guarda XML -> persiste nota.

Portado da lógica do upload do V1, agora rodando no WORKER (assíncrono) e sob
RLS. Dedupe por (empresa, chave). Eventos de cancelamento viram NotaEvento e
marcam a nota; se a nota ainda não existe, o evento fica "órfão".
"""
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import Storage, xml_key
from app.modules.cfop_rules.infrastructure.repositories import CfopRegraRepository
from app.modules.companies.infrastructure.models import Empresa
from app.modules.contrapartes.application.service import ContraparteService
from app.modules.contrapartes.infrastructure.models import TIPO_CLIENTE, TIPO_FORNECEDOR
from app.modules.fiscal.domain import parser as xmlparser
from app.modules.fiscal.domain.cfop_sped import sugerir_tipo_sped
from app.modules.fiscal.domain.flow import FlowRejected, classificar_fluxo
from app.modules.fiscal.infrastructure.models import (
    NfeCteVinculo,
    Nota,
    NotaEvento,
    NotaItem,
)
from app.modules.fiscal.infrastructure.repositories import NotaRepository


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _novo_resumo(total: int) -> dict:
    return {
        "total_arquivos": total,
        "importadas": 0,
        "importadas_por_fluxo": {},
        "competencias": {},
        "duplicadas": [],
        "canceladas": [],
        "correcoes": [],
        "eventos_orfaos": [],
        "rejeitadas": [],
        "erros": [],
    }


class ImportService:
    def __init__(self, session: AsyncSession, storage: Storage):
        self.session = session
        self.storage = storage
        self.repo = NotaRepository(session)
        self.contrapartes = ContraparteService(session)
        self._regras: dict = {}  # cfop_origem -> regra De/Para (carregado no import_staged)
        self.notas_auditaveis: list[UUID] = []  # NF-e/NFC-e p/ auditar ST após o lote

    async def import_staged(
        self, *, tenant_id: UUID, empresa: Empresa, user_id: UUID, staging: list[dict]
    ) -> dict:
        """staging: [{"key": <storage key>, "filename": <nome original>}]"""
        resumo = _novo_resumo(len(staging))
        # Regras De/Para CFOP -> Tipo de Item (uma vez por lote).
        self._regras = await CfopRegraRepository(self.session).as_map()
        for item in staging:
            nome = item.get("filename", "arquivo.xml")
            try:
                content = self.storage.get(item["key"])
            except Exception as e:
                resumo["erros"].append({"arquivo": nome, "erro": f"Falha ao ler upload: {e}"})
                continue
            await self._processar_arquivo(content, nome, tenant_id, empresa, user_id, resumo)
            try:
                self.storage.delete(item["key"])  # limpa o staging
            except Exception:
                pass
        return resumo

    async def _processar_arquivo(self, content, nome, tenant_id, empresa, user_id, resumo):
        try:
            notas = xmlparser.parse_xml_multi(content)
        except ValueError as e:
            resumo["erros"].append({"arquivo": nome, "erro": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            resumo["erros"].append({"arquivo": nome, "erro": f"Erro inesperado: {e}"})
            return

        for parsed in notas:
            if parsed.get("_erro"):
                resumo["erros"].append({"arquivo": nome, "erro": parsed["_erro"]})
            elif parsed.get("tipo") == "EventoCancelamento":
                await self._evento_cancelamento(parsed, tenant_id, empresa, resumo, nome)
            elif parsed.get("tipo") == "EventoCCe":
                await self._evento_cce(parsed, tenant_id, empresa, resumo, nome)
            else:
                await self._processar_nota(parsed, tenant_id, empresa, user_id, content, resumo, nome)

    async def _processar_nota(self, parsed, tenant_id, empresa, user_id, content, resumo, nome):
        try:
            fluxo = classificar_fluxo(parsed, empresa.cnpj)
        except FlowRejected as e:
            resumo["rejeitadas"].append(
                {"arquivo": nome, "motivo": str(e), "chave": parsed.get("chave_acesso", "")}
            )
            return

        chave = parsed.get("chave_acesso", "")
        if await self.repo.by_chave(empresa.id, chave):
            resumo["duplicadas"].append({"arquivo": nome, "chave": chave})
            return

        ano, mes = parsed.get("ano", ""), parsed.get("mes", "")
        key = xml_key(tenant_id, empresa.cnpj, ano, mes, chave)
        try:
            self.storage.put(key, content)
        except Exception as e:  # noqa: BLE001
            resumo["erros"].append({"arquivo": nome, "erro": f"Falha ao salvar XML: {e}"})
            return

        competencia = parsed.get("competencia") or (f"{ano}-{mes}" if ano and mes else None)
        status, cancelada_em = "ativa", None
        if parsed.get("_cancelada_inline"):
            status = "cancelada"
            cancelada_em = parsed.get("_cancelada_em") or datetime.now(UTC).isoformat()

        nota = Nota(
            id=uuid4(),
            tenant_id=tenant_id,
            empresa_id=empresa.id,
            chave_acesso=chave,
            tipo=parsed.get("tipo", ""),
            fluxo=fluxo,
            modelo=parsed.get("modelo", ""),
            serie=parsed.get("serie"),
            numero=parsed.get("numero"),
            cnpj_emit=parsed.get("cnpj_emit"),
            nome_emit=parsed.get("nome_emit"),
            uf_emit=parsed.get("uf_emit"),
            crt_emit=parsed.get("crt_emit"),
            cnpj_dest=parsed.get("cnpj_dest"),
            nome_dest=parsed.get("nome_dest"),
            uf_dest=parsed.get("uf_dest"),
            transportadora_cnpj=parsed.get("transportadora_cnpj"),
            transportadora_nome=parsed.get("transportadora_nome"),
            valor_total=_dec(parsed.get("valor_total")),
            data_emissao=parsed.get("data_emissao"),
            competencia=competencia,
            iss_retido=parsed.get("iss_retido"),
            ano=ano,
            mes=mes,
            storage_key=key,
            status=status,
            cancelada_em=cancelada_em,
            protocolo=parsed.get("protocolo"),
            uploaded_by=user_id,
        )
        self.repo.add(nota)
        await self.session.flush()  # garante que o próximo by_chave (mesma txn) veja a nota

        # NF-e/NFC-e entram na fila de auditoria de ST (rodada ao fim do lote,
        # quando os CT-e vinculados do mesmo lote já foram persistidos — ADR-0001).
        if parsed.get("tipo") in ("NFe", "NFCe"):
            self.notas_auditaveis.append(nota.id)

        is_entry = fluxo in ("entrada", "cte")
        for it in parsed.get("itens", []):
            cfop_xml = it.get("cfop", "")
            # De/Para CFOP -> Tipo de Item (só em entradas). Match no CFOP do XML;
            # se houver regra, reclassifica o CFOP p/ o destino e preenche o tipo.
            # cfop_original SEMPRE guarda o CFOP que veio no XML.
            regra = self._regras.get(re.sub(r"\D", "", cfop_xml)) if is_entry else None
            if regra:
                cfop_final = regra.cfop_destino or cfop_xml
                tipo_item = regra.tipo_item
            else:
                cfop_final = cfop_xml
                tipo_item = sugerir_tipo_sped(cfop_xml)
            self.repo.add_item(
                NotaItem(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    nota_id=nota.id,
                    numero_item=it.get("numero_item", 0),
                    codigo=it.get("codigo"),
                    descricao=it.get("descricao"),
                    ncm=it.get("ncm"),
                    cfop=cfop_final,
                    cfop_original=cfop_xml,  # preserva o CFOP original do XML
                    tipo_sped=tipo_item,
                    unidade=it.get("unidade"),
                    quantidade=_dec(it.get("quantidade")),
                    valor_unitario=_dec(it.get("valor_unitario")),
                    valor_total=_dec(it.get("valor_total")),
                    valor_produto=_dec(it.get("valor_produto") or it.get("valor_total")),
                    valor_desconto=_dec(it.get("valor_desconto")),
                    valor_frete=_dec(it.get("valor_frete")),
                    valor_seguro=_dec(it.get("valor_seguro")),
                    valor_outro=_dec(it.get("valor_outro")),
                    valor_ipi=_dec(it.get("valor_ipi")),
                    base_calculo=_dec(it.get("base_calculo")),
                    valor_icms=_dec(it.get("valor_icms")),
                    valor_icms_st=_dec(it.get("valor_icms_st")),
                    # tags de ST / FCP (insumos do motor de auditoria)
                    cest=it.get("cest"),
                    orig=it.get("orig"),
                    cst=it.get("cst") or None,
                    csosn=it.get("csosn") or None,
                    mod_bc_st=it.get("mod_bc_st"),
                    p_icms=_dec(it.get("p_icms")),
                    p_red_bc=_dec(it.get("p_red_bc")),
                    p_mva_st=_dec(it.get("p_mva_st")),
                    p_red_bc_st=_dec(it.get("p_red_bc_st")),
                    p_icms_st=_dec(it.get("p_icms_st")),
                    v_bc_st=_dec(it.get("v_bc_st")),
                    v_fcp=_dec(it.get("v_fcp")),
                    p_fcp=_dec(it.get("p_fcp")),
                    v_bc_fcp=_dec(it.get("v_bc_fcp")),
                    v_fcp_st=_dec(it.get("v_fcp_st")),
                    p_fcp_st=_dec(it.get("p_fcp_st")),
                    v_bc_fcp_st=_dec(it.get("v_bc_fcp_st")),
                    # IBS/CBS (destaque do ano-teste 2026)
                    cst_ibs_cbs=it.get("cst_ibs_cbs"),
                    v_bc_ibs_cbs=_dec(it.get("v_bc_ibs_cbs")),
                    p_ibs_uf=_dec(it.get("p_ibs_uf")),
                    v_ibs_uf=_dec(it.get("v_ibs_uf")),
                    p_ibs_mun=_dec(it.get("p_ibs_mun")),
                    v_ibs_mun=_dec(it.get("v_ibs_mun")),
                    p_cbs=_dec(it.get("p_cbs")),
                    v_cbs=_dec(it.get("v_cbs")),
                )
            )

        # ADR-0001: CT-e registra um vínculo por NF-e transportada (tolera órfão —
        # a NF-e pode ainda não existir). vTPrest fica no vínculo para a agregação.
        if parsed.get("tipo") == "CTe":
            for chave_nfe in parsed.get("chaves_nfe", []):
                self.repo.add_vinculo_cte(
                    NfeCteVinculo(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        empresa_id=empresa.id,
                        chave_nfe=chave_nfe,
                        chave_cte=chave,
                        vtprest=_dec(parsed.get("vtprest")),
                        tp_cte=parsed.get("tp_cte") or None,
                    )
                )
        await self.session.flush()

        # Auto-cadastro da contraparte (cliente em saída/serviço; fornecedor em
        # entrada/cte). Não chama API externa — só dados do XML. Falha aqui não
        # impede a importação da nota.
        try:
            if fluxo in ("saida", "servico"):
                await self.contrapartes.upsert_from_xml(
                    tenant_id=tenant_id, empresa_id=empresa.id, tipo=TIPO_CLIENTE,
                    cnpj=parsed.get("cnpj_dest", ""), nome=parsed.get("nome_dest", ""),
                    uf=parsed.get("uf_dest", ""),
                )
            elif fluxo in ("entrada", "cte"):
                await self.contrapartes.upsert_from_xml(
                    tenant_id=tenant_id, empresa_id=empresa.id, tipo=TIPO_FORNECEDOR,
                    cnpj=parsed.get("cnpj_emit", ""), nome=parsed.get("nome_emit", ""),
                    uf=parsed.get("uf_emit", ""),
                )
            await self.session.flush()
        except Exception:  # noqa: BLE001
            pass

        resumo["importadas"] += 1
        resumo["importadas_por_fluxo"][fluxo] = resumo["importadas_por_fluxo"].get(fluxo, 0) + 1
        if competencia:
            resumo["competencias"][competencia] = resumo["competencias"].get(competencia, 0) + 1

    async def _evento_cancelamento(self, parsed, tenant_id, empresa, resumo, nome):
        chave = parsed.get("chave_acesso", "")
        nota = await self.repo.by_chave(empresa.id, chave)
        self.repo.add_evento(
            NotaEvento(
                id=uuid4(),
                tenant_id=tenant_id,
                empresa_id=empresa.id,
                nota_id=nota.id if nota else None,
                chave_acesso=chave,
                tipo_evento="cancelamento",
                protocolo=parsed.get("protocolo_cancelamento"),
                data_evento=parsed.get("data_evento"),
                justificativa=parsed.get("justificativa"),
            )
        )
        if nota:
            nota.status = "cancelada"
            nota.cancelada_em = parsed.get("data_evento") or datetime.now(UTC).isoformat()
            if parsed.get("protocolo_cancelamento"):
                nota.protocolo = parsed.get("protocolo_cancelamento")
            resumo["canceladas"].append({"arquivo": nome, "chave": chave})
        else:
            resumo["eventos_orfaos"].append({"arquivo": nome, "chave": chave})
        await self.session.flush()

    async def _evento_cce(self, parsed, tenant_id, empresa, resumo, nome):
        """Carta de Correção: registra o evento e marca tem_correcao na nota."""
        chave = parsed.get("chave_acesso", "")
        nota = await self.repo.by_chave(empresa.id, chave)
        self.repo.add_evento(
            NotaEvento(
                id=uuid4(),
                tenant_id=tenant_id,
                empresa_id=empresa.id,
                nota_id=nota.id if nota else None,
                chave_acesso=chave,
                tipo_evento="cce",
                protocolo=parsed.get("protocolo_cancelamento"),
                data_evento=parsed.get("data_evento"),
                justificativa=parsed.get("justificativa"),
            )
        )
        if nota:
            nota.tem_correcao = True
            resumo["correcoes"].append({"arquivo": nome, "chave": chave})
        else:
            resumo["eventos_orfaos"].append({"arquivo": nome, "chave": chave})
        await self.session.flush()
