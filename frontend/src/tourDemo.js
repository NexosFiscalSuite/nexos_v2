// Modo demonstração do tour: uma "Empresa Exemplo" com dados FICTÍCIOS que
// vivem só NESTE navegador. Enquanto o modo está ativo:
//   • toda ESCRITA (upload, cadastros, triagem…) é bloqueada com aviso —
//     ninguém trava nada nem suja a base fazendo o tour;
//   • as LEITURAS da empresa exemplo são respondidas aqui mesmo, sem tocar o
//     servidor — várias pessoas podem fazer o tour ao mesmo tempo sem se
//     atrapalhar, e cada início recomeça do zero (nada persiste).
// Os números são os do caso-gabarito do motor (autopeça SP→MG): MVA 71,78%
// ajustada para 84,35%, base R$ 1.473,69, ST devido R$ 177,50.

export const DEMO_EMPRESA = {
  id: 'tour-demo',
  razao_social: 'Empresa Exemplo (tour)',
  cnpj: '00000000000191',
  uf: 'MG',
  regime: 'Normal',
}

let ativo = false
export const demoAtivo = () => ativo
export const ativarDemo = () => { ativo = true }
export const desativarDemo = () => { ativo = false }

const CHAVE_NFE = '1'.repeat(44)
const CHAVE_CTE = '3'.repeat(44)

const ITEM_DIVERGENTE = {
  chave_acesso: CHAVE_NFE, nota_id: 'tour-demo-nota', numero_item: 1,
  descricao: 'Pneu novo para automóvel de passageiros (EXEMPLO)',
  codigo: 'EX-1', ncm: '40111000', cest: '1600100',
  numero_nota: '123', fornecedor: 'Fornecedor Exemplo S.A.',
  cnpj_emit: '00000000000272', uf_origem: 'SP', uf_destino: 'MG',
  data_emissao: '2026-07-15', fluxo: 'entrada',
  cst_csosn: '10', mod_bc_st: 4,
  pmva_xml: 0, pmva_calculada: 84.35,
  vbc_st_xml: 0, vbc_st_calculado: 1473.69,
  vicms_st_xml: 0, vicms_st_calculado: 177.5, diferenca: -177.5,
  vfcp_st_xml: 0, vfcp_st_calculado: 0,
  status: 'DIVERGENTE', codigo_erro: 'ERRO_104_VALOR_ST_DIVERGENTE',
  observacao: null, triagem: null, ctes_vinculados: [CHAVE_CTE],
  memoria: {
    mva_original: '71.78', mva_aplicada: '84.35', mva_foi_ajustada: true,
    alq_intra: '18.00', alq_inter: '12.00',
    base_st_calculada: '1473.69',
    custo_produto: '731.35', custo_frete: '68.05', custo_frete_cte: '68.05',
    custo_seguro: '0', custo_outras: '0', custo_ipi: '0', custo_desconto: '0',
    icms_proprio_deduzido: '87.76', st_debito: '177.50', fcp_st_debito: '0',
    mva_base_legal: 'RICMS/MG 2023, Anexo VII (dado de exemplo)',
    aliquota_base_legal: 'Lei 6.763/1975, art. 12 (dado de exemplo)',
  },
}

const ITEM_PENDENTE = {
  ...ITEM_DIVERGENTE,
  numero_item: 2, codigo: 'EX-2',
  descricao: 'Pneu de carga (EXEMPLO) — frete aguardando CT-e',
  pmva_calculada: 0, vbc_st_calculado: 0, vicms_st_calculado: 0, diferenca: 0,
  status: 'NAO_AUDITAVEL', codigo_erro: 'ERRO_FRETE_PENDENTE_CTE',
  observacao: 'Frete por conta do destinatário sem CT-e vinculado — importe o CT-e ou confirme que não há.',
  memoria: null, ctes_vinculados: [],
}

const DIVERGENCIAS = {
  total: 2, page: 1, page_size: 200,
  itens: [ITEM_DIVERGENTE, ITEM_PENDENTE],
  resumo: {
    a_recolher: 177.5, a_favor: 0, antecipacao: 0,
    divergentes: 1, nao_auditaveis: 1,
    triagem: { EM_ABERTO: 1 },
  },
  ranking_fornecedores: [
    { cnpj: '00000000000272', nome: 'Fornecedor Exemplo S.A.', itens: 1, valor: 177.5 },
  ],
}

const clonar = (v) => JSON.parse(JSON.stringify(v))

// Intercepta as chamadas do modo demonstração. `null` = segue ao servidor.
export function responderDemo(method, path) {
  if (!ativo) return null
  if (method !== 'GET') {
    return Promise.reject(new Error(
      'Modo demonstração: nada é salvo nem enviado. Conclua o tour (ou feche no X) para operar de verdade.'
    ))
  }
  if (!path.includes('tour-demo')) return null   // leitura de dados reais: passa

  if (path.startsWith('/auditoria/st/divergencias')) {
    return Promise.resolve(clonar(DIVERGENCIAS))
  }
  // Qualquer outra tela da empresa exemplo: resposta vazia inofensiva (a
  // superfície cobre as formas comuns de lista/resumo das páginas).
  return Promise.resolve({
    itens: [], total: 0, total_itens: 0, page: 1, page_size: 200,
    resumo: {}, grupos: [], quebras: [], ranking_fornecedores: [],
  })
}
