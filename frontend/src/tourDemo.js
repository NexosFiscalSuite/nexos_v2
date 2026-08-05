// Modo demonstração do tour: uma "Empresa Exemplo" com dados FICTÍCIOS que
// vivem só NESTE navegador. Enquanto o modo está ativo:
//   • escritas reais são bloqueadas; as correções do TOUR (Não há CT-e /
//     Não há acordo / Reprocessar) são SIMULADAS aqui — o estado muda só na
//     memória deste navegador e a pessoa VÊ a pendência virar valor;
//   • leituras da empresa exemplo são respondidas localmente, sem tocar o
//     servidor — várias pessoas simultâneas sem conflito;
//   • cada início de tour reseta tudo (nada persiste, nem um F5 segura).
// Os números partem do caso-gabarito do motor (autopeça SP→MG).

export const DEMO_EMPRESA = {
  id: 'tour-demo',
  razao_social: 'Empresa Exemplo (tour)',
  cnpj: '00000000000191',
  uf: 'MG',
  regime: 'Normal',
}

let ativo = false
// O que o usuário "corrigiu" durante o tour (reset a cada início).
let estado = { semCte: false, semAcordo: false }

export const demoAtivo = () => ativo
export const ativarDemo = () => { ativo = true; estado = { semCte: false, semAcordo: false } }
export const desativarDemo = () => { ativo = false }
export const TOUR_ADVANCE_EVENT = 'sol-tour:advance-after-action'

const CHAVE_1 = '1'.repeat(44)
const CHAVE_2 = '2'.repeat(44)
const CHAVE_3 = '4'.repeat(44)
const CHAVE_CTE = '3'.repeat(44)

const base = {
  uf_destino: 'MG', fluxo: 'entrada', data_emissao: '2026-07-15',
  cst_csosn: '10', mod_bc_st: 4, pmva_xml: 0, vfcp_st_xml: 0,
  vfcp_st_calculado: 0, observacao: null, triagem: null,
}

// Nota 1 — DIVERGENTE com CT-e vinculado (o exemplo de CT-e no cálculo).
const NOTA1_ITEM = {
  ...base,
  chave_acesso: CHAVE_1, nota_id: 'tour-demo-nota1', numero_item: 1,
  descricao: 'Pneu novo para automóvel de passageiros (EXEMPLO)',
  codigo: 'EX-1', ncm: '40111000', cest: '1600100', numero_nota: '101',
  fornecedor: 'Fornecedor Exemplo S.A.', cnpj_emit: '00000000000272',
  uf_origem: 'SP', pmva_calculada: 84.35,
  vbc_st_xml: 0, vbc_st_calculado: 1473.69,
  vicms_st_xml: 0, vicms_st_calculado: 177.5, diferenca: -177.5,
  status: 'DIVERGENTE', codigo_erro: 'ERRO_104_VALOR_ST_DIVERGENTE',
  ctes_vinculados: [CHAVE_CTE],
  memoria: {
    mva_original: '71.78', mva_aplicada: '84.35', mva_foi_ajustada: true,
    alq_intra: '18.00', alq_inter: '12.00', base_st_calculada: '1473.69',
    custo_produto: '731.35', custo_frete: '68.05', custo_frete_cte: '68.05',
    custo_seguro: '0', custo_outras: '0', custo_ipi: '0', custo_desconto: '0',
    icms_st_debito: '265.26', deducao_aplicada: '87.76', deducao_tipo: 'real',
    icms_st_calculado: '177.50', fcp_st_debito: '0',
    mva_base_legal: 'RICMS/MG 2023, Anexo VII (dado de exemplo)',
    aliquota_base_legal: 'Lei 6.763/1975, art. 12 (dado de exemplo)',
  },
}

// Nota 2 — pendência de CT-e; corrigida, vira divergência calculada SEM frete.
const nota2Item = () => (estado.semCte ? {
  ...base,
  chave_acesso: CHAVE_2, nota_id: 'tour-demo-nota2', numero_item: 1,
  descricao: 'Pneu para caminhonete (EXEMPLO)',
  codigo: 'EX-2', ncm: '40111000', cest: '1600100', numero_nota: '102',
  fornecedor: 'Transportes & Peças Exemplo Ltda', cnpj_emit: '00000000000353',
  uf_origem: 'SP', pmva_calculada: 84.35,
  vbc_st_xml: 0, vbc_st_calculado: 1348.24,
  vicms_st_xml: 0, vicms_st_calculado: 154.92, diferenca: -154.92,
  status: 'DIVERGENTE', codigo_erro: 'ERRO_104_VALOR_ST_DIVERGENTE',
  ctes_vinculados: [],
  memoria: {
    mva_original: '71.78', mva_aplicada: '84.35', mva_foi_ajustada: true,
    alq_intra: '18.00', alq_inter: '12.00', base_st_calculada: '1348.24',
    custo_produto: '731.35', custo_frete: '0', custo_frete_cte: '0',
    custo_seguro: '0', custo_outras: '0', custo_ipi: '0', custo_desconto: '0',
    icms_st_debito: '242.68', deducao_aplicada: '87.76', deducao_tipo: 'real',
    icms_st_calculado: '154.92', fcp_st_debito: '0',
    mva_base_legal: 'RICMS/MG 2023, Anexo VII (dado de exemplo)',
    aliquota_base_legal: 'Lei 6.763/1975, art. 12 (dado de exemplo)',
  },
} : {
  ...base,
  chave_acesso: CHAVE_2, nota_id: 'tour-demo-nota2', numero_item: 1,
  descricao: 'Pneu para caminhonete (EXEMPLO)',
  codigo: 'EX-2', ncm: '40111000', cest: '1600100', numero_nota: '102',
  fornecedor: 'Transportes & Peças Exemplo Ltda', cnpj_emit: '00000000000353',
  uf_origem: 'SP', pmva_calculada: 0,
  vbc_st_xml: 0, vbc_st_calculado: 0,
  vicms_st_xml: 0, vicms_st_calculado: 0, diferenca: 0,
  status: 'NAO_AUDITAVEL', codigo_erro: 'ERRO_FRETE_PENDENTE_CTE',
  observacao: 'Frete por conta do destinatário sem CT-e vinculado — importe o CT-e ou confirme que não há.',
  ctes_vinculados: [], memoria: null,
})

