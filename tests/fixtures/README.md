# 테스트 fixture

- `market_ust_sample.txt`: ORE `market.txt` 형식(`날짜 키 값`)의 **합성 샘플**. 미 재무부 par yield 곡선 모양을 흉내 낸
  임의 값이고 실제 시세가 아니다. 커브 구축의 자기 일관성 검사용. `CSVLoader`로 읽는다.
  실제 데이터는 별도 레포 `market-data`가 수집·적재한다(`../market-data`, `docs/data_catalog.md`).
