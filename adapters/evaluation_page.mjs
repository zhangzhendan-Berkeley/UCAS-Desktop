// Original UCAS Desktop integration. Form conventions were checked against
// Chess9380/ucas-eval-extension and Jinddddd/ucas_evaluation_script; see THIRD_PARTY.md.
export function mountEvaluation({templates = {}, batch = false} = {}) {
  if (location.origin !== 'https://xkcts.ucas.ac.cn:8443' || window.top !== window) return;
  if (document.getElementById('ucas-desktop-evaluation')) return;
  const kind = /\/evaluateTeacher\//i.test(location.pathname) ? 'teacher'
    : /\/evaluateCourse\//i.test(location.pathname) ? 'course' : null;
  const list = /^\/evaluate\/(teacher|course)(\/|$)/i.test(location.pathname);
  if (!kind && !list) return;
  const visible = e => e.getClientRects().length && !e.disabled && !e.readOnly;
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  const panel = document.createElement('aside');
  panel.id = 'ucas-desktop-evaluation';
  panel.style.cssText = 'position:fixed;left:18px;bottom:18px;z-index:2147483647;width:320px;max-height:65vh;overflow:auto;padding:18px;background:#173d35;color:white;border-radius:14px;box-shadow:0 8px 28px #0005;font:14px/1.6 sans-serif';
  const title = document.createElement('strong'); title.textContent = 'UCAS Desktop · 评教助手'; panel.append(title);
  const status = document.createElement('p'); panel.append(status);
  const say = text => {status.textContent = text;};
  function button(text, fn) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = text;
    b.style.cssText = 'padding:7px 10px;margin:4px;background:#e4f2e8;color:#173d35;border:0;border-radius:6px;cursor:pointer';
    b.addEventListener('click', fn); panel.append(b); return b;
  }
  const question = element => {
    const row = element.closest('tr');
    const cells = row && [...row.cells].filter(c => !c.querySelector('input,textarea,select') && clean(c.textContent));
    const label = element.labels?.[0];
    const previous = element.previousElementSibling || element.parentElement.previousElementSibling;
    return clean(cells?.map(c=>c.textContent).join(' ') || label?.textContent || previous?.textContent || element.name || element.id);
  };
  function fields() {
    const result = [], groups = new Map();
    for (const e of document.querySelectorAll('input[type=radio],input[type=checkbox],textarea')) {
      if (panel.contains(e) || !visible(e)) continue;
      const q = question(e);
      if (!q) continue;
      const type = e.tagName === 'TEXTAREA' ? 'text' : e.type;
      if (type === 'text') result.push({key: JSON.stringify([kind,type,e.name || e.id,q]), type, elements:[e]});
      else {
        if (!e.name) continue;
        const key = JSON.stringify([kind,type,e.name]);
        if (!groups.has(key)) groups.set(key, {key, type, elements:[], questions:[]});
        const group = groups.get(key); group.elements.push(e); group.questions.push(q);
      }
    }
    for (const group of groups.values()) {
      // Include question and option signatures so a changed questionnaire is not filled by position.
      group.key = JSON.stringify([group.key, group.questions, group.elements.map(e=>[e.value,clean(e.labels?.[0]?.textContent || e.parentElement.textContent)])]);
      result.push(group);
    }
    // Ambiguous duplicate text keys are left for the user.
    return result.filter(f => result.filter(other=>other.key===f.key).length===1);
  }
  async function remember() {
    const answers = {};
    for (const f of fields()) {
      if (f.type === 'text') {if (f.elements[0].value.trim()) answers[f.key] = f.elements[0].value;}
      else {
        const selected = f.elements.map((e,i)=>e.checked?i:-1).filter(i=>i>=0);
        if (selected.length) answers[f.key] = selected;
      }
    }
    if (!Object.keys(answers).length) return say('未找到已填写的问卷答案。验证码不会保存。');
    try {
      await window.ucasSaveEvaluation({kind, answers});
      templates = {...templates, ...answers};
      say(`已在本机记住 ${Object.keys(answers).length} 组答案。之后可修改；只用于题目和选项完全匹配的问卷。`);
    } catch { say('模板保存失败，未确认保存。请查看任务日志。'); }
  }
  function fill() {
    let filled = 0, skipped = 0;
    for (const f of fields()) {
      const value = templates[f.key];
      if (f.type === 'text') {
        const e = f.elements[0];
        if (e.value.trim()) continue;
        if (typeof value !== 'string' || !value || (e.maxLength >= 0 && value.length > e.maxLength)) {skipped++; continue;}
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,value);
        e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); filled++;
      } else {
        if (f.elements.some(e=>e.checked)) continue;
        if (!Array.isArray(value) || !value.length || (f.type==='radio' && value.length!==1) || value.some(i=>!Number.isInteger(i) || i<0 || i>=f.elements.length)) {skipped++; continue;}
        // Some official non-scale options all have value=""; indexes are safe only
        // within the already matched full question + ordered option signature.
        for (const i of value) if (!f.elements[i].checked) f.elements[i].click();
        filled++;
      }
    }
    say(`已填 ${filled} 组；${skipped} 组尚无匹配模板，需自行填写。已填写内容保留。请核对本课程/教师的评价，输入验证码并使用学校页面的保存按钮。`);
    return {filled, skipped};
  }
  function next() {
    const targets = [...document.querySelectorAll('a,button,input[type=button]')].filter(e=>!panel.contains(e) && visible(e) && clean(e.value || e.textContent)==='评估');
    if (!targets.length) return say('本页没有待评估项目。请检查当前学期、评估开放时间或翻到下一页；没有将空列表当作全部完成。');
    targets[0].click();
  }
  if (kind) {
    button('记住本页答案', remember);
    button('按模板填写空白项', fill);
  } else button('打开本页下一个待评估项目', next);
  const hint = document.createElement('p');
  hint.style.fontSize='12px';
  hint.textContent='首次分别填写一份课程、教师问卷并记住答案。之后自动填入匹配的空白题，提交前可逐题修改。验证码与提交由你完成。'; panel.append(hint);
  button('收起', () => {panel.style.maxHeight='48px'; panel.style.overflow='hidden'; title.style.cursor='pointer'; title.onclick=()=>{panel.style.maxHeight='65vh';panel.style.overflow='auto';};});
  document.body.append(panel);
  if (kind) fill();
  else if (batch) next();
  else say('选择一个待评估项目。已有评价不会自动打开修改。');
}
