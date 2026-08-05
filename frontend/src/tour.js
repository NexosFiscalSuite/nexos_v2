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
    + '<b>empresa de exemplo com dados fictícios</b> — nada do que acontecer aqui é salvo, e os envios ficam desativados.'),
  info('[data-tour="topbar-competencia"]', 'Competência global 📅',
    'Este seletor define o <b>mês/ano</b> de tudo o que você vê. Trocou aqui, todas as telas obedecem.'),
  pratico('[data-tour="nav-upload"]', 'Upload de XMLs',
    'Tudo começa aqui: é por onde os XMLs (NF-e, NFC-e, CT-e, NFS-e) entram no sistema.'),
  info('[data-tour="upload-area"]', 'A área de importação 📥',
    'No dia a dia: arraste vários XMLs (ou um .zip) e o processamento roda em segundo plano — parse, classificação e '
    + '<b>auditoria de ST automática</b>. Durante o tour o <b>envio fica desativado</b>, então é só conhecer.'),
  info('[data-tour="nav-documentos"]', 'Documentos Fiscais 🗂️',
    'Aqui dentro vivem as <b>Notas</b> importadas (com edição em lote, DANFE, XML), os <b>Relatórios</b> em Excel e o <b>De/Para de CFOP</b>.'),

  // ── A empresa de exemplo: seleção OBRIGATÓRIA ──
  pratico('[data-tour="topbar-empresa"]', 'Vamos praticar de verdade 🏢',
    'As telas de análise trabalham sobre <b>uma empresa por vez</b>. Para este tour, preparamos uma '
    + '<b>Empresa Exemplo</b> com movimentação fictícia. Abra o seletor.'),
  pratico('[data-tour="empresa-demo"]', 'Selecione a Empresa Exemplo ☀️',
    'Os dados dela existem <b>só no seu navegador</b>: nada é salvo, ninguém mais vê, e cada tour recomeça do zero.'),

  // ── Divergências com dados de verdade na tela ──
  pratico('[data-tour="nav-divergencias-st"]', 'Divergências de ICMS-ST',
    'O coração fiscal do sistema. Com a Empresa Exemplo selecionada, a tela vai abrir <b>com dados</b> — '
    + 'uma nota de fornecedor com o ST errado, para você ver o motor em ação.'),
  info('[data-tour="st-cards"]', 'O dinheiro em jogo 💰',
    'Os cards somam o período da empresa: aqui o exemplo mostra <b>R$ 177,50 de ST a recolher</b> '
    + '(o fornecedor zerou a retenção) e <b>1 item não auditável</b> (uma pendência que você já vai entender). '
    + 'Clique num card para filtrar a lista; no ranking abaixo, a <b>Carta PDF</b> cobra o fornecedor.'),
  pratico('[data-tour="st-nota-demo"]', 'Abra a nota de exemplo 📄',
    'Cada linha é uma nota; os totais mostram o ICMS-ST e a diferença. Clique na linha para <b>expandir os itens</b>.'),
  info('[data-tour="st-nota-demo"]', 'Os itens e seus selos 🏷️',
    'O <b>item 1</b> está <b>divergente</b>: a nota destacou R$ 0,00 e o devido é R$ 177,50. O <b>selo colorido</b> '
    + 'abre o balão com a explicação e a ação sugerida, e <b>“Abrir memória de cálculo”</b> mostra a conta inteira '
    + '(explore depois do tour — é tudo fictício). O <b>item 2</b> é a pendência: falta o <b>CT-e do frete</b>.'),

  // ── As aulas do cálculo, com os números da tela ──
  aula('Como o motor chegou nos R$ 177,50 — os portões 🚪',
    'Antes da conta, o item passou por dois portões:<br/><br/>'
    + '<b>1º — Enquadramento:</b> pneu (NCM 4011 + CEST 16.001.00) é ST em MG? A matriz diz que sim. '
    + 'A busca vai do específico ao geral: NCM com <b>8 → 6 → 4 dígitos</b>.<br/><br/>'
    + '<b>2º — Protocolo:</b> vindo de SP para MG, há acordo obrigando o fornecedor a reter? '
    + '<b>ATIVO</b> → cobra retenção · <b>SEM ACORDO</b> → vira antecipação do cliente · '
    + '<b>sem registro</b> → o motor trava e pede curadoria. <b>Ele nunca adivinha.</b>'),
  aula('A conta do exemplo, linha a linha 🧮',
    '<b>Base própria</b> = produto R$ 731,35 + frete do CT-e R$ 68,05 = <b>R$ 799,40</b> '
    + '(por isso o CT-e importa tanto!).<br/><br/>'
    + '<b>MVA:</b> a matriz guarda a original de <b>71,78%</b>; como a compra veio de fora (alíquota 12%), '
    + 'o motor ajusta para <b>84,35%</b> — o ajuste equaliza a carga de comprar dentro × fora do estado.<br/><br/>'
    + '<b>Base do ST</b> = 799,40 × 1,8435 = <b>R$ 1.473,69</b><br/>'
    + '<b>ST devido</b> = 1.473,69 × 18% − ICMS próprio R$ 87,76 = <b>R$ 177,50</b><br/><br/>'
    + 'A nota destacou R$ 0,00 → divergência de <b>R$ 177,50 a recolher</b>. '
    + 'É exatamente essa conta que a memória de cálculo mostra, com as bases legais.'),
  aula('A pendência do item 2 — o CT-e 🚚',
    'O frete era por conta do destinatário e <b>não há CT-e vinculado</b>: o motor NÃO calcula uma base menor '
    + 'em silêncio — trava o item e explica. No dia a dia, dois caminhos no balão do selo: '
    + '<b>Importar CT-e</b> (e a auditoria destrava sozinha) ou <b>“Não há CT-e”</b> (a confirmação fica '
    + 'registrada no seu usuário). Aqui no tour o envio está bloqueado — é só para conhecer o caminho.'),

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
    allowClose: true,
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