// Nota 3 — GO→MG sem curadoria de protocolo; corrigida ("não há acordo"),
// vira ANTECIPAÇÃO do destinatário (ERRO_111).
const nota3Item = () => (estado.semAcordo ? {
  ...base,
  chave_acesso: CHAVE_3, nota_id: 'tour-demo-nota3', numero_item: 1,
  descricao: 'Câmara de ar (EXEMPLO)',
  codigo: 'EX-3', ncm: '40131000', cest: '1600900', numero_nota: '103',
  fornecedor: 'Distribuidora Exemplo GO', cnpj_emit: '00000000000434',
  uf_origem: 'GO', pmva_calculada: 59.6,
  vbc_st_xml: 0, vbc_st_calculado: 498.4,
  vicms_st_xml: 0, vicms_st_calculado: 89.3, diferenca: -89.3,
  status: 'DIVERGENTE', codigo_erro: 'ERRO_111_ANTECIPACAO_DESTINATARIO',
  observacao: 'Sem acordo GO→MG: a antecipação é obrigação do próprio cliente (guia local).',
  ctes_vinculados: [], memoria: null,
} : {
  ...base,
  chave_acesso: CHAVE_3, nota_id: 'tour-demo-nota3', numero_item: 1,
  descricao: 'Câmara de ar (EXEMPLO)',
  codigo: 'EX-3', ncm: '40131000', cest: '1600900', numero_nota: '103',
  fornecedor: 'Distribuidora Exemplo GO', cnpj_emit: '00000000000434',
  uf_origem: 'GO', pmva_calculada: 0,
  vbc_st_xml: 0, vbc_st_calculado: 0,
  vicms_st_xml: 0, vicms_st_calculado: 0, diferenca: 0,
  status: 'NAO_AUDITAVEL', codigo_erro: 'ERRO_PROTOCOLO_NAO_AVALIADO',
  observacao: 'Par GO→MG sem curadoria: registre o acordo (ou a ausência dele) na matriz de Protocolos.',
  ctes_vinculados: [], memoria: null,
})

function montarDivergencias() {
  const itens = [NOTA1_ITEM, nota2Item(), nota3Item()]
  const aRecolher = 177.5 + (estado.semCte ? 154.92 : 0)
  const antecipacao = estado.semAcordo ? 89.3 : 0
  const naoAuditaveis = (estado.semCte ? 0 : 1) + (estado.semAcordo ? 0 : 1)
  return {
    total: itens.length, page: 1, page_size: 200, itens,
    resumo: {
      a_recolher: Math.round(aRecolher * 100) / 100, a_favor: 0,
      antecipacao, divergentes: itens.length - naoAuditaveis,
      nao_auditaveis: naoAuditaveis,
      triagem: { EM_ABERTO: itens.length - naoAuditaveis },
    },
    ranking_fornecedores: [
      { cnpj: '00000000000272', nome: 'Fornecedor Exemplo S.A.', itens: 1, valor: 177.5 },
      ...(estado.semCte
        ? [{ cnpj: '00000000000353', nome: 'Transportes & Peças Exemplo Ltda', itens: 1, valor: 154.92 }]
        : []),
    ],
  }
}

const clonar = (v) => JSON.parse(JSON.stringify(v))

// Intercepta as chamadas do modo demonstração. `null` = segue ao servidor.
export function responderDemo(method, path) {
  if (!ativo) return null

  if (method !== 'GET') {
    // Correções do PRÓPRIO tour: simuladas aqui (nada vai ao servidor).
    if (path.includes('tour-demo') && path.includes('/confirmar-sem-cte')) {
      estado.semCte = true
      return Promise.resolve({ confirmado: true, por: 'você (demonstração)' })
    }
    if (path.startsWith('/matrizes/protocolos')) {
      estado.semAcordo = true
      return Promise.resolve({ id: 0, situacao: 'SEM_ACORDO' })
    }
    if (path.startsWith('/auditoria/st/reprocessar-pendentes')) {
      return Promise.resolve({
        notas_reprocessadas: 1, notas_destravadas: 1, cfop_reclassificados: 0,
      })
    }
    return Promise.reject(new Error(
      'Modo demonstração: nada é salvo nem enviado. Conclua o tour (ou feche no X) para operar de verdade.'
    ))
  }

  if (!path.includes('tour-demo')) return null   // leitura de dados reais: passa

  if (path.startsWith('/auditoria/st/divergencias')) {
    return Promise.resolve(clonar(montarDivergencias()))
  }
  // Outras telas da empresa exemplo: resposta vazia inofensiva.
  return Promise.resolve({
    itens: [], total: 0, total_itens: 0, page: 1, page_size: 200,
    resumo: {}, grupos: [], quebras: [], ranking_fornecedores: [],
  })
}
