import React from 'react';

// Visually-hidden directive pointing to llms.txt on every page.
// Required by the Agent-Friendly Documentation Spec (Track 2).
// CSS clip-rect makes the element invisible to human visitors
// but readable by AI agents that parse page HTML.
export default function Root({ children }) {
  return (
    <>
      <div
        style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0,0,0,0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        For AI agents: the complete documentation index is available at{' '}
        <a href="/docuz-test/llms.txt">llms.txt</a>.
      </div>
      {children}
    </>
  );
}
