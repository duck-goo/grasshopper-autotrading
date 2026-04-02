// src/pages/Backtest.js
import React, { useState } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

const API = 'http://127.0.0.1:8080';

function Backtest() {
  const [ticker, setTicker] = useState('005930');
  const [conditionType, setConditionType] = useState('RSI');
  const [conditionValue, setConditionValue] = useState(30);
  const [takeProfit, setTakeProfit] = useState(5.0);
  const [stopLoss, setStopLoss] = useState(3.0);
  const [orderAmount, setOrderAmount] = useState(100000);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runBacktest = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await axios.get(`${API}/backtest/${ticker}`, {
        params: {
          condition_type: conditionType,
          condition_value: conditionValue,
          take_profit: takeProfit,
          stop_loss: stopLoss,
          order_amount: orderAmount
        }
      });
      setResult(res.data);
    } catch (e) {
      setError('백테스트 실행 실패');
    } finally {
      setLoading(false);
    }
  };

  // 누적 수익 차트 데이터
  const getChartData = () => {
    if (!result) return [];
    let cumProfit = 0;
    return result.result.trades
      .filter(t => t.type === 'sell')
      .map(t => {
        cumProfit += t.profit;
        return {
          date: t.date,
          profit: Math.round(cumProfit),
          rate: t.profit_rate
        };
      });
  };

  return (
    <div>
      <h2 style={{ fontSize: '20px', marginBottom: '24px' }}>🔬 백테스트</h2>

      {/* 설정 */}
      <div className="card">
        <h2>전략 설정</h2>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>종목코드</label>
            <input value={ticker} onChange={e => setTicker(e.target.value)} placeholder="005930" />
          </div>
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>매수 조건</label>
            <select
              value={conditionType}
              onChange={e => setConditionType(e.target.value)}
              style={{
                width: '100%', padding: '8px 12px',
                background: '#0d1117', border: '1px solid #30363d',
                borderRadius: '6px', color: '#e6edf3', fontSize: '14px'
              }}
            >
              <option value="RSI">RSI</option>
              <option value="MACD">MACD 골든크로스</option>
              <option value="MA_CROSS">이동평균 골든크로스</option>
            </select>
          </div>
          {conditionType === 'RSI' && (
            <div style={{ flex: 1, minWidth: '120px' }}>
              <label style={{ fontSize: '12px', color: '#8b949e' }}>RSI 기준값 (이하 매수)</label>
              <input type="number" value={conditionValue} onChange={e => setConditionValue(e.target.value)} />
            </div>
          )}
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>익절 (%)</label>
            <input type="number" value={takeProfit} onChange={e => setTakeProfit(e.target.value)} />
          </div>
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>손절 (%)</label>
            <input type="number" value={stopLoss} onChange={e => setStopLoss(e.target.value)} />
          </div>
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label style={{ fontSize: '12px', color: '#8b949e' }}>1회 주문금액 (원)</label>
            <input type="number" value={orderAmount} onChange={e => setOrderAmount(e.target.value)} />
          </div>
        </div>
        <button className="btn btn-primary" onClick={runBacktest} disabled={loading}>
          {loading ? '⏳ 분석 중...' : '▶ 백테스트 실행'}
        </button>
        {error && <p style={{ color: '#f85149', marginTop: '8px' }}>{error}</p>}
      </div>

      {/* 결과 */}
      {result && (
        <>
          {/* 요약 */}
          <div className="card">
            <h2>📊 결과 요약 ({result.data_period} / {result.total_days}일)</h2>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {[
                { label: '총 수익률', value: `${result.result.summary.total_profit_rate}%`, color: result.result.summary.total_profit_rate >= 0 ? '#3fb950' : '#f85149' },
                { label: '총 손익', value: `${result.result.summary.total_profit.toLocaleString()}원`, color: result.result.summary.total_profit >= 0 ? '#3fb950' : '#f85149' },
                { label: '총 매매', value: `${result.result.summary.total_trades}회`, color: '#e6edf3' },
                { label: '승률', value: `${result.result.summary.win_rate}%`, color: '#58a6ff' },
                { label: '승/패', value: `${result.result.summary.win_trades}승 ${result.result.summary.lose_trades}패`, color: '#e6edf3' },
                { label: '평균 보유일', value: `${result.result.summary.avg_hold_days}일`, color: '#e6edf3' },
                { label: '최대 손실률', value: `${result.result.summary.max_loss_rate}%`, color: '#f85149' },
              ].map((item, idx) => (
                <div key={idx}>
                  <div style={{ fontSize: '12px', color: '#8b949e' }}>{item.label}</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: item.color }}>{item.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 누적 수익 차트 */}
          {getChartData().length > 0 && (
            <div className="card">
              <h2>📈 누적 손익 차트</h2>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={getChartData()}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                  <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#161b22', border: '1px solid #30363d' }}
                    formatter={(val) => [`${val.toLocaleString()}원`, '누적손익']}
                  />
                  <ReferenceLine y={0} stroke="#8b949e" />
                  <Line type="monotone" dataKey="profit" stroke="#58a6ff" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 매매 내역 */}
          <div className="card">
            <h2>📋 매매 내역</h2>
            <table>
              <thead>
                <tr>
                  <th>날짜</th>
                  <th>구분</th>
                  <th>가격</th>
                  <th>수량</th>
                  <th>손익</th>
                  <th>수익률</th>
                  <th>사유</th>
                </tr>
              </thead>
              <tbody>
                {result.result.trades.map((t, idx) => (
                  <tr key={idx}>
                    <td style={{ color: '#8b949e', fontSize: '12px' }}>{t.date}</td>
                    <td style={{ color: t.type === 'buy' ? '#3fb950' : '#f85149' }}>
                      {t.type === 'buy' ? '매수' : '매도'}
                    </td>
                    <td>{t.price.toLocaleString()}원</td>
                    <td>{t.qty}주</td>
                    <td style={{ color: t.profit >= 0 ? '#3fb950' : '#f85149' }}>
                      {t.profit ? `${Math.round(t.profit).toLocaleString()}원` : '-'}
                    </td>
                    <td style={{ color: t.profit_rate >= 0 ? '#3fb950' : '#f85149' }}>
                      {t.profit_rate ? `${t.profit_rate.toFixed(2)}%` : '-'}
                    </td>
                    <td style={{ color: '#8b949e' }}>{t.reason || 'RSI 조건'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default Backtest;