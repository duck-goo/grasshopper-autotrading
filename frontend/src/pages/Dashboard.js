// src/pages/Dashboard.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:8080';
const toNum = (val) => {
    const n = parseInt(val);
    return isNaN(n) ? 0 : n;
};

function Dashboard() {
  const [stocks, setStocks] = useState([]);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [orderMsg, setOrderMsg] = useState('');

  const fetchData = async () => {
    // ✅ 잔고 - 실패해도 기존 데이터 유지
    try {
      const balanceRes = await axios.get(`${API}/balance`, { timeout: 30000 });
      if (balanceRes.data.data?.success) {   // ✅ success일 때만 업데이트!
        setBalance(balanceRes.data.data);
      }
    } catch (e) {
      console.error('잔고 조회 실패 - 기존 데이터 유지');
    }

    // 관심종목은 실패해도 로딩 해제
    try {
      const priceRes = await axios.get(`${API}/watchlist/prices`, { timeout: 30000 });
      setStocks(priceRes.data.data);
    } catch (e) {
      console.error('관심종목 조회 실패:', e);
    }

    setLoading(false);
};

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleOrder = async (ticker, name, type) => {
    const qty = prompt(`${name} ${type === 'buy' ? '매수' : '매도'} 수량을 입력하세요:`);
    if (!qty || isNaN(qty) || qty <= 0) return;

    try {
      const res = await axios.post(`${API}/order/${type}?ticker=${ticker}&name=${name}&qty=${qty}`);
      if (res.data.data.success) {
        setOrderMsg(`✅ ${name} ${type === 'buy' ? '매수' : '매도'} ${qty}주 완료!`);

        // ✅ 매도 성공 시 해당 종목 즉시 화면에서 제거
        if (type === 'sell') {
          setBalance(prev => {
            if (!prev) return prev;
            return {
              ...prev,
              holdings: prev.holdings.filter(h => h.ticker !== ticker)
            };
          });
        }

        // 3초 후 실제 잔고 데이터로 갱신
        setTimeout(() => fetchData(), 1000);

      } else {
        setOrderMsg(`❌ 주문 실패: ${res.data.data.message}`);
      }
    } catch (e) {
      setOrderMsg('❌ 주문 오류 발생');
    }

    setTimeout(() => setOrderMsg(''), 5000);
};

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px' }}>📊🦗 메뚜기의 실시간 대시보드</h2>
        <button className="btn btn-primary" onClick={fetchData}>🔄 새로고침</button>
      </div>

      {/* 주문 메시지 */}
      {orderMsg && (
        <div style={{
          padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
          background: orderMsg.includes('✅') ? '#1a4731' : '#4a1515',
          border: `1px solid ${orderMsg.includes('✅') ? '#3fb950' : '#f85149'}`
        }}>
          {orderMsg}
        </div>
      )}

      {/* 계좌 요약 */}
      {balance && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <h2>💰 계좌 현황</h2>
          <div style={{ display: 'flex', gap: '32px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: '12px', color: '#8b949e' }}>총 평가금액</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#58a6ff' }}>
                {toNum(balance.total_eval).toLocaleString()}원
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#8b949e' }}>가용 현금</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                {toNum(balance.available_cash).toLocaleString()}원
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#8b949e' }}>총 손익</div>
              <div style={{
                fontSize: '20px', fontWeight: 'bold',
                color: toNum(balance.profit_loss) >= 0 ? '#3fb950' : '#f85149'
              }}>
                {toNum(balance.profit_loss).toLocaleString()}원
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 보유종목 */}
      {balance && balance.holdings && balance.holdings.length > 0 && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <h2>📦 보유종목</h2>
          <table>
            <thead>
              <tr>
                <th>종목</th>
                <th>보유수량</th>
                <th>매수평균단가</th>
                <th>현재가</th>
                <th>손익</th>
                <th>수익률</th>
                <th>매도</th>
              </tr>
            </thead>
            <tbody>
              {balance.holdings.map((h, idx) => (
                <tr key={idx}>
                  <td>{h.name} ({h.ticker})</td>
                  <td>{parseInt(h.qty).toLocaleString()}주</td>
                  <td>{toNum(h.avg_price).toLocaleString()}원</td>
                  <td>{toNum(h.current_price).toLocaleString()}원</td>
                  <td style={{ color: toNum(h.profit_loss) >= 0 ? '#3fb950' : '#f85149' }}>
                    {toNum(h.profit_loss).toLocaleString()}원
                  </td>
                  <td style={{ color: parseFloat(h.profit_rate) >= 0 ? '#3fb950' : '#f85149' }}>
                    {parseFloat(h.profit_rate).toFixed(2)}%
                  </td>
                  <td>
                    <button
                      className="btn btn-danger"
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                      onClick={() => handleOrder(h.ticker, h.name, 'sell')}
                    >
                      매도
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 관심종목 */}
      {loading ? (
        <p style={{ color: '#8b949e' }}>로딩 중...</p>
      ) : stocks.length === 0 ? (
        <div className="card">
          <p style={{ color: '#8b949e' }}>관심종목이 없어요. 설정에서 종목을 추가해주세요!</p>
        </div>
      ) : (
        <div>
          <h2 style={{ fontSize: '16px', marginBottom: '16px', color: '#8b949e' }}>📋 관심종목</h2>
          <div className="grid">
            {stocks.map((stock, idx) => (
              <StockCard key={idx} stock={stock} onOrder={handleOrder} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StockCard({ stock, onOrder }) {
  const changeRate = parseFloat(stock.change_rate || 0);
  const isUp = changeRate >= 0;
  const price = parseInt(stock.price || 0).toLocaleString();
  const change = parseInt(stock.change || 0).toLocaleString();

  return (
    <div className="stock-card">
      <div className="ticker">{stock.ticker}</div>
      <div className="name">{stock.name || stock.ticker}</div>
      <div className="price">{price}원</div>
      <div className={`change ${isUp ? 'up' : 'down'}`}>
        {isUp ? '▲' : '▼'} {change}원 ({changeRate}%)
      </div>
      <div className="indicators">
        <span className="indicator">거래량 {parseInt(stock.volume || 0).toLocaleString()}</span>
      </div>
      <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
        <button
          className="btn btn-primary"
          style={{ flex: 1, padding: '6px', fontSize: '13px' }}
          onClick={() => onOrder(stock.ticker, stock.name, 'buy')}
        >
          매수
        </button>
        <button
          className="btn btn-danger"
          style={{ flex: 1, padding: '6px', fontSize: '13px' }}
          onClick={() => onOrder(stock.ticker, stock.name, 'sell')}
        >
          매도
        </button>
      </div>
    </div>
  );
}

export default Dashboard;