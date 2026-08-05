// Tour guiado (driver.js) em MODO DEMONSTRAÇÃO: escurece a tela, destaca um
// elemento por vez e BLOQUEIA o resto. Passos "práticos" não têm botão
// Próximo — a pessoa é obrigada a clicar no item destacado para avançar.
//
// O tour trabalha numa EMPRESA EXEMPLO com dados fictícios (tourDemo.js):
// nada é salvo, uploads ficam bloqueados, várias pessoas podem fazer ao
// mesmo tempo e cada início recomeça do zero. Ao concluir (ou fechar no X),
// o modo demonstração desliga e a empresa anterior volta ao seletor.
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import { ativarDemo, desativarDemo } from './tourDemo'

// Passo informativo (avança pelo botão Próximo).
const info = (element, title, description) => ({
  element,
  popover: { title, description },
})

// Passo prático: só o clique no elemento destacado avança.
const pratico = (element, title, description) => ({
  element,
  pratico: true,
  // Só passos práticos liberam o elemento destacado para receber o clique.
  // Nos passos informativos a tela permanece totalmente bloqueada.
  disableActiveInteraction: false,
  popover: {
    title,
    description: `${description}<br/><br/>👉 <b>Clique no item destacado para continuar.</b>`,
    showButtons: ['previous', 'close'],
  },
})

// Passo-aula: sem âncora (centralizado, mais largo) — conteúdo didático que
// não depende do que a tela tem carregado.
const aula = (title, description) => ({
  popover: { title, description, popoverClass: 'sol-tour sol-tour-aula' },
})

