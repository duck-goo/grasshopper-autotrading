// src/App.js
import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Logs from './pages/Logs';
import Settings from './pages/Settings';
import './App.css';
import Backtest from './pages/Backtest';
import AiPredict from './pages/AiPredict';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        {/* 상단 네비게이션 */}
        <nav className="navbar">
          <h1>🤖 Auto Trader</h1>
          <div className="nav-links">
            <Link to="/">📊 대시보드</Link>
            <Link to="/logs">📋 로그</Link>
            <Link to="/settings">⚙️ 설정</Link>
            <Link to="/backtest">🔬 백테스트</Link>
            <Link to="/ai">🦗 메뚜기의 예측</Link>
          </div>
        </nav>

        {/* 페이지 라우팅 */}
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/ai" element={<AiPredict />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;