# 테스트 fixture

- `ust_par_sample.csv`: 미 재무부 Daily Treasury Par Yield Curve CSV와 **같은 형식**의 합성 샘플.
  값은 실제 시세가 아니라 형태가 그럴듯한 임의 값이다. 커브 구축의 자기 일관성 검사용.
  실제 데이터는 `pipeline/`에서 수집해 `data/`(gitignore)에 둔다.
