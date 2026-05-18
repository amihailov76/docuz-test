/**
 * src/theme/MDXComponents.js
 *
 * Заменяет Mintlify-компоненты на Docusaurus-совместимые реализации.
 * Покрывает все компоненты, найденные в репозитории:
 *   Card, CardGroup, Steps, Step,
 *   Note, Tip, Warning, Info,
 *   CodeGroup,
 *   Tabs, Tab,
 *   Accordion, AccordionGroup
 *
 * Установка: скопируйте этот файл в src/theme/MDXComponents.js
 */

import React from 'react';
import MDXComponents from '@theme-original/MDXComponents';
// Импортируем под именем DocTabs/DocTabItem, чтобы не конфликтовать
// с нашим кастомным компонентом Tabs (контентные вкладки Mintlify).
import DocTabs from '@theme/Tabs';
import DocTabItem from '@theme/TabItem';

// ─── Иконки ─────────────────────────────────────────────────────────────────
// Маппинг Mintlify-имён иконок (FontAwesome) → эмодзи.
// Добавьте новые строки по мере необходимости.
const ICON_MAP = {
  download:            '⬇️',
  bolt:                '⚡',
  folder:              '📁',
  'chart-bar':         '📊',
  sliders:             '⚙️',
  'file-lines':        '📄',
  'magnifying-glass':  '🔍',
  'list-check':        '✅',
  brain:               '🧠',
  book:                '📚',
  refresh:             '🔄',
  'code-compare':      '🔀',
  lock:                '🔒',
  globe:               '🌐',
  'chart-simple':      '📈',
  wrench:              '🔧',
  star:                '⭐',
  rocket:              '🚀',
  info:                'ℹ️',
  warning:             '⚠️',
  check:               '✔️',
  // иконки из concepts/evaluation.mdx
  'circle-check':      '✅',
  'circle-exclamation':'❕',
  'triangle-exclamation':'⚠️',
  'circle-xmark':      '❌',
  // иконки из concepts/documents.mdx
  'file-pdf':          '📕',
  'file-word':         '📘',
  'file-code':         '📝',
  'list-ol':           '🔢',
  // иконки из concepts/criteria.mdx
  'pen-to-square':     '✏️',
};

// ─── Card ────────────────────────────────────────────────────────────────────
/**
 * @param {string}  title    — заголовок карточки
 * @param {string}  [icon]   — имя иконки FontAwesome (напр. "bolt")
 * @param {string}  [href]   — ссылка (превращает карточку в кликабельную)
 * @param {React.ReactNode} children — тело карточки
 */
function Card({ title, icon, href, children }) {
  const emoji = icon ? (ICON_MAP[icon] ?? '📄') : null;

  const inner = (
    <div className="doc-card">
      <div className="doc-card-header">
        {emoji && <span className="doc-card-icon" aria-hidden="true">{emoji}</span>}
        <span className="doc-card-title">{title}</span>
      </div>
      {children && <div className="doc-card-body">{children}</div>}
    </div>
  );

  if (href) {
    return (
      <a href={href} className="doc-card-link" style={{ textDecoration: 'none' }}>
        {inner}
      </a>
    );
  }
  return inner;
}

// ─── CardGroup ───────────────────────────────────────────────────────────────
/**
 * @param {1|2|3|4} [cols=2] — количество колонок сетки
 */
function CardGroup({ cols = 2, children }) {
  return (
    <div
      className="doc-card-group"
      style={{ '--doc-card-cols': cols }}
    >
      {children}
    </div>
  );
}

// ─── Steps / Step ────────────────────────────────────────────────────────────
/**
 * Контейнер шагов. Автоматически нумерует дочерние <Step>.
 */
function Steps({ children }) {
  const steps = React.Children.toArray(children);
  return (
    <div className="doc-steps">
      {steps.map((child, index) =>
        React.isValidElement(child)
          ? React.cloneElement(child, { _stepIndex: index + 1 })
          : child
      )}
    </div>
  );
}

/**
 * @param {string} title       — заголовок шага
 * @param {number} _stepIndex  — порядковый номер (проставляется Steps автоматически)
 */
function Step({ title, children, _stepIndex }) {
  return (
    <div className="doc-step">
      <div className="doc-step-marker" aria-hidden="true">
        {_stepIndex}
      </div>
      <div className="doc-step-content">
        <div className="doc-step-title">{title}</div>
        <div className="doc-step-body">{children}</div>
      </div>
    </div>
  );
}

// ─── Admonitions: Note / Tip / Warning ──────────────────────────────────────
// Используем классы Docusaurus alert, чтобы визуально совпадало со встроенными
// admonition-блоками (:::note, :::tip, :::warning).

