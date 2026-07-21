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
    'O coração fiscal do sistema: o motor recalcula a ST de cada item e mostra <b>quem errou, quanto e por quê</b> — com a memória de cálculo aberta para a defesa.'),
  pratico('[data-tour="nav-ibs-cbs"]', 'IBS/CBS — Reforma Tributária 🧪',
    '2026 é o ano-teste da Reforma: aqui você fiscaliza o destaque de IBS/CBS dos fornecedores contra a tabela oficial.'),
  info('[data-tour="ibscbs-atualizar"]', 'Atualizar consulta 🔄',
    'Depois de importar XMLs de uma competência, clique aqui <b>uma vez</b> para reler os arquivos e preencher os dados de IBS/CBS das notas.'),
  info('[data-tour="nav-cadastros-grp"]', 'Cadastros e Matrizes 📚',
    'Clientes/fornecedores e as <b>Matrizes Fiscais</b> (MVA, enquadramento, alíquotas…) — o combustível do motor de auditoria. A aba <b>Cobertura</b> mostra o que falta cadastrar, por valor.'),
  info('[data-tour="topbar-ajuda"]', 'Pronto! 🎉',
    'Você conhece o essencial. Para <b>refazer este tour</b> a qualquer momento, clique neste botão de ajuda. Bom trabalho!'),
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
