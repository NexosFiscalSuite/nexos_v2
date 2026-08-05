// Tour guiado de primeiro acesso (driver.js): escurece a tela, destaca um
// elemento por vez e BLOQUEIA o resto. Passos "práticos" não têm botão
// Próximo — a pessoa é obrigada a clicar no item destacado para avançar
// (o overlay impede qualquer outro clique). ESC/X fecham a qualquer momento.
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'

// Passo informativo (avança pelo botão Próximo).
const info = (element, title, description) => ({
  element,
  popover: { title, description },
})

// Passo prático: só o clique no elemento destacado avança.
const pratico = (element, title, description) => ({
  element,
  pratico: true,
  popover: {
    title,
    description: `${description}<br/><br/>👉 <b>Clique no item destacado para continuar.</b>`,
    showButtons: ['previous', 'close'],
  },
})

// Passo-aula: sem âncora (centralizado, mais largo) — o conteúdo didático
// sobre o cálculo e as matrizes, independente do que a tela tem carregado.
const aula = (title, description) => ({
  popover: { title, description, popoverClass: 'sol-tour sol-tour-aula' },
})

const PASSOS = [
  info('[data-tour="nav-dashboard"]', 'Bem-vindo ao Sol Contabilidade! ☀️',
    'Este é o <b>Dashboard</b>: a visão geral do escritório — volume de notas, saúde de cada cliente e impacto financeiro das divergências.'),
  info('[data-tour="topbar-competencia"]', 'Competência global 📅',
    'Este seletor define o <b>mês/ano</b> de tudo o que você vê. Trocou aqui, todas as telas obedecem.'),
  info('[data-tour="topbar-empresa"]', 'Empresa selecionada 🏢',
    'E este define <b>qual cliente</b> você está analisando. As telas de notas, divergências e IBS/CBS filtram por ele.'),
  pratico('[data-tour="nav-upload"]', 'Upload de XMLs',
    'Tudo começa aqui: é por onde os XMLs (NF-e, NFC-e, CT-e, NFS-e) entram no sistema.'),
  info('[data-tour="upload-area"]', 'A área de importação 📥',
    'Arraste vários XMLs de uma vez (ou clique para selecionar). O processamento roda em segundo plano: parse, classificação do fluxo e <b>auditoria de ST automática</b>.'),
  info('[data-tour="nav-documentos"]', 'Documentos Fiscais 🗂️',
    'Aqui dentro vivem as <b>Notas</b> importadas (com edição em lote, DANFE, XML), os <b>Relatórios</b> em Excel e o <b>De/Para de CFOP</b>.'),
  pratico('[data-tour="nav-conformidade"]', 'Conformidade',
    'Vamos conhecer a checagem de <b>quebras de sequência</b> na numeração das notas — o ponto vermelho no menu avisa quando há pendência.'),
  pratico('[data-tour="nav-divergencias-st"]', 'Divergências de ICMS-ST',
    'O coração fiscal do sistema: o motor recalcula a ST de cada item e mostra <b>quem errou, quanto e por quê</b> — com a memória de cálculo aberta para a defesa. Nos próximos passos, veja <b>como essa conta funciona</b>.'),

  // ── A aula do motor: como o ST é calculado ──
  aula('Como o motor calcula — os dois portões 🚪',
    'Antes de qualquer conta, o item precisa passar por dois portões:<br/><br/>'
    + '<b>1º — Enquadramento:</b> o produto (NCM + CEST) é de ST na UF de destino? '
    + 'A busca vai do específico ao geral: NCM com <b>8 → 6 → 4 dígitos</b> (a regra de capítulo cobre o que não tem regra própria).<br/><br/>'
    + '<b>2º — Protocolo (entre estados):</b> existe acordo obrigando o fornecedor a reter?<br/>'
    + '• <b>ATIVO</b> → o motor cobra a retenção;<br/>'
    + '• <b>SEM ACORDO</b> registrado → vira <b>antecipação do cliente</b> (não se cobra o fornecedor);<br/>'
    + '• <b>Sem registro</b> → o motor <b>trava e pede curadoria</b> — ele nunca adivinha.'),
  aula('A conta, passo a passo 🧮',
    '<b>Base própria</b> = produto + frete (inclusive o <b>CT-e vinculado</b>) + seguro + IPI − desconto.<br/><br/>'
    + '<b>MVA:</b> a matriz guarda a margem <b>original</b>; em operação interestadual o motor calcula a <b>ajustada</b> '
    + '(equaliza a carga, porque o ICMS veio com alíquota menor de outro estado). Ex.: 71,78% vira <b>84,35%</b> de SP→MG.<br/><br/>'
    + '<b>ST devido</b> = Base × (1 + MVA) × alíquota interna − ICMS próprio destacado (+ FCP quando houver).<br/><br/>'
    + '<b>Exemplo real:</b> item de R$ 731,35 + frete R$ 68,05 → base do ST R$ 1.473,69 → <b>R$ 177,50 a recolher</b>. '
    + 'O confronto com o XML tolera centavos — arredondamento não vira cobrança.'),
  aula('“Não auditável” não é erro — é honestidade 🔒',
    'Faltou matriz, protocolo ou CT-e? O motor <b>não chuta</b>: o item trava com um código que diz exatamente o que falta.<br/><br/>'
    + '• Clique no <b>selo colorido</b> do item → explicação em português + <b>ação sugerida</b> (com botão que resolve);<br/>'
    + '• <b>“Abrir memória de cálculo”</b> → a conta completa, com base legal — pronta para defender o número;<br/>'
    + '• Resolveu a pendência? <b>Reprocessar Pendentes</b> reaudita tudo.'),
  info('[data-tour="st-cards"]', 'O dinheiro em jogo 💰',
    'Os cards somam o período inteiro: <b>ST a recolher</b>, a favor e antecipações — clique num card para filtrar a lista. '
    + 'No <b>ranking</b>, gere a <b>Carta PDF</b> (pede a ciência da legislação e marca os itens como <b>“Cobrada”</b>) '
    + 'e registre o desfecho na <b>triagem</b> 🏷 (justificada/aceita).'),

  pratico('[data-tour="nav-ibs-cbs"]', 'IBS/CBS — Reforma Tributária 🧪',
    '2026 é o ano-teste da Reforma: aqui você fiscaliza o destaque de IBS/CBS dos fornecedores contra a tabela oficial.'),
  info('[data-tour="ibscbs-atualizar"]', 'Atualizar consulta 🔄',
    'Depois de importar XMLs de uma competência, clique aqui <b>uma vez</b> para reler os arquivos e preencher os dados de IBS/CBS das notas.'),

  // ── A aula das matrizes ──
  info('[data-tour="nav-cadastros-grp"]', 'Cadastros e Matrizes 📚',
    'Clientes/fornecedores e as <b>Matrizes Fiscais</b> — o combustível do motor. Os dois próximos passos explicam como essa base funciona.'),
  aula('As Matrizes Fiscais — o combustível ⛽',
    'Cinco tabelas globais respondem tudo o que o motor pergunta:<br/>'
    + '• <b>Enquadramento</b> — o produto é ST naquela UF?<br/>'
    + '• <b>Protocolos</b> — há acordo entre as UFs (e para qual produto)?<br/>'
    + '• <b>MVA</b> — qual margem aplicar?<br/>'
    + '• <b>Alíquotas</b> — a alíquota interna da UF (com FCP integrado);<br/>'
    + '• <b>FCP</b> — o adicional do Fundo de Combate à Pobreza.<br/><br/>'
    + '<b>Regra de ouro — vigência:</b> taxa que muda vira <b>linha nova</b> (encerra a antiga). '
    + 'O motor usa a regra <b>vigente na data de emissão da nota</b>: a MVA pode ser 40% para a nota de 2025 '
    + 'e 55% para a de 2026 — e as duas auditorias continuam defensáveis.'),
  aula('Robôs alimentam, você decide 🤖',
    'Robôs leem as fontes oficiais (CONFAZ, Anexo VII do RICMS/MG) e <b>propõem</b> atualizações na aba <b>Revisão</b> — '
    + 'o chip mostra quantas esperam. Nada entra sem aprovação, <b>linha cadastrada à mão nunca é tocada</b> '
    + 'e rejeitar uma proposta vale para sempre.<br/><br/>'
    + 'A aba <b>Saúde</b> é o radar: quanto da base foi verificado nos últimos 90 dias, a data que sai no aviso da carta '
    + 'e os <b>pares de UF pendentes</b> (com botão que abre o cadastro já preenchido). '
    + 'E a <b>Cobertura</b> mostra o que a carteira movimenta × o que falta cadastrar, por valor.'),

  info('[data-tour="topbar-ajuda"]', 'Pronto! 🎉',
    'Você conhece o essencial — inclusive como o cálculo funciona por dentro. Para <b>refazer este tour</b> a qualquer momento, clique neste botão de ajuda. Bom trabalho!'),
]

export function iniciarTour() {
  const d = driver({
    steps: PASSOS,
    showProgress: true,
    allowClose: true,
    overlayOpacity: 0.65,
    stagePadding: 6,
    popoverClass: 'sol-tour',   // visual do app (styles.css) por cima do default
    stageRadius: 10,
    nextBtnText: 'Próximo →',
    prevBtnText: '← Voltar',
    doneBtnText: 'Concluir',
    progressText: '{{current}} de {{total}}',
    onDestroyed: () => document.removeEventListener('click', aoClicar, true),
  })

  // Nos passos práticos, o clique REAL no elemento destacado avança o tour
  // (com folga para a navegação/render da página de destino).
  function aoClicar(e) {
    const passo = d.getActiveStep?.()
    const alvo = d.getActiveElement?.()
    if (!passo?.pratico || !alvo) return
    if (alvo === e.target || alvo.contains(e.target)) {
      setTimeout(() => d.moveNext(), 400)
    }
  }
  document.addEventListener('click', aoClicar, true)
  d.drive()
}
