// frontend/src/pages/Scanner.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';

function Scanner() {
  const [status, setStatus] = useState({
    is_running: false, total: 0, scanned: 0, found: 0, last_scan: null
  });
  const [results, setResults] = useState([]);
  const [filterMarket, setFilterMarket] = useState('ALL');
  const [filterCondition, setFilterCondition] = useState('ALL');
  const [msg, setMsg] = useState('');
  // 핫풀 설정 state
  const [hotConfig, setHotConfig] = useState({
    min_price: 0,
    max_price: 0,
    market: 'ALL',
    sort_by: 'amount',
  });
  const [hotSaving, setHotSaving] = useState(false);
  const [hotRefreshing, setHotRefreshing] = useState(false);
  const [hotUniverse, setHotUniverse] = useState({ count: 0, age_seconds: 0 });

  // 상태 + 결과 불러오기
  const fetchData = async () => {
    try {
      const [statusRes, resultsRes] = await Promise.all([
        axios.get(`${API}/scanner/status`),
        axios.get(`${API}/scanner/results`)
      ]);
      setStatus(statusRes.data.data);
      setResults(Array.isArray(resultsRes.data.data) ? resultsRes.data.data : []);
    } catch (e) {
      console.error('스캐너 데이터 조회 실패:', e);
    }
  };

  // 핫풀 설정 불러오기
  const fetchHotConfig = async () => {
    try {
      const res = await axios.get(`${API}/scanner/universe/config`);
      setHotConfig(res.data.data);
    } catch (e) {
      console.error('핫풀 설정 조회 실패:', e);
    }
  };

  // 핫풀 현재 상태 불러오기
  const fetchHotUniverse = async () => {
    try {
      const res = await axios.get(`${API}/scanner/universe`);
      setHotUniverse({
        count: res.data.count || 0,
        age_seconds: res.data.age_seconds || 0,
      });
    } catch (e) {
      console.error('핫풀 상태 조회 실패:', e);
    }
  };

  // 핫풀 설정 저장
  const saveHotConfig = async () => {
    setHotSaving(true);
    try {
      const params = new URLSearchParams({
        min_price: hotConfig.min_price,
        max_price: hotConfig.max_price,
        market: hotConfig.market,
        sort_by: hotConfig.sort_by,
      });
      const res = await axios.post(`${API}/scanner/universe/config?${params}`);
      if (res.data.status === 'ok') {
        setMsg('✅ 핫풀 설정 저장 완료!');
      } else {
        setMsg(`❌ ${res.data.message || '저장 실패'}`);
      }
    } catch (e) {
      setMsg('❌ 핫풀 설정 저장 실패');
    } finally {
      setHotSaving(false);
      setTimeout(() => setMsg(''), 3000);
    }
  };

  // 핫풀 즉시 갱신
  const refreshHotUniverse = async () => {
    setHotRefreshing(true);
    try {
      const res = await axios.post(`${API}/scanner/universe/refresh`);
      if (res.data.status === 'ok') {
        setMsg(`✅ 핫풀 갱신 완료: ${res.data.count}개 종목`);
        fetchHotUniverse();
      } else {
        setMsg('❌ 핫풀 갱신 실패');
      }
    } catch (e) {
      setMsg('❌ 핫풀 갱신 실패');
    } finally {
      setHotRefreshing(false);
      setTimeout(() => setMsg(''), 3000);
    }
  };

  // 스캔 실행 중이면 2초마다 자동 갱신
  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      fetchData();
    }, status.is_running ? 2000 : 10000);
    return () => clearInterval(interval);
  }, [status.is_running]);

  // 핫풀 설정/상태 초기 로드 + 주기적 갱신
  useEffect(() => {
    fetchHotConfig();
    fetchHotUniverse();
    const interval = setInterval(() => {
      fetchHotUniverse();
    }, 10000);  // 10초마다 핫풀 상태 갱신
    return () => clearInterval(interval);
  }, []);

  // 수동 스캔 실행
  const runScan = async () => {
    try {
      const res = await axios.post(`${API}/scanner/run`);
      setMsg(res.data.message || '스캔 시작!');
      setTimeout(() => setMsg(''), 3000);
    } catch (e) {
      setMsg('❌ 스캔 실행 실패');
      setTimeout(() => setMsg(''), 3000);
    }
  };

  // 진행률 계산
  const progress = status.total > 0
    ? Math.round((status.scanned / status.total) * 100)
    : 0;

  // 조건식 목록 (필터용)
  const conditionNames = ['ALL', ...new Set(results.map(r => r.condition_name))];

  // 필터 적용
  const filtered = results.filter(r => {
    const marketOk = filterMarket === 'ALL' || r.market === filterMarket;
    const condOk = filterCondition === 'ALL' || r.condition_name === filterCondition;
    return marketOk && condOk;
  });

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px' }}>🔍 전종목 스캐너</h2>
        <button
          className="btn btn-primary"
          onClick={runScan}
          disabled={status.is_running}
          style={{ opacity: status.is_running ? 0.5 : 1 }}
        >
          {status.is_running ? '⏳ 스캔 중...' : '▶ 스캔 실행'}
        </button>
      </div>

      {/* 메시지 */}
      {msg && (
        <div style={{
          padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
          background: msg.includes('❌') ? '#4a1515' : '#1a4731',
          border: `1px solid ${msg.includes('❌') ? '#f85149' : '#3fb950'}`
        }}>
          {msg}
        </div>
      )}

      {/* 🔥 핫풀 설정 */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '15px', margin: 0 }}>🔥 핫풀 설정</h3>
          <div style={{ fontSize: '12px', color: '#8b949e' }}>
            현재: <span style={{ color: '#f0883e', fontWeight: 'bold' }}>{hotUniverse.count}개 종목</span>
            {hotUniverse.age_seconds > 0 && (
              <span style={{ marginLeft: '8px' }}>
                · {hotUniverse.age_seconds < 60
                    ? `${hotUniverse.age_seconds}초 전`
                    : `${Math.floor(hotUniverse.age_seconds / 60)}분 전`} 갱신
              </span>
            )}
          </div>
        </div>

        {/* 입력 필드들 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>
              최소 현재가 (원)
            </label>
            <input
              type="number"
              value={hotConfig.min_price}
              onChange={e => setHotConfig({ ...hotConfig, min_price: parseInt(e.target.value) || 0 })}
              placeholder="0 = 제한 없음"
            />
          </div>

          <div>
            <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>
              최대 현재가 (원)
            </label>
            <input
              type="number"
              value={hotConfig.max_price}
              onChange={e => setHotConfig({ ...hotConfig, max_price: parseInt(e.target.value) || 0 })}
              placeholder="0 = 제한 없음"
            />
          </div>

          <div>
            <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>
              시장
            </label>
            <select
              value={hotConfig.market}
              onChange={e => setHotConfig({ ...hotConfig, market: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px',
                background: '#0d1117', border: '1px solid #30363d',
                borderRadius: '6px', color: '#e6edf3', fontSize: '14px'
              }}
            >
              <option value="ALL">전체</option>
              <option value="KOSPI">KOSPI</option>
              <option value="KOSDAQ">KOSDAQ</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '12px', color: '#8b949e', display: 'block', marginBottom: '4px' }}>
              정렬 기준
            </label>
            <select
              value={hotConfig.sort_by}
              onChange={e => setHotConfig({ ...hotConfig, sort_by: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px',
                background: '#0d1117', border: '1px solid #30363d',
                borderRadius: '6px', color: '#e6edf3', fontSize: '14px'
              }}
            >
              <option value="amount">거래대금</option>
              <option value="volume">거래량</option>
            </select>
          </div>
        </div>

        {/* 액션 버튼 */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-primary"
            onClick={saveHotConfig}
            disabled={hotSaving}
            style={{ opacity: hotSaving ? 0.5 : 1 }}
          >
            {hotSaving ? '⏳ 저장 중...' : '💾 설정 저장'}
          </button>
          <button
            className="btn"
            onClick={refreshHotUniverse}
            disabled={hotRefreshing}
            style={{
              background: '#1f6feb', color: '#fff',
              opacity: hotRefreshing ? 0.5 : 1
            }}
          >
            {hotRefreshing ? '⏳ 갱신 중...' : '🔄 즉시 갱신'}
          </button>
          <div style={{ flex: 1 }} />
          <div style={{ color: '#8b949e', fontSize: '12px', alignSelf: 'center' }}>
            💡 저장 = DB 영구 저장 / 갱신 = 지금 설정으로 핫풀 재생성
          </div>
        </div>
      </div>

      {/* 상태 카드 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
        {[
          { label: '상태', value: status.is_running ? '🟢 스캔 중' : '⚪ 대기', color: status.is_running ? '#3fb950' : '#8b949e' },
          { label: '전체 종목', value: `${status.total.toLocaleString()}개` },
          { label: '스캔 완료', value: `${status.scanned.toLocaleString()}개` },
          { label: '발견 종목', value: `${status.found}개`, color: status.found > 0 ? '#f0883e' : '#e6edf3' },
        ].map((item, i) => (
          <div key={i} className="card" style={{ textAlign: 'center', padding: '16px' }}>
            <div style={{ color: '#8b949e', fontSize: '12px', marginBottom: '8px' }}>{item.label}</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: item.color || '#e6edf3' }}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* 진행률 바 */}
      {status.is_running && (
        <div className="card" style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '13px' }}>
            <span>스캔 진행률</span>
            <span style={{ color: '#58a6ff' }}>{progress}%</span>
          </div>
          <div style={{ background: '#21262d', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
            <div style={{
              width: `${progress}%`, height: '100%',
              background: 'linear-gradient(90deg, #238636, #3fb950)',
              transition: 'width 0.3s'
            }} />
          </div>
          <div style={{ color: '#8b949e', fontSize: '12px', marginTop: '8px' }}>
            {status.scanned.toLocaleString()} / {status.total.toLocaleString()} 종목
          </div>
        </div>
      )}

      {/* 마지막 스캔 시간 */}
      {status.last_scan && (
        <div style={{ color: '#8b949e', fontSize: '12px', marginBottom: '16px' }}>
          마지막 스캔: {status.last_scan}
        </div>
      )}

      {/* 필터 */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div>
          <span style={{ fontSize: '13px', color: '#8b949e', marginRight: '8px' }}>시장</span>
          {['ALL', 'KOSPI', 'KOSDAQ'].map(m => (
            <button
              key={m}
              onClick={() => setFilterMarket(m)}
              style={{
                padding: '4px 12px', borderRadius: '20px', fontSize: '13px',
                marginRight: '6px', cursor: 'pointer', border: 'none',
                background: filterMarket === m ? '#238636' : '#21262d',
                color: filterMarket === m ? '#fff' : '#8b949e'
              }}
            >
              {m}
            </button>
          ))}
        </div>
        <div>
          <span style={{ fontSize: '13px', color: '#8b949e', marginRight: '8px' }}>조건식</span>
          {conditionNames.map(c => (
            <button
              key={c}
              onClick={() => setFilterCondition(c)}
              style={{
                padding: '4px 12px', borderRadius: '20px', fontSize: '13px',
                marginRight: '6px', cursor: 'pointer', border: 'none',
                background: filterCondition === c ? '#1f6feb' : '#21262d',
                color: filterCondition === c ? '#fff' : '#8b949e'
              }}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* 결과 테이블 */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '15px' }}>📋 조건 충족 종목 ({filtered.length}개)</h3>
          <button className="btn" onClick={fetchData}
            style={{ background: '#21262d', color: '#e6edf3', padding: '4px 12px', fontSize: '13px' }}>
            🔄 새로고침
          </button>
        </div>

        {filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#8b949e' }}>
            {status.is_running ? '⏳ 스캔 중...' : '조건을 충족한 종목이 없어요'}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>종목명</th>
                <th>코드</th>
                <th>시장</th>
                <th>현재가</th>
                <th>등락률</th>
                <th>충족 조건식</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const rate = parseFloat(r.change_rate);
                return (
                  <tr key={i}>
                    <td style={{ fontWeight: 'bold' }}>{r.name}</td>
                    <td style={{ color: '#8b949e', fontSize: '13px' }}>{r.ticker}</td>
                    <td>
                      <span style={{
                        padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
                        background: r.market === 'KOSPI' ? '#1f3a5f' : '#2d1f5f',
                        color: r.market === 'KOSPI' ? '#58a6ff' : '#d2a8ff'
                      }}>
                        {r.market}
                      </span>
                    </td>
                    <td style={{ fontWeight: 'bold' }}>{r.price.toLocaleString()}원</td>
                    <td style={{ color: rate > 0 ? '#f85149' : rate < 0 ? '#3fb950' : '#8b949e', fontWeight: 'bold' }}>
                      {rate > 0 ? '+' : ''}{rate}%
                    </td>
                    <td>
                      <span style={{
                        padding: '2px 10px', borderRadius: '12px', fontSize: '12px',
                        background: '#2d2a1f', color: '#f0883e', border: '1px solid #f0883e44'
                      }}>
                        {r.condition_name}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Scanner;