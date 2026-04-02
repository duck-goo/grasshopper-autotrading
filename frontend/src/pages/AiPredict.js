// src/pages/AiPredict.js
import React, { useState } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';

function AiPredict() {
  const [ticker, setTicker] = useState('005930');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runPredict = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await axios.get(`${API}/ai/predict/${ticker}`);
      setResult(res.data);
    } catch (e) {
      setError('예측 실패');
    } finally {
      setLoading(false);
    }
  };

  const r = result?.result;

  return (
    <div>
      <h2 style={{ fontSize: '20px', marginBottom: '24px' }}>🤖 AI 예측</h2>

      {/* 입력 */}
      <div className="card">
        <h2>종목 선택</h2>
        <div style={{ display: 'flex', gap: '12px' }}>
          <input
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            placeholder="종목코드 (예: 005930)"
            style={{ maxWidth: '200px' }}
          />
          <button className="btn btn-primary" onClick={runPredict} disabled={loading}>
            {loading ? '⏳ 분석 중...' : '🤖 예측 실행'}
          </button>
        </div>
        {error && <p style={{ color: '#f85149', marginTop: '8px' }}>{error}</p>}
      </div>

      {/* 결과 */}
      {r && !r.error && (
        <>
          {/* 예측 결과 */}
          <div className="card" style={{ textAlign: 'center' }}>
            <h2>📊 내일 예측 - {ticker}</h2>
            <div style={{ fontSize: '48px', margin: '16px 0' }}>
              {r.prediction === '상승' ? '📈' : '📉'}
            </div>
            <div style={{
              fontSize: '32px', fontWeight: 'bold',
              color: r.prediction === '상승' ? '#3fb950' : '#f85149'
            }}>
              {r.prediction}
            </div>

            {/* 확률 바 */}
            <div style={{ margin: '24px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                <span style={{ color: '#3fb950' }}>📈 상승 {r.up_probability}%</span>
                <span style={{ color: '#f85149' }}>📉 하락 {r.down_probability}%</span>
              </div>
              <div style={{ background: '#30363d', borderRadius: '4px', height: '12px', overflow: 'hidden' }}>
                <div style={{
                  width: `${r.up_probability}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #3fb950, #58a6ff)',
                  transition: 'width 0.5s'
                }} />
              </div>
            </div>

            <div style={{ color: '#8b949e', fontSize: '13px' }}>
              모델 정확도: {r.model_accuracy}%
            </div>
          </div>

          {/* 현재 지표 */}
          <div className="card">
            <h2>📉 현재 기술적 지표</h2>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {[
                { label: 'RSI', value: r.current_indicators.RSI, color: r.current_indicators.RSI <= 30 ? '#f85149' : r.current_indicators.RSI >= 70 ? '#3fb950' : '#e6edf3' },
                { label: 'MACD', value: r.current_indicators.MACD?.toFixed(1), color: r.current_indicators.MACD > 0 ? '#3fb950' : '#f85149' },
                { label: 'MACD Signal', value: r.current_indicators.MACD_Signal?.toFixed(1), color: '#e6edf3' },
                { label: 'MA5', value: r.current_indicators.MA5?.toLocaleString(), color: '#58a6ff' },
                { label: 'MA20', value: r.current_indicators.MA20?.toLocaleString(), color: '#58a6ff' },
              ].map((item, idx) => (
                <div key={idx}>
                  <div style={{ fontSize: '12px', color: '#8b949e' }}>{item.label}</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: item.color }}>{item.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 주요 근거 */}
          <div className="card">
            <h2>🔍 예측 주요 근거 (피처 중요도)</h2>
            {r.top_features.map((f, idx) => (
              <div key={idx} style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '13px' }}>
                  <span>{idx + 1}. {f.name}</span>
                  <span style={{ color: '#58a6ff' }}>{f.importance}%</span>
                </div>
                <div style={{ background: '#30363d', borderRadius: '4px', height: '6px' }}>
                  <div style={{
                    width: `${f.importance * 5}%`,
                    height: '100%',
                    background: '#58a6ff',
                    borderRadius: '4px'
                  }} />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {r?.error && (
        <div className="card">
          <p style={{ color: '#f85149' }}>❌ {r.error}</p>
        </div>
      )}
    </div>
  );
}

export default AiPredict;