# 테스트 fixture

- `market_sample.txt`: `날짜 키 값` 형식의 **합성 샘플**. 미 재무부 par yield 곡선 모양을 흉내 낸
  임의 값이고 실제 시세가 아니다. 커브 구축의 자기 일관성 검사용. `quanttool.market.quotes.read_quotes`로 읽는다.
  실제 데이터는 별도 레포 `market-data`가 수집·적재한다(`../market-data`, `docs/data_catalog.md`).
- `ust_book.yaml`, `krw_swaps.yaml`: **예시 북**(거래 레코드). `configs/products.yaml` 템플릿을 쓴다.
  테스트(`conftest.load`)와 노트북이 읽는다.
