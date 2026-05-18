import json

# Read demo data
with open('docs/compare-quant-demo-data.json', 'r', encoding='utf-8') as f:
    demo_data = json.load(f)

# Limit to 2 papers and simplify content for preview
papers = demo_data['papers'][:2]

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>对比分析 v2.0 - 七步精读预览</title>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <style>
    :root {
      --bg-canvas: #faf8f5;
      --bg-surface: #ffffff;
      --bg-hover: #f2efe9;
      --bg-selected: #eaf0e8;
      --text-primary: #1a1714;
      --text-secondary: #4a4540;
      --text-tertiary: #9a9590;
      --accent-primary: #2d5a3d;
      --accent-primary-hover: #1e3d28;
      --accent-gold: #c4782a;
      --accent-coral: #b5423e;
      --border-light: #e8e4df;
      --border-medium: #d5d0ca;
      --shadow-sm: 0 1px 3px rgba(26,23,20,0.04);
      --shadow-md: 0 4px 12px rgba(26,23,20,0.06);
      --shadow-lg: 0 12px 24px rgba(26,23,20,0.08);
      --font-serif: Georgia, 'Times New Roman', 'STSong', 'SimSun', serif;
      --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
      --font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: var(--font-sans); background: var(--bg-canvas); color: var(--text-primary); font-size: 14px; line-height: 1.6; overflow: hidden; }
    .app { display: flex; flex-direction: column; height: 100vh; }
    .topbar { height: 64px; background: var(--bg-surface); border-bottom: 1px solid var(--border-light); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; flex-shrink: 0; position: relative; z-index: 100; box-shadow: var(--shadow-sm); }
    .topbar-brand { display: flex; align-items: baseline; gap: 16px; }
    .topbar-brand h1 { font-family: var(--font-serif); font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
    .topbar-brand span { font-size: 13px; color: var(--text-tertiary); }
    .btn-synthesis { background: var(--accent-primary); color: white; border: none; padding: 10px 24px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.25s ease; }
    .btn-synthesis:hover:not(:disabled) { background: var(--accent-primary-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(45,90,61,0.25); }
    .btn-synthesis:disabled { opacity: 0.35; cursor: not-allowed; }
    .paper-strip { background: var(--bg-surface); border-bottom: 1px solid var(--border-light); padding: 20px 32px; display: flex; gap: 14px; overflow-x: auto; flex-shrink: 0; position: relative; z-index: 99; }
    .paper-chip { min-width: 220px; max-width: 300px; padding: 14px 18px; border-radius: 10px; border: 2px solid transparent; background: var(--bg-canvas); cursor: pointer; position: relative; transition: all 0.2s ease; flex-shrink: 0; }
    .paper-chip:hover { background: var(--bg-hover); transform: translateY(-1px); box-shadow: var(--shadow-md); }
    .paper-chip.active { border-color: var(--accent-primary); background: var(--bg-selected); }
    .paper-chip-title { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.4; padding-right: 20px; }
    .paper-chip-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 5px; }
    .paper-chip-check { position: absolute; top: 10px; right: 10px; width: 16px; height: 16px; border-radius: 50%; background: var(--accent-primary); color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; opacity: 0; transform: scale(0.6); transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1); }
    .paper-chip.active .paper-chip-check { opacity: 1; transform: scale(1); }
    .step-strip { height: 56px; background: var(--bg-canvas); border-bottom: 1px solid var(--border-light); padding: 0 32px; display: flex; gap: 10px; overflow-x: auto; align-items: center; flex-shrink: 0; position: relative; z-index: 98; }
    .step-badge { padding: 7px 16px; border-radius: 100px; font-size: 13px; border: 1.5px solid var(--border-medium); background: transparent; color: var(--text-secondary); cursor: pointer; transition: all 0.2s ease; white-space: nowrap; }
    .step-badge:hover { background: var(--bg-hover); }
    .step-badge.active { background: var(--accent-primary); color: white; border-color: var(--accent-primary); font-weight: 600; box-shadow: 0 2px 8px rgba(45,90,61,0.2); }
    .action-strip { height: 52px; background: var(--bg-surface); border-bottom: 1px solid var(--border-light); padding: 0 32px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; position: relative; z-index: 97; }
    .action-info { display: flex; align-items: center; gap: 20px; font-size: 13px; }
    .action-info .step-name { color: var(--text-primary); font-weight: 600; }
    .action-info .count { color: var(--text-tertiary); }
    .action-btns { display: flex; gap: 10px; }
    .btn-ghost { background: none; border: 1px solid var(--border-light); padding: 7px 14px; font-size: 12px; color: var(--text-secondary); cursor: pointer; border-radius: 6px; transition: all 0.15s ease; }
    .btn-ghost:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
    .btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
    .content-area { flex: 1; overflow-y: auto; padding: 24px 32px 40px; }
    .dimension-card { background: var(--bg-surface); border-radius: 14px; border: 1px solid var(--border-light); box-shadow: var(--shadow-sm); overflow: hidden; margin-bottom: 16px; animation: slideUp 0.5s ease-out both; transition: box-shadow 0.3s ease; }
    .dimension-card:hover { box-shadow: var(--shadow-md); }
    .dimension-card:nth-child(1) { animation-delay: 0ms; }
    .dimension-card:nth-child(2) { animation-delay: 60ms; }
    .dimension-card:nth-child(3) { animation-delay: 120ms; }
    .dimension-card:nth-child(4) { animation-delay: 180ms; }
    .dim-header { display: flex; align-items: center; justify-content: space-between; padding: 0 24px; height: 56px; cursor: pointer; user-select: none; transition: background 0.15s ease; }
    .dim-header:hover { background: var(--bg-hover); }
    .dim-header-left { display: flex; align-items: center; gap: 14px; }
    .dim-check { width: 20px; height: 20px; border-radius: 5px; border: 2px solid var(--border-medium); display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s ease; flex-shrink: 0; background: white; }
    .dim-check.checked { background: var(--accent-primary); border-color: var(--accent-primary); animation: popIn 0.2s ease; }
    .dim-check .checkmark { color: white; font-size: 13px; font-weight: 700; opacity: 0; transition: opacity 0.1s ease; }
    .dim-check.checked .checkmark { opacity: 1; }
    .dim-num { font-size: 12px; color: var(--text-tertiary); font-family: var(--font-mono); font-weight: 500; min-width: 28px; }
    .dim-title { font-size: 15px; font-weight: 600; }
    .dim-arrow { font-size: 11px; color: var(--text-tertiary); transition: transform 0.3s ease; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 6px; }
    .dim-header:hover .dim-arrow { background: var(--bg-hover); }
    .dimension-card.expanded .dim-arrow { transform: rotate(90deg); }
    .dim-body { max-height: 0; overflow: hidden; transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1); background: var(--bg-canvas); border-top: 1px solid transparent; }
    .dimension-card.expanded .dim-body { max-height: 600px; border-top-color: var(--border-light); }
    .cards-scroll { display: flex; gap: 16px; padding: 20px 24px 24px; overflow-x: auto; scroll-behavior: smooth; -webkit-overflow-scrolling: touch; cursor: grab; }
    .cards-scroll:active { cursor: grabbing; }
    .answer-card { flex: 0 0 auto; width: 380px; min-height: 220px; max-height: 520px; background: var(--bg-surface); border-radius: 12px; border: 1px solid var(--border-light); padding: 20px; overflow: hidden; display: flex; flex-direction: column; transition: all 0.25s ease; }
    .answer-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: var(--border-medium); }
    .answer-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
    .answer-avatar { width: 36px; height: 36px; border-radius: 8px; background: linear-gradient(135deg, var(--accent-primary), #3d7a52); color: white; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; flex-shrink: 0; box-shadow: 0 2px 6px rgba(45,90,61,0.2); }
    .answer-info { min-width: 0; }
    .answer-title { font-size: 13px; font-weight: 600; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .answer-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }
    .answer-content { flex: 1; overflow-y: auto; font-size: 13px; line-height: 1.8; color: var(--text-secondary); user-select: text; cursor: text; padding-right: 4px; }
    .md-content p { margin: 8px 0; line-height: 1.8; }
    .md-content h1, .md-content h2, .md-content h3 { font-size: 14px; font-weight: 700; margin: 14px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border-light); }
    .md-content h4, .md-content h5, .md-content h6 { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin: 10px 0 6px; }
    .md-content strong { font-weight: 700; color: var(--text-primary); }
    .md-content blockquote { margin: 12px 0; padding: 12px 16px; border-left: 3px solid var(--accent-gold); background: rgba(196,120,42,0.04); border-radius: 0 8px 8px 0; color: var(--text-secondary); font-size: 12.5px; }
    .md-content ul, .md-content ol { margin: 8px 0; padding-left: 22px; }
    .md-content li { margin: 5px 0; }
    .md-content li::marker { color: var(--accent-primary); font-weight: 600; }
    .md-content table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; line-height: 1.5; margin: 12px 0; border: 1px solid var(--border-light); border-radius: 8px; overflow: hidden; }
    .md-content thead { background: var(--bg-hover); }
    .md-content th { padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border-medium); white-space: nowrap; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
    .md-content td { padding: 8px 12px; border-bottom: 1px solid var(--border-light); color: var(--text-secondary); vertical-align: top; }
    .md-content tbody tr:nth-child(even) { background: rgba(0,0,0,0.012); }
    .md-content code { background: var(--bg-hover); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px; color: var(--accent-coral); font-weight: 500; }
    .md-content pre { background: #24201c; color: #e8e4df; padding: 16px; border-radius: 10px; overflow-x: auto; font-size: 12px; line-height: 1.6; margin: 12px 0; }
    .md-content pre code { background: transparent; color: inherit; padding: 0; }
    .md-content hr { border: none; height: 1px; background: var(--border-light); margin: 18px 0; }
    .md-content a { color: var(--accent-primary); text-decoration: none; font-weight: 500; }
    .md-content a:hover { text-decoration: underline; }
    .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 100px 20px; color: var(--text-tertiary); }
    .empty-icon { width: 64px; height: 64px; border-radius: 50%; background: var(--bg-hover); display: flex; align-items: center; justify-content: center; font-size: 28px; margin-bottom: 20px; }
    .empty-text { font-size: 16px; font-weight: 500; color: var(--text-secondary); }
    .modal-backdrop { display: none; position: fixed; inset: 0; background: rgba(26,23,20,0.45); z-index: 200; justify-content: center; align-items: center; backdrop-filter: blur(6px); }
    .modal-backdrop.active { display: flex; }
    .modal-panel { background: var(--bg-surface); border-radius: 16px; width: 92%; max-width: 800px; max-height: 82vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shadow-lg); }
    .modal-header { padding: 20px 28px; border-bottom: 1px solid var(--border-light); display: flex; justify-content: space-between; align-items: center; }
    .modal-header h2 { font-family: var(--font-serif); font-size: 18px; font-weight: 700; }
    .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-tertiary); width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 8px; transition: all 0.15s ease; }
    .modal-close:hover { background: var(--bg-hover); color: var(--text-primary); }
    .modal-body { padding: 28px; overflow-y: auto; flex: 1; line-height: 1.8; font-size: 14px; }
    @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes popIn { 0% { transform: scale(1); } 50% { transform: scale(1.2); } 100% { transform: scale(1); } }
    @media (max-width: 768px) {
      .topbar { padding: 0 20px; height: 56px; }
      .topbar-brand h1 { font-size: 18px; }
      .paper-strip { padding: 16px 20px; }
      .step-strip { padding: 0 20px; }
      .action-strip { padding: 0 20px; }
      .content-area { padding: 16px 20px 32px; }
      .answer-card { width: 85vw; min-height: 180px; }
      .dim-header { padding: 0 20px; }
      .cards-scroll { padding: 16px 20px 20px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="topbar-brand">
        <h1>对比分析</h1>
        <span>七步精读 · 横向维度对比</span>
      </div>
      <button class="btn-synthesis" id="btnSynthesis" disabled>生成 AI 综述</button>
    </header>

    <div class="paper-strip" id="paperStrip"></div>
    <div class="step-strip" id="stepStrip"></div>

    <div class="action-strip">
      <div class="action-info">
        <span class="step-name" id="currentStepName">请选择分析步骤</span>
        <span class="count" id="selectedCount">已选 0 个问题</span>
      </div>
      <div class="action-btns">
        <button class="btn-ghost" id="btnSelectAll" disabled>当前步骤全选</button>
        <button class="btn-ghost" id="btnClearAll" disabled>清空选择</button>
      </div>
    </div>

    <div class="content-area" id="contentArea">
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-text">请选择步骤和文献开始对比</div>
        <div style="font-size:13px;color:var(--text-tertiary);margin-top:8px;">点击上方文献卡片和步骤标签开始浏览</div>
      </div>
    </div>
  </div>

  <div class="modal-backdrop" id="modal">
    <div class="modal-panel">
      <div class="modal-header">
        <h2>AI 文献综述</h2>
        <button class="modal-close" id="modalClose">&times;</button>
      </div>
      <div class="modal-body" id="modalBody"></div>
    </div>
  </div>

  <script>
    const DEMO_DATA = {demo_data_json};

    let allPapers = [];
    let selectedPapers = [];
    let selectedSubQuestions = new Set();
    let selectedStep = '';
    let expandedDimensions = new Set();

    const STEPS = [
      {{ id: '第一步：核心贡献识别', label: '①核心贡献' }},
      {{ id: '第二步：理论框架评估', label: '②理论框架' }},
      {{ id: '第三步：方法论批判', label: '③方法论' }},
      {{ id: '第四步：实证结果解读', label: '④实证结果' }},
      {{ id: '第五步：局限性分析', label: '⑤局限性' }},
      {{ id: '第六步：实践意义', label: '⑥实践意义' }},
      {{ id: '第七步：未来方向', label: '⑦未来方向' }}
    ];

    function init() {{
      allPapers = DEMO_DATA.papers;
      selectedPapers = allPapers.map(p => p.id);
      renderPaperStrip();
      renderStepStrip();
      selectStep(STEPS[0].id);
    }}

    function renderPaperStrip() {{
      const container = document.getElementById('paperStrip');
      container.innerHTML = allPapers.map(paper => {{
        const isSelected = selectedPapers.includes(paper.id);
        const firstAuthor = paper.authors?.[0] || '';
        const meta = [firstAuthor, paper.year].filter(Boolean).join(', ');
        return `
          <div class="paper-chip ${{isSelected ? 'active' : ''}}" onclick="togglePaper('${{paper.id}}')">
            <div class="paper-chip-title">${{paper.title}}</div>
            <div class="paper-chip-meta">${{meta}} · ${{paper.journal || ''}}</div>
            <div class="paper-chip-check">&#10003;</div>
          </div>
        `;
      }}).join('');
    }}

    function renderStepStrip() {{
      const container = document.getElementById('stepStrip');
      container.innerHTML = STEPS.map(step => `
        <button class="step-badge ${{selectedStep === step.id ? 'active' : ''}}" onclick="selectStep('${{step.id}}')">
          ${{step.label}}
        </button>
      `).join('');
    }}

    function selectStep(stepId) {{
      selectedStep = stepId;
      renderStepStrip();
      updateActionBar();
      if (selectedPapers.length > 0 && selectedStep) {{
        renderDimensions();
      }}
    }}

    function togglePaper(paperId) {{
      const idx = selectedPapers.indexOf(paperId);
      if (idx > -1) {{
        selectedPapers.splice(idx, 1);
      }} else {{
        selectedPapers.push(paperId);
      }}
      renderPaperStrip();
      updateActionBar();
      if (selectedPapers.length > 0 && selectedStep) {{
        renderDimensions();
      }}
    }}

    function renderDimensions() {{
      const container = document.getElementById('contentArea');
      const papers = allPapers.filter(p => selectedPapers.includes(p.id));
      const stepData = papers[0]?.steps?.[selectedStep];

      if (!stepData || !stepData.subQuestions) {{
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">&#128196;</div>
            <div class="empty-text">该步骤下暂无子问题</div>
          </div>
        `;
        return;
      }}

      const subQuestions = stepData.subQuestions;

      container.innerHTML = subQuestions.map((sq, idx) => {{
        const questionKey = `[${{selectedStep}}] ${{sq.label}}`;
        const isChecked = selectedSubQuestions.has(questionKey);
        const isExpanded = expandedDimensions.has(sq.id);

        const cardsHtml = papers.map(paper => {{
          const paperSq = paper.steps?.[selectedStep]?.subQuestions?.find(q => q.id === sq.id);
          const content = paperSq?.content || '';
          const firstAuthor = paper.authors?.[0] || '';
          const initial = firstAuthor.charAt(0) || '?';
          const meta = [firstAuthor, paper.year].filter(Boolean).join(', ');

          return `
            <div class="answer-card">
              <div class="answer-header">
                <div class="answer-avatar">${{initial}}</div>
                <div class="answer-info">
                  <div class="answer-title">${{paper.title}}</div>
                  <div class="answer-meta">${{meta}}</div>
                </div>
              </div>
              <div class="answer-content md-content">
                ${{content ? marked.parse(content) : '<span style="color:var(--text-tertiary);font-style:italic;">（未回答）</span>'}}
              </div>
            </div>
          `;
        }}).join('');

        return `
          <div class="dimension-card ${{isExpanded ? 'expanded' : ''}}">
            <div class="dim-header" onclick="toggleDimension('${{sq.id}}', event)">
              <div class="dim-header-left">
                <div class="dim-check ${{isChecked ? 'checked' : ''}}" onclick="toggleSubQuestion('${{sq.id}}', '${{sq.label}}', event)">
                  <span class="checkmark">&#10003;</span>
                </div>
                <span class="dim-num">${{String(idx + 1).padStart(2, '0')}}</span>
                <span class="dim-title">${{sq.label}}</span>
              </div>
              <span class="dim-arrow">&#9654;</span>
            </div>
            <div class="dim-body">
              <div class="cards-scroll">
                ${{cardsHtml}}
              </div>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function toggleDimension(sqId, event) {{
      if (event.target.closest('.dim-check')) return;
      if (expandedDimensions.has(sqId)) {{
        expandedDimensions.delete(sqId);
      }} else {{
        expandedDimensions.add(sqId);
      }}
      renderDimensions();
    }}

    function toggleSubQuestion(sqId, sqLabel, event) {{
      event.stopPropagation();
      const key = `[${{selectedStep}}] ${{sqLabel}}`;
      if (selectedSubQuestions.has(key)) {{
        selectedSubQuestions.delete(key);
      }} else {{
        selectedSubQuestions.add(key);
      }}
      updateActionBar();
      renderDimensions();
    }}

    function updateActionBar() {{
      const stepLabel = STEPS.find(s => s.id === selectedStep)?.label || '请选择';
      document.getElementById('currentStepName').textContent = `当前步骤：${{stepLabel}}`;
      document.getElementById('selectedCount').textContent = `已选 ${{selectedSubQuestions.size}} 个问题`;

      const hasStep = !!selectedStep;
      const hasPapers = selectedPapers.length > 0;
      document.getElementById('btnSelectAll').disabled = !hasStep || !hasPapers;
      document.getElementById('btnClearAll').disabled = selectedSubQuestions.size === 0;

      const canSynthesize = selectedPapers.length >= 2 && selectedSubQuestions.size >= 1;
      document.getElementById('btnSynthesis').disabled = !canSynthesize;
    }}

    document.getElementById('btnSelectAll').onclick = function() {{
      if (!selectedStep) return;
      const papers = allPapers.filter(p => selectedPapers.includes(p.id));
      const stepData = papers[0]?.steps?.[selectedStep];
      if (!stepData?.subQuestions) return;

      stepData.subQuestions.forEach(sq => {{
        selectedSubQuestions.add(`[${{selectedStep}}] ${{sq.label}}`);
      }});
      updateActionBar();
      renderDimensions();
    }};

    document.getElementById('btnClearAll').onclick = function() {{
      selectedSubQuestions.clear();
      updateActionBar();
      renderDimensions();
    }};

    document.getElementById('btnSynthesis').onclick = function() {{
      document.getElementById('modal').classList.add('active');
      document.getElementById('modalBody').innerHTML = `
        <div style="text-align:center;color:var(--text-tertiary);padding:40px 0;">
          <div style="font-size:40px;margin-bottom:16px;">🤖</div>
          <div style="font-size:15px;font-weight:600;color:var(--text-secondary);">AI 综述生成功能（演示模式）</div>
          <div style="margin-top:8px;">已选择 ${{selectedPapers.length}} 篇文献，${{selectedSubQuestions.size}} 个问题</div>
        </div>
      `;
    }};

    document.getElementById('modalClose').onclick = function() {{
      document.getElementById('modal').classList.remove('active');
    }};
    document.getElementById('modal').onclick = function(e) {{
      if (e.target === document.getElementById('modal')) {{
        document.getElementById('modal').classList.remove('active');
      }}
    }};

    // Drag scroll
    let isDown = false;
    let startX;
    let scrollLeft;

    document.addEventListener('mousedown', (e) => {{
      const container = e.target.closest('.cards-scroll');
      if (!container) return;
      isDown = true;
      startX = e.pageX - container.offsetLeft;
      scrollLeft = container.scrollLeft;
    }});

    document.addEventListener('mouseleave', () => isDown = false);
    document.addEventListener('mouseup', () => isDown = false);
    document.addEventListener('mousemove', (e) => {{
      if (!isDown) return;
      const container = e.target.closest('.cards-scroll');
      if (!container) return;
      e.preventDefault();
      const x = e.pageX - container.offsetLeft;
      const walk = (x - startX) * 1.5;
      container.scrollLeft = scrollLeft - walk;
    }});

    init();
  </script>
</body>
</html>
'''

# Convert demo data to JSON string for embedding
demo_data_json = json.dumps({"papers": papers}, ensure_ascii=False)

# Replace placeholder
final_html = HTML_TEMPLATE.replace('{demo_data_json}', demo_data_json)

# Write to file
with open('docs/compare_7step_preview.html', 'w', encoding='utf-8') as f:
    f.write(final_html)

print("Preview file generated successfully: docs/compare_7step_preview.html")
print(f"Included {len(papers)} papers with full 7-step data")
