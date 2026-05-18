// @ts-check
const { themes: prismThemes } = require('prism-react-renderer');

/**
 * Конфигурация Docusaurus для Doc Reviewer.
 * Цвета взяты из docs.json: primary #2D7DD2, dark #1A4F8A.
 *
 * @type {import('@docusaurus/types').Config}
 */
const config = {
  title: 'Doc Reviewer',
  tagline: 'Evaluate instruction quality with AI',
  favicon: 'img/favicon.ico',

  url: 'https://amihailov76.github.io',
  baseUrl: '/docuz-test/',
  organizationName: 'amihailov76',
  projectName: 'docuz-test',
  trailingSlash: false,

  // Предупреждать о сломанных ссылках, но не прерывать сборку —
  // удобно на этапе миграции контента.
  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          // Папка с документами. Скопируйте en/ и ru/ из репозитория сюда.
          path: 'docs',
          // Ссылка «Редактировать эту страницу» — ведёт в ваш репозиторий
          editUrl: 'https://github.com/amihailov76/mintlify-docs/edit/main/',
        },
        // Блог отключён — документация без блога
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        defaultMode: 'light',
        respectPrefersColorScheme: true,
      },

      navbar: {
        title: 'Doc Reviewer',
        // logo: { alt: 'Doc Reviewer Logo', src: 'img/logo.svg' },
        items: [
          // Два языковых раздела — аналог tabs в Mintlify
          {
            type: 'docSidebar',
            sidebarId: 'enSidebar',
            position: 'left',
            label: 'English',
          },
          {
            type: 'docSidebar',
            sidebarId: 'ruSidebar',
            position: 'left',
            label: 'Русский',
          },
          // Ссылка на GitHub (из navbar.primary в docs.json)
          {
            href: 'https://github.com/amihailov76/doc-reviewer',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },

      footer: {
        style: 'light',
        links: [
          {
            title: 'Docs',
            items: [
              { label: 'Introduction', to: '/docs/en/introduction' },
              { label: 'Введение', to: '/docs/ru/introduction' },
            ],
          },
          {
            title: 'More',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/amihailov76/doc-reviewer',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} Doc Reviewer. Built with Docusaurus.`,
      },

      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

module.exports = config;
