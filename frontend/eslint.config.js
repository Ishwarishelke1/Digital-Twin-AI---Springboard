import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'test-results', 'tests_e2e/report', 'tests_e2e/.auth']),
  {
    files: ['**/*.{js,jsx}'],
    ignores: ['playwright.config.js', 'tests_e2e/**'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // playwright.config.js and tests_e2e/ run under Node, driving a browser —
    // not React source. globals.browser doesn't have `process` (Node-only),
    // and eslint-plugin-react-hooks' rules-of-hooks false-positives on
    // Playwright's own `use` fixture parameter, an unrelated API that just
    // happens to share the name with React's `use` hook.
    files: ['playwright.config.js', 'tests_e2e/**/*.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      globals: globals.node,
    },
  },
])