const PASSOS = [
  info('[data-tour="nav-dashboard"]', 'Bem-vindo ao Sol Contabilidade! ☀️',
    'Este é o <b>Dashboard</b>: a visão geral do escritório. Neste tour você vai trabalhar numa '
    + '<b>empresa de exemplo com dados fictícios</b>, corrigir pendências de verdade e ver o cálculo por dentro — '
    + 'nada do que acontecer aqui é salvo.'),
  info('[data-tour="topbar-competencia"]', 'Competência — a vigência do trabalho 📅',
    'Este seletor define o <b>mês/ano</b> em que você vai trabalhar: todas as telas obedecem a ele, '
    + 'e o motor usa as regras <b>vigentes na data de emissão</b> de cada nota.'),

  // ── A empresa de exemplo: seleção OBRIGATÓRIA (antes de tudo) ──
  pratico('[data-tour="topbar-empresa"]', 'Escolha com quem trabalhar 🏢',
    'As telas de análise trabalham sobre <b>uma empresa por vez</b>. Para este tour, preparamos uma '
    + '<b>Empresa Exemplo</b> com movimentação fictícia. Abra o seletor.'),
  pratico('[data-tour="empresa-demo"]', 'Selecione a Empresa Exemplo ☀️',
    'Os dados dela existem <b>só no seu navegador</b>: nada é salvo, ninguém mais vê, e cada tour recomeça do zero.'),

  pratico('[data-tour="nav-upload"]', 'Upload de XMLs',
    'Tudo começa aqui: é por onde os XMLs (NF-e, NFC-e, CT-e, NFS-e) entram no sistema.'),
  info('[data-tour="upload-area"]', 'A área de importação 📥',
    'No dia a dia: arraste vários XMLs (ou um .zip) e o processamento roda em segundo plano — parse, classificação e '
    + '<b>auditoria de ST automática</b>. Durante o tour o <b>envio fica desativado</b>, então é só conhecer.'),
  info('[data-tour="nav-documentos"]', 'Documentos Fiscais 🗂️',
    'Aqui dentro vivem as <b>Notas</b> importadas (com edição em lote, DANFE, XML), os <b>Relatórios</b> em Excel e o <b>De/Para de CFOP</b>.'),

  // ── Divergências com dados de verdade na tela ──
  pratico('[data-tour="nav-divergencias-st"]', 'Divergências de ICMS-ST',
    'O coração fiscal do sistema. A Empresa Exemplo tem <b>1 divergência apontada e 2 pendências</b> — '
    + 'você vai entender e <b>corrigir cada uma</b> agora.'),
  info('[data-tour="st-cards"]', 'O dinheiro em jogo 💰',
    'Os cards somam o período: <b>R$ 177,50 de ST a recolher</b> já apontado e <b>2 itens não auditáveis</b> '
    + '(as pendências). Clique num card para filtrar a lista; no ranking, a <b>Carta PDF</b> cobra o fornecedor.'),
  aula('Antes da conta: os dois portões 🚪',
    'Todo item passa por dois portões antes do cálculo:<br/><br/>'
    + '<b>1º — Enquadramento:</b> o produto (NCM + CEST) é ST na UF de destino? '
    + 'A busca vai do específico ao geral: NCM com <b>8 → 6 → 4 dígitos</b>.<br/><br/>'
    + '<b>2º — Protocolo (entre estados):</b> há acordo obrigando o fornecedor a reter? '
    + '<b>ATIVO</b> → cobra retenção · <b>SEM ACORDO</b> → antecipação do cliente · '
    + '<b>sem registro</b> → o motor trava e pede curadoria. <b>Ele nunca adivinha</b> — '
    + 'as 2 pendências que você vai corrigir são exatamente portões sem resposta.'),

  // ── Nota 1: a divergência com CT-e + memória de cálculo ──
  pratico('[data-tour="st-nota-demo"]', 'Abra a 1ª nota — NF-e 101 📄',
    'Cada linha é uma nota. Repare no <b>caminhão 🚚</b>: há um <b>CT-e vinculado</b> — o frete dele entra na conta. '
    + 'Clique na linha para expandir o item.'),
  pratico('[data-tour="st-nota-demo-selo"]', 'Clique no SELO do item 🏷️',
    'O fornecedor destacou <b>R$ 0,00</b> de ST e o devido é <b>R$ 177,50</b>. '
    + 'O selo abre o balão com a explicação do motor e as ações.'),
  pratico('[data-tour="st-abrir-memoria"]', 'Abra a memória de cálculo 🧮',
    'É a <b>calculadora</b> do item: a conta completa que chegou nos R$ 177,50 — o que você usa para defender o número.'),
  info('[data-tour="st-memoria"]', 'A conta, passo a passo — leia junto 👇',
    '<b>Passo 1:</b> alíquotas e de onde vêm (interna 18% de MG; interestadual 12% de SP).<br/>'
    + '<b>Passo 2:</b> MVA original <b>71,78%</b> → <b>ajustada 84,35%</b> (equaliza comprar dentro × fora do estado).<br/>'
    + '<b>Passo 3:</b> base = produto R$ 731,35 <b>+ frete do CT-e R$ 68,05</b> = R$ 799,40 → × 1,8435 = <b>R$ 1.473,69</b>.<br/>'
    + '<b>Passo 4-6:</b> × 18% − ICMS próprio R$ 87,76 = <b>R$ 177,50</b>, confrontado com o XML (tolerância de centavos).<br/><br/>'
    + 'Tudo com a <b>base legal</b> de cada regra — pronto para auditoria.'),
  pratico('[data-tour="st-memoria-fechar"]', 'Feche a memória ✖',
    'No dia a dia ela está a um clique em qualquer item calculado.'),

  // ── Pendência 1: o CT-e ──
  pratico('[data-tour="st-nota-demo2"]', 'Abra a 2ª nota — NF-e 102 🚚',
    'Esta nota tem a <b>1ª pendência</b>: frete por conta do cliente e <b>nenhum CT-e vinculado</b>. '
    + 'O motor não calcula base menor em silêncio — ele trava e explica.'),
  pratico('[data-tour="st-nota-demo2-selo"]', 'Clique no selo da pendência 🏷️',
    'O balão mostra os dois caminhos: <b>Importar CT-e</b> (a auditoria destrava sozinha) '
    + 'ou <b>“Não há CT-e”</b> (a confirmação fica registrada no seu usuário).'),
  pratico('[data-tour="st-sem-cte"]', 'CORRIJA: “Não há CT-e” ✅',
    'Clique e <b>aceite a confirmação</b> do navegador. Aqui é simulação — no dia a dia fica registrado quem confirmou e quando. '
    + '<i>(Se cancelar sem querer, volte um passo e repita.)</i>'),
  info('[data-tour="st-cards"]', 'A pendência virou valor 💡',
    'Reaudita na hora: o card subiu para <b>R$ 332,42 a recolher</b> (+R$ 154,92 da nota destravada — '
    + 'sem o frete na base, a conta fecha menor que a da 1ª nota). <b>Destravar pendência revela dinheiro.</b>'),

  // ── Pendência 2: o protocolo ──
  pratico('[data-tour="st-nota-demo3"]', 'Abra a 3ª nota — NF-e 103, GO→MG 🗺️',
    'A <b>2ª pendência</b>: ninguém disse ao motor se existe acordo de ST entre <b>GO e MG</b> para este produto.'),
  pratico('[data-tour="st-nota-demo3-selo"]', 'Clique no selo da pendência 🏷️',
    'O balão explica: registre o acordo na matriz de Protocolos — ou registre que <b>não há acordo</b>. '
    + 'Os dois destravam, com efeitos diferentes.'),
  pratico('[data-tour="st-sem-acordo"]', 'CORRIJA: “Não há acordo” ✅',
    'Clique e <b>aceite a confirmação</b>. O registro explícito também é curadoria: sem acordo, o fornecedor '
    + 'não era obrigado a reter. <i>(Cancelou? Volte um passo e repita.)</i>'),
  info('[data-tour="st-cards"]', 'Virou antecipação 📌',
    'O item saiu de “não auditável” para <b>Antecipações: R$ 89,30</b> — obrigação do PRÓPRIO cliente (guia local), '
    + 'por isso <b>não entra na carta</b> ao fornecedor. Todas as pendências foram tratadas! 🎉'),
  info('[data-tour="st-reprocessar"]', 'Reprocessar Pendentes 🔄',
    'No dia a dia: corrigiu matrizes, De/Para ou CT-e reais? Este botão <b>reaudita as notas travadas</b> de uma vez.'),
  aula('E quando a pendência é de MATRIZ? ⛽',
    'Faltou <b>enquadramento, MVA ou alíquota</b>, o balão do selo traz o botão <b>“Cadastrar matriz”</b> — '
    + 'abre o cadastro já preenchido com NCM/CEST/UF do item. E a aba <b>Cobertura</b> das Matrizes lista '
    + 'tudo o que falta cadastrar, ordenado pelo valor que está travado.'),

  // ── Matrizes ──
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
    'Robôs leem as fontes oficiais (CONFAZ, Anexo VII do RICMS/MG) e <b>propõem</b> atualizações na aba '
    + '<b>Revisão</b> — o chip mostra quantas esperam. Nada entra sem aprovação, <b>linha cadastrada à mão '
    + 'nunca é tocada</b> e rejeitar vale para sempre.<br/><br/>'
    + 'A aba <b>Saúde</b> é o radar: frescor da base, a data que sai no aviso da carta e os '
    + '<b>pares de UF pendentes</b>. E a <b>Cobertura</b> mostra o que falta cadastrar, por valor.'),

  info('[data-tour="nav-ibs-cbs"]', 'IBS/CBS — Reforma Tributária 🧪',
    '2026 é o ano-teste da Reforma: nessa tela você fiscaliza o destaque de IBS/CBS dos fornecedores — '
    + 'mesma lógica de selos e balões que você acabou de ver no ST.'),
  info('[data-tour="topbar-ajuda"]', 'Pronto! 🎉',
    'Ao concluir, a <b>Empresa Exemplo some</b> e a sua empresa volta ao seletor — nada do tour foi salvo. '
    + 'Para refazer (sempre do zero), clique neste botão de ajuda. Bom trabalho!'),
]

export function iniciarTour({ aoEncerrar } = {}) {
  ativarDemo()   // liga a Empresa Exemplo e bloqueia escritas — reset a cada início

  const d = driver({
    steps: PASSOS,
    showProgress: true,
    // Mantém o X disponível, mas nenhum clique fora do popover encerra o tour.
    allowClose: true,
    overlayClickBehavior: () => {},
    // Escape e setas não podem encerrar/pular etapas: a navegação acontece
    // somente pelos controles visíveis e pelas ações solicitadas no passo.
    allowKeyboardControl: false,
    // Por padrão nem o elemento destacado recebe cliques. `pratico()` libera
    // exclusivamente o alvo necessário para cumprir cada etapa interativa.
    disableActiveInteraction: true,
    overlayOpacity: 0.65,
    stagePadding: 6,
    popoverClass: 'sol-tour',   // visual do app (styles.css) por cima do default
    stageRadius: 10,
    nextBtnText: 'Próximo →',
    prevBtnText: '← Voltar',
    doneBtnText: 'Concluir',
    progressText: '{{current}} de {{total}}',
    onDestroyed: () => {
      document.removeEventListener('click', aoClicar, true)
      desativarDemo()
      aoEncerrar?.()            // devolve a empresa que estava selecionada
    },
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
