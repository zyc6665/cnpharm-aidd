import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import * as parserVue from 'vue-eslint-parser'
import * as parserTs from '@typescript-eslint/parser'
import pluginTs from '@typescript-eslint/eslint-plugin'

const browserGlobals = {
  Blob: 'readonly',
  console: 'readonly',
  clearInterval: 'readonly',
  clearTimeout: 'readonly',
  CustomEvent: 'readonly',
  document: 'readonly',
  File: 'readonly',
  FileReader: 'readonly',
  FormData: 'readonly',
  HTMLElement: 'readonly',
  HTMLInputElement: 'readonly',
  KeyboardEvent: 'readonly',
  localStorage: 'readonly',
  navigator: 'readonly',
  ResizeObserver: 'readonly',
  setInterval: 'readonly',
  setTimeout: 'readonly',
  SVGSVGElement: 'readonly',
  URL: 'readonly',
  window: 'readonly'
}

const nodeGlobals = {
  __dirname: 'readonly',
  Buffer: 'readonly',
  process: 'readonly'
}

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parser: parserVue,
      globals: browserGlobals,
      parserOptions: {
        parser: parserTs,
        ecmaVersion: 2022,
        sourceType: 'module',
        extraFileExtensions: ['.vue']
      }
    },
    plugins: {
      vue: pluginVue
    },
    rules: {
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/attributes-order': 'off',
      'vue/html-indent': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/no-mutating-props': 'off',
      'vue/no-template-shadow': 'off',
      'vue/no-v-html': 'off',
      'vue/require-default-prop': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/html-quotes': 'off',
      'vue/singleline-html-element-content-newline': 'off'
    }
  },
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: parserTs,
      globals: browserGlobals,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: 'module'
      }
    },
    plugins: {
      '@typescript-eslint': pluginTs
    },
    rules: {
      ...pluginTs.configs.recommended.rules,
      'no-redeclare': 'off',
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
    }
  },
  {
    files: ['*.config.ts', '*.config.js', 'test/**/*.ts'],
    languageOptions: {
      globals: {
        ...browserGlobals,
        ...nodeGlobals
      }
    }
  },
  {
    ignores: ['node_modules/', 'dist/', '*.d.ts']
  }
]
