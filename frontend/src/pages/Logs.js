// src/pages/Logs.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';

function Logs() {
  const [monitorLogs, setMonitorLogs] = useState([]);
  const [alertLogs, setAlertLogs] = useState([]);
  const [tradeLogs, setTradeLogs] = useState([]);
  const [tab, setTab] = useState('monitor');

  useEffect(() => {
    axios.get(`${API}/logs/monitor`).then(res => setMonitorLogs(res.data.data));
    axios.get(`${API}/logs/alerts`).then(res => setAlertLogs(res.data.data));
    axios.get(`${API}/logs/trades`).then(res => setTradeLogs(res.data.data));
  }, []);

  return (
    <div>
      <h2 style={{ fontSize: '20px', marginBottom: '24px' }}>📋 로그</h2>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
        <button
          className={`btn ${tab === 'monitor' ? 'btn-primary' : ''}`}
          style={tab !== 'monitor' ? { background: '#21262d', color: '#e6edf3' } : {}}
          onClick={() => setTab('monitor')}
        >
          모니터링 로그
        </button>
        <button
          className={`btn ${tab === 'alert' ? 'btn-primary' : ''}`}
          style={tab !== 'alert' ? { background: '#21262d', color: '#e6edf3' } : {}}
          onClick={() => setTab('alert')}
        >
          알림 로그
        </button>
        <button className={`btn ${tab === 'trade' ? 'btn-primary' : ''}`}
          style={tab !== 'trade' ? { background: '#21262d', color: '#e6edf3' } : {}}
          onClick={() => setTab('trade')}>
          💹 매매 이력
        </button>
      </div>

      {/* 모니터링 로그 */}
      {tab === 'monitor' && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>시간</th>
                <th>종목</th>
                <th>현재가</th>
                <th>RSI</th>
                <th>MACD</th>
                <th>MA5</th>
                <th>MA20</th>
              </tr>
            </thead>
            <tbody>
              {monitorLogs.map(log => (
                <tr key={log.id}>
                  <td style={{ color: '#8b949e', fontSize: '12px' }}>
                    {log.created_at.replace('T', ' ').slice(0, 19)}
                  </td>
                  <td>{log.name} ({log.ticker})</td>
                  <td>{parseInt(log.price).toLocaleString()}원</td>
                  <td style={{ color: log.rsi <= 30 ? '#f85149' : log.rsi >= 70 ? '#3fb950' : '#e6edf3' }}>
                    {log.rsi}
                  </td>
                  <td>{log.macd}</td>
                  <td>{parseInt(log.ma5).toLocaleString()}</td>
                  <td>{parseInt(log.ma20).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 알림 로그 */}
      {tab === 'alert' && (
        <div className="card">
          {alertLogs.length === 0 ? (
            <p style={{ color: '#8b949e' }}>아직 알림 내역이 없어요.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>시간</th>
                  <th>종목</th>
                  <th>현재가</th>
                  <th>조건</th>
                </tr>
              </thead>
              <tbody>
                {alertLogs.map(log => (
                  <tr key={log.id}>
                    <td style={{ color: '#8b949e', fontSize: '12px' }}>
                      {log.created_at.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td>{log.name} ({log.ticker})</td>
                    <td>{parseInt(log.price).toLocaleString()}원</td>
                    <td style={{ color: '#f85149' }}>{log.condition_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {tab === 'trade' && (
      <div className="card">
        {tradeLogs.length === 0 ? (
          <p style={{ color: '#8b949e' }}>아직 매매 내역이 없어요.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>시간</th><th>종목</th><th>구분</th>
                <th>가격</th><th>수량</th><th>금액</th>
                <th>조건식</th><th>수익률</th><th>사유</th>
              </tr>
            </thead>
            <tbody>
              {tradeLogs.map(log => (
                <tr key={log.id}>
                  <td style={{ color: '#8b949e', fontSize: '12px' }}>
                    {log.created_at.replace('T',' ').slice(0,19)}
                  </td>
                  <td>{log.name} ({log.ticker})</td>
                  <td style={{ color: log.trade_type === 'buy' ? '#f85149' : '#3fb950',
                              fontWeight: 'bold' }}>
                    {log.trade_type === 'buy' ? '🔴 매수' : '🔵 매도'}
                  </td>
                  <td>{parseInt(log.price).toLocaleString()}원</td>
                  <td>{log.qty}주</td>
                  <td>{parseInt(log.amount).toLocaleString()}원</td>
                  <td style={{ fontSize: '12px', color: '#f0883e' }}>{log.condition_name}</td>
                  <td style={{ color: log.profit_rate > 0 ? '#f85149' :
                              log.profit_rate < 0 ? '#3fb950' : '#8b949e' }}>
                    {log.profit_rate != null ? `${log.profit_rate > 0 ? '+' : ''}${log.profit_rate}%` : '-'}
                  </td>
                  <td style={{ fontSize: '12px' }}>{log.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    )}
    </div>
  );
}

export default Logs;