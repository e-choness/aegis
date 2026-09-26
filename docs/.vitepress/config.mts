import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import { execSync } from 'node:child_process'

const repo = 'https://github.com/e-choness/aegis'

// Versions come from git tags (hatch-vcs); show the latest release.
function latestRelease(): string {
  try {
    return execSync('git describe --tags --abbrev=0 --match "v[0-9]*"', { encoding: 'utf8' }).trim()
  } catch {
    return 'dev'
  }
}
const version = latestRelease().replace(/^v/, '')

export default withMermaid(
  defineConfig({
    title: 'Aegis',
    description: 'The self-hosted AI gateway that shows its work — guardrails, human approvals, and a tamper-evident audit ledger.',
    base: '/aegis/',
    lang: 'en-US',
    cleanUrls: true,
    lastUpdated: true,
    // Only the docs tree is published; CONTRIBUTING/SECURITY are rendered as pages too.
    srcExclude: ['**/README.md'],

    head: [
      ['link', { rel: 'icon', type: 'image/svg+xml', href: '/aegis/logo.svg' }],
      ['meta', { name: 'theme-color', content: '#ff7a2e' }],
      ['meta', { property: 'og:type', content: 'website' }],
      ['meta', { property: 'og:title', content: 'Aegis — the self-hosted AI gateway that shows its work' }],
      ['meta', { property: 'og:image', content: 'https://e-choness.github.io/aegis/social-preview.png' }],
    ],

    // Mermaid ships as one large chunk; it's lazy-loaded, so the size warning is noise.
    vite: { build: { chunkSizeWarningLimit: 3000 } },

    markdown: {
      theme: { light: 'github-light', dark: 'github-dark' },
      lineNumbers: false,
    },

    themeConfig: {
      logo: '/logo.svg',
      siteTitle: 'Aegis',

      nav: [
        { text: 'Guide', link: '/guide/', activeMatch: '/guide/' },
        { text: 'Policy packs', link: '/packs/', activeMatch: '/packs/' },
        { text: 'Develop', link: '/develop/codebase', activeMatch: '/develop/' },
        { text: 'Reference', link: '/reference/configuration', activeMatch: '/reference/' },
        {
          text: `v${version}`,
          items: [
            { text: 'Changelog', link: '/changelog' },
            { text: 'Contributing', link: '/CONTRIBUTING' },
            { text: 'Security policy', link: '/SECURITY' },
          ],
        },
      ],

      sidebar: {
        '/guide/': [
          {
            text: 'Getting started',
            items: [
              { text: 'Introduction', link: '/guide/' },
              { text: 'Quickstart', link: '/guide/quickstart' },
              { text: 'Core concepts', link: '/guide/concepts' },
            ],
          },
          {
            text: 'Using Aegis',
            items: [
              { text: 'Human approvals', link: '/guide/approvals' },
              { text: 'Audit & evidence ledger', link: '/guide/audit' },
              { text: 'Streaming', link: '/guide/streaming' },
              { text: 'Tool governance (MCP)', link: '/guide/tool-governance' },
              { text: 'RAG', link: '/guide/rag' },
              { text: 'Deploying', link: '/guide/deployment' },
            ],
          },
        ],
        '/packs/': [
          {
            text: 'Policy packs',
            items: [
              { text: 'Overview', link: '/packs/' },
              { text: 'PII masking', link: '/packs/pii' },
              { text: 'Residency', link: '/packs/residency' },
              { text: 'Classification', link: '/packs/classification' },
              { text: 'Budgets', link: '/packs/budgets' },
              { text: 'LLM Guard', link: '/packs/llm-guard' },
            ],
          },
        ],
        '/develop/': [
          {
            text: 'Build on Aegis',
            items: [
              { text: 'Codebase tour', link: '/develop/codebase' },
              { text: 'Write a plugin', link: '/develop/plugins' },
              { text: 'Testing', link: '/develop/testing' },
              { text: 'Contributing', link: '/CONTRIBUTING' },
            ],
          },
        ],
        '/reference/': [
          {
            text: 'Reference',
            items: [
              { text: 'aegis.yaml', link: '/reference/configuration' },
              { text: 'CLI', link: '/reference/cli' },
              { text: 'REST API', link: '/reference/rest-api' },
              { text: 'SDKs', link: '/reference/sdks' },
              { text: 'Error codes', link: '/reference/errors' },
              { text: 'Metrics & traces', link: '/reference/observability' },
            ],
          },
        ],
      },

      socialLinks: [{ icon: 'github', link: repo }],

      search: { provider: 'local' },

      editLink: {
        pattern: `${repo}/edit/main/docs/:path`,
        text: 'Edit this page on GitHub',
      },

      outline: { level: [2, 3] },

      footer: {
        message: 'Released under the <a href="https://github.com/e-choness/aegis/blob/main/LICENSE">GNU AGPL-3.0-or-later</a>.',
        copyright: 'Copyright © 2024–present Aegis contributors',
      },
    },

    mermaid: {
      theme: 'base',
      themeVariables: {
        fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
        primaryColor: '#1d4ed8',
        primaryTextColor: '#ffffff',
        primaryBorderColor: '#1e3a8a',
        lineColor: '#7c8db5',
        secondaryColor: '#ff7a2e',
        tertiaryColor: '#e8eefc',
        clusterBkg: 'rgba(59,130,246,0.08)',
        clusterBorder: '#7c8db5',
        edgeLabelBackground: 'transparent',
        actorBkg: '#1d4ed8',
        actorTextColor: '#ffffff',
        actorBorder: '#1e3a8a',
        signalColor: '#7c8db5',
        signalTextColor: '#7c8db5',
        noteBkgColor: '#fff1e6',
        noteTextColor: '#7a3410',
        noteBorderColor: '#ff7a2e',
      },
    },
  }),
)
