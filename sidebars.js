// @ts-check

/**
 * Sidebars для Doc Reviewer — два языка: English и Русский.
 * Структура точно соответствует навигации из docs.json (Mintlify).
 *
 * Docusaurus автоматически определяет, какой sidebar показывать,
 * на основе того, в каком из них находится текущий документ.
 *
 * @type {import('@docusaurus/plugin-content-docs').SidebarsConfig}
 */
const sidebars = {

  // ─── English ────────────────────────────────────────────────────────────────
  enSidebar: [
    {
      type: 'category',
      label: 'Get Started',
      collapsed: false,
      items: [
        'en/introduction',
        'en/installation',
        'en/quickstart',
      ],
    },
    {
      type: 'category',
      label: 'Core Concepts',
      collapsed: false,
      items: [
        'en/concepts/projects',
        'en/concepts/documents',
        'en/concepts/evaluation',
        'en/concepts/criteria',
      ],
    },
    {
      type: 'category',
      label: 'Workflows',
      items: [
        'en/workflows/upload-document',
        'en/workflows/evaluate-web-page',
        'en/workflows/review-results',
        'en/workflows/snapshots',
        'en/workflows/export',
      ],
    },
    {
      type: 'category',
      label: 'Configuration',
      items: [
        'en/configuration/llm-models',
        'en/configuration/criteria-sets',
        'en/configuration/custom-criteria',
      ],
    },
    {
      type: 'category',
      label: 'Troubleshooting',
      items: [
        'en/troubleshooting/faq',
        'en/troubleshooting/known-limitations',
      ],
    },
  ],

  // ─── Русский ─────────────────────────────────────────────────────────────────
  ruSidebar: [
    {
      type: 'category',
      label: 'Начало работы',
      collapsed: false,
      items: [
        'ru/introduction',
        'ru/installation',
        'ru/quickstart',
      ],
    },
    {
      type: 'category',
      label: 'Основные концепции',
      collapsed: false,
      items: [
        'ru/concepts/projects',
        'ru/concepts/documents',
        'ru/concepts/evaluation',
        'ru/concepts/criteria',
      ],
    },
    {
      type: 'category',
      label: 'Рабочие процессы',
      items: [
        'ru/workflows/upload-document',
        'ru/workflows/evaluate-web-page',
        'ru/workflows/review-results',
        'ru/workflows/snapshots',
        'ru/workflows/export',
      ],
    },
    {
      type: 'category',
      label: 'Настройка',
      items: [
        'ru/configuration/llm-models',
        'ru/configuration/criteria-sets',
        'ru/configuration/custom-criteria',
      ],
    },
    {
      type: 'category',
      label: 'Решение проблем',
      items: [
        'ru/troubleshooting/faq',
        'ru/troubleshooting/known-limitations',
      ],
    },
  ],
};

module.exports = sidebars;