function Note({ children }) {
  return (
    <div className="admonition admonition-note alert alert--secondary doc-admonition">
      <div className="admonition-heading">
        <span className="admonition-icon" aria-hidden="true">ℹ️</span>
        <strong>Note</strong>
      </div>
      <div className="admonition-content">{children}</div>
    </div>
  );
}

function Tip({ children }) {
  return (
    <div className="admonition admonition-tip alert alert--success doc-admonition">
      <div className="admonition-heading">
        <span className="admonition-icon" aria-hidden="true">💡</span>
        <strong>Tip</strong>
      </div>
      <div className="admonition-content">{children}</div>
    </div>
  );
}

function Warning({ children }) {
  return (
    <div className="admonition admonition-warning alert alert--warning doc-admonition">
      <div className="admonition-heading">
        <span className="admonition-icon" aria-hidden="true">⚠️</span>
        <strong>Warning</strong>
      </div>
      <div className="admonition-content">{children}</div>
    </div>
  );
}

// ─── CodeGroup ───────────────────────────────────────────────────────────────
/**
 * Оборачивает несколько code-блоков в Docusaurus Tabs.
 * Mintlify-синтаксис: ```text OpenAI — метка берётся из metastring.
 */
function CodeGroup({ children }) {
  const blocks = React.Children.toArray(children).filter(Boolean);

  return (
    <DocTabs groupId="code-group">
      {blocks.map((block, index) => {
        // Пытаемся извлечь метку из metastring кодового блока.
        // Структура: <pre><code className="language-xxx" metastring="Label">...
        let label = `Code ${index + 1}`;
        try {
          const codeEl = block?.props?.children;
          const meta = codeEl?.props?.metastring ?? codeEl?.props?.meta;
          if (meta) {
            label = meta.trim();
          } else {
            const cls = codeEl?.props?.className ?? '';
            const lang = cls.replace('language-', '');
            if (lang) label = lang;
          }
        } catch (_) {
          // Если не получилось — оставляем дефолтную метку
        }

        return (
          <DocTabItem key={index} value={String(index)} label={label}>
            {block}
          </DocTabItem>
        );
      })}
    </DocTabs>
  );
}

// ─── Tabs / Tab ───────────────────────────────────────────────────────────────
/**
 * Контентные вкладки Mintlify (<Tabs> + <Tab title="...">).
 * Отличие от CodeGroup: здесь вкладки содержат произвольный MDX-контент,
 * а не только кодовые блоки. Метка берётся из пропа title на каждом <Tab>.
 */
function Tabs({ children }) {
  const tabs = React.Children.toArray(children).filter(Boolean);
  return (
    <DocTabs>
      {tabs.map((child, index) => {
        const title = child?.props?.title ?? `Tab ${index + 1}`;
        return (
          <DocTabItem key={index} value={String(index)} label={title}>
            {child?.props?.children}
          </DocTabItem>
        );
      })}
    </DocTabs>
  );
}

/**
 * Одна вкладка. Содержимое извлекается родительским <Tabs>.
 * Рендерится самостоятельно только если попал за пределы <Tabs>.
 */
function Tab({ children }) {
  return <>{children}</>;
}

// ─── Info ─────────────────────────────────────────────────────────────────────
/**
 * Информационный блок — аналог Note, но с синей/info-стилистикой.
 * Используется в concepts/criteria.mdx.
 */
function Info({ children }) {
  return (
    <div className="admonition admonition-info alert alert--info doc-admonition">
      <div className="admonition-heading">
        <span className="admonition-icon" aria-hidden="true">ℹ️</span>
        <strong>Info</strong>
      </div>
      <div className="admonition-content">{children}</div>
    </div>
  );
}

// ─── AccordionGroup / Accordion ──────────────────────────────────────────────
/**
 * AccordionGroup — просто контейнер с отступами.
 */
function AccordionGroup({ children }) {
  return <div className="doc-accordion-group">{children}</div>;
}

/**
 * @param {string} title — вопрос / заголовок аккордеона
 */
function Accordion({ title, children }) {
  return (
    <details className="doc-accordion">
      <summary className="doc-accordion-summary">{title}</summary>
      <div className="doc-accordion-body">{children}</div>
    </details>
  );
}

// ─── Экспорт ─────────────────────────────────────────────────────────────────
export default {
  ...MDXComponents, // сохраняем все стандартные компоненты Docusaurus
  Card,
  CardGroup,
  Steps,
  Step,
  Note,
  Tip,
  Warning,
  Info,
  CodeGroup,
  Tabs,
  Tab,
  Accordion,
  AccordionGroup,
};
