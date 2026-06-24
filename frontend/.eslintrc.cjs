/* Config do ESLint 8 (legacy) — alinhada aos plugins já em devDependencies.
   Sem isto o script `npm run lint` falha por falta de configuração. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: '@babel/eslint-parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    requireConfigFile: false,
    babelOptions: { presets: ['@babel/preset-react'] },
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: 'detect' } },
  plugins: ['react', 'react-hooks', 'unused-imports'],
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  rules: {
    // JSX runtime novo dispensa import de React e PropTypes não é usado aqui.
    'react/prop-types': 'off',
    // unused-imports remove imports órfãos e avisa sobre variáveis não usadas
    // (ignora as prefixadas com _ por convenção).
    'no-unused-vars': 'off',
    'unused-imports/no-unused-imports': 'error',
    'unused-imports/no-unused-vars': [
      'warn',
      { vars: 'all', varsIgnorePattern: '^_', args: 'after-used', argsIgnorePattern: '^_' },
    ],
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    // catch {} silencioso é padrão deliberado (ex.: sessionStorage em modo privado).
    'no-empty': ['error', { allowEmptyCatch: true }],
  },
  ignorePatterns: ['dist', 'node_modules', '*.cjs'],
}
