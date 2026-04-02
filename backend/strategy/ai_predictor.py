# backend/strategy/ai_predictor.py
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from strategy.condition import calculate_rsi, calculate_macd, calculate_ma

def prepare_features(data: list) -> pd.DataFrame:
    """학습용 피처 생성"""
    df = pd.DataFrame(data)
    closes = df['close'].tolist()

    features = []
    for i in range(20, len(closes)):
        window = closes[:i+1]
        rsi = calculate_rsi(window) or 50
        macd, signal, hist = calculate_macd(window)
        ma5 = calculate_ma(window, 5) or closes[i]
        ma10 = calculate_ma(window, 10) or closes[i]
        ma20 = calculate_ma(window, 20) or closes[i]

        current = closes[i]
        prev = closes[i-1]
        prev5 = closes[i-5]

        features.append({
            'rsi': rsi,
            'macd': macd or 0,
            'macd_signal': signal or 0,
            'macd_hist': hist or 0,
            'ma5_ratio': (current / ma5 - 1) * 100,
            'ma10_ratio': (current / ma10 - 1) * 100,
            'ma20_ratio': (current / ma20 - 1) * 100,
            'price_change_1': (current / prev - 1) * 100,
            'price_change_5': (current / prev5 - 1) * 100,
            'volume': df['volume'].iloc[i],
            'volume_ma5': df['volume'].iloc[i-4:i+1].mean(),
        })

    return pd.DataFrame(features)

def run_ai_prediction(data: list) -> dict:
    """AI 예측 실행"""
    if len(data) < 40:
        return {"error": "데이터 부족 (최소 40일 필요)"}

    try:
        closes = [d['close'] for d in data]
        df_features = prepare_features(data)

        if df_features.empty:
            return {"error": "피처 생성 실패"}

        # 정답 레이블 생성 (다음날 상승이면 1, 하락이면 0)
        labels = []
        for i in range(20, len(closes) - 1):
            labels.append(1 if closes[i+1] > closes[i] else 0)

        # 마지막 행은 예측용 (정답 없음)
        X = df_features.iloc[:-1]
        y = labels
        X_pred = df_features.iloc[[-1]]

        if len(X) < 20:
            return {"error": "학습 데이터 부족"}

        # 학습/테스트 분리 (80/20)
        split = int(len(X) * 0.8)
        X_train = X.iloc[:split]
        X_test = X.iloc[split:]
        y_train = y[:split]
        y_test = y[split:]

        # 스케일링
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        X_pred_scaled = scaler.transform(X_pred)

        # 모델 학습
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            random_state=42
        )
        model.fit(X_train_scaled, y_train)

        # 테스트 정확도
        test_accuracy = model.score(X_test_scaled, y_test) * 100

        # 예측
        proba = model.predict_proba(X_pred_scaled)[0]
        up_prob = round(proba[1] * 100, 1)
        down_prob = round(proba[0] * 100, 1)
        prediction = "상승" if up_prob > down_prob else "하락"

        # 피처 중요도 Top 5
        feature_names = df_features.columns.tolist()
        importances = model.feature_importances_
        top_features = sorted(
            zip(feature_names, importances),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        # 현재 지표
        current_closes = closes
        current_rsi = calculate_rsi(current_closes)
        current_macd, current_signal, _ = calculate_macd(current_closes)
        current_ma5 = calculate_ma(current_closes, 5)
        current_ma20 = calculate_ma(current_closes, 20)
                                                                                                                                                                            
        return {
            "prediction": prediction,
            "up_probability": up_prob,
            "down_probability": down_prob,
            "model_accuracy": round(test_accuracy, 1),
            "current_indicators": {
                "RSI": current_rsi,
                "MACD": current_macd,
                "MACD_Signal": current_signal,
                "MA5": current_ma5,
                "MA20": current_ma20,
            },
            "top_features": [
                {"name": f[0], "importance": round(f[1] * 100, 1)}
                for f in top_features
            ]
        }

    except Exception as e:
        return {"error": f"예측 실패: {str(e)}"}