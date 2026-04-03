// frontend/src/pages/Conditions.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';

// 지표 타입별 설정 정의
const CONDITION_TYPES = {
  RSI:          { label: 'RSI',            needsOperator: true,  needsValue: true,  valueLabel: '기준값',    placeholder: '30' },
  MACD:         { label: 'MACD 크로스',    needsOperator: false, needsValue: false, extra: ['golden_cross','dead_cross'] },
  MA_CROSS:     { label: '이동평균 크로스', needsOperator: false, needsValue: false, extra: ['golden_cross','dead_cross'], needsShortLong: true },
  MA:           { label: '이동평균선',      needsOperator: true,  needsValue: false, needsPeriod: true },
  BOLLINGER:    { label: '볼린저밴드',      needsOperator: false, needsValue: false, extra: ['below_lower','above_upper','above_mid','below_mid'] },
  VOLUME_RATIO: { label: '거래량 비율(%)', needsOperator: true,  needsValue: true,  valueLabel: '기준값(%)', placeholder: '200' },
  CHANGE_RATE:  { label: '등락률(%)',       needsOperator: true,  needsValue: true,  valueLabel: '기준값(%)', placeholder: '5' },
  HIGH_52W:     { label: '52주 신고가(%)', needsOperator: true,  needsValue: true,  valueLabel: '비율(%)',   placeholder: '90' },
  LOW_52W:      { label: '52주 신저가(%)', needsOperator: true,  needsValue: true,  valueLabel: '비율(%)',   placeholder: '110' },
  PRICE:        { label: '현재가(원)',      needsOperator: true,  needsValue: true,  valueLabel: '가격(원)',  placeholder: '10000' },
};

const OPERATORS = [
  { value: '>=', label: '이상 (≥)' },
  { value: '<=', label: '이하 (≤)' },
  { value: '>',  label: '초과 (>)' },
  { value: '<',  label: '미만 (<)' },
  { value: '==', label: '같음 (=)' },
];

const EXTRA_LABELS = {
  golden_cross: '골든크로스',
  dead_cross:   '데드크로스',
  below_lower:  '하단밴드 아래',
  above_upper:  '상단밴드 위',
  above_mid:    '중심선 위',
  below_mid:    '중심선 아래',
};

// 빈 조건 아이템 기본값
const newItem = () => ({
  type: 'RSI', operator: '<=', value: 30, signal: 'golden_cross', period: 20, short: 5, long: 20
});

