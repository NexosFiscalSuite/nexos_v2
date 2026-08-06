import { useUfs, rotuloUf, UF_QUALQUER, UF_QUALQUER_LABEL } from '../constants/ufs'

// Seletor de UF — PONTO ÚNICO de renderização das unidades da federação no app.
//
// Antes a UF era campo de texto livre em todo lugar: quem digitava "Minas
// Gerais" ou "mg" gravava a linha torta e o motor, que procura pela SIGLA em
// maiúsculas, não encontrava a regra — o cálculo saía errado mesmo com a
// matriz cadastrada. Com a lista fechada, só sigla válida entra.
//
// Props:
//   todas       — rótulo do item vazio vira "Todas as UFs" (uso em filtros)
//   coringa     — acrescenta a opção "*" (vale para qualquer origem)
//   placeholder — sobrescreve o rótulo do item vazio
export default function SelectUf({
  value, onChange, required = false, todas = false, coringa = false, placeholder, style,
}) {
  const ufs = useUfs()
  const vazio = placeholder ?? (todas ? 'Todas as UFs' : 'Selecione a UF…')
  return (
    <select value={value ?? ''} required={required} style={style}
      onChange={e => onChange(e.target.value)}>
      <option value="">{vazio}</option>
      {coringa && <option value={UF_QUALQUER}>{UF_QUALQUER_LABEL}</option>}
      {ufs.map(u => (
        <option key={u.sigla} value={u.sigla}>{rotuloUf(u.sigla, u.nome)}</option>
      ))}
    </select>
  )
}
