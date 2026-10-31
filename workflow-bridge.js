/* Explicitly confirmed learning evidence, shared with the local growth archive. */
(function () {
  'use strict';
  const key = 'xb2080_confirmed_learning_v1';
  const $ = id => document.getElementById(id);
  function read() {
    const rows = JSON.parse(localStorage.getItem(key) || '[]');
    if (!Array.isArray(rows)) throw new Error('Invalid archive');
    return rows;
  }
  function render() {
    const list = $('learningEvidenceList');
    list.replaceChildren();
    let rows;
    try { rows = read(); } catch (e) { list.textContent = '无法读取本机成果，请检查浏览器存储设置。'; return; }
    if (!rows.length) { list.textContent = '还没有已确认的学习成果。完成学习计划后，可在学业领航中填写复盘并保存。'; return; }
    rows.slice().reverse().forEach(row => {
      const card = document.createElement('article'); card.className = 'step';
      const title = document.createElement('h4'); title.textContent = row.goal;
      const text = document.createElement('p'); text.textContent = row.outcome;
      const stamp = document.createElement('p'); stamp.className = 'small muted';
      stamp.textContent = '学业领航 · 本机已保存 · ' + new Date(row.time).toLocaleDateString('zh-CN');
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary'; remove.textContent = '删除这条成果';
      remove.onclick = () => {
        try { localStorage.setItem(key, JSON.stringify(read().filter(item => item.id !== row.id))); render(); }
        catch (e) { stamp.textContent = '删除失败，原记录仍保留。'; }
      };
      card.append(title, text, stamp, remove); list.append(card);
    });
  }
  document.addEventListener('click', event => {
    if (event.target.id !== 'archiveStudyOutcome') return;
    const status = $('studyArchiveStatus');
    if (![...document.querySelectorAll('[data-plan-step]')].every(box => box.checked)) {
      status.textContent = '请先完成学习计划的三个阶段。'; return;
    }
    const outcome = $('studyOutcome').value.trim();
    const goal = $('studyPlan .step p')?.textContent || '';
    if (outcome.length < 10) { status.textContent = '请用至少10个字描述实际成果与复盘，再确认保存。'; return; }
    try {
      const rows = read();
      if (rows.some(row => row.goal === goal && row.outcome === outcome)) { status.textContent = '这份成果已保存，无需重复提交。'; return; }
      rows.push({id: crypto.randomUUID(), goal, outcome, time: new Date().toISOString()});
      localStorage.setItem(key, JSON.stringify(rows)); render();
      status.textContent = '已保存到本机成长档案，可前往成长发展查看；未对外发送。';
    } catch (e) { status.textContent = '保存失败，请检查浏览器存储设置；复盘文字仍保留在这里。'; }
  });
  window.addEventListener('storage', event => { if (event.key === key) render(); });
  $('showVoiceControls').addEventListener('click', () => {
    $('realtimePanel').scrollIntoView({behavior: 'smooth', block: 'center'});
    const control = window.xiaobaiRealtime?.isActive() ? $('realtimeEnd') : $('realtimeStart');
    control.focus({preventScroll: true});
  });
  render();
})();
