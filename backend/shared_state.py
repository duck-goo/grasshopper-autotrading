# backend/shared_state.py
# 스캐너와 모니터가 함께 쓰는 공유 상태

# 스캐너가 발견한 자동매수 후보 목록
# scanner.py → 추가 / monitor.py → 읽고 삭제
auto_buy_candidates = []