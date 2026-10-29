# QuantTool
- 설계 기준·진행 현황·다음 단계는 docs/architecture.md (0 레퍼런스, 1 패키지 구조, 2 진행). 데이터 수집·저장은 별도 레포 ../market-data (설계 docs/design.md, 제공 데이터 docs/data_catalog.md).
- 구조와 원칙은 docs/architecture.md를 따른다. 새 모듈은 1.4 설계 원칙과 1.6 불변 조건을 지킨다. 객체 정리는 1.6 객체 가이드에 함께 갱신한다.
- 기능 요청을 받으면 먼저 ORE에서 그 관심사가 어디에 사는지 references/Engine 원본으로 찾고, 같은 자리·이름·인자로 넣는다(1.8 확장하는 법).
  요청이 ORE 구조와 충돌하면 구현 전에 "ORE는 이 이유로 여기에 둔다 / 요청대로 하면 이것이 깨진다 / 대안"을 먼저 설명한다.
  ORE와 다르게 하기로 하면 architecture.md 1.4 "ORE와 다른 점" 표에 한 줄(ORE 경로, QuantTool, 이유, 포기한 것)을 추가한다.
- 의존 방향: qle·data.utilities·data.configuration → data.marketdata → data.portfolio → analytics.scenario → analytics.cube → analytics.engine → analytics.app. 역방향 import 금지 (tests/test_layering.py가 검사).
- QuantLib API는 추측하지 말고 references/QuantLib-SWIG 또는 dir()/help()로 확인 후 사용.
- ORE 설계를 참조할 때는 references/Engine 원본을 확인하고 파일 경로를 남긴다. 요약은 docs/architecture.md 0.2.
- references/는 gitignore 대상이다. 없으면 `scripts/fetch_references.sh`로 클론한다.
- 모든 기능은 tests/에 QuantLib 직접 계산 또는 해석해와 비교하는 테스트를 함께 작성한다.
- 작업 단위는 작게: 모듈 하나, 테스트 통과, diff 리뷰 후 커밋.
- 설정 값은 configs/, 추정값은 configs/estimated/(출처 필수). 코드에 상수로 넣지 않는다.
- 검사: `python -m pytest -q && ruff check . && ruff format --check .`
