import { ExcecoesItemPanel } from './MatrizesFiscais'

export default function ExcecaoItem() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Exceção do Item</h1>
          <p className="page-breadcrumb">
            Decisão por empresa e código do item — Tributado ICMS ou ICMS-ST, com vigência e Lei ICMS
          </p>
        </div>
      </div>

      <div data-tour="matrizes-painel-excecoes">
        <ExcecoesItemPanel />
      </div>
    </div>
  )
}
