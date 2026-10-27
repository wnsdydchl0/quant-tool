# QuantTool
- 구조와 원칙은 docs/architecture.md를 따른다. 새 모듈은 2장 원칙과 6.4 불변 조건을 지킨다.
- 의존 방향: config·core → market → derivatives → scenario → analytics. 역방향 import 금지 (tests/test_layering.py가 검사).
- QuantLib API는 추측하지 말고 references/QuantLib-SWIG 또는 dir()/help()로 확인 후 사용.
- ORE 설계를 참조할 때는 references/Engine 원본을 확인하고 파일 경로를 남긴다. 요약은 docs/references/.
- references/는 gitignore 대상이다. 없으면 `scripts/fetch_references.sh`로 클론한다.
- 모든 기능은 tests/에 QuantLib 직접 계산 또는 해석해와 비교하는 테스트를 함께 작성한다.
- 작업 단위는 작게: 모듈 하나, 테스트 통과, diff 리뷰 후 커밋.
- 설정 값은 configs/, 추정값은 configs/estimated/(출처 필수). 코드에 상수로 넣지 않는다.
- 검사: `python -m pytest -q && ruff check . && ruff format --check .`
