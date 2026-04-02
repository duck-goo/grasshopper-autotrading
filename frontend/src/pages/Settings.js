// src/pages/Settings.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';

function Settings() {
  const [watchlist, setWatchlist] = useState([]);
  const [ticker, setTicker] = useState('');
  const [name, setName] = useState('');
  const [market, setMarket] = useState('KR');
  const [msg, setMsg] = useState('');
  const [settings, setSettings] = useState({});

  const fetchWatchlist = async () => {
    const res = await axios.get(`${API}/watchlist`);
    setWatchlist(res.data.data);
  };

  const fetchSettings = async () => {
    const res = await axios.get(`${API}/settings`);
    setSettings(res.data.data);
  };

  useEffect(() => {
    fetchWatchlist();
    fetchSettings();
  }, []);

  const addTicker = async () => {
    if (!ticker || !name) {
      setMsg('❌ 종목코드와 종목명을 입력해주세요!');
      return;
    }
    await axios.post(`${API}/watchlist?ticker=${ticker}&name=${name}&market=${market}`);
    setMsg(`✅ ${name} 추가 완료!`);
    setTicker('');
    setName('');
    fetchWatchlist();
  };

  const deleteTicker = async (id, name) => {
    if (!window.confirm(`${name}을 삭제할까요?`)) return;
    await axios.delete(`${API}/watchlist/${id}`);
    setMsg(`🗑️ ${name} 삭제 완료!`);
    fetchWatchlist();
  };

  const updateSetting = async (key, value) => {
    await axios.post(`${API}/settings?key=${key}&value=${value}`);
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const Toggle = ({ label, settingKey }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid #21262d' }}>
      <span style={{ fontSize: '14px' }}>{label}</span>
      <div
        onClick={() => updateSetting(settingKey, settings[settingKey] === 'true' ? 'false' : 'true')}
        style={{
          width: '48px', height: '24px', borderRadius: '12px', cursor: 'pointer',
          background: settings[settingKey] === 'true' ? '#238636' : '#30363d',
          position: 'relative', transition: 'background 0.2s'
        }}
      >
        <div style={{
          width: '18px', height: '18px', borderRadius: '50%', background: 'white',
          position: 'absolute', top: '3px',
          left: settings[settingKey] === 'true' ? '27px' : '3px',
          transition: 'left 0.2s'
        }} />
      </div>
    </div>
  );

  return (
    <div>
      <h2 style={{ fontSize: '20px', marginBottom: '24px' }}>⚙️ 설정</h2>

      {/* 알림 설정 */}
      <div className="card">
        <h2>🔔 알림 설정</h2>
        <Toggle label="텔레그램 알림" settingKey="telegram_alert" />
        <Toggle label="PC 팝업 알림" settingKey="popup_alert" />
      </div>

      {/* 주문 설정 */}
      <div className="card">
        <h2>📈 주문 설정</h2>
        <Toggle label="반자동 주문 사용" settingKey="semi_auto_order" />
        <Toggle label="자동 주문 사용" settingKey="auto_order" />

        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>1회 주문 금액 (원)</label>
            <input
              type="number"
              value={settings.order_amount || ''}
              onChange={e => setSettings(prev => ({ ...prev, order_amount: e.target.value }))}
              onBlur={e => updateSetting('order_amount', e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: '12px', color: '#8b949e' }}>익절 (%)</label>
              <input
                type="number"
                value={settings.take_profit || ''}
                onChange={e => setSettings(prev => ({ ...prev, take_profit: e.target.value }))}
                onBlur={e => updateSetting('take_profit', e.target.value)}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: '12px', color: '#8b949e' }}>손절 (%)</label>
              <input
                type="number"
                value={settings.stop_loss || ''}
                onChange={e => setSettings(prev => ({ ...prev, stop_loss: e.target.value }))}
                onBlur={e => updateSetting('stop_loss', e.target.value)}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 관심종목 추가 */}
      <div className="card">
        <h2>관심종목 추가</h2>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '150px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>종목코드</label>
            <input value={ticker} onChange={e => setTicker(e.target.value)} placeholder="예: 005930" />
          </div>
          <div style={{ flex: 1, minWidth: '150px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>종목명</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="예: 삼성전자" />
          </div>
          <div style={{ minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>시장</label>
            <select
              value={market}
              onChange={e => setMarket(e.target.value)}
              style={{
                width: '100%', padding: '8px 12px',
                background: '#0d1117', border: '1px solid #30363d',
                borderRadius: '6px', color: '#e6edf3', fontSize: '14px'
              }}
            >
              <option value="KR">국내 🇰🇷</option>
              <option value="US">미국 🇺🇸</option>
            </select>
          </div>
        </div>
        <button className="btn btn-primary" style={{ marginTop: '12px' }} onClick={addTicker}>
          + 추가
        </button>
        {msg && <p style={{ marginTop: '12px', color: '#8b949e' }}>{msg}</p>}
      </div>

      {/* 관심종목 목록 */}
      <div className="card">
        <h2>관심종목 목록</h2>
        {watchlist.length === 0 ? (
          <p style={{ color: '#8b949e' }}>등록된 종목이 없어요.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>종목코드</th>
                <th>종목명</th>
                <th>시장</th>
                <th>등록일</th>
                <th>삭제</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map(item => (
                <tr key={item.id}>
                  <td>{item.ticker}</td>
                  <td>{item.name}</td>
                  <td>{item.market === 'KR' ? '🇰🇷 국내' : '🇺🇸 미국'}</td>
                  <td style={{ color: '#8b949e', fontSize: '12px' }}>
                    {item.created_at.replace('T', ' ').slice(0, 19)}
                  </td>
                  <td>
                    <button
                      className="btn btn-danger"
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                      onClick={() => deleteTicker(item.id, item.name)}
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Settings;