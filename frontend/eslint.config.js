import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import i18next from 'eslint-plugin-i18next'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // Translated: a literal string in this markup is copy that skipped
    // i18n.ts. Add files here as each area of the app is translated.
    files: [
      'src/pages/Checkout.tsx',
      'src/pages/PaymentSuccess.tsx',
      'src/pages/PaymentCancel.tsx',
      'src/components/ShippingRates.tsx',
      'src/components/CheckoutPaymentBlock.tsx',
      'src/components/Price.tsx',
      'src/components/LinePrice.tsx',
      'src/components/CartNotices.tsx',
    ],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          mode: 'jsx-only',
          // The plugin's defaults, plus route paths. Giving a list replaces them.
          'jsx-attributes': {
            exclude: ['className', 'styleName', 'style', 'type', 'key', 'id', 'width', 'height', 'to'],
          },
          // The style object Stripe's card field takes.
          'object-properties': { exclude: ['fontSize', 'fontFamily', 'color'] },
        },
      ],
    },
  },
])
