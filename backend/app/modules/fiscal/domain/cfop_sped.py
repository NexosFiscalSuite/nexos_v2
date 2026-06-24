"""Mapeamento CFOP -> Tipo do Item SPED (Bloco 0200). Portado do V1.

CFOPs não listados retornam "" (o usuário preenche manualmente depois).
"""
TIPOS_SPED = [
    "Mercadoria para Revenda",
    "Materia-prima",
    "Embalagem",
    "Produto em Processo",
    "Produto Acabado",
    "Subproduto",
    "Produto Intermediario",
    "Material de Uso e Consumo",
    "Ativo Imobilizado",
    "Servicos",
    "Outros Insumos",
    "Outras",
]

CFOP_SPED_MAP = {
    "1102": "Mercadoria para Revenda", "2102": "Mercadoria para Revenda",
    "3102": "Mercadoria para Revenda", "1403": "Mercadoria para Revenda",
    "2403": "Mercadoria para Revenda",
    "1101": "Materia-prima", "2101": "Materia-prima", "3101": "Materia-prima",
    "1401": "Materia-prima", "2401": "Materia-prima",
    "1556": "Material de Uso e Consumo", "2556": "Material de Uso e Consumo",
    "3556": "Material de Uso e Consumo",
    "1551": "Ativo Imobilizado", "2551": "Ativo Imobilizado", "3551": "Ativo Imobilizado",
    "1352": "Servicos", "2352": "Servicos", "3352": "Servicos",
    "1932": "Servicos", "2932": "Servicos", "1933": "Servicos", "2933": "Servicos",
}


def sugerir_tipo_sped(cfop: str) -> str:
    if not cfop:
        return ""
    cfop_clean = "".join(c for c in str(cfop) if c.isdigit())
    return CFOP_SPED_MAP.get(cfop_clean, "")