function Conditions() {
  const [conditions, setConditions] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [msg, setMsg] = useState('');

  // 폼 상태
  const [form, setForm] = useState({
    name: '', description: '', logic: 'AND',
    min_price: 5000, max_price: 0, market: 'ALL',
    items: [newItem()]
  });

  const fetchConditions = async () => {
    try {
      const res = await axios.get(`${API}/conditions`);
      setConditions(res.data.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchConditions(); }, []);

  const showMsg = (text) => { setMsg(text); setTimeout(() => setMsg(''), 3000); };

  // 조건 아이템 추가
  const addItem = () => setForm(f => ({ ...f, items: [...f.items, newItem()] }));

  // 조건 아이템 삭제
  const removeItem = (i) => setForm(f => ({ ...f, items: f.items.filter((_, idx) => idx !== i) }));

  // 조건 아이템 수정
  const updateItem = (i, key, val) => {
    setForm(f => {
      const items = [...f.items];
      items[i] = { ...items[i], [key]: val };
      // 타입 바꾸면 기본값 리셋
      if (key === 'type') items[i] = { ...newItem(), type: val };
      return { ...f, items };
    });
  };

  // 저장
  const saveCondition = async () => {
    if (!form.name.trim()) return showMsg('❌ 조건식 이름을 입력해주세요!');
    if (form.items.length === 0) return showMsg('❌ 조건을 1개 이상 추가해주세요!');

    // 백엔드 형식으로 변환
    const items = form.items.map(item => {
      const t = CONDITION_TYPES[item.type];
      const base = { type: item.type };
      if (t.needsOperator) base.operator = item.operator;
      if (t.needsValue)    base.value    = parseFloat(item.value);
      if (t.extra)         base.signal   = item.signal;
      if (t.needsPeriod)   { base.operator = item.operator; base.value = item.period; }
      if (t.needsShortLong){ base.short = parseInt(item.short); base.long = parseInt(item.long); base.signal = item.signal; }
      return base;
    });

    try {
      await axios.post(`${API}/conditions`, {
        name: form.name, description: form.description,
        logic: form.logic, min_price: parseInt(form.min_price),
        max_price: parseInt(form.max_price) || 0,
        market: form.market, items
      });
      showMsg('✅ 조건식 저장 완료!');
      setShowForm(false);
      setForm({ name: '', description: '', logic: 'AND', min_price: 5000, max_price: 0, market: 'ALL', items: [newItem()] });
      fetchConditions();
    } catch (e) { showMsg('❌ 저장 실패'); }
  };

  // 삭제
  const deleteCondition = async (id, name) => {
    if (!window.confirm(`"${name}" 조건식을 삭제할까요?`)) return;
    await axios.delete(`${API}/conditions/${id}`);
    showMsg('🗑️ 삭제 완료');
    fetchConditions();
  };

  // 활성/비활성 토글
  const toggleCondition = async (id, isActive) => {
    await axios.post(`${API}/conditions/${id}/toggle?is_active=${!isActive}`);
    fetchConditions();
  };

  const inp = { // 공통 input 스타일
    background: '#0d1117', border: '1px solid #30363d',
    borderRadius: '6px', color: '#e6edf3', fontSize: '13px',
    padding: '6px 10px'
  };
  const sel = { ...inp, cursor: 'pointer' };

  return (
    <div>
      {/* 헤더 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px' }}>📐 조건식 관리</h2>
        <button className="btn btn-primary" onClick={() => setShowForm(v => !v)}>
          {showForm ? '✕ 닫기' : '+ 새 조건식'}
        </button>
      </div>

      {/* 메시지 */}
      {msg && (
        <div style={{
          padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
          background: msg.includes('❌') ? '#4a1515' : '#1a4731',
          border: `1px solid ${msg.includes('❌') ? '#f85149' : '#3fb950'}`
        }}>{msg}</div>
      )}

      {/* ───── 조건식 추가 폼 ───── */}
      {showForm && (
        <div className="card" style={{ marginBottom: '24px', border: '1px solid #1f6feb' }}>
          <h3 style={{ fontSize: '15px', marginBottom: '16px', color: '#58a6ff' }}>✏️ 새 조건식 만들기</h3>

          {/* 기본 정보 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>조건식 이름 *</label>
              <input style={{ ...inp, width: '100%' }} placeholder="예: RSI 과매도 전략"
                value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>설명 (선택)</label>
              <input style={{ ...inp, width: '100%' }} placeholder="조건식 설명"
                value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
            </div>
          </div>

          {/* 필터 옵션 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>시장</label>
              <select style={{ ...sel, width: '100%' }} value={form.market}
                onChange={e => setForm(f => ({ ...f, market: e.target.value }))}>
                <option value="ALL">전체</option>
                <option value="KOSPI">KOSPI</option>
                <option value="KOSDAQ">KOSDAQ</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>최소 주가 (원)</label>
              <input style={{ ...inp, width: '100%' }} type="number" placeholder="5000"
                value={form.min_price} onChange={e => setForm(f => ({ ...f, min_price: e.target.value }))} />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>최대 주가 (0=무제한)</label>
              <input style={{ ...inp, width: '100%' }} type="number" placeholder="0"
                value={form.max_price} onChange={e => setForm(f => ({ ...f, max_price: e.target.value }))} />
            </div>
            <div>
              <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>조건 연산</label>
              <select style={{ ...sel, width: '100%' }} value={form.logic}
                onChange={e => setForm(f => ({ ...f, logic: e.target.value }))}>
                <option value="AND">AND (모두 충족)</option>
                <option value="OR">OR (하나라도 충족)</option>
              </select>
            </div>
          </div>

          {/* 조건 아이템 목록 */}
          <div style={{ marginBottom: '12px' }}>
            <label style={{ fontSize: '13px', color: '#8b949e', display: 'block', marginBottom: '8px' }}>
              📋 조건 목록 ({form.logic === 'AND' ? '모두 충족해야 함' : '하나라도 충족하면 됨'})
            </label>

            {form.items.map((item, i) => {
              const t = CONDITION_TYPES[item.type];
              return (
                <div key={i} style={{
                  display: 'flex', gap: '8px', alignItems: 'center',
                  padding: '10px 12px', borderRadius: '8px', marginBottom: '8px',
                  background: '#161b22', border: '1px solid #21262d', flexWrap: 'wrap'
                }}>
                  {/* 번호 */}
                  <span style={{ color: '#58a6ff', fontSize: '13px', minWidth: '20px' }}>#{i+1}</span>

                  {/* 지표 타입 선택 */}
                  <select style={{ ...sel }} value={item.type}
                    onChange={e => updateItem(i, 'type', e.target.value)}>
                    {Object.entries(CONDITION_TYPES).map(([k, v]) => (
                      <option key={k} value={k}>{v.label}</option>
                    ))}
                  </select>

                  {/* 연산자 */}
                  {t.needsOperator && (
                    <select style={{ ...sel }} value={item.operator}
                      onChange={e => updateItem(i, 'operator', e.target.value)}>
                      {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                    </select>
                  )}

                  {/* 값 입력 */}
                  {t.needsValue && (
                    <input style={{ ...inp, width: '80px' }} type="number"
                      placeholder={t.placeholder} value={item.value}
                      onChange={e => updateItem(i, 'value', e.target.value)} />
                  )}

                  {/* 기간 (MA용) */}
                  {t.needsPeriod && (
                    <>
                      <select style={{ ...sel }} value={item.operator}
                        onChange={e => updateItem(i, 'operator', e.target.value)}>
                        {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                      </select>
                      <select style={{ ...sel }} value={item.period}
                        onChange={e => updateItem(i, 'period', e.target.value)}>
                        {[5,10,20,60,120,240].map(p => <option key={p} value={p}>MA{p}</option>)}
                      </select>
                    </>
                  )}

                  {/* 단기/장기 MA (MA_CROSS용) */}
                  {t.needsShortLong && (
                    <>
                      <select style={{ ...sel }} value={item.short}
                        onChange={e => updateItem(i, 'short', e.target.value)}>
                        {[3,5,10,20].map(p => <option key={p} value={p}>단기 MA{p}</option>)}
                      </select>
                      <select style={{ ...sel }} value={item.long}
                        onChange={e => updateItem(i, 'long', e.target.value)}>
                        {[10,20,60,120].map(p => <option key={p} value={p}>장기 MA{p}</option>)}
                      </select>
                    </>
                  )}

                  {/* 신호 선택 (extra가 있는 타입) */}
                  {t.extra && (
                    <select style={{ ...sel }} value={item.signal}
                      onChange={e => updateItem(i, 'signal', e.target.value)}>
                      {t.extra.map(ex => <option key={ex} value={ex}>{EXTRA_LABELS[ex]}</option>)}
                    </select>
                  )}

                  {/* 삭제 버튼 */}
                  {form.items.length > 1 && (
                    <button onClick={() => removeItem(i)} style={{
                      background: 'none', border: 'none', color: '#f85149',
                      cursor: 'pointer', fontSize: '16px', padding: '0 4px'
                    }}>🗑️</button>
                  )}
                </div>
              );
            })}

            <button onClick={addItem} style={{
              background: '#21262d', border: '1px dashed #30363d',
              color: '#8b949e', borderRadius: '8px', padding: '8px 16px',
              cursor: 'pointer', fontSize: '13px', width: '100%'
            }}>
              + 조건 추가
            </button>
          </div>

          {/* 저장 버튼 */}
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
            <button className="btn" onClick={() => setShowForm(false)}
              style={{ background: '#21262d', color: '#e6edf3' }}>취소</button>
            <button className="btn btn-primary" onClick={saveCondition}>💾 저장</button>
          </div>
        </div>
      )}

      {/* ───── 저장된 조건식 목록 ───── */}
      {conditions.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '40px', color: '#8b949e' }}>
          아직 조건식이 없어요. 위에서 새 조건식을 만들어봐요! 🚀
        </div>
      ) : (
        conditions.map(cond => (
          <div key={cond.id} className="card" style={{
            marginBottom: '12px',
            borderLeft: `3px solid ${cond.is_active ? '#3fb950' : '#30363d'}`
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                  <span style={{ fontSize: '15px', fontWeight: 'bold' }}>{cond.name}</span>
                  <span style={{
                    padding: '2px 8px', borderRadius: '12px', fontSize: '11px',
                    background: cond.is_active ? '#1a4731' : '#21262d',
                    color: cond.is_active ? '#3fb950' : '#8b949e'
                  }}>
                    {cond.is_active ? '🟢 활성' : '⚫ 비활성'}
                  </span>
                  <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', background: '#1f3a5f', color: '#58a6ff' }}>
                    {cond.market}
                  </span>
                  <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', background: '#2d1f1f', color: '#f0883e' }}>
                    {cond.logic}
                  </span>
                </div>
                {cond.description && (
                  <div style={{ color: '#8b949e', fontSize: '12px', marginBottom: '8px' }}>{cond.description}</div>
                )}
                <div style={{ color: '#8b949e', fontSize: '12px', marginBottom: '10px' }}>
                  💰 가격 범위: {cond.min_price.toLocaleString()}원 ~ {cond.max_price > 0 ? cond.max_price.toLocaleString()+'원' : '무제한'}
                </div>
                {/* 조건 아이템 태그들 */}
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {cond.items?.map((item, i) => (
                    <span key={i} style={{
                      padding: '3px 10px', borderRadius: '12px', fontSize: '12px',
                      background: '#161b22', border: '1px solid #30363d', color: '#e6edf3'
                    }}>
                      {CONDITION_TYPES[item.type]?.label || item.type}
                      {item.operator && ` ${item.operator}`}
                      {item.value && ` ${item.value}`}
                      {item.extra && item.extra !== 'None' && item.extra !== '' && ` (${EXTRA_LABELS[item.extra] || item.extra})`}
                    </span>
                  ))}
                </div>
              </div>

              {/* 버튼들 */}
              <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                <button onClick={() => toggleCondition(cond.id, cond.is_active)} style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', border: 'none',
                  background: cond.is_active ? '#21262d' : '#238636', color: '#e6edf3'
                }}>
                  {cond.is_active ? '비활성화' : '활성화'}
                </button>
                <button onClick={() => deleteCondition(cond.id, cond.name)} style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
                  border: 'none', background: '#4a1515', color: '#f85149'
                }}>
                  삭제
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default Conditions;