import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// Ícones Tabler empacotados localmente (sem CDN -> sem "tofu" no 1º acesso e funciona offline)
import '@tabler/icons-webfont/dist/tabler-icons.min.css'

// Fontes locais: Manrope variável (corpo/UI — arredondada e legível) +
// Plus Jakarta Sans (títulos) + JetBrains Mono (só códigos: chave/CNPJ/NCM)
import '@fontsource-variable/manrope'
import '@fontsource/plus-jakarta-sans/latin-500.css'
import '@fontsource/plus-jakarta-sans/latin-600.css'
import '@fontsource/plus-jakarta-sans/latin-700.css'
import '@fontsource/plus-jakarta-sans/latin-800.css'
import '@fontsource/jetbrains-mono/latin-400.css'
import '@fontsource/jetbrains-mono/latin-500.css'

import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
